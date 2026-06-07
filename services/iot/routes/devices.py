"""IoT device routes — Full CRUD for device registry with HA integration.

Provides endpoints for listing, reading, creating, updating, and deleting
IoT devices, plus device control via Home Assistant service calls,
state synchronization, and live state queries.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.iot.database import get_session
from services.iot.ha_client import (
    HARestClient,
    decrypt_token,
    ha_entity_to_device_type,
    ha_state_to_device_status,
)
from services.iot.models import IoTDevice, IoTIntegration

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

DEVICE_TYPES = [
    "camera", "sensor", "light", "lock", "switch",
    "climate", "alarm", "energy", "presence", "other",
]

DEVICE_STATUSES = ["online", "offline", "unavailable", "error", "updating"]


class DeviceCreate(BaseModel):
    """Schema for registering a new IoT device."""
    ha_entity_id: str = Field(..., max_length=255, description="Home Assistant entity ID")
    ha_domain: str = Field(..., max_length=64, description="HA domain (e.g. light, switch)")
    friendly_name: str = Field(..., max_length=255)
    device_type: str = Field(..., description=f"One of: {', '.join(DEVICE_TYPES)}")
    integration_id: Optional[uuid.UUID] = None
    room_id: Optional[uuid.UUID] = None
    product_id: Optional[uuid.UUID] = Field(None, description="Linked inventory product ID")
    manufacturer: Optional[str] = Field(None, max_length=128)
    model: Optional[str] = Field(None, max_length=128)
    sw_version: Optional[str] = Field(None, max_length=64)
    hw_version: Optional[str] = Field(None, max_length=64)
    serial_number: Optional[str] = Field(None, max_length=128)
    mac_address: Optional[str] = Field(None, max_length=32)
    ip_address: Optional[str] = Field(None, max_length=64)
    is_controllable: bool = False
    is_configurable: bool = False
    attributes: Optional[Dict[str, Any]] = Field(default_factory=dict)


class DeviceUpdate(BaseModel):
    """Schema for updating an existing device (all fields optional)."""
    friendly_name: Optional[str] = Field(None, max_length=255)
    device_type: Optional[str] = Field(None, description=f"One of: {', '.join(DEVICE_TYPES)}")
    integration_id: Optional[uuid.UUID] = None
    room_id: Optional[uuid.UUID] = None
    product_id: Optional[uuid.UUID] = Field(None, description="Linked inventory product ID")
    manufacturer: Optional[str] = Field(None, max_length=128)
    model: Optional[str] = Field(None, max_length=128)
    sw_version: Optional[str] = Field(None, max_length=64)
    hw_version: Optional[str] = Field(None, max_length=64)
    serial_number: Optional[str] = Field(None, max_length=128)
    mac_address: Optional[str] = Field(None, max_length=32)
    ip_address: Optional[str] = Field(None, max_length=64)
    status: Optional[str] = Field(None, description=f"One of: {', '.join(DEVICE_STATUSES)}")
    is_controllable: Optional[bool] = None
    is_configurable: Optional[bool] = None
    battery_level: Optional[int] = None
    signal_strength: Optional[int] = None
    attributes: Optional[Dict[str, Any]] = None


class DeviceRead(BaseModel):
    """Schema for device responses."""
    id: uuid.UUID
    tenant_id: uuid.UUID
    integration_id: Optional[uuid.UUID]
    room_id: Optional[uuid.UUID]
    product_id: Optional[uuid.UUID]
    ha_entity_id: str
    ha_domain: str
    friendly_name: str
    device_type: str
    manufacturer: Optional[str]
    model: Optional[str]
    sw_version: Optional[str]
    hw_version: Optional[str]
    serial_number: Optional[str]
    mac_address: Optional[str]
    ip_address: Optional[str]
    status: str
    is_controllable: bool
    is_configurable: bool
    battery_level: Optional[int]
    signal_strength: Optional[int]
    last_seen: Optional[datetime]
    last_changed: Optional[datetime]
    last_updated: Optional[datetime]
    attributes: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaginatedDeviceResponse(BaseModel):
    items: List[DeviceRead]
    total: int
    page: int
    page_size: int
    pages: int


class DeviceControlRequest(BaseModel):
    """Schema for controlling a device via HA service calls."""
    service: str = Field(..., description="HA service name, e.g. turn_on, turn_off, toggle, lock, unlock, set_brightness")
    service_data: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional service data, e.g. {'brightness': 128} for dimming",
    )


class DeviceControlResponse(BaseModel):
    success: bool
    entity_id: str
    service: str
    ha_response: Any


class DeviceStateResponse(BaseModel):
    entity_id: str
    state: str
    attributes: Dict[str, Any]
    last_changed: Optional[str]
    last_updated: Optional[str]
    fetched_at: datetime


class DeviceSyncResponse(BaseModel):
    entity_id: str
    synced: bool
    state: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_ha_client(session, tenant_id: uuid.UUID) -> Optional[HARestClient]:
    """Return a configured HARestClient for the tenant's primary integration."""
    stmt = select(IoTIntegration).where(
        IoTIntegration.tenant_id == tenant_id,
        IoTIntegration.is_primary.is_(True),
    )
    result = await session.execute(stmt)
    integration = result.scalar_one_or_none()
    if not integration:
        # Fall back to any integration
        stmt = select(IoTIntegration).where(
            IoTIntegration.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        integration = result.scalar_one_or_none()
    if not integration:
        return None
    token = decrypt_token(integration.ha_token_encrypted)
    return HARestClient(integration.ha_url, token)


def _device_to_read(device: IoTDevice) -> DeviceRead:
    """Convert an IoTDevice ORM instance to a DeviceRead schema."""
    return DeviceRead.model_validate(device)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedDeviceResponse)
async def list_devices(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    device_type: Optional[str] = Query(None, description="Filter by device type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    room_id: Optional[uuid.UUID] = Query(None, description="Filter by room ID"),
    ha_domain: Optional[str] = Query(None, description="Filter by HA domain"),
    search: Optional[str] = Query(None, description="Search by friendly name or entity ID"),
    is_controllable: Optional[bool] = Query(None, description="Filter by controllability"),
    product_id: Optional[uuid.UUID] = Query(None, description="Filter by linked inventory product"),
):
    """List IoT devices with optional filters and pagination."""
    async with get_session() as session:
        # Base query scoped to tenant
        stmt = select(IoTDevice).where(IoTDevice.tenant_id == ctx.tenant_id)

        # Apply filters
        if device_type:
            stmt = stmt.where(IoTDevice.device_type == device_type)
        if status:
            stmt = stmt.where(IoTDevice.status == status)
        if room_id:
            stmt = stmt.where(IoTDevice.room_id == room_id)
        if ha_domain:
            stmt = stmt.where(IoTDevice.ha_domain == ha_domain)
        if is_controllable is not None:
            stmt = stmt.where(IoTDevice.is_controllable == is_controllable)
        if product_id:
            stmt = stmt.where(IoTDevice.product_id == product_id)
        if search:
            search_term = f"%{search}%"
            stmt = stmt.where(
                IoTDevice.friendly_name.ilike(search_term)
                | IoTDevice.ha_entity_id.ilike(search_term)
            )

        # Count total
        count_stmt = select(func.count(IoTDevice.id)).where(
            IoTDevice.tenant_id == ctx.tenant_id
        )
        if device_type:
            count_stmt = count_stmt.where(IoTDevice.device_type == device_type)
        if status:
            count_stmt = count_stmt.where(IoTDevice.status == status)
        if room_id:
            count_stmt = count_stmt.where(IoTDevice.room_id == room_id)
        if ha_domain:
            count_stmt = count_stmt.where(IoTDevice.ha_domain == ha_domain)
        if is_controllable is not None:
            count_stmt = count_stmt.where(IoTDevice.is_controllable == is_controllable)
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

        return PaginatedDeviceResponse(
            items=[_device_to_read(d) for d in devices],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(
    device_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get a single IoT device by ID."""
    async with get_session() as session:
        stmt = select(IoTDevice).where(
            IoTDevice.id == device_id,
            IoTDevice.tenant_id == ctx.tenant_id,
        )
        result = await session.execute(stmt)
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        return _device_to_read(device)


@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def register_device(
    body: DeviceCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Register a new IoT device in the tenant's device registry."""
    async with get_session() as session:
        # Check for duplicate ha_entity_id within tenant
        existing_stmt = select(IoTDevice).where(
            IoTDevice.tenant_id == ctx.tenant_id,
            IoTDevice.ha_entity_id == body.ha_entity_id,
        )
        existing_result = await session.execute(existing_stmt)
        if existing_result.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"Device with ha_entity_id '{body.ha_entity_id}' already exists for this tenant",
            )

        device = IoTDevice(
            tenant_id=ctx.tenant_id,
            ha_entity_id=body.ha_entity_id,
            ha_domain=body.ha_domain,
            friendly_name=body.friendly_name,
            device_type=body.device_type,
            integration_id=body.integration_id,
            room_id=body.room_id,
            product_id=body.product_id,
            manufacturer=body.manufacturer,
            model=body.model,
            sw_version=body.sw_version,
            hw_version=body.hw_version,
            serial_number=body.serial_number,
            mac_address=body.mac_address,
            ip_address=body.ip_address,
            is_controllable=body.is_controllable,
            is_configurable=body.is_configurable,
            attributes=body.attributes or {},
        )
        session.add(device)
        await session.flush()
        await session.refresh(device)
        return _device_to_read(device)


@router.put("/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: uuid.UUID,
    body: DeviceUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Update an existing IoT device."""
    async with get_session() as session:
        stmt = select(IoTDevice).where(
            IoTDevice.id == device_id,
            IoTDevice.tenant_id == ctx.tenant_id,
        )
        result = await session.execute(stmt)
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(device, field, value)

        await session.flush()
        await session.refresh(device)
        return _device_to_read(device)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Delete an IoT device from the registry."""
    async with get_session() as session:
        stmt = select(IoTDevice).where(
            IoTDevice.id == device_id,
            IoTDevice.tenant_id == ctx.tenant_id,
        )
        result = await session.execute(stmt)
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        await session.delete(device)


@router.post("/{device_id}/control", response_model=DeviceControlResponse)
async def control_device(
    device_id: uuid.UUID,
    body: DeviceControlRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Control a device by calling a Home Assistant service.

    Common service calls:
    - light/turn_on, light/turn_off, light/toggle
    - light/turn_on with brightness in service_data (dimming)
    - switch/turn_on, switch/turn_off, switch/toggle
    - lock/lock, lock/unlock
    - climate/set_temperature, climate/set_hvac_mode
    - alarm_control_panel/arm_away, alarm_control_panel/disarm
    """
    async with get_session() as session:
        stmt = select(IoTDevice).where(
            IoTDevice.id == device_id,
            IoTDevice.tenant_id == ctx.tenant_id,
        )
        result = await session.execute(stmt)
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        if not device.is_controllable:
            raise HTTPException(
                status_code=400,
                detail=f"Device '{device.friendly_name}' is not controllable",
            )

        ha_client = await _get_ha_client(session, ctx.tenant_id)
        if not ha_client:
            raise HTTPException(
                status_code=503,
                detail="No Home Assistant integration configured for this tenant",
            )

        try:
            target = {"entity_id": device.ha_entity_id}
            ha_response = await ha_client.call_service(
                domain=device.ha_domain,
                service=body.service,
                service_data=body.service_data or {},
                target=target,
            )
            return DeviceControlResponse(
                success=True,
                entity_id=device.ha_entity_id,
                service=f"{device.ha_domain}/{body.service}",
                ha_response=ha_response,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Home Assistant service call failed: {exc}",
            ) from exc
        finally:
            await ha_client.close()


@router.post("/{device_id}/sync", response_model=DeviceSyncResponse)
async def sync_device(
    device_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Sync a single device's state from Home Assistant.

    Fetches the current entity state from HA and updates the local
    device record (status, attributes, last_seen, last_changed).
    """
    async with get_session() as session:
        stmt = select(IoTDevice).where(
            IoTDevice.id == device_id,
            IoTDevice.tenant_id == ctx.tenant_id,
        )
        result = await session.execute(stmt)
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        ha_client = await _get_ha_client(session, ctx.tenant_id)
        if not ha_client:
            raise HTTPException(
                status_code=503,
                detail="No Home Assistant integration configured for this tenant",
            )

        try:
            ha_state = await ha_client.get_state(device.ha_entity_id)

            # Update device fields from HA state
            state_value = ha_state.get("state", "unavailable")
            device.status = ha_state_to_device_status(state_value)
            device.attributes = ha_state.get("attributes", {})

            # Parse timestamps from HA
            last_changed = ha_state.get("last_changed")
            last_updated = ha_state.get("last_updated")
            if last_changed:
                device.last_changed = datetime.fromisoformat(
                    last_changed.replace("Z", "+00:00")
                )
            if last_updated:
                device.last_updated = datetime.fromisoformat(
                    last_updated.replace("Z", "+00:00")
                )
            device.last_seen = datetime.now(timezone.utc)

            # Update friendly_name if available in HA attributes
            ha_friendly_name = ha_state.get("attributes", {}).get("friendly_name")
            if ha_friendly_name:
                device.friendly_name = ha_friendly_name

            await session.flush()
            await session.refresh(device)

            return DeviceSyncResponse(
                entity_id=device.ha_entity_id,
                synced=True,
                state=state_value,
                attributes=device.attributes,
                message="Device synced successfully from Home Assistant",
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Home Assistant sync failed: {exc}",
            ) from exc
        finally:
            await ha_client.close()


@router.get("/{device_id}/state", response_model=DeviceStateResponse)
async def get_device_state(
    device_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get the current live state of a device from Home Assistant.

    This queries HA in real-time and does not update the local registry.
    Use POST /{id}/sync to persist the state locally.
    """
    async with get_session() as session:
        stmt = select(IoTDevice).where(
            IoTDevice.id == device_id,
            IoTDevice.tenant_id == ctx.tenant_id,
        )
        result = await session.execute(stmt)
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        ha_client = await _get_ha_client(session, ctx.tenant_id)
        if not ha_client:
            raise HTTPException(
                status_code=503,
                detail="No Home Assistant integration configured for this tenant",
            )

        try:
            ha_state = await ha_client.get_state(device.ha_entity_id)
            return DeviceStateResponse(
                entity_id=device.ha_entity_id,
                state=ha_state.get("state", "unknown"),
                attributes=ha_state.get("attributes", {}),
                last_changed=ha_state.get("last_changed"),
                last_updated=ha_state.get("last_updated"),
                fetched_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Home Assistant state query failed: {exc}",
            ) from exc
        finally:
            await ha_client.close()
