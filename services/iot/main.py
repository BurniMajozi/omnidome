from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid
from datetime import datetime
import logging
from services.common.entitlements import EntitlementGuard
from services.common.auth import get_current_tenant_id

app = FastAPI(title="CoreConnect IoT Service", version="0.1.0")
guard = EntitlementGuard(module_id="iot")


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)

# --- Models ---
class DeviceBase(BaseModel):
    device_name: str
    device_type: str # ONT, ROUTER, SMART_BULB
    mac_address: Optional[str]
    serial_number: Optional[str]

class Device(DeviceBase):
    id: uuid.UUID
    status: str
    last_seen: Optional[datetime]

class TelemetryData(BaseModel):
    device_id: uuid.UUID
    metric_name: str
    metric_value: float

class CommandRequest(BaseModel):
    device_id: uuid.UUID
    command_type: str # REBOOT, TOGGLE_POWER
    payload: Optional[Dict] = {}

class SignalTelemetry(BaseModel):
    device_id: uuid.UUID
    rx_power_dbm: float
    tx_power_dbm: Optional[float]
    temp_c: Optional[float]

# --- In-memory device store (replace with DB in production) ────────────
# Structure: {tenant_id: {device_id: {device fields}}}
_device_store: Dict[str, Dict[str, dict]] = {}


def _get_tenant_devices(tenant_id: str) -> Dict[str, dict]:
    if tenant_id not in _device_store:
        _device_store[tenant_id] = {}
    return _device_store[tenant_id]


def _ensure_sample_devices(tenant_id: str):
    """Seed sample device data for demo purposes"""
    devices = _get_tenant_devices(tenant_id)
    if not devices:
        sample_devices = {
            "dev-001": {
                "id": "dev-001", "device_name": "ONT-Lerato-001", "device_type": "ONT",
                "mac_address": "AA:BB:CC:DD:EE:01", "serial_number": "ONT-V1-001",
                "status": "ONLINE", "last_seen": datetime.utcnow().isoformat(),
                "rx_power_dbm": -18.5, "tx_power_dbm": 2.1, "temperature_c": 42.3,
                "firmware_version": "v2.1.4", "contact_id": "contact-001",
            },
            "dev-002": {
                "id": "dev-002", "device_name": "Router-Lerato-001", "device_type": "ROUTER",
                "mac_address": "AA:BB:CC:DD:EE:02", "serial_number": "RTR-NET-001",
                "status": "ONLINE", "last_seen": datetime.utcnow().isoformat(),
                "rx_power_dbm": None, "tx_power_dbm": None, "temperature_c": 38.0,
                "firmware_version": "v1.0.2", "contact_id": "contact-001",
            },
            "dev-003": {
                "id": "dev-003", "device_name": "ONT-Sipho-002", "device_type": "ONT",
                "mac_address": "AA:BB:CC:DD:EE:03", "serial_number": "ONT-H1-002",
                "status": "OFFLINE", "last_seen": "2026-06-01T10:30:00",
                "rx_power_dbm": -27.2, "tx_power_dbm": 1.8, "temperature_c": 45.1,
                "firmware_version": "v2.0.1", "contact_id": "contact-002",
            },
        }
        devices.update(sample_devices)
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
        # In reality, this would:
        # 1. Check if an open ticket already exists for this device
        # 2. Create a PROACTIVE maintenance ticket via the Support Service
        # 3. Notify the NOC via Slack/Webhooks
        return {"alert_triggered": True, "severity": severity}
    return {"alert_triggered": False}

# --- Routes ---
@app.get("/")
async def root():
    return {"message": "CoreConnect IoT Service is active"}

@app.post("/telemetry/signal", status_code=status.HTTP_202_ACCEPTED)
async def ingest_signal_telemetry(data: SignalTelemetry, background_tasks: BackgroundTasks):
    """Real-time signal ingestion from ONTs/OLTs"""
    logging.info(f"Signal Update: {data.device_id} | RX: {data.rx_power_dbm} dBm")
    
    # Store in ont_signal_history (Mock)
    background_tasks.add_task(analyze_fiber_signal, data.device_id, data.rx_power_dbm)
    
    return {"status": "ingested"}

@app.get("/reports/at-risk-signals")
async def get_at_risk_customers():
    """Return list of customers with degrading fiber signals"""
    return [
        {
            "customer_name": "Lerato Khumalo",
            "device_id": uuid.uuid4(),
            "rx_power": -27.2,
            "status": "SIGNAL_DEGRADATION",
            "region": "Cape Town",
            "fno": "Vumatel"
        }
    ]


# ── Device CRUD (for mobile technician app) ───────────────────────────

@app.get("/devices")
async def list_devices(
    contact_id: Optional[str] = None,
    status: Optional[str] = None,
    device_type: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """List devices, optionally filtered by contact, status, or type"""
    _ensure_sample_devices(str(tenant_id))
    devices = _get_tenant_devices(str(tenant_id))

    result = []
    for did, d in devices.items():
        if contact_id and d.get("contact_id") != contact_id:
            continue
        if status and d.get("status") != status.upper():
            continue
        if device_type and d.get("device_type") != device_type.upper():
            continue
        result.append(d)

    return result


@app.get("/devices/{device_id}")
async def get_device(
    device_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Get a single device by ID"""
    _ensure_sample_devices(str(tenant_id))
    devices = _get_tenant_devices(str(tenant_id))
    device = devices.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@app.get("/devices/{device_id}/signal")
async def get_device_signal(
    device_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Get real-time signal telemetry for a device"""
    _ensure_sample_devices(str(tenant_id))
    devices = _get_tenant_devices(str(tenant_id))
    device = devices.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return {
        "device_id": device_id,
        "rx_power_dbm": device.get("rx_power_dbm"),
        "tx_power_dbm": device.get("tx_power_dbm"),
        "temperature_c": device.get("temperature_c"),
        "measured_at": device.get("last_seen", datetime.utcnow().isoformat()),
    }


@app.post("/devices/{device_id}/reboot")
async def reboot_device(
    device_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Send reboot command to a device"""
    _ensure_sample_devices(str(tenant_id))
    devices = _get_tenant_devices(str(tenant_id))
    device = devices.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    logging.info(f"Reboot command sent to device {device_id}")
    # In production: send command via TR-069, SNMP, or MQTT
    return {"status": "REBOOT_COMMAND_SENT", "device_id": device_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
