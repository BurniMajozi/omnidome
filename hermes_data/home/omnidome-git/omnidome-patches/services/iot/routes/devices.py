"""IoT device routes — CRUD, telemetry history, health summary, remote reboot."""

import uuid
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.common.auth import AuthContext, get_auth_context
from iot.database import session_scope
from iot.models import Device, TelemetryReading
from iot.schemas import (
    DeviceCreate, DeviceRead, DeviceUpdate, DeviceWithTelemetry,
    DeviceHealthSummary, PaginatedResponse, RebootResponse,
    TelemetryRead,
)
from sqlalchemy import select, func, and_

router = APIRouter(prefix="/api/v1/iot/devices", tags=["IoT Devices"])


@router.get("", response_model=PaginatedResponse)
async def list_devices(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[uuid.UUID] = Query(None),
    device_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Search by serial number or model"),
):
    """List devices with optional filtering and pagination."""
    async with session_scope() as session:
        query = select(Device).where(Device.tenant_id == ctx.tenant_id)

        if customer_id:
            query = query.where(Device.customer_id == customer_id)
        if device_type:
            query = query.where(Device.device_type == device_type)
        if status:
            query = query.where(Device.status == status)
        if search:
            search_term = f"%{search}%"
            query = query.where(
                Device.serial_number.ilike(search_term) | Device.model.ilike(search_term)
            )

        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        items = (
            await session.execute(
                query.order_by(Device.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

        return PaginatedResponse(
            items=[DeviceRead.model_validate(i) for i in items],
            total=total or 0,
            page=page,
            page_size=page_size,
            pages=max(1, math.ceil((total or 0) / page_size)),
        )


@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def register_device(
    body: DeviceCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Register a new CPE device."""
    async with session_scope() as session:
        # Check for duplicate device_id within tenant
        existing = await session.scalar(
            select(Device).where(
                Device.tenant_id == ctx.tenant_id,
                Device.device_id == body.device_id,
            )
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Device with device_id '{body.device_id}' already exists in this tenant",
            )

        device = Device(
            tenant_id=ctx.tenant_id,
            device_id=body.device_id,
            customer_id=body.customer_id,
            device_type=body.device_type,
            model=body.model,
            serial_number=body.serial_number,
            firmware_version=body.firmware_version,
            status=body.status,
            ip_address=body.ip_address,
            mac_address=body.mac_address,
            signal_strength=body.signal_strength,
            uptime_seconds=body.uptime_seconds,
            location=body.location,
        )
        session.add(device)
        await session.flush()
        await session.refresh(device)
        return DeviceRead.model_validate(device)


@router.get("/{device_id}", response_model=DeviceWithTelemetry)
async def get_device(
    device_id: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get a single device with its latest telemetry readings."""
    async with session_scope() as session:
        device = await session.scalar(
            select(Device).where(
                Device.tenant_id == ctx.tenant_id,
                Device.device_id == device_id,
            )
        )
        if not device:
            raise HTTPException(404, "Device not found")

        # Fetch latest telemetry — one per metric type
        latest_telemetry = []
        for metric in ["signal_strength", "uptime", "throughput", "temperature", "packet_loss", "latency"]:
            reading = await session.scalar(
                select(TelemetryReading)
                .where(
                    TelemetryReading.device_id == device.id,
                    TelemetryReading.metric == metric,
                )
                .order_by(TelemetryReading.recorded_at.desc())
                .limit(1)
            )
            if reading:
                latest_telemetry.append(TelemetryRead.model_validate(reading))

        device_data = DeviceWithTelemetry.model_validate(device)
        device_data.latest_telemetry = latest_telemetry
        return device_data


@router.put("/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: str,
    body: DeviceUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Update device fields (firmware, status, etc.)."""
    async with session_scope() as session:
        device = await session.scalar(
            select(Device).where(
                Device.tenant_id == ctx.tenant_id,
                Device.device_id == device_id,
            )
        )
        if not device:
            raise HTTPException(404, "Device not found")

        update = body.model_dump(exclude_unset=True)
        for k, v in update.items():
            setattr(device, k, v)

        await session.flush()
        await session.refresh(device)
        return DeviceRead.model_validate(device)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deregister_device(
    device_id: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Deregister (delete) a device and its telemetry data."""
    async with session_scope() as session:
        device = await session.scalar(
            select(Device).where(
                Device.tenant_id == ctx.tenant_id,
                Device.device_id == device_id,
            )
        )
        if not device:
            raise HTTPException(404, "Device not found")
        await session.delete(device)
        await session.flush()
        return None


@router.get("/{device_id}/telemetry", response_model=PaginatedResponse)
async def get_telemetry_history(
    device_id: str,
    ctx: AuthContext = Depends(get_auth_context),
    metric: Optional[str] = Query(None, description="Filter by metric type"),
    hours: int = Query(24, ge=1, le=720, description="Hours of history (default 24h)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Get telemetry history for a device, filtered by metric and time range."""
    async with session_scope() as session:
        device = await session.scalar(
            select(Device).where(
                Device.tenant_id == ctx.tenant_id,
                Device.device_id == device_id,
            )
        )
        if not device:
            raise HTTPException(404, "Device not found")

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        query = select(TelemetryReading).where(
            TelemetryReading.device_id == device.id,
            TelemetryReading.recorded_at >= cutoff,
        )

        if metric:
            query = query.where(TelemetryReading.metric == metric)

        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        items = (
            await session.execute(
                query.order_by(TelemetryReading.recorded_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

        return PaginatedResponse(
            items=[TelemetryRead.model_validate(i) for i in items],
            total=total or 0,
            page=page,
            page_size=page_size,
            pages=max(1, math.ceil((total or 0) / page_size)),
        )


@router.get("/{device_id}/health", response_model=DeviceHealthSummary)
async def get_device_health(
    device_id: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get a health summary for a specific device."""
    async with session_scope() as session:
        device = await session.scalar(
            select(Device).where(
                Device.tenant_id == ctx.tenant_id,
                Device.device_id == device_id,
            )
        )
        if not device:
            raise HTTPException(404, "Device not found")

        alerts = []
        metrics_summary = {}

        # Gather latest readings for health assessment
        for metric in ["signal_strength", "uptime", "throughput", "temperature", "packet_loss", "latency"]:
            reading = await session.scalar(
                select(TelemetryReading)
                .where(
                    TelemetryReading.device_id == device.id,
                    TelemetryReading.metric == metric,
                )
                .order_by(TelemetryReading.recorded_at.desc())
                .limit(1)
            )
            if reading:
                metrics_summary[metric] = {
                    "value": reading.value,
                    "unit": reading.unit,
                    "recorded_at": reading.recorded_at.isoformat(),
                }

        # Determine overall status and alerts
        overall_status = device.status

        if device.status == "error":
            alerts.append("Device is in error state")

        if device.last_seen:
            offline_threshold = datetime.now(timezone.utc) - timedelta(minutes=15)
            if device.last_seen < offline_threshold and device.status == "online":
                alerts.append(f"Device last seen {device.last_seen.isoformat()} — may be offline")
        else:
            alerts.append("Device has never reported in")

        # Signal strength check
        if "signal_strength" in metrics_summary:
            ss = metrics_summary["signal_strength"]["value"]
            if ss < -27:
                alerts.append(f"Weak signal: {ss} dBm (below -27 dBm threshold)")
                if overall_status == "online":
                    overall_status = "warning"

        # Packet loss check
        if "packet_loss" in metrics_summary:
            pl = metrics_summary["packet_loss"]["value"]
            if pl > 5.0:
                alerts.append(f"High packet loss: {pl}% (above 5% threshold)")
                if overall_status == "online":
                    overall_status = "warning"

        # Temperature check
        if "temperature" in metrics_summary:
            temp = metrics_summary["temperature"]["value"]
            if temp > 70.0:
                alerts.append(f"High temperature: {temp}°C (above 70°C threshold)")
                if overall_status == "online":
                    overall_status = "warning"

        return DeviceHealthSummary(
            device_id=device.device_id,
            customer_id=device.customer_id,
            overall_status=overall_status,
            last_seen=device.last_seen,
            alerts=alerts,
            metrics_summary=metrics_summary,
        )


@router.post("/{device_id}/reboot", response_model=RebootResponse)
async def trigger_reboot(
    device_id: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Trigger a remote reboot of the device (mock implementation)."""
    async with session_scope() as session:
        device = await session.scalar(
            select(Device).where(
                Device.tenant_id == ctx.tenant_id,
                Device.device_id == device_id,
            )
        )
        if not device:
            raise HTTPException(404, "Device not found")

        # Mock: In production, this would send a TR-069 or SNMP reboot command
        now = datetime.now(timezone.utc)
        device.last_seen = now
        device.status = "offline"
        await session.flush()

        return RebootResponse(
            device_id=device.device_id,
            status="reboot_initiated",
            message=f"Reboot command sent to device {device.model or device.device_id}. Device will come back online shortly.",
            initiated_at=now,
        )
