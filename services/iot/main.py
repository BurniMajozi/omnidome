from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid
from datetime import datetime
import logging

app = FastAPI(title="CoreConnect IoT Service", version="0.1.0")

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

# --- IAM Middleware (Stub) ---
async def get_current_tenant_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000000")

class SignalTelemetry(BaseModel):
    device_id: uuid.UUID
    rx_power_dbm: float
    tx_power_dbm: Optional[float]
    temp_c: Optional[float]

# --- Proactive Logic ---
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
