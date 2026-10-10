"""The dream engine: runs the phases for ONE tenant, resumable and kill-switchable.

    run_tenant(tenant, dry_run=, phases=, trigger=)  ->  the stored dream_runs record

Guarantees
  * one run per tenant at a time (advisory lock `dream:<tenant>`); the worker walks tenants one after another;
  * every phase is idempotent and its result is persisted before the next starts: an interrupted night resumes at the
    first unfinished phase (and, inside a phase, from its persisted cursor);
  * a failing phase is recorded and the night continues; the kill switch aborts between batches;
  * dry run: nothing but the dream_* log tables is written, JEV is not called.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from services.tenant_memory.knowledge.dream import PHASES
from services.tenant_memory.knowledge.dream import adjudicate, consolidate, drift, embedding_health, numbers, relevance, report
from services.tenant_memory.knowledge.dream.context import Aborted, PhaseCtx
from services.tenant_memory.knowledge.dream.ports import DreamDeps
from services.tenant_memory.knowledge.dream.settings import DreamSettings, from_env, merged

logger = logging.getLogger("knowledge.dream")

PHASE_FUNCS = {"drift": drift.run, "embeddings": embedding_health.run, "numbers": numbers.run, "relevance": relevance.run,
               "adjudicate": adjudicate.run, "consolidate": consolidate.run, "report": report.run}


def local_tz(name: str):
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - no tzdata on the box: Africa/Johannesburg has no DST, so a fixed +2 is exact
        return timezone(timedelta(hours=2)) if "Johannesburg" in name or "Africa" in name else timezone.utc


def local_date(now: datetime, tz_name: str) -> str:
    return now.astimezone(local_tz(tz_name)).date().isoformat()


def in_window(now: datetime, cfg: DreamSettings) -> bool:
    """True while the local wall clock is inside [window_start, window_start + window_hours)."""
    loc = now.astimezone(local_tz(cfg.timezone))
    hh, mm = (int(x) for x in cfg.window_start.split(":"))
    start = loc.replace(hour=hh, minute=mm, second=0, microsecond=0)
    for s in (start, start - timedelta(days=1)):
        if s <= loc < s + timedelta(hours=cfg.window_hours):
            return True
    return False


class DreamEngine:
    def __init__(self, deps: DreamDeps):
        self.deps = deps

    async def settings_for(self, tenant: str) -> DreamSettings:
        return merged(await self.deps.store.get_settings(tenant), self.deps.base_settings or from_env())

    async def run_tenant(self, tenant: str, *, dry_run: bool = False, phases: Optional[list[str]] = None, trigger: str = "manual",
                         requested_by: Optional[str] = None, resume: bool = True) -> dict:
        deps = self.deps
        cfg = await self.settings_for(tenant)
        if deps.kill():
            return {"status": "skipped", "reason": "kill switch is on (DREAM_KILL_SWITCH)"}
        if trigger == "nightly" and not cfg.enabled:
            return {"status": "skipped", "reason": "dream state is disabled for this tenant"}
        wanted = [p for p in PHASES if not phases or p in phases]
        if not wanted:
            raise ValueError(f"unknown phases {phases}; valid: {list(PHASES)}")
        lock = f"dream:{tenant}"
        if not await deps.store.kstore.try_lock(lock):
            return {"status": "skipped", "reason": "another dream run holds the lock for this tenant"}
        try:
            return await self._run_locked(tenant, cfg, wanted, dry_run, trigger, requested_by, resume)
        finally:
            await deps.store.kstore.unlock(lock)

    async def _run_locked(self, tenant, cfg, wanted, dry_run, trigger, requested_by, resume) -> dict:
        deps = self.deps
        today = local_date(deps.now(), cfg.timezone)
        run = None
        if resume and not dry_run:
            run = await deps.store.find_resumable(tenant, today)
            if run and run.get("trigger") != trigger:
                run = None
        if run is None:
            run = await deps.store.create_run(tenant, {
                "run_date": today, "trigger": trigger, "dry_run": dry_run, "status": "running", "phases_requested": wanted,
                "phases_done": [], "phase_results": {}, "state": {}, "report": {}, "errors": [], "counts": {}, "jev_calls": 0,
                "jev_cost_usd": 0.0, "requested_by": requested_by, "started_at": deps.now().isoformat()})
        else:
            run = await deps.store.update_run(tenant, run["id"], {"status": "running"})
            logger.info("dream run %s resumes for tenant %s after %s", run["id"], tenant, run.get("phases_done"))
        shared = dict((run.get("state") or {}).get("shared") or {})
        done = list(run.get("phases_done") or [])
        results = dict(run.get("phase_results") or {})
        status = "completed"
        try:
            for phase in wanted:
                if phase in done:
                    continue
                if deps.kill():
                    raise Aborted("kill switch")
                ctx = PhaseCtx(tenant=tenant, run=run, deps=deps, cfg=cfg, dry_run=dry_run, phase=phase,
                               state=dict((run.get("state") or {}).get(phase) or {}), shared=shared)
                t0 = time.monotonic()
                outcome = "ok"
                err = None
                try:
                    await PHASE_FUNCS[phase](ctx)
                except Aborted:
                    raise
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - a failing phase must not end the night
                    logger.exception("dream phase %s failed for tenant %s", phase, tenant)
                    outcome, err = "error", f"{type(exc).__name__}: {str(exc)[:200]}"
                results[phase] = {"status": outcome, "counts": ctx.counts, "notes": ctx.notes, "errors": ctx.errors,
                                  "duration_s": round(time.monotonic() - t0, 2), **({"error": err} if err else {})}
                if outcome == "error" or ctx.errors:
                    status = "completed_with_errors"
                done.append(phase)
                jev = shared.get("jev") or {}
                run = await deps.store.update_run(tenant, run["id"], {
                    "phases_done": done, "phase_results": results, "jev_calls": int(jev.get("calls", 0)),
                    "jev_cost_usd": float(jev.get("cost_usd", 0.0)),
                    "state": {**(run.get("state") or {}), "shared": {k: v for k, v in shared.items() if not k.startswith("_")}}})
        except Aborted:
            status = "aborted"
        except asyncio.CancelledError:
            await deps.store.update_run(tenant, run["id"], {"status": "interrupted", "phases_done": done, "phase_results": results})
            raise
        rep = shared.get("report") or {}
        patch = {"status": status, "finished_at": deps.now().isoformat(), "phases_done": done, "phase_results": results,
                 "report": rep, "health_score": rep.get("health_score"),
                 "errors": rep.get("errors") or [], "jev_calls": int((shared.get("jev") or {}).get("calls", 0)),
                 "jev_cost_usd": float((shared.get("jev") or {}).get("cost_usd", 0.0)),
                 "counts": {p: r.get("counts", {}) for p, r in results.items()}}
        return await deps.store.update_run(tenant, run["id"], patch)


async def run_due(engine: DreamEngine, tenants: list[str], *, trigger: str = "nightly") -> list[dict]:
    """Worker entry: for every tenant whose window is open and whose night has not run, one tenant after another."""
    deps = engine.deps
    out = []
    for tenant in tenants:
        if deps.kill():
            break
        cfg = await engine.settings_for(tenant)
        if not cfg.enabled or not in_window(deps.now(), cfg):
            continue
        day = local_date(deps.now(), cfg.timezone)
        if await deps.store.nightly_done(tenant, day):
            continue
        try:
            out.append({"tenant": tenant, **(await engine.run_tenant(tenant, trigger=trigger))})
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("dream run failed for tenant %s", tenant)
        await deps.sleep(cfg.tenant_pause_s)
    return out
