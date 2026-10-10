"""Admin endpoints of the dream state (mounted under /api/v1 by knowledge/routes.py):

    GET  /knowledge/dream/status                  last run, health, trend, settings, JEV + kill-switch state
    GET  /knowledge/dream/runs                    history
    GET  /knowledge/dream/runs/{id}               one run with per-phase results and its report
    GET  /knowledge/dream/findings                filters: status, severity, phase, type
    POST /knowledge/dream/run                     manual run (dry_run defaults to TRUE); queued for the worker, or inline=true
    POST /knowledge/dream/findings/{id}/resolve   accept | dismiss | apply
    GET/PUT /knowledge/dream/settings             per-tenant window, enabled, JEV cap/thresholds, tunables

Imports from knowledge.routes happen lazily (that module includes this router at its end).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services.common.auth import AuthContext, get_auth_context
from services.tenant_memory.knowledge.dream import PHASES, actions
from services.tenant_memory.knowledge.dream.engine import DreamEngine, local_tz
from services.tenant_memory.knowledge.dream.settings import TENANT_KEYS, from_env, kill_switch_on, merged
from services.tenant_memory.knowledge.dream.store import OPEN_STATES
from services.tenant_memory.knowledge.kdata import ADMIN_ROLES

logger = logging.getLogger("knowledge.dream.routes")
router = APIRouter(prefix="/knowledge/dream")
_state: dict = {}


def set_engine(engine: Optional[DreamEngine]) -> None:
    """Tests (and the worker) inject a fully wired engine here."""
    _state["engine"], _state["key"] = engine, None


def get_engine() -> DreamEngine:
    if _state.get("engine") is not None and _state.get("key") is None:
        return _state["engine"]
    from services.tenant_memory.knowledge.routes import get_runtime          # lazy: avoids the import cycle
    kstore, embedder = get_runtime()
    if _state.get("key") != id(kstore):
        from services.tenant_memory.knowledge.dream.adapters import build_deps
        _state["engine"], _state["key"] = DreamEngine(build_deps(kstore, embedder)), id(kstore)
    return _state["engine"]


def require_admin(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    roles = {r.lower() for r in ctx.roles}
    if not (ctx.is_platform_admin or roles & ADMIN_ROLES or "agents.manage" in {p.lower() for p in ctx.permissions}):
        raise HTTPException(403, "Admin role required")
    return ctx


def _missing_tables(exc: Exception) -> bool:
    m = str(exc).lower()
    return "does not exist" in m or "undefinedtable" in m


def next_window(now: datetime, cfg) -> str:
    loc = now.astimezone(local_tz(cfg.timezone))
    hh, mm = (int(x) for x in cfg.window_start.split(":"))
    nxt = loc.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if nxt <= loc:
        nxt += timedelta(days=1)
    return nxt.astimezone(timezone.utc).isoformat()


@router.get("/status")
async def status(ctx: AuthContext = Depends(require_admin)):
    eng = get_engine()
    deps, tenant = eng.deps, str(ctx.tenant_id)
    overrides = {}
    cfg = merged({}, deps.base_settings or from_env())
    out = {"kill_switch": kill_switch_on() or deps.kill(), "phases": list(PHASES), "ready": True}
    try:
        overrides = await deps.store.get_settings(tenant)
        cfg = await eng.settings_for(tenant)
        runs = await deps.store.list_runs(tenant, 30, include_dry=True)
        counts = await deps.store.finding_counts(tenant)
        cards = await deps.store.count_cards(tenant)
    except Exception as exc:  # noqa: BLE001
        if not _missing_tables(exc):
            raise
        return {**out, "ready": False, "note": "The dream tables are created by the knowledge worker at startup; none exist yet.",
                "settings": cfg.to_dict(), "overrides": {}, "trend": [], "last_run": None, "running": None, "findings": {"open": {}, "total_open": 0}}
    real = [r for r in runs if not r.get("dry_run")]
    trend = [{"run_date": r["run_date"], "health_score": r.get("health_score"),
              "canary_recall": ((r.get("report") or {}).get("canary") or {}).get("recall_at_3"),
              "stale": ((r.get("report") or {}).get("cards") or {}).get("stale"), "status": r["status"]}
             for r in reversed(real[:14])]
    summary = lambda r: None if r is None else {k: r.get(k) for k in ("id", "run_date", "trigger", "dry_run", "status", "started_at", "finished_at",  # noqa: E731
                                                                      "health_score", "jev_calls", "jev_cost_usd", "phases_done")} | {"report": r.get("report") or {}}
    return {**out, "settings": cfg.to_dict(), "overrides": overrides, "last_run": summary(real[0] if real else None),
            "last_dry_run": summary(next((r for r in runs if r.get("dry_run")), None)),
            "running": summary(next((r for r in runs if r["status"] == "running"), None)), "trend": trend, "findings": counts,
            "cards": {k: cards[k] for k in ("live_chunks", "live_sources", "stale_tagged", "tombstoned")},
            "next_window": next_window(deps.now(), cfg) if cfg.enabled else None,
            "jev": {"enabled": cfg.jev_enabled, "credentials": bool(deps.jev and deps.jev.configured()), "external": True}}


@router.get("/runs")
async def runs(limit: int = Query(20, ge=1, le=100), ctx: AuthContext = Depends(require_admin)):
    rows = await get_engine().deps.store.list_runs(str(ctx.tenant_id), limit, include_dry=True)
    return {"runs": [{k: v for k, v in r.items() if k not in ("state", "phase_results")} for r in rows]}


@router.get("/runs/{run_id}")
async def run_detail(run_id: str, ctx: AuthContext = Depends(require_admin)):
    r = await get_engine().deps.store.get_run(str(ctx.tenant_id), run_id)
    if r is None:
        raise HTTPException(404, "Run not found")
    r.pop("state", None)
    return r


@router.get("/findings")
async def findings(status: Optional[str] = None, severity: Optional[str] = None, phase: Optional[str] = None, type: Optional[str] = None,
                   run_id: Optional[str] = None, limit: int = Query(100, ge=1, le=500), ctx: AuthContext = Depends(require_admin)):
    rows = await get_engine().deps.store.list_findings(str(ctx.tenant_id), status=status, severity=severity, phase=phase, type=type,
                                                       run_id=run_id, limit=limit)
    return {"findings": rows}


class RunRequest(BaseModel):
    dry_run: bool = Field(True, description="default TRUE: a dry run changes nothing but the dream_* log tables")
    phases: Optional[list[str]] = None
    inline: bool = Field(False, description="run inside this request instead of queueing it for the worker (small tenants / debugging)")


@router.post("/run", status_code=202)
async def run_now(req: RunRequest, ctx: AuthContext = Depends(require_admin)):
    bad = [p for p in (req.phases or []) if p not in PHASES]
    if bad:
        raise HTTPException(400, f"unknown phases {bad}; valid: {list(PHASES)}")
    eng = get_engine()
    if eng.deps.kill():
        raise HTTPException(409, "The dream kill switch is on (DREAM_KILL_SWITCH)")
    tenant = str(ctx.tenant_id)
    if req.inline:
        return await eng.run_tenant(tenant, dry_run=req.dry_run, phases=req.phases, trigger="manual", requested_by=str(ctx.user_id))
    jid = await eng.deps.store.kstore.enqueue_job(tenant, "dream", {"dry_run": req.dry_run, "phases": req.phases}, str(ctx.user_id))
    return {"job_id": jid, "status": "queued", "dry_run": req.dry_run, "note": "the knowledge worker picks it up within a minute"}


class ResolveRequest(BaseModel):
    action: str = Field(..., pattern=r"^(accept|dismiss|apply)$")
    note: Optional[str] = Field(None, max_length=500)


@router.post("/findings/{finding_id}/resolve")
async def resolve(finding_id: str, req: ResolveRequest, ctx: AuthContext = Depends(require_admin)):
    eng, tenant = get_engine(), str(ctx.tenant_id)
    f = await eng.deps.store.get_finding(tenant, finding_id)
    if f is None:
        raise HTTPException(404, "Finding not found")
    if f["status"] not in OPEN_STATES + ("auto_applied",):
        raise HTTPException(409, f"Finding is already {f['status']}")
    resolution: dict = {"action": req.action, "note": req.note}
    if req.action == "apply":
        res = await actions.apply_action(eng.deps, tenant, f)
        if not res.get("applied"):
            raise HTTPException(400, res.get("note") or "Nothing could be applied")
        resolution["result"] = res
    status_ = {"accept": "accepted", "dismiss": "dismissed", "apply": "applied"}[req.action]
    out = await eng.deps.store.update_finding(tenant, finding_id, {"status": status_, "resolved_by": str(ctx.user_id),
                                                                   "resolved_at": eng.deps.now().isoformat(), "resolution": resolution})
    return out


class SettingsPatch(BaseModel):
    enabled: Optional[bool] = None
    window_start: Optional[str] = Field(None, pattern=r"^\d{1,2}:\d{2}$")
    window_hours: Optional[float] = Field(None, ge=0.5, le=12)
    timezone: Optional[str] = Field(None, max_length=60)
    max_cards_per_night: Optional[int] = Field(None, ge=0, le=20000)
    rotation_days: Optional[int] = Field(None, ge=1, le=60)
    semantic_drift: Optional[float] = Field(None, ge=0.05, le=1.0)
    canary_n: Optional[int] = Field(None, ge=0, le=100)
    canary_recall_floor: Optional[float] = Field(None, ge=0, le=1)
    canary_alert_drop: Optional[float] = Field(None, ge=0.01, le=1)
    metric_tolerance: Optional[float] = Field(None, ge=0, le=0.5)
    decay_after_days: Optional[int] = Field(None, ge=14, le=720)
    jev_enabled: Optional[bool] = None
    jev_max_calls: Optional[int] = Field(None, ge=0, le=200)
    jev_max_cost_usd: Optional[float] = Field(None, ge=0, le=20)
    jev_approve: Optional[float] = Field(None, ge=0.8, le=0.999, description="act only at or above this; cannot be looser than 0.80")
    jev_reject: Optional[float] = Field(None, ge=0.001, le=0.2, description="act only at or below this; cannot be looser than 0.20")
    stale_days: Optional[dict[str, int]] = None


@router.get("/settings")
async def get_settings_(ctx: AuthContext = Depends(require_admin)):
    eng, tenant = get_engine(), str(ctx.tenant_id)
    try:
        overrides = await eng.deps.store.get_settings(tenant)
    except Exception as exc:  # noqa: BLE001
        if not _missing_tables(exc):
            raise
        overrides = {}
    cfg = merged(overrides, eng.deps.base_settings or from_env())
    return {"settings": cfg.to_dict(), "overrides": overrides, "tunable": list(TENANT_KEYS)}


@router.put("/settings")
async def put_settings(body: SettingsPatch, ctx: AuthContext = Depends(require_admin)):
    eng, tenant = get_engine(), str(ctx.tenant_id)
    patch = body.model_dump(exclude_unset=True)
    if "timezone" in patch and patch["timezone"]:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(patch["timezone"])
        except Exception:  # noqa: BLE001
            raise HTTPException(400, f"unknown timezone {patch['timezone']!r}") from None
    if "window_start" in patch and patch["window_start"] and not re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", patch["window_start"]):
        raise HTTPException(400, "window_start must be HH:MM (00:00-23:59)")
    current = await eng.deps.store.get_settings(tenant)
    for k, v in patch.items():
        if v is None:
            current.pop(k, None)
        else:
            current[k] = v
    await eng.deps.store.put_settings(tenant, current, str(ctx.user_id))
    cfg = merged(current, eng.deps.base_settings or from_env())
    return {"settings": cfg.to_dict(), "overrides": current}
