"""Room / Zone management routes for IoT devices.

All routes use async SQLAlchemy with tenant-scoped queries.
Maps to Home Assistant areas.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.iot.database import get_session
from services.iot.models import IoTDevice, IoTRoom

logger = logging.getLogger("iot.rooms")

router = APIRouter(prefix="/rooms", tags=["iot-rooms"])


# ---------------------------------------------------------------------------
# Helper: fetch a room or 404
# ---------------------------------------------------------------------------

async def _get_room_or_404(session, room_id: uuid.UUID, tenant_id: uuid.UUID) -> IoTRoom:
    result = await session.execute(
        select(IoTRoom).where(
            IoTRoom.id == room_id,
            IoTRoom.tenant_id == tenant_id,
        )
    )
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    return room


# ---------------------------------------------------------------------------
# Helper: serialize a room to a dict
# ---------------------------------------------------------------------------

def _room_dict(room: IoTRoom) -> dict:
    return {
        "id": str(room.id),
        "tenant_id": str(room.tenant_id),
        "ha_area_id": room.ha_area_id,
        "name": room.name,
        "icon": room.icon,
        "floor": room.floor,
        "description": room.description,
        "created_at": room.created_at.isoformat() if room.created_at else None,
        "updated_at": room.updated_at.isoformat() if room.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Helper: serialize a device to a dict (room-scoped subset)
# ---------------------------------------------------------------------------

def _device_summary(d: IoTDevice) -> dict:
    return {
        "id": str(d.id),
        "ha_entity_id": d.ha_entity_id,
        "friendly_name": d.friendly_name,
        "device_type": d.device_type,
        "status": d.status,
        "is_controllable": d.is_controllable,
        "battery_level": d.battery_level,
        "signal_strength": d.signal_strength,
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
    }


# ---------------------------------------------------------------------------
# GET /api/iot/rooms — List rooms
# ---------------------------------------------------------------------------

@router.get("")
async def list_rooms(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    name: str | None = Query(None),
    floor: int | None = Query(None),
):
    """List all rooms/zones for the current tenant."""
    async with get_session() as session:
        stmt = select(IoTRoom).where(IoTRoom.tenant_id == ctx.tenant_id)
        count_stmt = select(func.count(IoTRoom.id)).where(IoTRoom.tenant_id == ctx.tenant_id)

        if name:
            stmt = stmt.where(IoTRoom.name.ilike(f"%{name}%"))
            count_stmt = count_stmt.where(IoTRoom.name.ilike(f"%{name}%"))
        if floor is not None:
            stmt = stmt.where(IoTRoom.floor == floor)
            count_stmt = count_stmt.where(IoTRoom.floor == floor)

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = (
            stmt.order_by(IoTRoom.floor.nulls_last(), IoTRoom.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items_result = await session.execute(stmt)
        rooms = items_result.scalars().all()

        return {
            "items": [_room_dict(r) for r in rooms],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": pages,
        }


# ---------------------------------------------------------------------------
# GET /api/iot/rooms/{room_id} — Room detail
# ---------------------------------------------------------------------------

@router.get("/{room_id}")
async def get_room(
    room_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get a single room by ID."""
    async with get_session() as session:
        room = await _get_room_or_404(session, room_id, ctx.tenant_id)
        return _room_dict(room)


# ---------------------------------------------------------------------------
# POST /api/iot/rooms — Create a room
# ---------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_room(
    body: dict,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create a new room/zone."""
    name = body.get("name")
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Field 'name' is required",
        )

    async with get_session() as session:
        room = IoTRoom(
            tenant_id=ctx.tenant_id,
            ha_area_id=body.get("ha_area_id"),
            name=name,
            icon=body.get("icon"),
            floor=body.get("floor"),
            description=body.get("description"),
        )
        session.add(room)
        await session.flush()
        await session.refresh(room)
        logger.info("Room %s created (tenant %s)", room.id, ctx.tenant_id)
        return _room_dict(room)


# ---------------------------------------------------------------------------
# PUT /api/iot/rooms/{room_id} — Update a room
# ---------------------------------------------------------------------------

@router.put("/{room_id}")
async def update_room(
    room_id: uuid.UUID,
    body: dict,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Update an existing room/zone."""
    async with get_session() as session:
        room = await _get_room_or_404(session, room_id, ctx.tenant_id)

        if "name" in body:
            room.name = body["name"]
        if "ha_area_id" in body:
            room.ha_area_id = body["ha_area_id"]
        if "icon" in body:
            room.icon = body["icon"]
        if "floor" in body:
            room.floor = body["floor"]
        if "description" in body:
            room.description = body["description"]

        await session.flush()
        await session.refresh(room)
        logger.info("Room %s updated (tenant %s)", room.id, ctx.tenant_id)
        return _room_dict(room)


# ---------------------------------------------------------------------------
# DELETE /api/iot/rooms/{room_id} — Delete a room
# ---------------------------------------------------------------------------

@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Delete a room. Devices in the room are unassigned (room_id set to NULL)."""
    async with get_session() as session:
        room = await _get_room_or_404(session, room_id, ctx.tenant_id)
        await session.delete(room)
        await session.flush()
        logger.info("Room %s deleted (tenant %s)", room_id, ctx.tenant_id)
        return None


# ---------------------------------------------------------------------------
# GET /api/iot/rooms/{room_id}/devices — List devices in a room
# ---------------------------------------------------------------------------

@router.get("/{room_id}/devices")
async def list_room_devices(
    room_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all devices assigned to a specific room."""
    async with get_session() as session:
        # Verify room exists and belongs to tenant
        await _get_room_or_404(session, room_id, ctx.tenant_id)

        stmt = (
            select(IoTDevice)
            .where(
                IoTDevice.room_id == room_id,
                IoTDevice.tenant_id == ctx.tenant_id,
            )
        )
        count_stmt = select(func.count(IoTDevice.id)).where(
            IoTDevice.room_id == room_id,
            IoTDevice.tenant_id == ctx.tenant_id,
        )

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = (
            stmt.order_by(IoTDevice.friendly_name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items_result = await session.execute(stmt)
        devices = items_result.scalars().all()

        return {
            "items": [_device_summary(d) for d in devices],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": pages,
        }


# ---------------------------------------------------------------------------
# POST /api/iot/rooms/{room_id}/devices/{device_id} — Assign device to room
# ---------------------------------------------------------------------------

@router.post("/{room_id}/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def assign_device_to_room(
    room_id: uuid.UUID,
    device_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Assign an IoT device to a room."""
    async with get_session() as session:
        # Verify room exists
        await _get_room_or_404(session, room_id, ctx.tenant_id)

        # Fetch device
        result = await session.execute(
            select(IoTDevice).where(
                IoTDevice.id == device_id,
                IoTDevice.tenant_id == ctx.tenant_id,
            )
        )
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found",
            )

        device.room_id = room_id
        await session.flush()
        logger.info(
            "Device %s assigned to room %s (tenant %s)",
            device_id, room_id, ctx.tenant_id,
        )
        return None


# ---------------------------------------------------------------------------
# DELETE /api/iot/rooms/{room_id}/devices/{device_id} — Remove device from room
# ---------------------------------------------------------------------------

@router.delete("/{room_id}/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_device_from_room(
    room_id: uuid.UUID,
    device_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Remove an IoT device from a room (sets device.room_id to NULL)."""
    async with get_session() as session:
        # Verify room exists
        await _get_room_or_404(session, room_id, ctx.tenant_id)

        # Fetch device
        result = await session.execute(
            select(IoTDevice).where(
                IoTDevice.id == device_id,
                IoTDevice.tenant_id == ctx.tenant_id,
            )
        )
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found",
            )

        if str(device.room_id) != str(room_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Device is not assigned to this room",
            )

        device.room_id = None
        await session.flush()
        logger.info(
            "Device %s removed from room %s (tenant %s)",
            device_id, room_id, ctx.tenant_id,
        )
        return None
