from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime
import logging

app = FastAPI(title="CoreConnect Network Service", version="0.1.0")

# --- Models ---
class RadiusAccountCreate(BaseModel):
    contact_id: uuid.UUID
    subscription_id: uuid.UUID
    username: str
    password: str
    profile_name: str
    framing_protocol: str = "PPP" # PPP, IPOE

class RadiusProfileCreate(BaseModel):
    name: str # e.g. "50M_UNCAPPED"
    download_speed: str # e.g. "50M"
    upload_speed: str # e.g. "50M"
    mikrotik_rate_limit: Optional[str] = None # e.g. "50M/50M"

class AutomationJobCreate(BaseModel):
    job_type: str # FNO_AVAILABILITY, FNO_ORDER
    fno_name: str
    payload: Dict

# --- IAM Middleware (Stub) ---
async def get_current_tenant_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000000")

from .adapters.factory import FNOFactory

# --- RADIUS Logic ---
@app.post("/radius/profiles", status_code=status.HTTP_201_CREATED)
async def create_profile(profile: RadiusProfileCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Configure speed profiles in radgroupreply"""
    logging.info(f"Configuring RADIUS Profile: {profile.name} with rate limit {profile.mikrotik_rate_limit}")
    # In reality, this would insert into radgroupreply:
    # INSERT INTO radgroupreply (groupname, attribute, op, value) VALUES (profile.name, 'Mikrotik-Rate-Limit', '=', profile.mikrotik_rate_limit)
    return {"status": "CONFIGURED", "profile": profile.name}

@app.post("/radius/accounts", status_code=status.HTTP_201_CREATED)
async def create_radius_account(acc: RadiusAccountCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Provision a new RADIUS account in radcheck/radusergroup"""
    logging.info(f"Provisioning RADIUS Account: {acc.username}")
    # 1. Insert into radcheck (Cleartext-Password)
    # 2. Insert into radusergroup (Link to speed profile)
    return {
        "id": uuid.uuid4(),
        "username": acc.username,
        "status": "ACTIVE",
        "created_at": datetime.now()
    }

@app.get("/radius/sessions")
async def get_active_sessions(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Query radacct for live sessions"""
    return [
        {
            "username": "thabo@CoreConnect.net",
            "nas_ip": "154.22.8.5",
            "uptime": "14h 22m",
            "input_octets": 4523000,
            "output_octets": 12500000
        }
    ]

# --- FNO Automation Routes ---
@app.post("/automation/jobs", status_code=status.HTTP_202_ACCEPTED)
async def start_automation_job(job: AutomationJobCreate, background_tasks: BackgroundTasks, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Trigger a fluid FNO interaction (API or Browser)"""
    fno_configs = {
        "Vumatel": {"api_key": "vuma_secret_123", "base_url": "https://api.vumatel.co.za"},
        "Openserve": {"portal_url": "https://portal.openserve.co.za", "credentials": {"user": "admin", "pass": "secret"}}
    }
    
    config = fno_configs.get(job.fno_name, {})
    adapter = FNOFactory.get_adapter(job.fno_name, config)
    
    job_id = uuid.uuid4()
    logging.info(f"Dispatched {job.job_type} for {job.fno_name} via {type(adapter).__name__}")
    
    if job.job_type == "FNO_AVAILABILITY":
        background_tasks.add_task(adapter.check_availability, job.payload.get("address"))
    
    return {
        "id": job_id,
        "status": "PROCESSING",
        "created_at": datetime.now()
    }

@app.get("/automation/jobs/{job_id}")
async def get_job_status(job_id: uuid.UUID):
    return {"id": job_id, "status": "IN_PROGRESS", "progress": "Logging into Openserve Portal..."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
