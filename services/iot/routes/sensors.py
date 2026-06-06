"""IoT sensor routes — list sensors, historical readings, current state, and alert thresholds.

Provides endpoints for querying sensor-type IoT devices (device_type 'sensor'
or 'binary_sensor'), their historical state readings, current readings, and
alert threshold configuration.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.iot.database import get_session
from services.iot.models import IoTAlert, IoTDevice, IoTDeviceState

router = APIRouter(prefix="/api/iot/sensors", tags=["iot-sensors"])

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class SensorListItem(BaseModel):
    """Summary representation of a sensor device."""
    id: uuid.UUID
    ha_entity_id: str
    friendly_name: str
    device_type: str
    status: str
    manufacturer: Optional[str]
    model: Optional[str]
    battery_level: Optional[int]
    signal_strength: Optional[int]
    room_id: Optional[uuid.UUID]
    attributes: Optional[Dict[str, Any]]
    last_seen: Optional[datetime]
    last_changed: Optional[datetime]
    last_updated: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaginatedSensorResponse(BaseModel):
    items: List[SensorListItem]
    total: int
    page: int
    page_size: int
    pages: int


class SensorReading(BaseModel):
    """A single historical sensor reading."""
    id: uuid.UUID
    device_id: uuid.UUID
    state_value: str
    unit_of_measurement: Optional[str]
    attributes: Optional[Dict[str, Any]]
    recorded_at: datetime

    class Config:
        from_attributes = True


class PaginatedReadingsResponse(BaseModel):
    items: List[SensorReading]
    total: int
    page: int
    page_size: int
    pages: int


class CurrentReadingResponse(BaseModel):
    """The most recent reading for a sensor device."""
    device_id: uuid.UUID
    ha_entity_id: str
    friendly_name: str
    state_value: str
    unit_of_measurement: Optional[str]
    attributes: Optional[Dict[str, Any]]
    recorded_at: Optional[datetime]
    device_status: str
    last_seen: Optional[datetime]


class ThresholdCreate(BaseModel):
    """Schema for setting an alert threshold on a sensor."""
    name: str = Field(..., max_length=255, description="Alert rule name")
    description: Optional[str] = None
    severity: str = Field("warning", description="One of: info, warning, critical, emergency")
    condition_type: str = Field(
        ...,
        description="Condition type, e.g. 'above', 'below', 'equals', 'range'",
    )
    condition_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Condition parameters, e.g. {'value': 30, 'unit': '°C'}",
    )
    notify_email: bool = False
    notify_sms: bool = False
    notify_push: bool = True
    notify_webhook: bool = False
    webhook_url: Optional[str] = Field(None, max_length=512)
    cooldown_minutes: int = Field(15, ge=1, le=1440)


class ThresholdResponse(BaseModel):
    """Response schema for an alert threshold."""
    id: uuid.UUID
    tenant_id: uuid.UUID
    device_id: uuid.UUID
    name: str
    description: Optional[str]
    severity: str
    condition_type: str
    condition_config: Dict[str, Any]
    notify_email: bool
    notify_sms: bool
    notify_push: bool
    notify_webhook: bool
    webhook_url: Optional[str]
    is_enabled: bool
    cooldown_minutes: int
    last_triggered: Optional[datetime]
    trigger_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedSensorResponse)
async def list_sensors(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by device status"),
    room_id: Optional[uuid.UUID] = Query(None, description="Filter by room ID"),
    search: Optional[str] = Query(None, description="Search by friendly name or entity ID"),
):
    """List sensor and binary_sensor devices for the current tenant."""
    async with get_session() as session:
        stmt = select(IoTDevice).where(
            IoTDevice.tenant_id == ctx.tenant_id,
            IoTDevice.device_type.in_(["sensor", "binary_sensor"]),
        )

        if status:
            stmt = stmt.where(IoTDevice.status == status)
        if room_id:
            stmt = stmt.where(IoTDevice.room_id == room_id)
        if search:
            search_term = f"%{search}%"
            stmt = stmt.where(
                IoTDevice.friendly_name.ilike(search_term)
                | IoTDevice.ha_entity_id.ilike(search_term)
            )

        # Count total
        count_stmt = select(func.count(IoTDevice.id)).where(
            IoTDevice.tenant_id == ctx.tenant_id,
            IoTDevice.device_type.in_(["sensor", "binary_sensor"]),
        )
        if status:
            count_stmt = count_stmt.where(IoTDevice.status == status)
        if room_id:
            count_stmt = count_stmt.where(IoTDevice.room_id == room_id)
        if search:
            count_stmt = count_stmt.where(
                IoTDevice.friendly_name.ilike(search_term)
                | IoTDevice.ha_entity_id.ilike(search_term)
            )

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        # Paginated query
        stmt = (
            stmt.order_by(IoTDevice.friendly_name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        devices = result.scalars().all()

        return PaginatedSensorResponse(
            items=[SensorListItem.model_validate(d) for d in devices],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


@router.get("/{sensor_id}/readings", response_model=PaginatedReadingsResponse)
async def get_sensor_readings(
    sensor_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    from_: Optional[datetime] = Query(None, alias="from", description="Start of time range (ISO 8601)"),
    to: Optional[datetime] = Query(None, description="End of time range (ISO 8601)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of readings to return"),
):
    """Get historical readings for a sensor device, filtered by time range."""
    async with get_session() as session:
        # Verify the device exists, belongs to tenant, and is a sensor type
        device_stmt = select(IoTDevice).where(
            IoTDevice.id == sensor_id,
            IoTDevice.tenant_id == ctx.tenant_id,
            IoTDevice.device_type.in_(["sensor", "binary_sensor"]),
        )
        device_result = await session.execute(device_stmt)
        device = device_result.scalar_one_or_none()
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sensor not found",
            )

        # Build readings query
        stmt = select(IoTDeviceState).where(
            IoTDeviceState.device_id == sensor_id,
            IoTDeviceState.tenant_id == ctx.tenant_id,
        )

        if from_:
            stmt = stmt.where(IoTDeviceState.recorded_at >= from_)
        if to:
            stmt = stmt.where(IoTDeviceState.recorded_at <= to)

        # Count total matching
        count_stmt = select(func.count(IoTDeviceState.id)).where(
            IoTDeviceState.device_id == sensor_id,
            IoTDeviceState.tenant_id == ctx.tenant_id,
        )
        if from_:
            count_stmt = count_stmt.where(IoTDeviceState.recorded_at >= from_)
        if to:
            count_stmt = count_stmt.where(IoTDeviceState.recorded_at <= to)

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Fetch readings ordered by time descending, limited
        stmt = (
            stmt.order_by(IoTDeviceState.recorded_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        readings = result.scalars().all()

        return PaginatedReadingsResponse(
            items=[SensorReading.model_validate(r) for r in readings],
            total=total,
            page=1,
            page_size=limit,
            pages=max(1, (total + limit - 1) // limit) if total else 1,
        )


@router.get("/{sensor_id}/current", response_model=CurrentReadingResponse)
async def get_current_reading(
    sensor_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get the most recent reading for a sensor device."""
    async with get_session() as session:
        # Verify the device exists, belongs to tenant, and is a sensor type
        device_stmt = select(IoTDevice).where(
            IoTDevice.id == sensor_id,
            IoTDevice.tenant_id == ctx.tenant_id,
            IoTDevice.device_type.in_(["sensor", "binary_sensor"]),
        )
        device_result = await session.execute(device_stmt)
        device = device_result.scalar_one_or_none()
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sensor not found",
            )

        # Get the latest state reading
        state_stmt = (
            select(IoTDeviceState)
            .where(
                IoTDeviceState.device_id == sensor_id,
                IoTDeviceState.tenant_id == ctx.tenant_id,
            )
            .order_by(IoTDeviceState.recorded_at.desc())
            .limit(1)
        )
        state_result = await session.execute(state_stmt)
        latest_state = state_result.scalar_one_or_none()

        if latest_state:
            return CurrentReadingResponse(
                device_id=device.id,
                ha_entity_id=device.ha_entity_id,
                friendly_name=device.friendly_name,
                state_value=latest_state.state_value,
                unit_of_measurement=latest_state.unit_of_measurement,
                attributes=latest_state.attributes,
                recorded_at=latest_state.recorded_at,
                device_status=device.status,
                last_seen=device.last_seen,
            )

        # No readings recorded yet — return device info with null reading fields
        return CurrentReadingResponse(
            device_id=device.id,
            ha_entity_id=device.ha_entity_id,
            friendly_name=device.friendly_name,
            state_value="unknown",
            unit_of_measurement=None,
            attributes=None,
            recorded_at=None,
            device_status=device.status,
            last_seen=device.last_seen,
        )


@router.post(
    "/{sensor_id}/threshold",
    response_model=ThresholdResponse,
    status_code=status.HTTP_201_CREATED,
)
async def set_sensor_threshold(
    sensor_id: uuid.UUID,
    body: ThresholdCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Set an alert threshold for a sensor device.

    Creates an IoTAlert rule that triggers when the sensor reading meets
    the specified condition (e.g. above/below a value).
    """
    async with get_session() as session:
        # Verify the device exists, belongs to tenant, and is a sensor type
        device_stmt = select(IoTDevice).where(
            IoTDevice.id == sensor_id,
            IoTDevice.tenant_id == ctx.tenant_id,
            IoTDevice.device_type.in_(["sensor", "binary_sensor"]),
        )
        device_result = await session.execute(device_stmt)
        device = device_result.scalar_one_or_none()
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sensor not found",
            )

        alert = IoTAlert(
            tenant_id=ctx.tenant_id,
            device_id=sensor_id,
            name=body.name,
            description=body.description,
            severity=body.severity,
            condition_type=body.condition_type,
            condition_config=body.condition_config,
            notify_email=body.notify_email,
            notify_sms=body.notify_sms,
            notify_push=body.notify_push,
            notify_webhook=body.notify_webhook,
            webhook_url=body.webhook_url,
            is_enabled=True,
            cooldown_minutes=body.cooldown_minutes,
        )
        session.add(alert)
        await session.flush()
        await session.refresh(alert)

        return ThresholdResponse.model_validate(alert)
