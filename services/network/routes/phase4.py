"""Phase 4 network routes: property linkage, traffic classification, ONT provisioning, Wi-Fi config, session recording, lead generation."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.network.database import get_session
from services.network.models import (
    FNOSessionRecording,
    NetworkLead,
    ONTProvisioningProfile,
    PropertyNetworkLink,
    ServiceTrafficUsage,
    TrafficClassification,
    WiFiConfigProfile,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/network", tags=["Network Phase 4"])


# ===========================================================================
# PROPERTY-TO-NETWORK LINKAGE
# ===========================================================================

class PropertyLinkCreate(BaseModel):
    property_id: uuid.UUID
    region_id: Optional[uuid.UUID] = None
    metro_id: Optional[uuid.UUID] = None
    area_id: Optional[uuid.UUID] = None
    service_id: Optional[uuid.UUID] = None
    coverage_status: str = "unknown"
    fno_provider: Optional[str] = None
    max_available_speed_mbps: Optional[int] = None


class PropertyLinkRead(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    region_id: Optional[uuid.UUID]
    metro_id: Optional[uuid.UUID]
    area_id: Optional[uuid.UUID]
    service_id: Optional[uuid.UUID]
    coverage_status: str
    fno_provider: Optional[str]
    max_available_speed_mbps: Optional[int]
    is_lead: bool
    lead_score: int

    class Config:
        from_attributes = True


@router.post("/property-links", response_model=PropertyLinkRead, status_code=status.HTTP_201_CREATED)
async def create_property_link(
    body: PropertyLinkCreate, ctx: AuthContext = Depends(get_auth_context),
):
    """Link a CRM property to the network typography hierarchy."""
    with get_session() as session:
        link = PropertyNetworkLink(
            tenant_id=ctx.tenant_id,
            property_id=body.property_id,
            region_id=body.region_id,
            metro_id=body.metro_id,
            area_id=body.area_id,
            service_id=body.service_id,
            coverage_status=body.coverage_status,
            fno_provider=body.fno_provider,
            max_available_speed_mbps=body.max_available_speed_mbps,
        )
        session.add(link)
        session.flush()
        session.refresh(link)
        return PropertyLinkRead.model_validate(link)


@router.get("/property-links", response_model=list[PropertyLinkRead])
async def list_property_links(
    ctx: AuthContext = Depends(get_auth_context),
    property_id: Optional[uuid.UUID] = None,
    area_id: Optional[uuid.UUID] = None,
    coverage_status: Optional[str] = None,
    is_lead: Optional[bool] = None,
):
    with get_session() as session:
        stmt = select(PropertyNetworkLink).where(
            PropertyNetworkLink.tenant_id == ctx.tenant_id
        )
        if property_id:
            stmt = stmt.where(PropertyNetworkLink.property_id == property_id)
        if area_id:
            stmt = stmt.where(PropertyNetworkLink.area_id == area_id)
        if coverage_status:
            stmt = stmt.where(PropertyNetworkLink.coverage_status == coverage_status)
        if is_lead is not None:
            stmt = stmt.where(PropertyNetworkLink.is_lead == is_lead)
        result = session.execute(stmt)
        return [PropertyLinkRead.model_validate(l) for l in result.scalars().all()]


@router.post("/property-links/auto-match")
async def auto_match_properties(
    ctx: AuthContext = Depends(get_auth_context),
    background_tasks: BackgroundTasks = None,
):
    """Auto-match CRM properties to network typography by postal code / GPS.

    In production this runs as a batch job. For now, triggers background matching.
    """
    # TODO: Match properties to network_areas by postal_code overlap
    # TODO: Match properties to nearest topology element by GPS
    # TODO: Update coverage_status based on FNO coverage data
    return {"status": "queued", "message": "Auto-match started"}


# ===========================================================================
# TRAFFIC CLASSIFICATION (DPI)
# ===========================================================================

class TrafficClassCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    traffic_class: str
    protocols: Optional[list[str]] = None
    port_ranges: Optional[list[str]] = None
    domains: Optional[list[str]] = None
    ip_ranges: Optional[list[str]] = None
    dpi_signatures: Optional[list[str]] = None
    priority: int = 5
    bandwidth_limit_mbps: Optional[float] = None


class TrafficClassRead(BaseModel):
    id: uuid.UUID
    name: str
    traffic_class: str
    priority: int
    bandwidth_limit_mbps: Optional[float]
    is_active: bool

    class Config:
        from_attributes = True


class TrafficUsageIngest(BaseModel):
    service_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    period_type: str = "daily"
    traffic_class: str
    download_bytes: int = 0
    upload_bytes: int = 0
    pct_of_total: Optional[float] = None


@router.post("/traffic/classifications", response_model=TrafficClassRead, status_code=status.HTTP_201_CREATED)
async def create_traffic_classification(
    body: TrafficClassCreate, ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        tc = TrafficClassification(
            tenant_id=ctx.tenant_id, name=body.name,
            description=body.description, traffic_class=body.traffic_class,
            protocols=body.protocols, port_ranges=body.port_ranges,
            domains=body.domains, ip_ranges=body.ip_ranges,
            dpi_signatures=body.dpi_signatures, priority=body.priority,
            bandwidth_limit_mbps=body.bandwidth_limit_mbps,
        )
        session.add(tc)
        session.flush()
        session.refresh(tc)
        return TrafficClassRead.model_validate(tc)


@router.get("/traffic/classifications", response_model=list[TrafficClassRead])
async def list_traffic_classifications(
    ctx: AuthContext = Depends(get_auth_context),
    traffic_class: Optional[str] = None,
):
    with get_session() as session:
        stmt = select(TrafficClassification).where(
            TrafficClassification.tenant_id == ctx.tenant_id,
            TrafficClassification.is_active.is_(True),
        )
        if traffic_class:
            stmt = stmt.where(TrafficClassification.traffic_class == traffic_class)
        stmt = stmt.order_by(TrafficClassification.priority)
        result = session.execute(stmt)
        return [TrafficClassRead.model_validate(t) for t in result.scalars().all()]


@router.post("/traffic/usage", status_code=status.HTTP_201_CREATED)
async def ingest_traffic_usage(
    body: TrafficUsageIngest, ctx: AuthContext = Depends(get_auth_context),
):
    """Ingest per-service traffic usage by classification."""
    with get_session() as session:
        total = body.download_bytes + body.upload_bytes
        usage = ServiceTrafficUsage(
            tenant_id=ctx.tenant_id,
            service_id=body.service_id,
            period_start=body.period_start,
            period_end=body.period_end,
            period_type=body.period_type,
            traffic_class=body.traffic_class,
            download_bytes=body.download_bytes,
            upload_bytes=body.upload_bytes,
            total_bytes=total,
            download_gb=round(body.download_bytes / (1024 ** 3), 4),
            upload_gb=round(body.upload_bytes / (1024 ** 3), 4),
            pct_of_total=body.pct_of_total,
        )
        session.add(usage)
        session.flush()
        return {"id": str(usage.id), "traffic_class": body.traffic_class}


@router.get("/traffic/usage")
async def query_traffic_usage(
    ctx: AuthContext = Depends(get_auth_context),
    service_id: Optional[uuid.UUID] = None,
    traffic_class: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
):
    with get_session() as session:
        stmt = select(ServiceTrafficUsage).where(
            ServiceTrafficUsage.tenant_id == ctx.tenant_id
        )
        if service_id:
            stmt = stmt.where(ServiceTrafficUsage.service_id == service_id)
        if traffic_class:
            stmt = stmt.where(ServiceTrafficUsage.traffic_class == traffic_class)
        stmt = stmt.order_by(ServiceTrafficUsage.period_start.desc()).limit(limit)
        result = session.execute(stmt)
        return [{
            "id": str(u.id), "service_id": str(u.service_id),
            "class": u.traffic_class, "download_gb": u.download_gb,
            "upload_gb": u.upload_gb, "pct": u.pct_of_total,
            "period": u.period_start.isoformat(),
        } for u in result.scalars().all()]


# ===========================================================================
# ONT PROVISIONING
# ===========================================================================

class ONTProvisionCreate(BaseModel):
    service_id: uuid.UUID
    gpon_serial_number: Optional[str] = None
    loid: Optional[str] = None
    loid_password: Optional[str] = None
    onu_id: Optional[int] = None
    internet_vlan_id: Optional[int] = None
    voice_vlan_id: Optional[int] = None
    iptv_vlan_id: Optional[int] = None
    management_vlan_id: Optional[int] = None
    service_profile_name: Optional[str] = None
    bandwidth_profile_name: Optional[str] = None
    olt_ip: Optional[str] = None
    olt_port: Optional[str] = None
    tr069_acs_url: Optional[str] = None


class ONTProvisionRead(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    gpon_serial_number: Optional[str]
    loid: Optional[str]
    internet_vlan_id: Optional[int]
    provisioning_status: str
    provisioned_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.post("/ont-provisioning", response_model=ONTProvisionRead, status_code=status.HTTP_201_CREATED)
async def create_ont_provisioning(
    body: ONTProvisionCreate, ctx: AuthContext = Depends(get_auth_context),
):
    """Create ONT provisioning profile for a service."""
    with get_session() as session:
        profile = ONTProvisioningProfile(
            tenant_id=ctx.tenant_id,
            service_id=body.service_id,
            gpon_serial_number=body.gpon_serial_number,
            loid=body.loid,
            loid_password=body.loid_password,
            onu_id=body.onu_id,
            internet_vlan_id=body.internet_vlan_id,
            voice_vlan_id=body.voice_vlan_id,
            iptv_vlan_id=body.iptv_vlan_id,
            management_vlan_id=body.management_vlan_id,
            service_profile_name=body.service_profile_name,
            bandwidth_profile_name=body.bandwidth_profile_name,
            olt_ip=body.olt_ip,
            olt_port=body.olt_port,
            tr069_acs_url=body.tr069_acs_url,
        )
        session.add(profile)
        session.flush()
        session.refresh(profile)
        return ONTProvisionRead.model_validate(profile)


@router.get("/ont-provisioning", response_model=list[ONTProvisionRead])
async def list_ont_provisioning(
    ctx: AuthContext = Depends(get_auth_context),
    service_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
):
    with get_session() as session:
        stmt = select(ONTProvisioningProfile).where(
            ONTProvisioningProfile.tenant_id == ctx.tenant_id
        )
        if service_id:
            stmt = stmt.where(ONTProvisioningProfile.service_id == service_id)
        if status:
            stmt = stmt.where(ONTProvisioningProfile.provisioning_status == status)
        result = session.execute(stmt)
        return [ONTProvisionRead.model_validate(p) for p in result.scalars().all()]


@router.post("/ont-provisioning/{profile_id}/provision")
async def provision_ont(
    profile_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Trigger ONT provisioning (calls OLT API / FNO adapter)."""
    with get_session() as session:
        profile = session.get(ONTProvisioningProfile, profile_id)
        if not profile or profile.tenant_id != ctx.tenant_id:
            raise HTTPException(404, detail="Profile not found")
        profile.provisioning_status = "provisioning"
        session.flush()

        background_tasks.add_task(_execute_ont_provisioning, profile_id)
        return {"id": str(profile.id), "status": "provisioning"}


async def _execute_ont_provisioning(profile_id: uuid.UUID):
    """Background task: provision ONT on OLT."""
    from services.network.database import get_session as _get_session
    async with _get_session() as session:
        profile = await session.get(ONTProvisioningProfile, profile_id)
        if not profile:
            return
        try:
            # TODO: Call OLT API / FNO adapter to provision ONT
            # adapter = FNOFactory.get_adapter(fno_provider, config)
            # await adapter.provision_ont(profile)
            profile.provisioning_status = "active"
            profile.provisioned_at = datetime.now(timezone.utc)
        except Exception as e:
            profile.provisioning_status = "failed"
            logger.error(f"ONT provisioning failed: {e}")
        await session.flush()


# ===========================================================================
# WI-FI CONFIGURATION
# ===========================================================================

class WiFiConfigCreate(BaseModel):
    service_id: uuid.UUID
    ssid_24ghz: Optional[str] = None
    ssid_5ghz: Optional[str] = None
    ssid_6ghz: Optional[str] = None
    security_mode: str = "wpa2_wpa3"
    passphrase: Optional[str] = None
    band_steering_enabled: bool = True
    preferred_band: str = "5ghz"
    channel_24ghz: Optional[int] = None
    channel_5ghz: Optional[int] = None
    channel_width_mhz: Optional[int] = None
    max_clients: int = 32
    hidden_ssid: bool = False
    guest_ssid_enabled: bool = False
    guest_ssid_name: Optional[str] = None
    guest_ssid_passphrase: Optional[str] = None


class WiFiConfigRead(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    ssid_24ghz: Optional[str]
    ssid_5ghz: Optional[str]
    security_mode: str
    push_status: str
    last_pushed_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.post("/wifi-config", response_model=WiFiConfigRead, status_code=status.HTTP_201_CREATED)
async def create_wifi_config(
    body: WiFiConfigCreate, ctx: AuthContext = Depends(get_auth_context),
):
    """Create Wi-Fi configuration profile for a service."""
    with get_session() as session:
        wifi = WiFiConfigProfile(
            tenant_id=ctx.tenant_id,
            service_id=body.service_id,
            ssid_24ghz=body.ssid_24ghz,
            ssid_5ghz=body.ssid_5ghz,
            ssid_6ghz=body.ssid_6ghz,
            security_mode=body.security_mode,
            passphrase=body.passphrase,
            band_steering_enabled=body.band_steering_enabled,
            preferred_band=body.preferred_band,
            channel_24ghz=body.channel_24ghz,
            channel_5ghz=body.channel_5ghz,
            channel_width_mhz=body.channel_width_mhz,
            max_clients=body.max_clients,
            hidden_ssid=body.hidden_ssid,
            guest_ssid_enabled=body.guest_ssid_enabled,
            guest_ssid_name=body.guest_ssid_name,
            guest_ssid_passphrase=body.guest_ssid_passphrase,
        )
        session.add(wifi)
        session.flush()
        session.refresh(wifi)
        return WiFiConfigRead.model_validate(wifi)


@router.post("/wifi-config/{config_id}/push")
async def push_wifi_config(
    config_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Push Wi-Fi configuration to device via TR-069."""
    with get_session() as session:
        config = session.get(WiFiConfigProfile, config_id)
        if not config or config.tenant_id != ctx.tenant_id:
            raise HTTPException(404, detail="Wi-Fi config not found")
        config.push_status = "pushed"
        config.last_pushed_at = datetime.now(timezone.utc)
        session.flush()

        background_tasks.add_task(_push_wifi_to_device, config_id)
        return {"id": str(config.id), "push_status": "pushed"}


async def _push_wifi_to_device(config_id: uuid.UUID):
    """Background task: push Wi-Fi config via TR-069."""
    from services.network.database import get_session as _get_session
    async with _get_session() as session:
        config = await session.get(WiFiConfigProfile, config_id)
        if not config:
            return
        try:
            # TODO: TR-069 SetParameterValues to push Wi-Fi config
            # ACS client → device.WLANConfiguration.{i}.SSID = config.ssid_24ghz
            logger.info(f"Pushing Wi-Fi config to service {config.service_id}")
        except Exception as e:
            config.push_status = "failed"
            logger.error(f"Wi-Fi push failed: {e}")
        await session.flush()


# ===========================================================================
# FNO SESSION RECORDING
# ===========================================================================

class RecordingCreate(BaseModel):
    session_id: uuid.UUID
    job_id: Optional[uuid.UUID] = None
    recording_path: str
    duration_seconds: Optional[int] = None
    resolution: str = "1920x1080"
    fps: int = 15


class RecordingRead(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    job_id: Optional[uuid.UUID]
    recording_path: str
    duration_seconds: Optional[int]
    status: str
    template_generated: bool
    confidence_score: Optional[float]

    class Config:
        from_attributes = True


@router.post("/session-recordings", response_model=RecordingRead, status_code=status.HTTP_201_CREATED)
async def create_session_recording(
    body: RecordingCreate, ctx: AuthContext = Depends(get_auth_context),
):
    """Create a session recording record for FNO portal automation."""
    with get_session() as session:
        recording = FNOSessionRecording(
            tenant_id=ctx.tenant_id,
            session_id=body.session_id,
            job_id=body.job_id,
            recording_path=body.recording_path,
            duration_seconds=body.duration_seconds,
            resolution=body.resolution,
            fps=body.fps,
            status="idle",
        )
        session.add(recording)
        session.flush()
        session.refresh(recording)
        return RecordingRead.model_validate(recording)


@router.get("/session-recordings", response_model=list[RecordingRead])
async def list_session_recordings(
    ctx: AuthContext = Depends(get_auth_context),
    session_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    with get_session() as session:
        stmt = select(FNOSessionRecording).where(
            FNOSessionRecording.tenant_id == ctx.tenant_id
        )
        if session_id:
            stmt = stmt.where(FNOSessionRecording.session_id == session_id)
        if status:
            stmt = stmt.where(FNOSessionRecording.status == status)
        result = session.execute(stmt.order_by(FNOSessionRecording.created_at.desc()).limit(limit))
        return [RecordingRead.model_validate(r) for r in result.scalars().all()]


@router.post("/session-recordings/{recording_id}/analyze")
async def analyze_recording(
    recording_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Analyze a session recording to extract automation steps and generate template."""
    with get_session() as session:
        recording = session.get(FNOSessionRecording, recording_id)
        if not recording or recording.tenant_id != ctx.tenant_id:
            raise HTTPException(404, detail="Recording not found")
        recording.status = "processing"
        session.flush()

        background_tasks.add_task(_analyze_session_recording, recording_id)
        return {"id": str(recording.id), "status": "processing"}


async def _analyze_session_recording(recording_id: uuid.UUID):
    """Background task: analyze recording and extract automation steps."""
    from services.network.database import get_session as _get_session
    async with _get_session() as session:
        recording = await session.get(FNOSessionRecording, recording_id)
        if not recording:
            return
        try:
            # TODO: Video analysis — extract mouse clicks, page transitions, form fills
            # This would use OpenCV + OCR + ML model in production
            recording.extracted_steps = []
            recording.page_transitions = []
            recording.error_events = []
            recording.status = "analyzed"
            recording.confidence_score = 0.0
        except Exception as e:
            recording.status = "failed"
            logger.error(f"Recording analysis failed: {e}")
        await session.flush()


# ===========================================================================
# NETWORK LEAD GENERATION
# ===========================================================================

class LeadCreate(BaseModel):
    lead_source: str
    source_detail: Optional[str] = None
    property_network_link_id: Optional[uuid.UUID] = None
    address_line1: Optional[str] = None
    suburb: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    target_fno: Optional[str] = None
    current_fno: Optional[str] = None
    interest_reason: Optional[str] = None
    score: int = 0


class LeadRead(BaseModel):
    id: uuid.UUID
    lead_source: str
    city: Optional[str]
    suburb: Optional[str]
    status: str
    score: int
    target_fno: Optional[str]
    assigned_to: Optional[uuid.UUID]
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/leads", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
async def create_network_lead(
    body: LeadCreate, ctx: AuthContext = Depends(get_auth_context),
):
    """Create a lead from network data (coverage gap, new area, outage, etc.)."""
    with get_session() as session:
        lead = NetworkLead(
            tenant_id=ctx.tenant_id,
            lead_source=body.lead_source,
            source_detail=body.source_detail,
            property_network_link_id=body.property_network_link_id,
            address_line1=body.address_line1,
            suburb=body.suburb,
            city=body.city,
            province=body.province,
            postal_code=body.postal_code,
            gps_lat=body.gps_lat,
            gps_lng=body.gps_lng,
            target_fno=body.target_fno,
            current_fno=body.current_fno,
            interest_reason=body.interest_reason,
            score=body.score,
        )
        session.add(lead)
        session.flush()
        session.refresh(lead)
        return LeadRead.model_validate(lead)


@router.get("/leads", response_model=list[LeadRead])
async def list_network_leads(
    ctx: AuthContext = Depends(get_auth_context),
    status: Optional[str] = None,
    lead_source: Optional[str] = None,
    city: Optional[str] = None,
    min_score: Optional[int] = None,
    assigned_to: Optional[uuid.UUID] = None,
    limit: int = Query(50, ge=1, le=500),
):
    with get_session() as session:
        stmt = select(NetworkLead).where(NetworkLead.tenant_id == ctx.tenant_id)
        if status:
            stmt = stmt.where(NetworkLead.status == status)
        if lead_source:
            stmt = stmt.where(NetworkLead.lead_source == lead_source)
        if city:
            stmt = stmt.where(NetworkLead.city.ilike(f"%{city}%"))
        if min_score:
            stmt = stmt.where(NetworkLead.score >= min_score)
        if assigned_to:
            stmt = stmt.where(NetworkLead.assigned_to == assigned_to)
        stmt = stmt.order_by(NetworkLead.score.desc()).limit(limit)
        result = session.execute(stmt)
        return [LeadRead.model_validate(l) for l in result.scalars().all()]


@router.post("/leads/generate-from-coverage-gaps")
async def generate_leads_from_coverage_gaps(
    ctx: AuthContext = Depends(get_auth_context),
    background_tasks: BackgroundTasks = None,
):
    """Auto-generate leads from FNO coverage gap analysis.

    Scans network_areas where coverage_status != 'available' but
    there are nearby active services, indicating potential churn risk.
    """
    with get_session() as session:
        # Find properties in areas with coverage gaps
        gap_areas = session.execute(
            select(PropertyNetworkLink).where(
                PropertyNetworkLink.tenant_id == ctx.tenant_id,
                PropertyNetworkLink.coverage_status.in_(("not_covered", "coming_soon")),
                PropertyNetworkLink.is_lead.is_(False),
            )
        ).scalars().all()

        leads_created = 0
        for link in gap_areas:
            lead = NetworkLead(
                tenant_id=ctx.tenant_id,
                lead_source="coverage_gap",
                property_network_link_id=link.id,
                city=link.area_id,  # Will be resolved to actual city name
                interest_reason=f"Coverage gap detected",
                score=50,
            )
            session.add(lead)
            link.is_lead = True
            leads_created += 1

        session.flush()
        return {"leads_created": leads_created}


@router.post("/leads/{lead_id}/convert")
async def convert_lead(
    lead_id: uuid.UUID,
    customer_id: uuid.UUID,
    service_id: Optional[uuid.UUID] = None,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Convert a network lead to a customer/service."""
    with get_session() as session:
        lead = session.get(NetworkLead, lead_id)
        if not lead or lead.tenant_id != ctx.tenant_id:
            raise HTTPException(404, detail="Lead not found")
        lead.status = "converted"
        lead.converted_to_customer_id = customer_id
        lead.converted_to_service_id = service_id
        lead.converted_at = datetime.now(timezone.utc)
        session.flush()
        return {"id": str(lead.id), "status": "converted"}
