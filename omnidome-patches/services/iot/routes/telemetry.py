"""IoT telemetry routes — ingestion, batch ingestion, dashboard, alerts."""

import uuid
import math
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.common.auth import AuthContext, get_auth_context
from iot.database import session_scope
from iot.models import Device, TelemetryReading
from iot.schemas import (
    AlertItem, DashboardSummary, DeviceHealthSummary, PaginatedResponse,
    TelemetryBatchCreate, TelemetryCreate, TelemetryRead,
)
from sqlalchemy import select, func, and_, text

router = APIRouter(prefix="/api/v1/iot/telemetry", tags=["IoT Telemetry"])


@router.post("", response_model=TelemetryRead, status_code=status.HTTP_201_CREATED)
async def ingest_telemetry(
    body: TelemetryCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Ingest a single telemetry reading from a CPE device."""
    async with session_scope() as session:
        device = await session.get(Device, body.device_id)
        if not device or device.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Device not found")

        reading = TelemetryReading(
            tenant_id=ctx.tenant_id,
            device_id=body.device_id,
            metric=body.metric,
            value=body.value,
            unit=body.unit,
        )
        session.add(reading)

        # Update device last_seen and signal_strength if applicable
        device.last_seen = datetime.now(timezone.utc)
        if body.metric == "signal_strength":
            device.signal_strength = body.value
        if body.metric == "uptime":
            device.uptime_seconds = int(body.value)

        await session.flush()
        await session.refresh(reading)
        return TelemetryRead.model_validate(reading)


@router.post("/batch", response_model=List[TelemetryRead], status_code=status.HTTP_201_CREATED)
async def ingest_batch_telemetry(
    body: TelemetryBatchCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Ingest a batch of telemetry readings (for bulk ingestion from CPE)."""
    async with session_scope() as session:
        device = await session.get(Device, body.device_id)
        if not device or device.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Device not found")

        now = datetime.now(timezone.utc)
        readings = []
        for item in body.readings:
            reading = TelemetryReading(
                tenant_id=ctx.tenant_id,
                device_id=body.device_id,
                metric=item.metric,
                value=item.value,
                unit=item.unit,
                recorded_at=now,
            )
            session.add(reading)
            readings.append(reading)

            # Update device last_seen and key metrics
            device.last_seen = now
            if item.metric == "signal_strength":
                device.signal_strength = item.value
            if item.metric == "uptime":
                device.uptime_seconds = int(item.value)

        await session.flush()
        for r in readings:
            await session.refresh(r)

        return [TelemetryRead.model_validate(r) for r in readings]


@router.get("/dashboard", response_model=DashboardSummary)
async def get_dashboard(
    ctx: AuthContext = Depends(get_auth_context),
):
    """
    Get IoT dashboard summary: total devices, online/offline counts,
    average signal strength, and recent alerts.
    """
    async with session_scope() as session:
        # Total devices
        total = await session.scalar(
            select(func.count()).select_from(
                select(Device).where(Device.tenant_id == ctx.tenant_id).subquery()
            )
        )

        # Status counts
        online_count = await session.scalar(
            select(func.count()).select_from(
                select(Device).where(
                    Device.tenant_id == ctx.tenant_id,
                    Device.status == "online",
                ).subquery()
            )
        )
        offline_count = await session.scalar(
            select(func.count()).select_from(
                select(Device).where(
                    Device.tenant_id == ctx.tenant_id,
                    Device.status == "offline",
                ).subquery()
            )
        )
        warning_count = await session.scalar(
            select(func.count()).select_from(
                select(Device).where(
                    Device.tenant_id == ctx.tenant_id,
                    Device.status == "warning",
                ).subquery()
            )
        )
        error_count = await session.scalar(
            select(func.count()).select_from(
                select(Device).where(
                    Device.tenant_id == ctx.tenant_id,
                    Device.status == "error",
                ).subquery()
            )
        )

        # Average signal strength from latest readings per device
        avg_signal = await session.scalar(
            select(func.avg(TelemetryReading.value)).where(
                TelemetryReading.tenant_id == ctx.tenant_id,
                TelemetryReading.metric == "signal_strength",
                TelemetryReading.recorded_at >= datetime.now(timezone.utc) - timedelta(hours=1),
            )
        )

        # Recent alerts — devices in warning or error state
        alert_devices = (
            await session.execute(
                select(Device).where(
                    Device.tenant_id == ctx.tenant_id,
                    Device.status.in_(["warning", "error"]),
                ).order_by(Device.updated_at.desc()).limit(10)
            )
        ).scalars().all()

        recent_alerts = []
        for device in alert_devices:
            alerts_list = []
            if device.status == "error":
                alerts_list.append("Device in error state")
            if device.status == "warning":
                alerts_list.append("Device in warning state")
            if device.signal_strength and device.signal_strength < -27:
                alerts_list.append(f"Weak signal: {device.signal_strength} dBm")
            if device.last_seen:
                threshold = datetime.now(timezone.utc) - timedelta(minutes=15)
                if device.last_seen < threshold:
                    alerts_list.append("Device not reporting")

            recent_alerts.append(
                DeviceHealthSummary(
                    device_id=device.device_id,
                    customer_id=device.customer_id,
                    overall_status=device.status,
                    last_seen=device.last_seen,
                    alerts=alerts_list,
                    metrics_summary={},
                )
            )

        return DashboardSummary(
            total_devices=total or 0,
            online_count=online_count or 0,
            offline_count=offline_count or 0,
            warning_count=warning_count or 0,
            error_count=error_count or 0,
            avg_signal_strength=round(avg_signal, 2) if avg_signal else None,
            recent_alerts=recent_alerts,
        )


@router.get("/alerts", response_model=List[AlertItem])
async def get_active_alerts(
    ctx: AuthContext = Depends(get_auth_context),
    hours: int = Query(1, ge=1, le=168, description="Lookback window in hours"),
):
    """
    Get active alerts — devices with:
    - signal_strength < -27 dBm
    - packet_loss > 5%
    - temperature > 70°C
    - status = error
    """
    async with session_scope() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        alerts = []

        # Subquery: latest reading per device per metric
        latest_readings = (
            select(
                TelemetryReading.device_id,
                TelemetryReading.metric,
                TelemetryReading.value,
                TelemetryReading.unit,
                TelemetryReading.recorded_at,
            )
            .distinct(TelemetryReading.device_id, TelemetryReading.metric)
            .where(
                TelemetryReading.tenant_id == ctx.tenant_id,
                TelemetryReading.recorded_at >= cutoff,
            )
            .order_by(
                TelemetryReading.device_id,
                TelemetryReading.metric,
                TelemetryReading.recorded_at.desc(),
            )
            .subquery()
        )

        # Fetch readings that breach thresholds
        breach_readings = (
            await session.execute(
                select(latest_readings).where(
                    (latest_readings.c.metric == "signal_strength") & (latest_readings.c.value < -27)
                    | (latest_readings.c.metric == "packet_loss") & (latest_readings.c.value > 5.0)
                    | (latest_readings.c.metric == "temperature") & (latest_readings.c.value > 70.0)
                )
            )
        ).all()

        # Map device UUIDs to device info
        device_ids = {r.device_id for r in breach_readings}
        device_map = {}
        if device_ids:
            devices = (
                await session.execute(
                    select(Device).where(Device.id.in_(device_ids))
                )
            ).scalars().all()
            device_map = {d.id: d for d in devices}

        alert_type_map = {
            "signal_strength": ("weak_signal", "Weak signal strength"),
            "packet_loss": ("high_packet_loss", "High packet loss"),
            "temperature": ("high_temperature", "High temperature"),
        }

        for r in breach_readings:
            device = device_map.get(r.device_id)
            if not device:
                continue
            alert_key, label = alert_type_map.get(r.metric, ("unknown", "Unknown alert"))
            alerts.append(
                AlertItem(
                    device_id=device.device_id,
                    customer_id=device.customer_id,
                    alert_type=alert_key,
                    alert_message=f"{label}: {r.value} {r.unit}",
                    metric=r.metric,
                    value=r.value,
                    recorded_at=r.recorded_at,
                )
            )

        # Also add devices with status = error
        error_devices = (
            await session.execute(
                select(Device).where(
                    Device.tenant_id == ctx.tenant_id,
                    Device.status == "error",
                )
            )
        ).scalars().all()

        error_device_ids = {d.device_id for d in alerts}
        for device in error_devices:
            if device.device_id not in error_device_ids:
                alerts.append(
                    AlertItem(
                        device_id=device.device_id,
                        customer_id=device.customer_id,
                        alert_type="device_error",
                        alert_message=f"Device {device.model or device.device_id} is in error state",
                    )
                )

        return alerts
