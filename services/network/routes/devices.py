"""Network device management routes.

Manages ONTs, routers, gateways, switches, and access points per service.
Provides device CRUD, status monitoring, and config snapshot management.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from services.common.auth import AuthContext, get_auth_context
from services.network.database import get_session
from services.network.models import NetworkDevice, NetworkService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/devices", tags=["Devices"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

DEVICE_TYPES = {"ont", "router", "gateway", "switch", "access_point", "media_converter"}
DEVICE_STATUSES = {"active", "offline", "error", "provisioning", "decommissioned"}
MGMT_PROTOCOLS = {"snmp", "tr069", "ssh", "telnet", "http"}


class DeviceCreate(BaseModel):
    service_id: uuid.UUID
    device_type: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    mac_address: Optional[str] = None
    firmware_version: Optional[str] = None
    management_ip: Optional[str] = None
    management_protocol: Optional[str] = None
    product_id: Optional[uuid.UUID] = None
    config_snapshot: Optional[dict] = None


class DeviceUpdate(BaseModel):
    device_type: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    mac_address: Optional[str] = None
    firmware_version: Optional[str] = None
    management_ip: Optional[str] = None
    management_protocol: Optional[str] = None
    status: Optional[str] = None
    product_id: Optional[uuid.UUID] = None
    config_snapshot: Optional[dict] = None


class DeviceRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    service_id: uuid.UUID
    device_type: str
    manufacturer: Optional[str]
    model: Optional[str]
    serial_number: Optional[str]
    mac_address: Optional[str]
    firmware_version: Optional[str]
    management_ip: Optional[str]
    management_protocol: Optional[str]
    status: str
    last_seen: Optional[datetime]
    product_id: Optional[uuid.UUID]
    config_snapshot: Optional[dict]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DeviceStatusUpdate(BaseModel):
    status: str
    last_seen: Optional[datetime] = None


class PaginatedDeviceResponse(BaseModel):
    items: list[DeviceRead]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Device CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def register_device(
    body: DeviceCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Register a network device (ONT, router, etc.) for a service."""
    with get_session() as session:
        svc = session.execute(
            select(NetworkService).where(
                NetworkService.id == body.service_id,
                NetworkService.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if not svc:
            raise HTTPException(status_code=404, detail="Network service not found")

        device = NetworkDevice(
            tenant_id=ctx.tenant_id,
            service_id=body.service_id,
            device_type=body.device_type,
            manufacturer=body.manufacturer,
            model=body.model,
            serial_number=body.serial_number,
            mac_address=body.mac_address,
            firmware_version=body.firmware_version,
            management_ip=body.management_ip,
            management_protocol=body.management_protocol,
            product_id=body.product_id,
            config_snapshot=body.config_snapshot,
            status="active",
            last_seen=datetime.now(timezone.utc),
        )
        session.add(device)
        session.flush()
        session.refresh(device)

        # Update service ONT serial if this is an ONT
        if body.device_type == "ont" and body.serial_number and not svc.ont_serial:
            svc.ont_serial = body.serial_number
            session.flush()

        return DeviceRead.model_validate(device)


@router.get("", response_model=PaginatedDeviceResponse)
async def list_devices(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service_id: Optional[uuid.UUID] = None,
    device_type: Optional[str] = None,
    status: Optional[str] = None,
    serial_number: Optional[str] = None,
):
    """List network devices with filters."""
    with get_session() as session:
        stmt = select(NetworkDevice).where(NetworkDevice.tenant_id == ctx.tenant_id)
        count_stmt = select(func.count(NetworkDevice.id)).where(
            NetworkDevice.tenant_id == ctx.tenant_id
        )

        if service_id:
            stmt = stmt.where(NetworkDevice.service_id == service_id)
            count_stmt = count_stmt.where(NetworkDevice.service_id == service_id)
        if device_type:
            stmt = stmt.where(NetworkDevice.device_type == device_type)
            count_stmt = count_stmt.where(NetworkDevice.device_type == device_type)
        if status:
            stmt = stmt.where(NetworkDevice.status == status)
            count_stmt = count_stmt.where(NetworkDevice.status == status)
        if serial_number:
            stmt = stmt.where(NetworkDevice.serial_number == serial_number)
            count_stmt = count_stmt.where(NetworkDevice.serial_number == serial_number)

        total = session.execute(count_stmt).scalar() or 0
        stmt = stmt.order_by(NetworkDevice.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size)
        result = session.execute(stmt)

        return PaginatedDeviceResponse(
            items=[DeviceRead.model_validate(d) for d in result.scalars().all()],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(
    device_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        device = session.execute(
            select(NetworkDevice).where(
                NetworkDevice.id == device_id,
                NetworkDevice.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        return DeviceRead.model_validate(device)


@router.put("/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: uuid.UUID,
    body: DeviceUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        device = session.execute(
            select(NetworkDevice).where(
                NetworkDevice.id == device_id,
                NetworkDevice.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(device, field, value)
        device.updated_at = datetime.now(timezone.utc)

        session.flush()
        session.refresh(device)
        return DeviceRead.model_validate(device)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        device = session.execute(
            select(NetworkDevice).where(
                NetworkDevice.id == device_id,
                NetworkDevice.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        session.delete(device)


@router.post("/{device_id}/heartbeat")
async def device_heartbeat(
    device_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Update device last_seen timestamp (called by device probes)."""
    with get_session() as session:
        device = session.execute(
            select(NetworkDevice).where(
                NetworkDevice.id == device_id,
                NetworkDevice.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        device.last_seen = datetime.now(timezone.utc)
        if device.status == "offline":
            device.status = "active"
        session.flush()
        return {"id": str(device.id), "status": device.status, "last_seen": device.last_seen.isoformat()}


@router.post("/{device_id}/config-snapshot")
async def save_config_snapshot(
    device_id: uuid.UUID,
    config: dict,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Save a configuration snapshot for a device (last known good config)."""
    with get_session() as session:
        device = session.execute(
            select(NetworkDevice).where(
                NetworkDevice.id == device_id,
                NetworkDevice.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        device.config_snapshot = config
        device.updated_at = datetime.now(timezone.utc)
        session.flush()
        return {"id": str(device.id), "config_saved": True}
