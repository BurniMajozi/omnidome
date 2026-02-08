"""SQLAlchemy models for the Network service."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
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
