"""Metric catalog, snapshot trigger and forecast-run queue (mounted under /api/fno/bi by bi_routes).

    GET  /bi/metrics/catalog        catalogued metrics (viewer)
    POST /bi/metrics/snapshot       run governed queries now and upsert ACTUAL metric facts (admin)
    POST /bi/forecast/runs          enqueue a forecast run row (admin). NO compute here: the batch job
                                    `python -m services.forecaster.run --pending` claims it.
    GET  /bi/forecast/runs          recent runs for the tenant (viewer)
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_current_tenant_id
from services.fno_intelligence import analytics_common as ac
from services.fno_intelligence import bi_metrics_writer as writer
from services.fno_intelligence import database
from services.fno_intelligence import metric_catalog as mc
from services.fno_intelligence.forecast_models import ForecastRun

router = APIRouter(tags=["BI metrics"])


class SnapshotBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metrics: Optional[list[str]] = Field(None, max_length=40)
    periods: Optional[int] = Field(None, ge=1, le=240)


class ForecastRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metrics: Optional[list[str]] = Field(None, max_length=40)
    horizon: Optional[int] = Field(None, ge=1, le=60)


def _unknown(keys: Optional[list], *, forecast: bool = False) -> None:
    if not keys:
        return
    bad = [k for k in keys if k not in mc.BY_KEY or (forecast and not (mc.BY_KEY[k].forecastable and mc.BY_KEY[k].shape == "series"))]
    if bad:
        raise HTTPException(422, f"{'not forecastable or unknown' if forecast else 'unknown'} metric key(s): {', '.join(bad)}")


@router.get("/metrics/catalog")
async def metrics_catalog(_: AuthContext = Depends(ac.require_viewer)):
    return {"metrics": [m.public() for m in mc.CATALOG],
            "history_rules": {"min_history": mc.MIN_HISTORY, "default_horizon": mc.DEFAULT_HORIZON, "max_horizon": mc.MAX_HORIZON},
            "writer_configured": writer.get_sink().configured()}


@router.post("/metrics/snapshot")
async def metrics_snapshot(body: SnapshotBody, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                           _: AuthContext = Depends(ac.require_admin), db: AsyncSession = Depends(database.get_session)):
    _unknown(body.metrics)
    try:
        summary = await writer.snapshot_metrics(db, tenant_id, body.metrics, body.periods)
    except writer.SinkError as exc:
        raise HTTPException(503, str(exc))
    return {"metrics": summary, "facts": sum(v.get("facts", 0) for v in summary.values()),
            "errors": sum(1 for v in summary.values() if v.get("error"))}


def _run_public(r: ForecastRun) -> dict:
    return {"id": str(r.id), "status": r.status, "metrics": r.metric_keys, "horizon": r.horizon, "summary": r.summary,
            "error": r.error, "created_at": r.created_at.isoformat() if r.created_at else None,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None}


@router.post("/forecast/runs", status_code=202)
async def forecast_enqueue(body: ForecastRunBody, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                           auth: AuthContext = Depends(ac.require_admin), db: AsyncSession = Depends(database.get_session)):
    _unknown(body.metrics, forecast=True)
    if body.horizon is not None and body.metrics:
        too_far = [k for k in body.metrics if body.horizon > mc.MAX_HORIZON[mc.BY_KEY[k].grain]]
        if too_far:
            raise HTTPException(422, f"horizon {body.horizon} exceeds the maximum for: {', '.join(too_far)}")
    active = (await db.execute(select(ForecastRun).where(ForecastRun.tenant_id == tenant_id, ForecastRun.status.in_(("queued", "running")))
                               .order_by(ForecastRun.created_at.desc()).limit(1))).scalar_one_or_none()
    if active is not None:
        return {**_run_public(active), "deduplicated": True}
    run = ForecastRun(tenant_id=tenant_id, status="queued", metric_keys=body.metrics or None, horizon=body.horizon,
                      requested_by=auth.user_id)
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return {**_run_public(run), "deduplicated": False}


@router.get("/forecast/runs")
async def forecast_runs(tenant_id: uuid.UUID = Depends(get_current_tenant_id), _: AuthContext = Depends(ac.require_viewer),
                        db: AsyncSession = Depends(database.get_session)):
    rows = (await db.execute(select(ForecastRun).where(ForecastRun.tenant_id == tenant_id)
                             .order_by(ForecastRun.created_at.desc()).limit(20))).scalars().all()
    return {"runs": [_run_public(r) for r in rows]}
