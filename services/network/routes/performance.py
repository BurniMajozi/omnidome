"""Network performance monitoring routes.

Provides:
- Metric ingestion (from probes, SNMP, TR-069, speed tests)
- Metric querying with aggregation
- SLA profile management
- SLA breach detection and reporting
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select

from services.common.auth import AuthContext, get_auth_context
from services.network.database import get_session
from services.network.models import (
    NetworkDevice,
    NetworkPerformanceMetric,
    NetworkService,
    NetworkSLABreach,
    NetworkSLAProfile,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/performance", tags=["Performance"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class MetricIngest(BaseModel):
    """Schema for ingesting a performance metric from a probe/device."""
    service_id: uuid.UUID
    device_id: Optional[uuid.UUID] = None
    metric_type: str
    metric_value: float
    unit: Optional[str] = None
    source: str = "probe"
    collected_at: Optional[datetime] = None


class MetricRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    service_id: uuid.UUID
    device_id: Optional[uuid.UUID]
    metric_type: str
    metric_value: float
    unit: Optional[str]
    source: str
    collected_at: datetime

    class Config:
        from_attributes = True


class MetricAggregate(BaseModel):
    metric_type: str
    period: str
    avg_value: float
    min_value: float
    max_value: float
    sample_count: int


class SLAProfileCreate(BaseModel):
    service_id: Optional[uuid.UUID] = None
    fno_provider: Optional[str] = None
    target_latency_ms: Optional[float] = Field(None, ge=0)
    target_jitter_ms: Optional[float] = Field(None, ge=0)
    target_packet_loss_pct: Optional[float] = Field(None, ge=0, le=100)
    target_download_mbps: Optional[float] = Field(None, ge=0)
    target_upload_mbps: Optional[float] = Field(None, ge=0)
    target_uptime_pct: Optional[float] = Field(None, ge=0, le=100)
    target_mttr_minutes: Optional[int] = Field(None, ge=0)
    evaluation_window_hours: int = Field(default=720, ge=1, le=8760)


class SLAProfileUpdate(BaseModel):
    target_latency_ms: Optional[float] = Field(None, ge=0)
    target_jitter_ms: Optional[float] = Field(None, ge=0)
    target_packet_loss_pct: Optional[float] = Field(None, ge=0, le=100)
    target_download_mbps: Optional[float] = Field(None, ge=0)
    target_upload_mbps: Optional[float] = Field(None, ge=0)
    target_uptime_pct: Optional[float] = Field(None, ge=0, le=100)
    target_mttr_minutes: Optional[int] = Field(None, ge=0)
    evaluation_window_hours: Optional[int] = Field(None, ge=1, le=8760)
    is_active: Optional[bool] = None


class SLAProfileRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    service_id: Optional[uuid.UUID]
    fno_provider: Optional[str]
    target_latency_ms: Optional[float]
    target_jitter_ms: Optional[float]
    target_packet_loss_pct: Optional[float]
    target_download_mbps: Optional[float]
    target_upload_mbps: Optional[float]
    target_uptime_pct: Optional[float]
    target_mttr_minutes: Optional[int]
    evaluation_window_hours: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SLABreachRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    sla_profile_id: uuid.UUID
    service_id: Optional[uuid.UUID]
    metric_type: str
    target_value: float
    actual_value: float
    severity: str
    started_at: datetime
    resolved_at: Optional[datetime]
    duration_seconds: Optional[int]
    acknowledged: bool
    acknowledged_by: Optional[uuid.UUID]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SpeedTestRequest(BaseModel):
    """Trigger a speed test for a service (placeholder for actual iperf3 integration)."""
    service_id: uuid.UUID


class SpeedTestResult(BaseModel):
    service_id: uuid.UUID
    download_mbps: float
    upload_mbps: float
    latency_ms: float
    jitter_ms: float
    tested_at: datetime


# ---------------------------------------------------------------------------
# Metric ingestion
# ---------------------------------------------------------------------------

@router.post("/metrics", response_model=MetricRead, status_code=status.HTTP_201_CREATED)
async def ingest_metric(
    body: MetricIngest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Ingest a performance metric from a probe, SNMP poll, TR-069, or speed test."""
    with get_session() as session:
        # Verify service belongs to tenant
        svc = session.execute(
            select(NetworkService).where(
                NetworkService.id == body.service_id,
                NetworkService.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if not svc:
            raise HTTPException(status_code=404, detail="Network service not found")

        metric = NetworkPerformanceMetric(
            tenant_id=ctx.tenant_id,
            service_id=body.service_id,
            device_id=body.device_id,
            metric_type=body.metric_type,
            metric_value=body.metric_value,
            unit=body.unit,
            source=body.source,
            collected_at=body.collected_at or datetime.now(timezone.utc),
        )
        session.add(metric)
        session.flush()
        session.refresh(metric)
        return MetricRead.model_validate(metric)


@router.post("/metrics/batch", status_code=status.HTTP_201_CREATED)
async def ingest_metrics_batch(
    body: list[MetricIngest],
    ctx: AuthContext = Depends(get_auth_context),
):
    """Batch ingest performance metrics."""
    with get_session() as session:
        metrics = []
        for item in body:
            svc = session.execute(
                select(NetworkService).where(
                    NetworkService.id == item.service_id,
                    NetworkService.tenant_id == ctx.tenant_id,
                )
            ).scalar_one_or_none()
            if not svc:
                continue
            metric = NetworkPerformanceMetric(
                tenant_id=ctx.tenant_id,
                service_id=item.service_id,
                device_id=item.device_id,
                metric_type=item.metric_type,
                metric_value=item.metric_value,
                unit=item.unit,
                source=item.source,
                collected_at=item.collected_at or datetime.now(timezone.utc),
            )
            session.add(metric)
            metrics.append(metric)
        session.flush()
        return {"ingested": len(metrics)}


# ---------------------------------------------------------------------------
# Metric querying
# ---------------------------------------------------------------------------

@router.get("/metrics", response_model=list[MetricRead])
async def query_metrics(
    ctx: AuthContext = Depends(get_auth_context),
    service_id: Optional[uuid.UUID] = None,
    device_id: Optional[uuid.UUID] = None,
    metric_type: Optional[str] = None,
    from_time: Optional[datetime] = Query(None, description="Start of time range (ISO 8601)"),
    to_time: Optional[datetime] = Query(None, description="End of time range (ISO 8601)"),
    limit: int = Query(100, ge=1, le=10000),
):
    """Query performance metrics with filters."""
    with get_session() as session:
        stmt = select(NetworkPerformanceMetric).where(
            NetworkPerformanceMetric.tenant_id == ctx.tenant_id
        )
        if service_id:
            stmt = stmt.where(NetworkPerformanceMetric.service_id == service_id)
        if device_id:
            stmt = stmt.where(NetworkPerformanceMetric.device_id == device_id)
        if metric_type:
            stmt = stmt.where(NetworkPerformanceMetric.metric_type == metric_type)
        if from_time:
            stmt = stmt.where(NetworkPerformanceMetric.collected_at >= from_time)
        if to_time:
            stmt = stmt.where(NetworkPerformanceMetric.collected_at <= to_time)

        stmt = stmt.order_by(NetworkPerformanceMetric.collected_at.desc()).limit(limit)
        result = session.execute(stmt)
        return [MetricRead.model_validate(m) for m in result.scalars().all()]


@router.get("/metrics/aggregate", response_model=list[MetricAggregate])
async def aggregate_metrics(
    ctx: AuthContext = Depends(get_auth_context),
    service_id: uuid.UUID = Query(..., description="Service ID to aggregate"),
    metric_type: str = Query(..., description="Metric type to aggregate"),
    period: str = Query("1h", description="Aggregation period: 1h, 24h, 7d, 30d"),
):
    """Get aggregated metrics (avg, min, max) for a service over a time period."""
    with get_session() as session:
        now = datetime.now(timezone.utc)
        period_map = {"1h": 1, "24h": 24, "7d": 168, "30d": 720}
        hours = period_map.get(period, 1)
        from_time = now - timedelta(hours=hours)

        stmt = select(
            NetworkPerformanceMetric.metric_type,
            func.avg(NetworkPerformanceMetric.metric_value).label("avg_value"),
            func.min(NetworkPerformanceMetric.metric_value).label("min_value"),
            func.max(NetworkPerformanceMetric.metric_value).label("max_value"),
            func.count(NetworkPerformanceMetric.id).label("sample_count"),
        ).where(
            NetworkPerformanceMetric.tenant_id == ctx.tenant_id,
            NetworkPerformanceMetric.service_id == service_id,
            NetworkPerformanceMetric.metric_type == metric_type,
            NetworkPerformanceMetric.collected_at >= from_time,
        ).group_by(NetworkPerformanceMetric.metric_type)

        result = session.execute(stmt)
        return [
            MetricAggregate(
                metric_type=row.metric_type,
                period=period,
                avg_value=round(float(row.avg_value), 4),
                min_value=round(float(row.min_value), 4),
                max_value=round(float(row.max_value), 4),
                sample_count=row.sample_count,
            )
            for row in result.all()
        ]


# ---------------------------------------------------------------------------
# Speed test
# ---------------------------------------------------------------------------

@router.post("/speed-test", response_model=SpeedTestResult)
async def run_speed_test(
    body: SpeedTestRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Run a speed test for a service.

    In production this triggers an actual iperf3 test or uses the ONT's
    built-in speed test. Currently returns a placeholder.
    """
    with get_session() as session:
        svc = session.execute(
            select(NetworkService).where(
                NetworkService.id == body.service_id,
                NetworkService.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if not svc:
            raise HTTPException(status_code=404, detail="Network service not found")

        # TODO: trigger actual speed test via iperf3 or ONT API
        import random
        result = SpeedTestResult(
            service_id=body.service_id,
            download_mbps=round(random.uniform(
                svc.download_speed_mbps * 0.7, svc.download_speed_mbps * 0.95
            ), 2),
            upload_mbps=round(random.uniform(
                svc.upload_speed_mbps * 0.7, svc.upload_speed_mbps * 0.95
            ), 2),
            latency_ms=round(random.uniform(3, 25), 2),
            jitter_ms=round(random.uniform(0.5, 5), 2),
            tested_at=datetime.now(timezone.utc),
        )

        # Store the results as metrics
        for metric_type, value in [
            ("download_mbps", result.download_mbps),
            ("upload_mbps", result.upload_mbps),
            ("latency_ms", result.latency_ms),
            ("jitter_ms", result.jitter_ms),
        ]:
            session.add(NetworkPerformanceMetric(
                tenant_id=ctx.tenant_id,
                service_id=body.service_id,
                metric_type=metric_type,
                metric_value=value,
                source="speed_test",
                collected_at=result.tested_at,
            ))
        session.flush()
        return result


# ---------------------------------------------------------------------------
# SLA Profiles
# ---------------------------------------------------------------------------

@router.post("/sla-profiles", response_model=SLAProfileRead, status_code=status.HTTP_201_CREATED)
async def create_sla_profile(
    body: SLAProfileCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create an SLA profile for a service or FNO provider."""
    with get_session() as session:
        profile = NetworkSLAProfile(
            tenant_id=ctx.tenant_id,
            service_id=body.service_id,
            fno_provider=body.fno_provider,
            target_latency_ms=body.target_latency_ms,
            target_jitter_ms=body.target_jitter_ms,
            target_packet_loss_pct=body.target_packet_loss_pct,
            target_download_mbps=body.target_download_mbps,
            target_upload_mbps=body.target_upload_mbps,
            target_uptime_pct=body.target_uptime_pct,
            target_mttr_minutes=body.target_mttr_minutes,
            evaluation_window_hours=body.evaluation_window_hours,
        )
        session.add(profile)
        session.flush()
        session.refresh(profile)
        return SLAProfileRead.model_validate(profile)


@router.get("/sla-profiles", response_model=list[SLAProfileRead])
async def list_sla_profiles(
    ctx: AuthContext = Depends(get_auth_context),
    service_id: Optional[uuid.UUID] = None,
    fno_provider: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    """List SLA profiles."""
    with get_session() as session:
        stmt = select(NetworkSLAProfile).where(
            NetworkSLAProfile.tenant_id == ctx.tenant_id
        )
        if service_id:
            stmt = stmt.where(NetworkSLAProfile.service_id == service_id)
        if fno_provider:
            stmt = stmt.where(NetworkSLAProfile.fno_provider == fno_provider)
        if is_active is not None:
            stmt = stmt.where(NetworkSLAProfile.is_active == is_active)
        result = session.execute(stmt)
        return [SLAProfileRead.model_validate(p) for p in result.scalars().all()]


@router.get("/sla-profiles/{profile_id}", response_model=SLAProfileRead)
async def get_sla_profile(
    profile_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        profile = session.execute(
            select(NetworkSLAProfile).where(
                NetworkSLAProfile.id == profile_id,
                NetworkSLAProfile.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if not profile:
            raise HTTPException(status_code=404, detail="SLA profile not found")
        return SLAProfileRead.model_validate(profile)


@router.put("/sla-profiles/{profile_id}", response_model=SLAProfileRead)
async def update_sla_profile(
    profile_id: uuid.UUID,
    body: SLAProfileUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        profile = session.execute(
            select(NetworkSLAProfile).where(
                NetworkSLAProfile.id == profile_id,
                NetworkSLAProfile.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if not profile:
            raise HTTPException(status_code=404, detail="SLA profile not found")

        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(profile, field, value)
        session.flush()
        session.refresh(profile)
        return SLAProfileRead.model_validate(profile)


@router.delete("/sla-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sla_profile(
    profile_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        profile = session.execute(
            select(NetworkSLAProfile).where(
                NetworkSLAProfile.id == profile_id,
                NetworkSLAProfile.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if not profile:
            raise HTTPException(status_code=404, detail="SLA profile not found")
        session.delete(profile)


# ---------------------------------------------------------------------------
# SLA Breaches
# ---------------------------------------------------------------------------

@router.get("/sla-breaches", response_model=list[SLABreachRead])
async def list_sla_breaches(
    ctx: AuthContext = Depends(get_auth_context),
    service_id: Optional[uuid.UUID] = None,
    severity: Optional[str] = None,
    open_only: bool = False,
    limit: int = Query(50, ge=1, le=500),
):
    """List SLA breaches."""
    with get_session() as session:
        stmt = select(NetworkSLABreach).where(
            NetworkSLABreach.tenant_id == ctx.tenant_id
        )
        if service_id:
            stmt = stmt.where(NetworkSLABreach.service_id == service_id)
        if severity:
            stmt = stmt.where(NetworkSLABreach.severity == severity)
        if open_only:
            stmt = stmt.where(NetworkSLABreach.resolved_at.is_(None))
        stmt = stmt.order_by(NetworkSLABreach.started_at.desc()).limit(limit)
        result = session.execute(stmt)
        return [SLABreachRead.model_validate(b) for b in result.scalars().all()]


@router.post("/sla-breaches/{breach_id}/acknowledge")
async def acknowledge_breach(
    breach_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    notes: Optional[str] = None,
):
    """Acknowledge an SLA breach."""
    with get_session() as session:
        breach = session.execute(
            select(NetworkSLABreach).where(
                NetworkSLABreach.id == breach_id,
                NetworkSLABreach.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if not breach:
            raise HTTPException(status_code=404, detail="SLA breach not found")
        breach.acknowledged = True
        breach.acknowledged_by = ctx.user_id
        if notes:
            breach.notes = notes
        session.flush()
        return {"id": str(breach.id), "acknowledged": True}


@router.post("/sla-breaches/{breach_id}/resolve")
async def resolve_breach(
    breach_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Resolve an SLA breach."""
    with get_session() as session:
        breach = session.execute(
            select(NetworkSLABreach).where(
                NetworkSLABreach.id == breach_id,
                NetworkSLABreach.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if not breach:
            raise HTTPException(status_code=404, detail="SLA breach not found")
        now = datetime.now(timezone.utc)
        breach.resolved_at = now
        if breach.started_at:
            breach.duration_seconds = int((now - breach.started_at).total_seconds())
        session.flush()
        return {"id": str(breach.id), "resolved": True, "duration_seconds": breach.duration_seconds}


# ---------------------------------------------------------------------------
# SLA Evaluation (can be called by cron job)
# ---------------------------------------------------------------------------

@router.post("/sla-evaluate")
async def evaluate_sla(
    ctx: AuthContext = Depends(get_auth_context),
    service_id: Optional[uuid.UUID] = None,
):
    """Evaluate SLA profiles against recent metrics and create breach records.

    In production this runs as a scheduled job (e.g. every 5 minutes).
    """
    with get_session() as session:
        # Get active SLA profiles
        stmt = select(NetworkSLAProfile).where(
            NetworkSLAProfile.tenant_id == ctx.tenant_id,
            NetworkSLAProfile.is_active.is_(True),
        )
        if service_id:
            stmt = stmt.where(NetworkSLAProfile.service_id == service_id)
        profiles = session.execute(stmt).scalars().all()

        breaches_created = 0
        now = datetime.now(timezone.utc)

        for profile in profiles:
            window_start = now - timedelta(hours=profile.evaluation_window_hours)

            # Determine which services to check
            if profile.service_id:
                service_ids = [profile.service_id]
            elif profile.fno_provider:
                svc_stmt = select(NetworkService.id).where(
                    NetworkService.tenant_id == ctx.tenant_id,
                    NetworkService.fno_provider == profile.fno_provider,
                )
                service_ids = [r[0] for r in session.execute(svc_stmt).all()]
            else:
                continue

            for sid in service_ids:
                # Check each target
                checks = [
                    ("latency_ms", profile.target_latency_ms, lambda v, t: v > t),
                    ("jitter_ms", profile.target_jitter_ms, lambda v, t: v > t),
                    ("packet_loss_pct", profile.target_packet_loss_pct, lambda v, t: v > t),
                    ("download_mbps", profile.target_download_mbps, lambda v, t: v < t),
                    ("upload_mbps", profile.target_upload_mbps, lambda v, t: v < t),
                ]
                for metric_type, target, comparator in checks:
                    if target is None:
                        continue
                    # Get average over window
                    avg_stmt = select(
                        func.avg(NetworkPerformanceMetric.metric_value)
                    ).where(
                        NetworkPerformanceMetric.tenant_id == ctx.tenant_id,
                        NetworkPerformanceMetric.service_id == sid,
                        NetworkPerformanceMetric.metric_type == metric_type,
                        NetworkPerformanceMetric.collected_at >= window_start,
                    )
                    result = session.execute(avg_stmt).scalar()
                    if result is None:
                        continue
                    avg_val = float(result)
                    if comparator(avg_val, target):
                        # Check if there's already an open breach
                        existing = session.execute(
                            select(NetworkSLABreach).where(
                                NetworkSLABreach.tenant_id == ctx.tenant_id,
                                NetworkSLABreach.sla_profile_id == profile.id,
                                NetworkSLABreach.service_id == sid,
                                NetworkSLABreach.metric_type == metric_type,
                                NetworkSLABreach.resolved_at.is_(None),
                            )
                        ).scalar_one_or_none()

                        if not existing:
                            severity = "warning"
                            deviation = abs(avg_val - target) / target if target else 0
                            if deviation > 0.5:
                                severity = "critical"
                            elif deviation > 0.2:
                                severity = "warning"

                            breach = NetworkSLABreach(
                                tenant_id=ctx.tenant_id,
                                sla_profile_id=profile.id,
                                service_id=sid,
                                metric_type=metric_type,
                                target_value=target,
                                actual_value=round(avg_val, 4),
                                severity=severity,
                                started_at=now,
                            )
                            session.add(breach)
                            breaches_created += 1

        session.flush()
        return {"evaluated": len(profiles), "breaches_created": breaches_created}
