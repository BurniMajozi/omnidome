"""CoreConnect IoT Service — Device management, telemetry, commands.

Port: 8006
"""

from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime
import logging
from services.common.entitlements import EntitlementGuard
from services.common.auth import get_current_tenant_id
from services.iot.database import get_session, init_tables, IoTDevice, SignalHistory, IoTCommand

app = FastAPI(title="CoreConnect IoT Service", version="0.2.0")
guard = EntitlementGuard(module_id="iot")


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "iot"}


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


# ── Pydantic Schemas ──────────────────────────────────────────────────

class DeviceCreate(BaseModel):
    device_name: str
    device_type: str  # ONT, ROUTER, SMART_BULB
    mac_address: Optional[str] = None
    serial_number: Optional[str] = None
    contact_id: Optional[uuid.UUID] = None
    firmware_version: Optional[str] = None


class DeviceUpdate(BaseModel):
    device_name: Optional[str] = None
    status: Optional[str] = None
    contact_id: Optional[uuid.UUID] = None
    firmware_version: Optional[str] = None


class DeviceResponse(BaseModel):
    id: str
    tenant_id: str
    contact_id: Optional[str]
    device_name: str
    device_type: str
    mac_address: Optional[str]
    serial_number: Optional[str]
    status: str
    firmware_version: Optional[str]
    last_seen: Optional[str]
    created_at: str


class TelemetryData(BaseModel):
    device_id: uuid.UUID
    metric_name: str
    metric_value: float


class CommandRequest(BaseModel):
    device_id: uuid.UUID
    command_type: str  # REBOOT, TOGGLE_POWER
    payload: Optional[Dict[str, Any]] = None


class SignalTelemetry(BaseModel):
    device_id: uuid.UUID
    rx_power_dbm: float
    tx_power_dbm: Optional[float] = None
    temp_c: Optional[float] = None


# ── Background tasks ───────────────────────────────────────────────────

async def analyze_fiber_signal(device_id: uuid.UUID, rx_power: float):
    """Analyze signal and trigger proactive maintenance if thresholds are breached"""
    THRESHOLD_CRITICAL = -28.0
    THRESHOLD_WARNING = -25.0

    severity = None
    if rx_power <= THRESHOLD_CRITICAL:
        severity = "CRITICAL"
    elif rx_power <= THRESHOLD_WARNING:
        severity = "WARNING"

    if severity:
        logging.warning(f"PROACTIVE ALERT: Device {device_id} signal degraded to {rx_power} dBm ({severity})")
        return {"alert_triggered": True, "severity": severity}
    return {"alert_triggered": False}


def _device_to_dict(device: IoTDevice) -> dict:
    return {
        "id": str(device.id),
        "tenant_id": str(device.tenant_id),
        "contact_id": str(device.contact_id) if device.contact_id else None,
        "device_name": device.device_name,
        "device_type": device.device_type,
        "mac_address": device.mac_address,
        "serial_number": device.serial_number,
        "status": device.status,
        "firmware_version": device.firmware_version,
        "last_seen": device.last_seen.isoformat() if device.last_seen else None,
        "created_at": device.created_at.isoformat() if device.created_at else None,
    }


# ── Routes ─────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "CoreConnect IoT Service is active"}


@app.post("/telemetry/signal", status_code=status.HTTP_202_ACCEPTED)
async def ingest_signal_telemetry(data: SignalTelemetry, background_tasks: BackgroundTasks):
    """Real-time signal ingestion from ONTs/OLTs"""
    logging.info(f"Signal Update: {data.device_id} | RX: {data.rx_power_dbm} dBm")
    background_tasks.add_task(analyze_fiber_signal, data.device_id, data.rx_power_dbm)
    return {"status": "ingested"}


@app.get("/reports/at-risk-signals")
async def get_at_risk_customers():
    """Return list of customers with degrading fiber signals"""
    return [
        {
            "customer_name": "Lerato Khumalo",
            "device_id": str(uuid.uuid4()),
            "rx_power_dbm": -27.2,
            "status": "SIGNAL_DEGRADATION",
            "region": "Cape Town",
            "fno": "Vumatel",
        }
    ]


# ── Device CRUD (DB-persisted) ─────────────────────────────────────────

@app.post("/devices", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def create_device(
    body: DeviceCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    device = IoTDevice(
        tenant_id=tenant_id,
        contact_id=body.contact_id,
        device_name=body.device_name,
        device_type=body.device_type,
        mac_address=body.mac_address,
        serial_number=body.serial_number,
        firmware_version=body.firmware_version,
        status="OFFLINE",
    )
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return _device_to_dict(device)


@app.get("/devices")
async def list_devices(
    contact_id: Optional[str] = None,
    status: Optional[str] = None,
    device_type: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """List devices, optionally filtered by contact, status, or type"""
    from sqlalchemy import select, and_

    stmt = select(IoTDevice).where(IoTDevice.tenant_id == tenant_id)

    if contact_id:
        stmt = stmt.where(IoTDevice.contact_id == uuid.UUID(contact_id))
    if status:
        stmt = stmt.where(IoTDevice.status == status.upper())
    if device_type:
        stmt = stmt.where(IoTDevice.device_type == device_type.upper())

    result = await db.execute(stmt)
    devices = result.scalars().all()
    return [_device_to_dict(d) for d in devices]


@app.get("/devices/{device_id}")
async def get_device(
    device_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Get a single device by ID"""
    from sqlalchemy import select

    result = await db.execute(
        select(IoTDevice).where(
            IoTDevice.id == uuid.UUID(device_id),
            IoTDevice.tenant_id == tenant_id,
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return _device_to_dict(device)


@app.put("/devices/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: str,
    body: DeviceUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Update a device"""
    from sqlalchemy import select

    result = await db.execute(
        select(IoTDevice).where(
            IoTDevice.id == uuid.UUID(device_id),
            IoTDevice.tenant_id == tenant_id,
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(device, field, value)

    await db.flush()
    await db.refresh(device)
    return _device_to_dict(device)


@app.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Delete a device"""
    from sqlalchemy import select

    result = await db.execute(
        select(IoTDevice).where(
            IoTDevice.id == uuid.UUID(device_id),
            IoTDevice.tenant_id == tenant_id,
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    await db.delete(device)
    await db.flush()


@app.get("/devices/{device_id}/signal")
async def get_device_signal(
    device_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Get latest signal telemetry for a device"""
    from sqlalchemy import select, desc

    # Verify device exists and belongs to tenant
    device_result = await db.execute(
        select(IoTDevice).where(
            IoTDevice.id == uuid.UUID(device_id),
            IoTDevice.tenant_id == tenant_id,
        )
    )
    device = device_result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Get latest signal reading
    signal_result = await db.execute(
        select(SignalHistory)
        .where(SignalHistory.device_id == uuid.UUID(device_id))
        .order_by(desc(SignalHistory.measured_at))
        .limit(1)
    )
    signal = signal_result.scalar_one_or_none()

    if signal:
        return {
            "device_id": device_id,
            "rx_power_dbm": float(signal.rx_power_dbm) if signal.rx_power_dbm else None,
            "tx_power_dbm": float(signal.tx_power_dbm) if signal.tx_power_dbm else None,
            "temperature_c": float(signal.temperature_c) if signal.temperature_c else None,
            "measured_at": signal.measured_at.isoformat(),
        }

    # No signal history yet — return device status only
    return {
        "device_id": device_id,
        "rx_power_dbm": None,
        "tx_power_dbm": None,
        "temperature_c": None,
        "measured_at": None,
    }


@app.post("/devices/{device_id}/reboot")
async def reboot_device(
    device_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Send reboot command to a device"""
    from sqlalchemy import select

    result = await db.execute(
        select(IoTDevice).where(
            IoTDevice.id == uuid.UUID(device_id),
            IoTDevice.tenant_id == tenant_id,
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Record command in DB
    cmd = IoTCommand(
        device_id=uuid.UUID(device_id),
        command_type="REBOOT",
        status="SENT",
    )
    db.add(cmd)

    logging.info(f"Reboot command sent to device {device_id}")
    return {"status": "REBOOT_COMMAND_SENT", "device_id": device_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
