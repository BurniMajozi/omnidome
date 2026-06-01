"""SQLAlchemy models for the IoT Service."""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    BigInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.db import Base as CommonBase


class Base(CommonBase):
    __abstract__ = True


# ── Enums ──────────────────────────────────────────────────────────────────

DEVICE_TYPE = SAEnum(
    "ont", "router", "camera", "access_point",
    name="device_type", create_type=True,
)

DEVICE_STATUS = SAEnum(
    "online", "offline", "warning", "error",
    name="device_status", create_type=True,
)

METRIC_TYPE = SAEnum(
    "signal_strength", "uptime", "throughput",
    "temperature", "packet_loss", "latency",
    name="metric_type", create_type=True,
)


UNIT_TYPE = SAEnum(
    "dBm", "seconds", "Mbps", "celsius", "percent", "ms",
    name="unit_type", create_type=True,
)


# ── Device ──────────────────────────────────────────────────────────────────

class Device(Base):
    __tablename__ = "iot_devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    device_type: Mapped[str] = mapped_column(DEVICE_TYPE, nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=True)
    serial_number: Mapped[str] = mapped_column(String(200), nullable=True)
    firmware_version: Mapped[str] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(DEVICE_STATUS, nullable=False, default="online")
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=True)
    mac_address: Mapped[str] = mapped_column(String(17), nullable=True)
    signal_strength: Mapped[float] = mapped_column(Float, nullable=True)
    uptime_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    location: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_iot_devices_tenant_device_id", "tenant_id", "device_id", unique=True),
        Index("ix_iot_devices_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_iot_devices_tenant_status", "tenant_id", "status"),
        Index("ix_iot_devices_tenant_type", "tenant_id", "device_type"),
        Index("ix_iot_devices_serial", "serial_number"),
        Index("ix_iot_devices_mac", "mac_address"),
    )


# ── Telemetry Reading ───────────────────────────────────────────────────────

class TelemetryReading(Base):
    __tablename__ = "iot_telemetry_readings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    metric: Mapped[str] = mapped_column(METRIC_TYPE, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(UNIT_TYPE, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_telemetry_tenant_device", "tenant_id", "device_id"),
        Index("ix_telemetry_device_metric_time", "device_id", "metric", "recorded_at"),
        Index("ix_telemetry_recorded_at", "recorded_at"),
    )
