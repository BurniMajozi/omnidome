"""Pydantic v2 schemas for the IoT Service."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Device Schemas ──────────────────────────────────────────────────────────

class DeviceCreate(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=255)
    customer_id: uuid.UUID
    device_type: str = Field(..., pattern="^(ont|router|camera|access_point)$")
    model: Optional[str] = None
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    status: str = "online"
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    signal_strength: Optional[float] = None
    uptime_seconds: int = 0
    location: Optional[str] = None


class DeviceUpdate(BaseModel):
    device_type: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(online|offline|warning|error)$")
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    signal_strength: Optional[float] = None
    uptime_seconds: Optional[int] = None
    location: Optional[str] = None


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    device_id: str
    customer_id: uuid.UUID
    device_type: str
    model: Optional[str]
    serial_number: Optional[str]
    firmware_version: Optional[str]
    status: str
    last_seen: Optional[datetime]
    ip_address: Optional[str]
    mac_address: Optional[str]
    signal_strength: Optional[float]
    uptime_seconds: int
    location: Optional[str]
    created_at: datetime
    updated_at: datetime


class DeviceWithTelemetry(DeviceRead):
    latest_telemetry: List["TelemetryRead"] = []


# ── Telemetry Schemas ───────────────────────────────────────────────────────

class TelemetryReadingItem(BaseModel):
    metric: str = Field(..., pattern="^(signal_strength|uptime|throughput|temperature|packet_loss|latency)$")
    value: float
    unit: str = Field(..., pattern="^(dBm|seconds|Mbps|celsius|percent|ms)$")


class TelemetryCreate(BaseModel):
    device_id: uuid.UUID
    metric: str = Field(..., pattern="^(signal_strength|uptime|throughput|temperature|packet_loss|latency)$")
    value: float
    unit: str = Field(..., pattern="^(dBm|seconds|Mbps|celsius|percent|ms)$")


class TelemetryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_id: uuid.UUID
    metric: str
    value: float
    unit: str
    recorded_at: datetime


class TelemetryBatchCreate(BaseModel):
    device_id: uuid.UUID
    readings: List[TelemetryReadingItem] = Field(..., min_length=1)


# ── Health Summary ──────────────────────────────────────────────────────────

class DeviceHealthSummary(BaseModel):
    device_id: str
    customer_id: uuid.UUID
    overall_status: str
    last_seen: Optional[datetime]
    alerts: List[str] = Field(default_factory=list)
    metrics_summary: Dict[str, Any] = Field(default_factory=dict)


# ── Dashboard Schemas ──────────────────────────────────────────────────────

class DashboardSummary(BaseModel):
    total_devices: int
    online_count: int
    offline_count: int
    warning_count: int
    error_count: int
    avg_signal_strength: Optional[float]
    recent_alerts: List[DeviceHealthSummary] = Field(default_factory=list)


class AlertItem(BaseModel):
    device_id: str
    customer_id: uuid.UUID
    alert_type: str
    alert_message: str
    metric: Optional[str] = None
    value: Optional[float] = None
    recorded_at: Optional[datetime] = None


# ── Pagination ─────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int


# ── Reboot ──────────────────────────────────────────────────────────────────

class RebootResponse(BaseModel):
    device_id: str
    status: str
    message: str
    initiated_at: datetime
