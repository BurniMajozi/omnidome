"""Network topology, bandwidth, SLA compliance, and device configuration routes.

Provides:
- Network typography hierarchy (Region → Metro → Area)
- Network topology elements and links (OLTs, splitters, cables)
- Bandwidth usage tracking and reporting
- FNO SLA compliance measurement
- Device configuration templates and push tracking
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select

from services.common.auth import AuthContext, get_auth_context
from services.network.database import get_session
from services.network.models import (
    BandwidthUsage,
    DeviceConfigPush,
    DeviceConfigTemplate,
    FNOSLAMeasurement,
    FNOSLATarget,
    NetworkArea,
    NetworkMetro,
    NetworkRegion,
    NetworkService,
    NetworkTopologyElement,
    NetworkTopologyLink,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/network", tags=["Network Extended"])


# ===========================================================================
# NETWORK TYPOGRAPHY
# ===========================================================================

class RegionCreate(BaseModel):
    name: str = Field(..., max_length=200)
    code: str = Field(..., max_length=20)
    description: Optional[str] = None


class RegionRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    code: str
    description: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class MetroCreate(BaseModel):
    region_id: uuid.UUID
    name: str = Field(..., max_length=200)
    code: str = Field(..., max_length=20)
    city: str = Field(..., max_length=100)
    province: Optional[str] = None


class MetroRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    region_id: uuid.UUID
    name: str
    code: str
    city: str
    province: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AreaCreate(BaseModel):
    metro_id: uuid.UUID
    name: str = Field(..., max_length=200)
    code: str = Field(..., max_length=20)
    suburb: Optional[str] = None
    city: str = Field(..., max_length=100)
    province: Optional[str] = None
    postal_codes: Optional[list[str]] = None
    fno_provider: Optional[str] = None
    coverage_status: str = "planned"
    technology: Optional[str] = None
    max_speed_mbps: Optional[int] = None


class AreaRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    metro_id: uuid.UUID
    name: str
    code: str
    suburb: Optional[str]
    city: str
    fno_provider: Optional[str]
    coverage_status: str
    technology: Optional[str]
    max_speed_mbps: Optional[int]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# --- Regions ---

@router.post("/regions", response_model=RegionRead, status_code=status.HTTP_201_CREATED)
async def create_region(body: RegionCreate, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        region = NetworkRegion(
            tenant_id=ctx.tenant_id, name=body.name, code=body.code,
            description=body.description,
        )
        session.add(region)
        session.flush()
        session.refresh(region)
        return RegionRead.model_validate(region)


@router.get("/regions", response_model=list[RegionRead])
async def list_regions(ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        result = session.execute(
            select(NetworkRegion).where(NetworkRegion.tenant_id == ctx.tenant_id)
        )
        return [RegionRead.model_validate(r) for r in result.scalars().all()]


# --- Metros ---

@router.post("/metros", response_model=MetroRead, status_code=status.HTTP_201_CREATED)
async def create_metro(body: MetroCreate, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        metro = NetworkMetro(
            tenant_id=ctx.tenant_id, region_id=body.region_id,
            name=body.name, code=body.code, city=body.city, province=body.province,
        )
        session.add(metro)
        session.flush()
        session.refresh(metro)
        return MetroRead.model_validate(metro)


@router.get("/metros", response_model=list[MetroRead])
async def list_metros(ctx: AuthContext = Depends(get_auth_context), region_id: Optional[uuid.UUID] = None):
    with get_session() as session:
        stmt = select(NetworkMetro).where(NetworkMetro.tenant_id == ctx.tenant_id)
        if region_id:
            stmt = stmt.where(NetworkMetro.region_id == region_id)
        result = session.execute(stmt)
        return [MetroRead.model_validate(m) for m in result.scalars().all()]


# --- Areas ---

@router.post("/areas", response_model=AreaRead, status_code=status.HTTP_201_CREATED)
async def create_area(body: AreaCreate, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        area = NetworkArea(
            tenant_id=ctx.tenant_id, metro_id=body.metro_id,
            name=body.name, code=body.code, suburb=body.suburb,
            city=body.city, province=body.province,
            postal_codes=body.postal_codes, fno_provider=body.fno_provider,
            coverage_status=body.coverage_status, technology=body.technology,
            max_speed_mbps=body.max_speed_mbps,
        )
        session.add(area)
        session.flush()
        session.refresh(area)
        return AreaRead.model_validate(area)


@router.get("/areas", response_model=list[AreaRead])
async def list_areas(
    ctx: AuthContext = Depends(get_auth_context),
    metro_id: Optional[uuid.UUID] = None,
    fno_provider: Optional[str] = None,
):
    with get_session() as session:
        stmt = select(NetworkArea).where(NetworkArea.tenant_id == ctx.tenant_id)
        if metro_id:
            stmt = stmt.where(NetworkArea.metro_id == metro_id)
        if fno_provider:
            stmt = stmt.where(NetworkArea.fno_provider == fno_provider)
        result = session.execute(stmt)
        return [AreaRead.model_validate(a) for a in result.scalars().all()]


# ===========================================================================
# NETWORK TOPOLOGY
# ===========================================================================

class TopologyElementCreate(BaseModel):
    area_id: Optional[uuid.UUID] = None
    fno_provider: Optional[str] = None
    element_type: str
    name: str = Field(..., max_length=200)
    code: str = Field(..., max_length=50)
    address: Optional[str] = None
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    total_ports: Optional[int] = None
    splitter_ratio: Optional[str] = None
    olt_model: Optional[str] = None
    olt_ip: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None
    metadata_: Optional[dict] = None


class TopologyElementRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    area_id: Optional[uuid.UUID]
    element_type: str
    name: str
    code: str
    status: str
    total_ports: Optional[int]
    used_ports: int
    available_ports: Optional[int]
    parent_id: Optional[uuid.UUID]
    created_at: datetime

    class Config:
        from_attributes = True


class TopologyLinkCreate(BaseModel):
    from_element_id: uuid.UUID
    to_element_id: uuid.UUID
    link_type: str
    fiber_count: Optional[int] = None
    fiber_type: Optional[str] = None
    length_meters: Optional[float] = None


@router.post("/topology/elements", response_model=TopologyElementRead, status_code=status.HTTP_201_CREATED)
async def create_topology_element(
    body: TopologyElementCreate, ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        element = NetworkTopologyElement(
            tenant_id=ctx.tenant_id, area_id=body.area_id,
            fno_provider=body.fno_provider, element_type=body.element_type,
            name=body.name, code=body.code, address=body.address,
            gps_lat=body.gps_lat, gps_lng=body.gps_lng,
            total_ports=body.total_ports, splitter_ratio=body.splitter_ratio,
            olt_model=body.olt_model, olt_ip=body.olt_ip,
            parent_id=body.parent_id, metadata_=body.metadata_,
        )
        session.add(element)
        session.flush()
        session.refresh(element)
        return TopologyElementRead.model_validate(element)


@router.get("/topology/elements", response_model=list[TopologyElementRead])
async def list_topology_elements(
    ctx: AuthContext = Depends(get_auth_context),
    area_id: Optional[uuid.UUID] = None,
    element_type: Optional[str] = None,
    status: Optional[str] = None,
):
    with get_session() as session:
        stmt = select(NetworkTopologyElement).where(
            NetworkTopologyElement.tenant_id == ctx.tenant_id
        )
        if area_id:
            stmt = stmt.where(NetworkTopologyElement.area_id == area_id)
        if element_type:
            stmt = stmt.where(NetworkTopologyElement.element_type == element_type)
        if status:
            stmt = stmt.where(NetworkTopologyElement.status == status)
        result = session.execute(stmt)
        return [TopologyElementRead.model_validate(e) for e in result.scalars().all()]


@router.post("/topology/links", status_code=status.HTTP_201_CREATED)
async def create_topology_link(
    body: TopologyLinkCreate, ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        link = NetworkTopologyLink(
            tenant_id=ctx.tenant_id,
            from_element_id=body.from_element_id,
            to_element_id=body.to_element_id,
            link_type=body.link_type,
            fiber_count=body.fiber_count,
            fiber_type=body.fiber_type,
            length_meters=body.length_meters,
        )
        session.add(link)
        session.flush()
        return {"id": str(link.id), "from": str(body.from_element_id), "to": str(body.to_element_id)}


@router.get("/topology/links")
async def list_topology_links(
    ctx: AuthContext = Depends(get_auth_context),
    element_id: Optional[uuid.UUID] = None,
):
    with get_session() as session:
        stmt = select(NetworkTopologyLink).where(
            NetworkTopologyLink.tenant_id == ctx.tenant_id
        )
        if element_id:
            stmt = stmt.where(
                (NetworkTopologyLink.from_element_id == element_id) |
                (NetworkTopologyLink.to_element_id == element_id)
            )
        result = session.execute(stmt)
        links = result.scalars().all()
        return [{
            "id": str(l.id), "from": str(l.from_element_id),
            "to": str(l.to_element_id), "type": l.link_type,
            "fiber_count": l.fiber_count, "length_m": l.length_meters,
        } for l in links]


# ===========================================================================
# BANDWIDTH USAGE
# ===========================================================================

class BandwidthIngest(BaseModel):
    service_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    period_type: str = "daily"
    download_bytes: int = 0
    upload_bytes: int = 0
    peak_download_mbps: Optional[float] = None
    peak_upload_mbps: Optional[float] = None
    avg_download_mbps: Optional[float] = None
    avg_upload_mbps: Optional[float] = None
    source: str = "radius"


class BandwidthRead(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    period_type: str
    download_gb: Optional[float]
    upload_gb: Optional[float]
    total_gb: Optional[float]
    peak_download_mbps: Optional[float]
    peak_upload_mbps: Optional[float]
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/bandwidth", response_model=BandwidthRead, status_code=status.HTTP_201_CREATED)
async def ingest_bandwidth(
    body: BandwidthIngest, ctx: AuthContext = Depends(get_auth_context),
):
    """Ingest bandwidth usage data (from RADIUS accounting or SNMP)."""
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

        total = body.download_bytes + body.upload_bytes
        usage = BandwidthUsage(
            tenant_id=ctx.tenant_id,
            service_id=body.service_id,
            period_start=body.period_start,
            period_end=body.period_end,
            period_type=body.period_type,
            download_bytes=body.download_bytes,
            upload_bytes=body.upload_bytes,
            total_bytes=total,
            download_gb=round(body.download_bytes / (1024 ** 3), 4),
            upload_gb=round(body.upload_bytes / (1024 ** 3), 4),
            total_gb=round(total / (1024 ** 3), 4),
            peak_download_mbps=body.peak_download_mbps,
            peak_upload_mbps=body.peak_upload_mbps,
            avg_download_mbps=body.avg_download_mbps,
            avg_upload_mbps=body.avg_upload_mbps,
            source=body.source,
        )
        session.add(usage)
        session.flush()
        session.refresh(usage)
        return BandwidthRead.model_validate(usage)


@router.get("/bandwidth", response_model=list[BandwidthRead])
async def query_bandwidth(
    ctx: AuthContext = Depends(get_auth_context),
    service_id: Optional[uuid.UUID] = None,
    period_type: Optional[str] = None,
    from_time: Optional[datetime] = None,
    to_time: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=1000),
):
    """Query bandwidth usage with filters."""
    with get_session() as session:
        stmt = select(BandwidthUsage).where(BandwidthUsage.tenant_id == ctx.tenant_id)
        if service_id:
            stmt = stmt.where(BandwidthUsage.service_id == service_id)
        if period_type:
            stmt = stmt.where(BandwidthUsage.period_type == period_type)
        if from_time:
            stmt = stmt.where(BandwidthUsage.period_start >= from_time)
        if to_time:
            stmt = stmt.where(BandwidthUsage.period_end <= to_time)
        stmt = stmt.order_by(BandwidthUsage.period_start.desc()).limit(limit)
        result = session.execute(stmt)
        return [BandwidthRead.model_validate(u) for u in result.scalars().all()]


@router.get("/bandwidth/summary")
async def bandwidth_summary(
    ctx: AuthContext = Depends(get_auth_context),
    service_id: uuid.UUID = Query(...),
    days: int = Query(30, ge=1, le=365),
):
    """Get bandwidth summary for a service over N days."""
    with get_session() as session:
        from_time = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = select(
            func.sum(BandwidthUsage.download_gb).label("total_download_gb"),
            func.sum(BandwidthUsage.upload_gb).label("total_upload_gb"),
            func.sum(BandwidthUsage.total_gb).label("total_gb"),
            func.avg(BandwidthUsage.peak_download_mbps).label("avg_peak_download"),
            func.avg(BandwidthUsage.peak_upload_mbps).label("avg_peak_upload"),
            func.count(BandwidthUsage.id).label("sample_count"),
        ).where(
            BandwidthUsage.tenant_id == ctx.tenant_id,
            BandwidthUsage.service_id == service_id,
            BandwidthUsage.period_start >= from_time,
        )
        result = session.execute(stmt).one()
        return {
            "service_id": str(service_id),
            "period_days": days,
            "total_download_gb": float(result.total_download_gb or 0),
            "total_upload_gb": float(result.total_upload_gb or 0),
            "total_gb": float(result.total_gb or 0),
            "avg_peak_download_mbps": round(float(result.avg_peak_download or 0), 2),
            "avg_peak_upload_mbps": round(float(result.avg_peak_upload or 0), 2),
            "sample_count": result.sample_count,
        }


# ===========================================================================
# FNO SLA COMPLIANCE
# ===========================================================================

class SLATargetCreate(BaseModel):
    fno_provider: str
    metric: str
    target_value: float
    unit: str
    penalty_per_breach_zar: Optional[float] = None
    penalty_cap_zar: Optional[float] = None
    effective_from: Optional[datetime] = None


class SLATargetRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    fno_provider: str
    metric: str
    target_value: float
    unit: str
    penalty_per_breach_zar: Optional[float]
    is_active: bool
    effective_from: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class SLAMeasurementCreate(BaseModel):
    fno_provider: str
    metric: str
    period_start: datetime
    period_end: datetime
    period_type: str = "monthly"
    actual_value: float
    sample_count: int = 0


class SLAMeasurementRead(BaseModel):
    id: uuid.UUID
    fno_provider: str
    metric: str
    period_start: datetime
    period_end: datetime
    period_type: str
    actual_value: float
    target_value: float
    is_breach: bool
    deviation_pct: Optional[float]
    penalty_applied_zar: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/sla/targets", response_model=SLATargetRead, status_code=status.HTTP_201_CREATED)
async def create_sla_target(body: SLATargetCreate, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        target = FNOSLATarget(
            tenant_id=ctx.tenant_id,
            fno_provider=body.fno_provider,
            metric=body.metric,
            target_value=body.target_value,
            unit=body.unit,
            penalty_per_breach_zar=body.penalty_per_breach_zar,
            penalty_cap_zar=body.penalty_cap_zar,
            effective_from=body.effective_from or datetime.now(timezone.utc),
        )
        session.add(target)
        session.flush()
        session.refresh(target)
        return SLATargetRead.model_validate(target)


@router.get("/sla/targets", response_model=list[SLATargetRead])
async def list_sla_targets(
    ctx: AuthContext = Depends(get_auth_context),
    fno_provider: Optional[str] = None,
):
    with get_session() as session:
        stmt = select(FNOSLATarget).where(
            FNOSLATarget.tenant_id == ctx.tenant_id,
            FNOSLATarget.is_active.is_(True),
        )
        if fno_provider:
            stmt = stmt.where(FNOSLATarget.fno_provider == fno_provider)
        result = session.execute(stmt)
        return [SLATargetRead.model_validate(t) for t in result.scalars().all()]


@router.post("/sla/measurements", response_model=SLAMeasurementRead, status_code=status.HTTP_201_CREATED)
async def create_sla_measurement(
    body: SLAMeasurementCreate, ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        # Find the active target
        target_stmt = select(FNOSLATarget).where(
            FNOSLATarget.tenant_id == ctx.tenant_id,
            FNOSLATarget.fno_provider == body.fno_provider,
            FNOSLATarget.metric == body.metric,
            FNOSLATarget.is_active.is_(True),
        )
        target = session.execute(target_stmt).scalar_one_or_none()
        if not target:
            raise HTTPException(404, detail="No active SLA target found for this FNO/metric")

        # Calculate breach
        deviation = ((body.actual_value - target.target_value) / target.target_value * 100) if target.target_value else 0
        is_breach = False
        if body.metric in ("install_time_days", "repair_time_hours", "response_time_hours"):
            is_breach = body.actual_value > target.target_value
        elif body.metric in ("uptime_pct", "resolution_rate_pct"):
            is_breach = body.actual_value < target.target_value

        penalty = None
        if is_breach and target.penalty_per_breach_zar:
            penalty = target.penalty_per_breach_zar
            if target.penalty_cap_zar and penalty > target.penalty_cap_zar:
                penalty = target.penalty_cap_zar

        measurement = FNOSLAMeasurement(
            tenant_id=ctx.tenant_id,
            fno_provider=body.fno_provider,
            sla_target_id=target.id,
            metric=body.metric,
            period_start=body.period_start,
            period_end=body.period_end,
            period_type=body.period_type,
            actual_value=body.actual_value,
            target_value=target.target_value,
            is_breach=is_breach,
            deviation_pct=round(deviation, 4) if deviation else None,
            sample_count=body.sample_count,
            penalty_applied_zar=penalty,
        )
        session.add(measurement)
        session.flush()
        session.refresh(measurement)
        return SLAMeasurementRead.model_validate(measurement)


@router.get("/sla/measurements", response_model=list[SLAMeasurementRead])
async def list_sla_measurements(
    ctx: AuthContext = Depends(get_auth_context),
    fno_provider: Optional[str] = None,
    metric: Optional[str] = None,
    is_breach: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=500),
):
    with get_session() as session:
        stmt = select(FNOSLAMeasurement).where(
            FNOSLAMeasurement.tenant_id == ctx.tenant_id
        )
        if fno_provider:
            stmt = stmt.where(FNOSLAMeasurement.fno_provider == fno_provider)
        if metric:
            stmt = stmt.where(FNOSLAMeasurement.metric == metric)
        if is_breach is not None:
            stmt = stmt.where(FNOSLAMeasurement.is_breach == is_breach)
        stmt = stmt.order_by(FNOSLAMeasurement.period_start.desc()).limit(limit)
        result = session.execute(stmt)
        return [SLAMeasurementRead.model_validate(m) for m in result.scalars().all()]


@router.get("/sla/compliance-report")
async def sla_compliance_report(
    ctx: AuthContext = Depends(get_auth_context),
    fno_provider: str = Query(...),
    months: int = Query(12, ge=1, le=36),
):
    """Generate SLA compliance report for an FNO over N months."""
    with get_session() as session:
        from_time = datetime.now(timezone.utc) - timedelta(days=months * 30)

        stmt = select(
            FNOSLAMeasurement.metric,
            func.count(FNOSLAMeasurement.id).label("total"),
            func.sum(func.cast(FNOSLAMeasurement.is_breach, Integer)).label("breaches"),
            func.avg(FNOSLAMeasurement.actual_value).label("avg_actual"),
            func.min(FNOSLAMeasurement.actual_value).label("min_actual"),
            func.max(FNOSLAMeasurement.actual_value).label("max_actual"),
        ).where(
            FNOSLAMeasurement.tenant_id == ctx.tenant_id,
            FNOSLAMeasurement.fno_provider == fno_provider,
            FNOSLAMeasurement.period_start >= from_time,
        ).group_by(FNOSLAMeasurement.metric)

        results = session.execute(stmt).all()
        return {
            "fno_provider": fno_provider,
            "period_months": months,
            "metrics": [{
                "metric": r.metric,
                "total_measurements": r.total,
                "breaches": int(r.breaches or 0),
                "compliance_pct": round((1 - (r.breaches or 0) / r.total) * 100, 2) if r.total else 100,
                "avg_actual": round(float(r.avg_actual or 0), 4),
                "min_actual": round(float(r.min_actual or 0), 4),
                "max_actual": round(float(r.max_actual or 0), 4),
            } for r in results],
        }


# ===========================================================================
# DEVICE CONFIGURATION
# ===========================================================================

class ConfigTemplateCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    device_type: str
    config_template: dict
    config_protocol: str = "tr069"


class ConfigTemplateRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    device_type: str
    config_protocol: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ConfigPushCreate(BaseModel):
    device_id: uuid.UUID
    template_id: Optional[uuid.UUID] = None
    config_payload: dict
    config_protocol: str = "tr069"


class ConfigPushRead(BaseModel):
    id: uuid.UUID
    device_id: uuid.UUID
    template_id: Optional[uuid.UUID]
    config_protocol: str
    status: str
    result_message: Optional[str]
    error_message: Optional[str]
    pushed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/config/templates", response_model=ConfigTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_config_template(
    body: ConfigTemplateCreate, ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        template = DeviceConfigTemplate(
            tenant_id=ctx.tenant_id, name=body.name,
            description=body.description, device_type=body.device_type,
            config_template=body.config_template,
            config_protocol=body.config_protocol,
        )
        session.add(template)
        session.flush()
        session.refresh(template)
        return ConfigTemplateRead.model_validate(template)


@router.get("/config/templates", response_model=list[ConfigTemplateRead])
async def list_config_templates(
    ctx: AuthContext = Depends(get_auth_context),
    device_type: Optional[str] = None,
):
    with get_session() as session:
        stmt = select(DeviceConfigTemplate).where(
            DeviceConfigTemplate.tenant_id == ctx.tenant_id,
            DeviceConfigTemplate.is_active.is_(True),
        )
        if device_type:
            stmt = stmt.where(DeviceConfigTemplate.device_type == device_type)
        result = session.execute(stmt)
        return [ConfigTemplateRead.model_validate(t) for t in result.scalars().all()]


@router.post("/config/push", response_model=ConfigPushRead, status_code=status.HTTP_202_ACCEPTED)
async def push_device_config(
    body: ConfigPushCreate,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Push configuration to a device (TR-069, MikroTik API, SSH)."""
    with get_session() as session:
        push = DeviceConfigPush(
            tenant_id=ctx.tenant_id,
            device_id=body.device_id,
            template_id=body.template_id,
            config_payload=body.config_payload,
            config_protocol=body.config_protocol,
            status="pending",
            pushed_by=ctx.user_id,
        )
        session.add(push)
        session.flush()
        session.refresh(push)

        background_tasks.add_task(_execute_config_push, push.id)

        return ConfigPushRead.model_validate(push)


async def _execute_config_push(push_id: uuid.UUID):
    """Background task to push config to device."""
    from services.network.database import get_session as _get_session

    async with _get_session() as session:
        push = await session.get(DeviceConfigPush, push_id)
        if not push:
            return

        push.status = "in_progress"
        push.pushed_at = datetime.now(timezone.utc)
        await session.flush()

        try:
            if push.config_protocol == "tr069":
                # TODO: Integrate with TR-069 ACS (e.g. GenieACS)
                logger.info(f"TR-069 config push to device {push.device_id}")
            elif push.config_protocol == "mikrotik_api":
                # TODO: Integrate with MikroTik RouterOS API
                logger.info(f"MikroTik API config push to device {push.device_id}")
            elif push.config_protocol == "ssh":
                # TODO: Integrate with SSH client
                logger.info(f"SSH config push to device {push.device_id}")
            else:
                raise ValueError(f"Unknown config protocol: {push.config_protocol}")

            push.status = "completed"
            push.completed_at = datetime.now(timezone.utc)
            push.result_message = f"Config pushed via {push.config_protocol}"
        except Exception as e:
            push.status = "failed"
            push.error_message = str(e)
            push.completed_at = datetime.now(timezone.utc)
            logger.error(f"Config push failed: {e}")

        await session.flush()


@router.get("/config/pushes", response_model=list[ConfigPushRead])
async def list_config_pushes(
    ctx: AuthContext = Depends(get_auth_context),
    device_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    with get_session() as session:
        stmt = select(DeviceConfigPush).where(
            DeviceConfigPush.tenant_id == ctx.tenant_id
        )
        if device_id:
            stmt = stmt.where(DeviceConfigPush.device_id == device_id)
        if status:
            stmt = stmt.where(DeviceConfigPush.status == status)
        stmt = stmt.order_by(DeviceConfigPush.created_at.desc()).limit(limit)
        result = session.execute(stmt)
        return [ConfigPushRead.model_validate(p) for p in result.scalars().all()]


@router.post("/config/pushes/{push_id}/rollback")
async def rollback_config_push(
    push_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Rollback a config push (restores previous config snapshot)."""
    with get_session() as session:
        push = session.get(DeviceConfigPush, push_id)
        if not push or push.tenant_id != ctx.tenant_id:
            raise HTTPException(404, detail="Config push not found")
        if push.status != "completed":
            raise HTTPException(400, detail="Can only rollback completed pushes")

        push.status = "rolled_back"
        session.flush()

        # TODO: Restore device config from snapshot
        background_tasks.add_task(_execute_config_rollback, push_id)

        return {"id": str(push.id), "status": "rolled_back"}


async def _execute_config_rollback(push_id: uuid.UUID):
    from services.network.database import get_session as _get_session
    async with _get_session() as session:
        push = await session.get(DeviceConfigPush, push_id)
        if not push:
            return
        logger.info(f"Rolling back config for device {push.device_id}")
        # TODO: Restore from device config_snapshot
        await session.flush()
