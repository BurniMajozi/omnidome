"""Glue between the knowledge worker loop and the dream engine (kept out of worker.py so that file only gets two small hooks)."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.tenant_memory.knowledge.dream.engine import DreamEngine, run_due

logger = logging.getLogger("knowledge.dream.runner")
TICK_EVERY = timedelta(seconds=int(os.getenv("DREAM_TICK_SECONDS", "300")))
_engines: dict[int, DreamEngine] = {}


def engine_for(kstore, embedder) -> DreamEngine:
    eng = _engines.get(id(kstore))
    if eng is None:
        from services.tenant_memory.knowledge.dream.adapters import build_deps
        eng = _engines[id(kstore)] = DreamEngine(build_deps(kstore, embedder))
    return eng


async def ensure_schema(kstore, embedder) -> None:
    """Create the dream_* tables (idempotent; same advisory-locked, owner-credential path as the knowledge tables)."""
    await engine_for(kstore, embedder).deps.store.ensure_schema()


async def run_dream_job(kstore, embedder, job: dict) -> dict:
    """Admin-triggered run (`knowledge_jobs.kind = 'dream'`): dry-run by default."""
    p = job.get("params") or {}
    run = await engine_for(kstore, embedder).run_tenant(job["tenant_id"], dry_run=bool(p.get("dry_run", True)), phases=p.get("phases"),
                                                        trigger="manual", requested_by=job.get("requested_by"), resume=False)
    return {k: run.get(k) for k in ("id", "status", "reason", "health_score", "phases_done") if k in run}


async def tick(kstore, embedder, tenants_fn, last: Optional[datetime], now: Optional[datetime] = None) -> datetime:
    """Called from the worker loop (`tenants_fn` is an async callable, only awaited when a tick is due); returns the new 'last tick' time. Cheap when no tenant is inside its window."""
    now = now or datetime.now(timezone.utc)
    if last is not None and now - last < TICK_EVERY:
        return last
    try:
        done = await run_due(engine_for(kstore, embedder), await tenants_fn())
        for d in done:
            logger.info("dream night finished: tenant=%s status=%s health=%s", d.get("tenant"), d.get("status"), d.get("health_score"))
    except Exception:  # noqa: BLE001 - the dream must never take the worker down
        logger.exception("dream tick failed")
    return now
