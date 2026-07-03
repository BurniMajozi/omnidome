"""SQLAlchemy models for the IoT service.

Manages IoT device registry, rooms/zones, automations, events,
scenes, alerts, device states, and Home Assistant integrations.
"""

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
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from services.common.db import register_tenant_scoped_base


class Base(DeclarativeBase):
    pass


# Every model below carries tenant_id; opt this Base into the automatic
# tenant filter in services.common.db so a missed manual .where() clause
# can no longer leak rows across tenants.
register_tenant_scoped_base(Base)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

DEVICE_TYPE = SAEnum(
    "camera",
    "sensor",
    "light",
    "lock",
    "switch",
    "climate",
    "alarm",
    "energy",
    "presence",
    "other",
    name="device_type",
)

DEVICE_STATUS = SAEnum(
    "online",
    "offline",
    "unavailable",
    "error",
    "updating",
    name="device_status",
)

ALERT_SEVERITY = SAEnum(
    "info",
    "warning",
    "critical",
    "emergency",
    name="alert_severity",
)

AUTOMATION_TRIGGER = SAEnum(
    "state_change",
    "schedule",
    "event",
    "webhook",
    "manual",
    name="automation_trigger",
)

INTEGRATION_STATUS = SAEnum(
    "connected",
    "disconnected",
    "error",
    "syncing",
    name="integration_status",
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class IoTDevice(Base):
    """Registered IoT device synced from Home Assistant."""

    __tablename__ = "iot_devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    integration_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iot_integrations.id"), nullable=True
    )
    room_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iot_rooms.id"), nullable=True
    )

    # HA entity info
    ha_entity_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ha_domain: Mapped[str] = mapped_column(String(64), nullable=False)
    friendly_name: Mapped[str] = mapped_column(String(255), nullable=False)
    device_type: Mapped[str] = mapped_column(DEVICE_TYPE, nullable=False, index=True)

    # Inventory link (optional — for devices that are also tracked inventory items)
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_products.id", ondelete="SET NULL"), nullable=True
    )

    # Device metadata
    manufacturer: Mapped[Optional[str]] = mapped_column(String(128))
    model: Mapped[Optional[str]] = mapped_column(String(128))
    sw_version: Mapped[Optional[str]] = mapped_column(String(64))
    hw_version: Mapped[Optional[str]] = mapped_column(String(64))
    serial_number: Mapped[Optional[str]] = mapped_column(String(128))
    mac_address: Mapped[Optional[str]] = mapped_column(String(32))
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))

    # State
    status: Mapped[str] = mapped_column(
        DEVICE_STATUS, nullable=False, default="unavailable"
    )
    is_controllable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_configurable: Mapped[bool] = mapped_column(Boolean, default=False)
    battery_level: Mapped[Optional[int]] = mapped_column(Integer)
    signal_strength: Mapped[Optional[int]] = mapped_column(Integer)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_changed: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Attributes (HA entity attributes as JSONB)
    attributes: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    room = relationship("IoTRoom", back_populates="devices")
    integration = relationship("IoTIntegration", back_populates="devices")
    states = relationship("IoTDeviceState", back_populates="device", cascade="all, delete-orphan")
    events = relationship("IoTEvent", back_populates="device", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_iot_devices_tenant_ha_entity", "tenant_id", "ha_entity_id", unique=True),
        Index("ix_iot_devices_product", "product_id"),
    )


class IoTRoom(Base):
    """Room/zone grouping for IoT devices (maps to HA areas)."""

    __tablename__ = "iot_rooms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    ha_area_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(64))
    floor: Mapped[Optional[int]] = mapped_column(Integer)
    description: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    devices = relationship("IoTDevice", back_populates="room")

    __table_args__ = (
        Index("ix_iot_rooms_tenant_name", "tenant_id", "name", unique=True),
    )


class IoTDeviceState(Base):
    """Current and historical device states."""

    __tablename__ = "iot_device_states"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iot_devices.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    state_value: Mapped[str] = mapped_column(String(512), nullable=False)
    unit_of_measurement: Mapped[Optional[str]] = mapped_column(String(32))
    attributes: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Relationships
    device = relationship("IoTDevice", back_populates="states")

    __table_args__ = (
        Index("ix_iot_device_states_device_time", "device_id", "recorded_at"),
    )


class IoTEvent(Base):
    """Event log for device state changes, triggers, and alerts."""

    __tablename__ = "iot_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    device_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iot_devices.id", ondelete="SET NULL"), nullable=True
    )
    automation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iot_automations.id", ondelete="SET NULL"), nullable=True
    )
    alert_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iot_alerts.id", ondelete="SET NULL"), nullable=True
    )

    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="ha")
    message: Mapped[Optional[str]] = mapped_column(Text)
    data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Relationships
    device = relationship("IoTDevice", back_populates="events")

    __table_args__ = (
        Index("ix_iot_events_tenant_time", "tenant_id", "created_at"),
    )


class IoTAutomation(Base):
    """Automation definitions (HA automations + OmniDome custom)."""

    __tablename__ = "iot_automations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    ha_automation_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    trigger_type: Mapped[str] = mapped_column(AUTOMATION_TRIGGER, nullable=False)
    trigger_config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    conditions: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    actions: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)

    last_triggered: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    trigger_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_iot_automations_tenant", "tenant_id", "is_enabled"),
    )


class IoTScene(Base):
    """Scene definitions (e.g., 'Away Mode', 'Night Mode', 'Movie')."""

    __tablename__ = "iot_scenes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    ha_scene_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(64))
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Scene configuration: list of device states to apply
    scene_config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    activation_count: Mapped[int] = mapped_column(Integer, default=0)
    last_activated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_iot_scenes_tenant", "tenant_id", "is_favorite"),
    )


class IoTAlert(Base):
    """Alert rules with thresholds and notification channels."""

    __tablename__ = "iot_alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    device_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iot_devices.id", ondelete="CASCADE"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(ALERT_SEVERITY, nullable=False, default="warning")

    # Alert condition
    condition_type: Mapped[str] = mapped_column(String(64), nullable=False)
    condition_config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    # Notification channels
    notify_email: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_sms: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_push: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_webhook: Mapped[bool] = mapped_column(Boolean, default=False)
    webhook_url: Mapped[Optional[str]] = mapped_column(String(512))

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=15)
    last_triggered: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    trigger_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_iot_alerts_tenant", "tenant_id", "is_enabled"),
    )


class IoTIntegration(Base):
    """Home Assistant instance configurations."""

    __tablename__ = "iot_integrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ha_url: Mapped[str] = mapped_column(String(512), nullable=False)
    # Token stored encrypted — see ha_client.py for encryption helpers
    ha_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        INTEGRATION_STATUS, nullable=False, default="disconnected"
    )
    ha_version: Mapped[Optional[str]] = mapped_column(String(32))
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    sync_interval_seconds: Mapped[int] = mapped_column(Integer, default=30)

    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    devices = relationship("IoTDevice", back_populates="integration")

    __table_args__ = (
        Index("ix_iot_integrations_tenant", "tenant_id", "is_primary"),
    )
