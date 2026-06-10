"""IoT camera routes — list cameras, snapshots, stream URLs, and motion events."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.iot.database import get_session
from services.iot.ha_client import HARestClient, decrypt_token
from services.iot.models import IoTDevice, IoTEvent, IoTIntegration

router = APIRouter(prefix="/api/iot/cameras", tags=["iot-cameras"])


async def _get_ha_client(session, tenant_id: uuid.UUID) -> HARestClient:
    """Resolve the primary HA integration for the tenant and return a configured client."""
    integration = await session.scalar(
        select(IoTIntegration).where(
            IoTIntegration.tenant_id == tenant_id,
            IoTIntegration.is_primary.is_(True),
        )
    )
    if not integration:
        # Fall back to any connected integration
        integration = await session.scalar(
            select(IoTIntegration).where(
                IoTIntegration.tenant_id == tenant_id,
                IoTIntegration.status == "connected",
            )
        )
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No Home Assistant integration configured for this tenant",
        )
    token = decrypt_token(integration.ha_token_encrypted)
    return HARestClient(ha_url=integration.ha_url, token=token)


# ---------------------------------------------------------------------------
# GET / — list camera devices
# ---------------------------------------------------------------------------

@router.get("")
async def list_cameras(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    room_id: Optional[uuid.UUID] = Query(None),
):
    """List all camera-type IoT devices for the current tenant."""
    async with get_session() as session:
        query = select(IoTDevice).where(
            IoTDevice.tenant_id == ctx.tenant_id,
            IoTDevice.device_type == "camera",
        )

        if status_filter:
            query = query.where(IoTDevice.status == status_filter)
        if room_id:
            query = query.where(IoTDevice.room_id == room_id)

        total = await session.scalar(
            select(func.count()).select_from(query.subquery())
        )

        items = (
            await session.execute(
                query.order_by(IoTDevice.friendly_name)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

    return {
        "items": [
            {
                "id": str(d.id),
                "ha_entity_id": d.ha_entity_id,
                "friendly_name": d.friendly_name,
                "device_type": d.device_type,
                "status": d.status,
                "manufacturer": d.manufacturer,
                "model": d.model,
                "sw_version": d.sw_version,
                "hw_version": d.hw_version,
                "serial_number": d.serial_number,
                "mac_address": d.mac_address,
                "ip_address": d.ip_address,
                "battery_level": d.battery_level,
                "signal_strength": d.signal_strength,
                "is_controllable": d.is_controllable,
                "is_configurable": d.is_configurable,
                "room_id": str(d.room_id) if d.room_id else None,
                "integration_id": str(d.integration_id) if d.integration_id else None,
                "attributes": d.attributes,
                "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                "last_changed": d.last_changed.isoformat() if d.last_changed else None,
                "last_updated": d.last_updated.isoformat() if d.last_updated else None,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "updated_at": d.updated_at.isoformat() if d.updated_at else None,
            }
            for d in items
        ],
        "total": total or 0,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size) if total else 1,
    }


# ---------------------------------------------------------------------------
# GET /{id}/snapshot — proxy camera image from HA
# ---------------------------------------------------------------------------

@router.get("/{camera_id}/snapshot")
async def get_camera_snapshot(
    camera_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Fetch a live snapshot image from the camera via Home Assistant."""
    async with get_session() as session:
        device = await session.get(IoTDevice, camera_id)
        if not device or device.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="Camera not found")
        if device.device_type != "camera":
            raise HTTPException(status_code=400, detail="Device is not a camera")

        ha_client = await _get_ha_client(session, ctx.tenant_id)

    image_bytes = await ha_client.get_camera_image(device.ha_entity_id)
    await ha_client.aclose()

    content_type = "image/jpeg"
    if device.attributes and isinstance(device.attributes, dict):
        content_type = device.attributes.get("content_type", content_type)

    return Response(
        content=image_bytes,
        media_type=content_type,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


# ---------------------------------------------------------------------------
# GET /{id}/stream — get camera stream URL
# ---------------------------------------------------------------------------

@router.get("/{camera_id}/stream")
async def get_camera_stream(
    camera_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get the camera stream URL from Home Assistant."""
    async with get_session() as session:
        device = await session.get(IoTDevice, camera_id)
        if not device or device.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="Camera not found")
        if device.device_type != "camera":
            raise HTTPException(status_code=400, detail="Device is not a camera")

        ha_client = await _get_ha_client(session, ctx.tenant_id)

    stream_url = await ha_client.get_camera_stream(device.ha_entity_id)
    await ha_client.aclose()

    return {
        "camera_id": str(device.id),
        "ha_entity_id": device.ha_entity_id,
        "stream_url": stream_url,
    }


# ---------------------------------------------------------------------------
# GET /{id}/motion-events — list motion detection events for camera
# ---------------------------------------------------------------------------

@router.get("/{camera_id}/motion-events")
async def list_motion_events(
    camera_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    hours: int = Query(24, ge=1, le=720, description="Lookback window in hours"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List motion detection events for a specific camera."""
    async with get_session() as session:
        device = await session.get(IoTDevice, camera_id)
        if not device or device.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="Camera not found")
        if device.device_type != "camera":
            raise HTTPException(status_code=400, detail="Device is not a camera")

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = select(IoTEvent).where(
            IoTEvent.tenant_id == ctx.tenant_id,
            IoTEvent.device_id == device.id,
            IoTEvent.event_type == "motion",
            IoTEvent.created_at >= cutoff,
        )

        total = await session.scalar(
            select(func.count()).select_from(query.subquery())
        )

        items = (
            await session.execute(
                query.order_by(IoTEvent.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

    return {
        "items": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "source": e.source,
                "message": e.message,
                "data": e.data,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in items
        ],
        "total": total or 0,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size) if total else 1,
    }
