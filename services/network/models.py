"""SQLAlchemy models for the Network service."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

SERVICE_STATUS = SAEnum(
    "pending", "provisioning", "active", "suspended", "terminated",
    name="service_status", create_type=True,
)

TECHNOLOGY_TYPE = SAEnum(
    "gpon", "xgs_pon", "point_to_point", "wireless", "dsl", "lte",
    name="technology_type", create_type=True,
)

FNO_PROVIDER = SAEnum(
    "vumatel", "openserve", "metrofibre", "frogfoot", "octotel", "other",
    name="fno_provider", create_type=True,
)

ORDER_STATUS = SAEnum(
    "submitted", "accepted", "scheduled", "in_progress", "completed",
    "failed", "cancelled",
    name="order_status", create_type=True,
)

ORDER_TYPE = SAEnum(
    "new_installation", "migration", "speed_change", "cancellation",
    name="order_type", create_type=True,
)

RADIUS_ACCOUNT_STATUS = SAEnum(
    "active", "suspended", "disabled",
    name="radius_account_status", create_type=True,
)

AUTOMATION_JOB_STATUS = SAEnum(
    "queued", "processing", "completed", "failed",
    name="automation_job_status", create_type=True,
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class NetworkService(Base):
    """A fibre/network service instance linked to a CRM customer."""
    __tablename__ = "network_services"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Service details
    service_reference: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(SERVICE_STATUS, default="pending", nullable=False)
    technology: Mapped[str] = mapped_column(TECHNOLOGY_TYPE, nullable=False)
    fno_provider: Mapped[str] = mapped_column(FNO_PROVIDER, nullable=False)

    # Speed profile
    download_speed_mbps: Mapped[int] = mapped_column(Integer, nullable=False)
    upload_speed_mbps: Mapped[int] = mapped_column(Integer, nullable=False)
    speed_profile_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Installation address
    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    province: Mapped[str] = mapped_column(String(50), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    gps_latitude: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    gps_longitude: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # FNO cross-reference
    fno_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fno_account_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ont_serial: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_products.id", ondelete="SET NULL"), nullable=True
    )

    # Timestamps
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    terminated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    # Relationships
    radius_account: Mapped[Optional["RadiusAccount"]] = relationship(
        back_populates="service", uselist=False, lazy="joined",
    )
    fno_orders: Mapped[list["FNOOrder"]] = relationship(
        back_populates="service", order_by="FNOOrder.created_at.desc()", lazy="selectin",
    )

    __table_args__ = (
        Index("ix_network_services_tenant", "tenant_id"),
        Index("ix_network_services_customer", "tenant_id", "customer_id"),
        Index("ix_network_services_status", "tenant_id", "status"),
        Index("ix_network_services_product", "product_id"),
    )


class RadiusAccount(Base):
    """RADIUS credentials and profile mapping for a service."""
    __tablename__ = "radius_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_services.id"), nullable=False, unique=True,
    )

    username: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    framing_protocol: Mapped[str] = mapped_column(String(20), default="PPPoE", nullable=False)
    status: Mapped[str] = mapped_column(RADIUS_ACCOUNT_STATUS, default="active", nullable=False)

    # Speed profile (maps to radgroupreply)
    profile_name: Mapped[str] = mapped_column(String(100), nullable=False)
    mikrotik_rate_limit: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # NAS details
    nas_ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    nas_port_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    service: Mapped["NetworkService"] = relationship(back_populates="radius_account")

    __table_args__ = (
        Index("ix_radius_accounts_tenant", "tenant_id"),
        Index("ix_radius_accounts_username", "tenant_id", "username", unique=True),
    )


class FNOOrder(Base):
    """Tracks orders placed with Fibre Network Operators."""
    __tablename__ = "fno_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_services.id"), nullable=False,
    )

    fno_provider: Mapped[str] = mapped_column(FNO_PROVIDER, nullable=False)
    order_type: Mapped[str] = mapped_column(ORDER_TYPE, nullable=False)
    status: Mapped[str] = mapped_column(ORDER_STATUS, default="submitted", nullable=False)

    # FNO reference
    fno_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    scheduled_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Request/response payloads for auditing
    request_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    response_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    service: Mapped["NetworkService"] = relationship(back_populates="fno_orders")

    __table_args__ = (
        Index("ix_fno_orders_tenant", "tenant_id"),
        Index("ix_fno_orders_service", "tenant_id", "service_id"),
        Index("ix_fno_orders_status", "tenant_id", "status"),
    )


class CoverageArea(Base):
    """Pre-cached FNO coverage zones for quick lookup."""
    __tablename__ = "coverage_areas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    fno_provider: Mapped[str] = mapped_column(FNO_PROVIDER, nullable=False)
    area_name: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    province: Mapped[str] = mapped_column(String(50), nullable=False)
    postal_codes: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    technology: Mapped[str] = mapped_column(TECHNOLOGY_TYPE, nullable=False)
    max_download_mbps: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_coverage_areas_tenant", "tenant_id"),
        Index("ix_coverage_areas_lookup", "tenant_id", "fno_provider", "province"),
    )


class AutomationJob(Base):
    """Logs FNO automation jobs (API or browser-based)."""
    __tablename__ = "automation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    fno_provider: Mapped[str] = mapped_column(FNO_PROVIDER, nullable=False)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(20), nullable=False)  # api / browser
    status: Mapped[str] = mapped_column(AUTOMATION_JOB_STATUS, default="queued", nullable=False)

    request_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    result_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_automation_jobs_tenant", "tenant_id"),
        Index("ix_automation_jobs_status", "tenant_id", "status"),
    )


# ---------------------------------------------------------------------------
# Network Performance Monitoring
# ---------------------------------------------------------------------------

METRIC_TYPE = SAEnum(
    "latency_ms", "jitter_ms", "packet_loss_pct", "download_mbps",
    "upload_mbps", "signal_dbm", "snr_db", "ont_cpu_pct", "ont_mem_pct",
    "router_cpu_pct", "router_mem_pct", "wifi_clients", "uptime_seconds",
    name="metric_type", create_type=True,
)

ALERT_SEVERITY = SAEnum(
    "info", "warning", "critical", "emergency",
    name="alert_severity", create_type=True,
)

NOTIFICATION_CHANNEL = SAEnum(
    "email", "sms", "push", "webhook", "in_app",
    name="notification_channel", create_type=True,
)

NOTIFICATION_STATUS = SAEnum(
    "pending", "sent", "failed", "read", "dismissed",
    name="notification_status", create_type=True,
)


class NetworkPerformanceMetric(Base):
    """Time-series performance metrics collected from network devices and probes."""

    __tablename__ = "network_performance_metrics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_services.id", ondelete="CASCADE"), nullable=False,
    )
    device_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_devices.id", ondelete="SET NULL"), nullable=True,
    )

    metric_type: Mapped[str] = mapped_column(METRIC_TYPE, nullable=False)
    metric_value: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Source of the metric
    source: Mapped[str] = mapped_column(String(30), default="probe")
    # probe, snmp, tr069, radius, speed_test, fno_api

    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True,
    )

    __table_args__ = (
        Index("ix_npm_tenant_service", "tenant_id", "service_id"),
        Index("ix_npm_tenant_type_time", "tenant_id", "metric_type", "collected_at"),
        Index("ix_npm_service_time", "service_id", "collected_at"),
    )


class NetworkSLAProfile(Base):
    """SLA targets per service or FNO provider."""

    __tablename__ = "network_sla_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Scope: either per-service or per-FNO (service_id NULL = FNO-wide)
    service_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_services.id", ondelete="CASCADE"), nullable=True,
    )
    fno_provider: Mapped[Optional[str]] = mapped_column(FNO_PROVIDER, nullable=True)

    # SLA targets
    target_latency_ms: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)
    target_jitter_ms: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)
    target_packet_loss_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    target_download_mbps: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    target_upload_mbps: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    target_uptime_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    target_mttr_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Evaluation window
    evaluation_window_hours: Mapped[int] = mapped_column(Integer, default=720)
    # 30 days default

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_nsla_tenant", "tenant_id", "is_active"),
        Index("ix_nsla_service", "service_id"),
        Index("ix_nsla_fno", "tenant_id", "fno_provider"),
    )


class NetworkSLABreach(Base):
    """Records SLA violations for reporting and FNO accountability."""

    __tablename__ = "network_sla_breaches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sla_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_sla_profiles.id", ondelete="CASCADE"), nullable=False,
    )
    service_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_services.id", ondelete="CASCADE"), nullable=True,
    )

    metric_type: Mapped[str] = mapped_column(METRIC_TYPE, nullable=False)
    target_value: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    actual_value: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    severity: Mapped[str] = mapped_column(ALERT_SEVERITY, nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_nslab_tenant", "tenant_id", "severity"),
        Index("ix_nslab_service", "service_id"),
        Index("ix_nslab_open", "tenant_id", "resolved_at"),
        Index("ix_nslab_profile", "sla_profile_id"),
    )


class NetworkDevice(Base):
    """Physical network devices per service: ONT, router, gateway, switch."""

    __tablename__ = "network_devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_services.id", ondelete="CASCADE"), nullable=False,
    )

    device_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # ont, router, gateway, switch, access_point, media_converter

    manufacturer: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    mac_address: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    firmware_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Management
    management_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    management_protocol: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # snmp, tr069, ssh, telnet, http

    # Status
    status: Mapped[str] = mapped_column(String(20), default="active")
    # active, offline, error, provisioning, decommissioned
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Inventory link
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_products.id", ondelete="SET NULL"), nullable=True,
    )

    # Config snapshot (last known good config)
    config_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_nd_tenant_service", "tenant_id", "service_id"),
        Index("ix_nd_serial", "serial_number"),
        Index("ix_nd_mac", "mac_address"),
        Index("ix_nd_status", "tenant_id", "status"),
        Index("ix_nd_product", "product_id"),
    )


class NetworkNotification(Base):
    """Notifications dispatched for network events: outages, SLA breaches, maintenance."""

    __tablename__ = "network_notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    service_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_services.id", ondelete="CASCADE"), nullable=True,
    )
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # What triggered it
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # fno_outage, sla_breach, maintenance, device_offline, speed_degradation,
    # billing_suspend, billing_reinstate, fault_reported
    trigger_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    # FK to the source record (sla_breach_id, fno_status_id, etc.)

    severity: Mapped[str] = mapped_column(ALERT_SEVERITY, nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Delivery
    channel: Mapped[str] = mapped_column(NOTIFICATION_CHANNEL, nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    # email address, phone number, device token, webhook URL
    status: Mapped[str] = mapped_column(NOTIFICATION_STATUS, nullable=False, default="pending")
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Retry
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_nn_tenant", "tenant_id", "status"),
        Index("ix_nn_service", "service_id"),
        Index("ix_nn_customer", "customer_id"),
        Index("ix_nn_trigger", "trigger_type", "trigger_id"),
        Index("ix_nn_pending", "tenant_id", "status", "retry_count"),
    )


class RadiusAccounting(Base):
    """RADIUS accounting records (radacct) for session tracking."""

    __tablename__ = "radius_accounting"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    radius_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("radius_accounts.id", ondelete="CASCADE"), nullable=False,
    )

    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    nas_ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    nas_port_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    framed_ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    calling_station_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    called_station_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Session timing
    acct_start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acct_stop_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acct_session_time: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # seconds

    # Traffic
    acct_input_octets: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    acct_output_octets: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    acct_input_packets: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    acct_output_packets: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Termination cause
    acct_terminate_cause: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # User-Request, Lost-Carrier, Idle-Timeout, Session-Timeout, Admin-Reset, etc.

    # Authentic
    acct_authentic: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    # RADIUS, Local, Remote

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_ra_tenant_account", "tenant_id", "radius_account_id"),
        Index("ix_ra_session", "session_id"),
        Index("ix_ra_start", "acct_start_time"),
        Index("ix_ra_active", "tenant_id", "acct_stop_time"),
        # acct_stop_time IS NULL = active session
    )


# ---------------------------------------------------------------------------
# Network Typography — geographic hierarchy
# ---------------------------------------------------------------------------

class NetworkRegion(Base):
    """Top-level network region (e.g. 'Gauteng North', 'Western Cape Metro')."""

    __tablename__ = "network_regions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Bounding box
    bbox_north: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    bbox_south: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    bbox_east: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)
    bbox_west: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_nr_tenant_code", "tenant_id", "code", unique=True),
        Index("ix_nr_tenant_active", "tenant_id", "is_active"),
    )


class NetworkMetro(Base):
    """Metro area within a region (e.g. 'Johannesburg', 'Cape Town')."""

    __tablename__ = "network_metros"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_regions.id", ondelete="CASCADE"), nullable=False,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    province: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_nm_tenant_region", "tenant_id", "region_id"),
        Index("ix_nm_tenant_code", "tenant_id", "code", unique=True),
    )


class NetworkArea(Base):
    """Network area within a metro (e.g. 'Sandton', 'Rondebosch')."""

    __tablename__ = "network_areas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    metro_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_metros.id", ondelete="CASCADE"), nullable=False,
    )
    fno_provider: Mapped[Optional[str]] = mapped_column(FNO_PROVIDER, nullable=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    suburb: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    province: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    postal_codes: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Coverage status
    coverage_status: Mapped[str] = mapped_column(String(30), default="planned")
    # planned, under_construction, available, expanding
    technology: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    max_speed_mbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # GPS centroid
    centroid_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    centroid_lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_na_tenant_metro", "tenant_id", "metro_id"),
        Index("ix_na_tenant_code", "tenant_id", "code", unique=True),
        Index("ix_na_fno", "tenant_id", "fno_provider"),
        Index("ix_na_suburb", "tenant_id", "suburb"),
    )


# ---------------------------------------------------------------------------
# Network Topology — fiber infrastructure
# ---------------------------------------------------------------------------

TOPOLOGY_ELEMENT_TYPE = SAEnum(
    "olt", "splitter", "distribution_point", "access_point",
    "fiber_cable", "splice_closure", "patch_panel", "ont",
    name="topology_element_type", create_type=True,
)

TOPOLOGY_STATUS = SAEnum(
    "planned", "under_construction", "active", "maintenance", "decommissioned",
    name="topology_status", create_type=True,
)


class NetworkTopologyElement(Base):
    """Physical network infrastructure elements: OLTs, splitters, cables, etc."""

    __tablename__ = "network_topology_elements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    area_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_areas.id", ondelete="SET NULL"), nullable=True,
    )
    fno_provider: Mapped[Optional[str]] = mapped_column(FNO_PROVIDER, nullable=True)

    element_type: Mapped[str] = mapped_column(TOPOLOGY_ELEMENT_TYPE, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)

    # Location
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    gps_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    gps_lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)

    # Capacity
    total_ports: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    used_ports: Mapped[int] = mapped_column(Integer, default=0)
    available_ports: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Splitter-specific
    splitter_ratio: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # 1:8, 1:16, 1:32, 1:64

    # OLT-specific
    olt_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    olt_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(TOPOLOGY_STATUS, nullable=False, default="planned")

    # Parent element (for hierarchical topology)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_topology_elements.id", ondelete="SET NULL"), nullable=True,
    )

    # Metadata
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_nte_tenant_type", "tenant_id", "element_type"),
        Index("ix_nte_tenant_area", "tenant_id", "area_id"),
        Index("ix_nte_tenant_code", "tenant_id", "code", unique=True),
        Index("ix_nte_fno", "tenant_id", "fno_provider"),
        Index("ix_nte_parent", "parent_id"),
        Index("ix_nte_status", "tenant_id", "status"),
    )


class NetworkTopologyLink(Base):
    """Links between topology elements (fiber cables, logical connections)."""

    __tablename__ = "network_topology_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    from_element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_topology_elements.id", ondelete="CASCADE"), nullable=False,
    )
    to_element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_topology_elements.id", ondelete="CASCADE"), nullable=False,
    )

    link_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # fiber_cable, logical_link, patch_cable

    # Fiber-specific
    fiber_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fiber_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # single_mode, multi_mode
    length_meters: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    status: Mapped[str] = mapped_column(TOPOLOGY_STATUS, nullable=False, default="active")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_ntl_tenant_from", "tenant_id", "from_element_id"),
        Index("ix_ntl_tenant_to", "tenant_id", "to_element_id"),
        Index("ix_ntl_type", "tenant_id", "link_type"),
    )


# ---------------------------------------------------------------------------
# Bandwidth Usage Tracking
# ---------------------------------------------------------------------------

class BandwidthUsage(Base):
    """Bandwidth usage per service per time period (from RADIUS accounting or SNMP)."""

    __tablename__ = "bandwidth_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_services.id", ondelete="CASCADE"), nullable=False,
    )

    # Time period
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False, default="daily")
    # hourly, daily, weekly, monthly

    # Traffic
    download_bytes: Mapped[int] = mapped_column(Integer, default=0)
    upload_bytes: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(Integer, default=0)

    # Computed
    download_gb: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    upload_gb: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    total_gb: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)

    # Peak speeds during period
    peak_download_mbps: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    peak_upload_mbps: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    avg_download_mbps: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    avg_upload_mbps: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    # Source
    source: Mapped[str] = mapped_column(String(30), default="radius")
    # radius, snmp, tr069, estimated

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_bw_tenant_service", "tenant_id", "service_id"),
        Index("ix_bw_tenant_period", "tenant_id", "period_start"),
        Index("ix_bw_service_period", "service_id", "period_start"),
        UniqueConstraint("service_id", "period_start", "period_type", name="uq_bw_service_period"),
    )


# ---------------------------------------------------------------------------
# FNO SLA Compliance Tracking
# ---------------------------------------------------------------------------

FNO_SLA_METRIC = SAEnum(
    "install_time_days", "repair_time_hours", "uptime_pct",
    "response_time_hours", "resolution_rate_pct",
    name="fno_sla_metric", create_type=True,
)


class FNOSLATarget(Base):
    """SLA targets agreed with each FNO provider."""

    __tablename__ = "fno_sla_targets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    fno_provider: Mapped[str] = mapped_column(FNO_PROVIDER, nullable=False)

    metric: Mapped[str] = mapped_column(FNO_SLA_METRIC, nullable=False)
    target_value: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    # days, hours, percent

    # Penalty for breach
    penalty_per_breach_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    penalty_cap_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_fno_sla_tenant_fno", "tenant_id", "fno_provider"),
        Index("ix_fno_sla_metric", "tenant_id", "fno_provider", "metric"),
        UniqueConstraint("tenant_id", "fno_provider", "metric", "effective_from", name="uq_fno_sla_target"),
    )


class FNOSLAMeasurement(Base):
    """Actual SLA measurements per FNO per period."""

    __tablename__ = "fno_sla_measurements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    fno_provider: Mapped[str] = mapped_column(FNO_PROVIDER, nullable=False)
    sla_target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fno_sla_targets.id", ondelete="CASCADE"), nullable=False,
    )

    metric: Mapped[str] = mapped_column(FNO_SLA_METRIC, nullable=False)

    # Measurement period
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False, default="monthly")
    # weekly, monthly, quarterly

    # Actual value
    actual_value: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    target_value: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)

    # Breach detection
    is_breach: Mapped[bool] = mapped_column(Boolean, default=False)
    breach_severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    deviation_pct: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)

    # Sample
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    # Number of tickets/orders measured

    # Penalty
    penalty_applied_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_fno_sla_m_tenant_fno", "tenant_id", "fno_provider"),
        Index("ix_fno_sla_m_period", "tenant_id", "period_start"),
        Index("ix_fno_sla_m_breach", "tenant_id", "is_breach"),
        UniqueConstraint("fno_provider", "metric", "period_start", "period_type", name="uq_fno_sla_measurement"),
    )


# ---------------------------------------------------------------------------
# Device Configuration (TR-069 / MikroTik stubs)
# ---------------------------------------------------------------------------

class DeviceConfigTemplate(Base):
    """Reusable configuration templates for network devices."""

    __tablename__ = "device_config_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    device_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # ont, router, gateway, access_point

    # Template config (device-specific JSON)
    config_template: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Protocol
    config_protocol: Mapped[str] = mapped_column(String(20), default="tr069")
    # tr069, mikrotik_api, ssh, snmp_set

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_dct_tenant_type", "tenant_id", "device_type"),
        Index("ix_dct_active", "tenant_id", "is_active"),
    )


class DeviceConfigPush(Base):
    """Tracks configuration push operations to devices."""

    __tablename__ = "device_config_pushes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_devices.id", ondelete="CASCADE"), nullable=False,
    )
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("device_config_templates.id", ondelete="SET NULL"), nullable=True,
    )

    # What was pushed
    config_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    config_protocol: Mapped[str] = mapped_column(String(20), nullable=False)

    # Result
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending, in_progress, completed, failed, rolled_back
    result_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timing
    pushed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Who pushed
    pushed_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_dcp_tenant_device", "tenant_id", "device_id"),
        Index("ix_dcp_status", "tenant_id", "status"),
        Index("ix_dcp_pending", "tenant_id", "status", "created_at"),
    )


# ---------------------------------------------------------------------------
# Property-to-Network Linkage
# ---------------------------------------------------------------------------

class PropertyNetworkLink(Base):
    """Links CRM properties to network typography hierarchy and services."""

    __tablename__ = "property_network_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # Network typography linkage
    region_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_regions.id", ondelete="SET NULL"), nullable=True,
    )
    metro_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_metros.id", ondelete="SET NULL"), nullable=True,
    )
    area_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_areas.id", ondelete="SET NULL"), nullable=True,
    )

    # Active service on this property
    service_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_services.id", ondelete="SET NULL"), nullable=True,
    )

    # Coverage info at this address
    coverage_status: Mapped[str] = mapped_column(String(30), default="unknown")
    # unknown, covered, not_covered, coming_soon, planned
    fno_provider: Mapped[Optional[str]] = mapped_column(FNO_PROVIDER, nullable=True)
    max_available_speed_mbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Distance to nearest infrastructure
    distance_to_olt_meters: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    distance_to_splitter_meters: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    # Lead generation
    is_lead: Mapped[bool] = mapped_column(Boolean, default=False)
    lead_score: Mapped[int] = mapped_column(Integer, default=0)
    lead_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_pnl_tenant_property", "tenant_id", "property_id", unique=True),
        Index("ix_pnl_tenant_area", "tenant_id", "area_id"),
        Index("ix_pnl_tenant_service", "tenant_id", "service_id"),
        Index("ix_pnl_leads", "tenant_id", "is_lead", "lead_score"),
        Index("ix_pnl_coverage", "tenant_id", "coverage_status"),
    )


# ---------------------------------------------------------------------------
# Traffic Classification (DPI / Package Sniffing)
# ---------------------------------------------------------------------------

TRAFFIC_CLASS = SAEnum(
    "web_browsing", "video_streaming", "social_media", "gaming",
    "voip", "file_download", "iot", "vpn", "unknown",
    name="traffic_class", create_type=True,
)


class TrafficClassification(Base):
    """DPI traffic classification rules for bandwidth management."""

    __tablename__ = "traffic_classifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    traffic_class: Mapped[str] = mapped_column(TRAFFIC_CLASS, nullable=False)

    # Matching rules
    protocols: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # ["tcp", "udp"]
    port_ranges: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # ["80-80", "443-443", "8000-8080"]
    domains: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # ["netflix.com", "youtube.com"]
    ip_ranges: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # ["10.0.0.0/8", "192.168.1.0/24"]
    dpi_signatures: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # ["SNI:netflix.com", "Host:*.googlevideo.com"]

    # Priority and shaping
    priority: Mapped[int] = mapped_column(Integer, default=5)
    # 1 = highest, 10 = lowest
    bandwidth_limit_mbps: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    # Per-service bandwidth cap

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_tc_tenant_class", "tenant_id", "traffic_class"),
        Index("ix_tc_tenant_active", "tenant_id", "is_active"),
        Index("ix_tc_priority", "tenant_id", "priority"),
    )


class ServiceTrafficUsage(Base):
    """Per-service traffic breakdown by classification."""

    __tablename__ = "service_traffic_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_services.id", ondelete="CASCADE"), nullable=False,
    )

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False, default="daily")

    traffic_class: Mapped[str] = mapped_column(TRAFFIC_CLASS, nullable=False)
    download_bytes: Mapped[int] = mapped_column(Integer, default=0)
    upload_bytes: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(Integer, default=0)
    download_gb: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    upload_gb: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)

    # Percentage of total
    pct_of_total: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_stu_tenant_service", "tenant_id", "service_id"),
        Index("ix_stu_service_period", "service_id", "period_start"),
        Index("ix_stu_class", "tenant_id", "traffic_class"),
        UniqueConstraint("service_id", "period_start", "period_type", "traffic_class", name="uq_stu_service_period_class"),
    )


# ---------------------------------------------------------------------------
# ONT Provisioning Parameters
# ---------------------------------------------------------------------------

class ONTProvisioningProfile(Base):
    """ONT/GPON provisioning parameters for device activation."""

    __tablename__ = "ont_provisioning_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_services.id", ondelete="CASCADE"), nullable=False,
    )

    # GPON identity
    gpon_serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # ONT serial (vendor-specific format)
    loid: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Logical ONT ID (used by some FNOs)
    loid_password: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    onu_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # ONU ID on the OLT

    # VLAN configuration
    internet_vlan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    voice_vlan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    iptv_vlan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    management_vlan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Service profile
    service_profile_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bandwidth_profile_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # OLT reference
    olt_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    olt_port: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # e.g. "1/1/1" (slot/port/pon)

    # Status
    provisioning_status: Mapped[str] = mapped_column(String(30), default="pending")
    # pending, provisioning, active, failed, deactivated
    provisioned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # TR-069
    tr069_acs_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    tr069_device_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_opp_tenant_service", "tenant_id", "service_id", unique=True),
        Index("ix_opp_tenant_status", "tenant_id", "provisioning_status"),
        Index("ix_opp_gpon_sn", "gpon_serial_number"),
        Index("ix_opp_loid", "loid"),
    )


# ---------------------------------------------------------------------------
# Wi-Fi Configuration (TR-069 remote push)
# ---------------------------------------------------------------------------

WIFI_BAND = SAEnum(
    "2.4ghz", "5ghz", "6ghz", "dual_band", "tri_band",
    name="wifi_band", create_type=True,
)

WIFI_SECURITY = SAEnum(
    "wpa2_psk", "wpa3_psk", "wpa2_wpa3", "wep", "open",
    name="wifi_security", create_type=True,
)


class WiFiConfigProfile(Base):
    """Wi-Fi configuration profiles for remote push to customer routers/ONTs."""

    __tablename__ = "wifi_config_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_services.id", ondelete="CASCADE"), nullable=False,
    )

    # SSID config
    ssid_24ghz: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ssid_5ghz: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ssid_6ghz: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Security
    security_mode: Mapped[str] = mapped_column(WIFI_SECURITY, nullable=False, default="wpa2_wpa3")
    passphrase: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Band steering
    band_steering_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    preferred_band: Mapped[str] = mapped_column(WIFI_BAND, default="5ghz")

    # Channel config
    channel_24ghz: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    channel_5ghz: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    channel_width_mhz: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # 20, 40, 80, 160

    # Advanced
    max_clients: Mapped[int] = mapped_column(Integer, default=32)
    hidden_ssid: Mapped[bool] = mapped_column(Boolean, default=False)
    guest_ssid_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    guest_ssid_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    guest_ssid_passphrase: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Push status
    push_status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending, pushed, confirmed, failed
    last_pushed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_wcp_tenant_service", "tenant_id", "service_id", unique=True),
        Index("ix_wcp_tenant_push", "tenant_id", "push_status"),
    )


# ---------------------------------------------------------------------------
# FNO Portal Session Recording
# ---------------------------------------------------------------------------

RECORDING_STATUS = SAEnum(
    "idle", "recording", "processing", "analyzed", "failed",
    name="recording_status", create_type=True,
)


class FNOSessionRecording(Base):
    """Screen recordings of FNO portal sessions for process analysis."""

    __tablename__ = "fno_session_recordings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fno_portal_sessions.id", ondelete="CASCADE"), nullable=False,
    )
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fno_automation_jobs.id", ondelete="SET NULL"), nullable=True,
    )

    # Recording info
    recording_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resolution: Mapped[str] = mapped_column(String(20), default="1920x1080")
    fps: Mapped[int] = mapped_column(Integer, default=15)

    # Status
    status: Mapped[str] = mapped_column(RECORDING_STATUS, nullable=False, default="idle")

    # Process analysis results
    extracted_steps: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # [{"action": "click", "selector": "#login-btn", "timestamp": 1.5}, ...]
    page_transitions: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # [{"from": "/login", "to": "/dashboard", "timestamp": 3.2}, ...]
    error_events: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # [{"type": "timeout", "element": "#submit", "timestamp": 10.5}, ...]

    # Template generation
    template_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)

    # Mouse tracking
    mouse_events: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # [{"x": 100, "y": 200, "action": "click", "timestamp": 1.5}, ...]

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_fsr_tenant_session", "tenant_id", "session_id"),
        Index("ix_fsr_tenant_job", "tenant_id", "job_id"),
        Index("ix_fsr_status", "tenant_id", "status"),
        Index("ix_fsr_template", "tenant_id", "template_generated"),
    )


# ---------------------------------------------------------------------------
# Lead Generation from FNO Data
# ---------------------------------------------------------------------------

LEAD_SOURCE_TYPE = SAEnum(
    "coverage_gap", "new_area", "fno_outage", "competitor_churn",
    "speed_upgrade", "address_inquiry",
    name="lead_source_type", create_type=True,
)


class NetworkLead(Base):
    """Leads generated from network data: coverage gaps, new areas, outages."""

    __tablename__ = "network_leads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # Source
    lead_source: Mapped[str] = mapped_column(LEAD_SOURCE_TYPE, nullable=False)
    source_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # "Vumatel coverage gap in Sandton", "New Openserve area: Midrand"

    # Property link
    property_network_link_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property_network_links.id", ondelete="SET NULL"), nullable=True,
    )

    # Location
    address_line1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    suburb: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    province: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    gps_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    gps_lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)

    # Qualification
    status: Mapped[str] = mapped_column(String(20), default="new")
    # new, qualified, contacted, converted, disqualified, expired
    score: Mapped[int] = mapped_column(Integer, default=0)
    # 0-100

    # FNO context
    target_fno: Mapped[Optional[str]] = mapped_column(FNO_PROVIDER, nullable=True)
    current_fno: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    interest_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Conversion
    converted_to_customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    converted_to_service_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Assignment
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_nl_tenant_status", "tenant_id", "status"),
        Index("ix_nl_tenant_source", "tenant_id", "lead_source"),
        Index("ix_nl_tenant_score", "tenant_id", "score"),
        Index("ix_nl_location", "tenant_id", "city", "suburb"),
        Index("ix_nl_postal", "postal_code"),
        Index("ix_nl_assigned", "tenant_id", "assigned_to"),
    )
