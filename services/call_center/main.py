from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid
from datetime import datetime
import logging

app = FastAPI(title="CoreConnect Call Center Service", version="0.1.0")

# --- Models ---
class Agent(BaseModel):
    id: uuid.UUID
    name: str
    extension: str
    status: str
    daily_sales: float
    mttr_minutes: float
    csat_score: float

class Script(BaseModel):
    id: Optional[uuid.UUID]
    title: str
    category: str
    content: str
    active: bool = True

class CallSession(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    start_time: datetime
    end_time: Optional[datetime]
    sentiment_score: float # 0.0 to 1.0
    duration_seconds: int

# --- IAM Middleware (Stub) ---
async def get_current_tenant_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000000")

# --- Routes ---
@app.get("/")
async def root():
    return {"message": "CoreConnect Call Center Service is active"}

@app.get("/agents", response_model=List[Agent])
async def list_agents(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return [
        Agent(id=uuid.uuid4(), name="Sipho Nkosi", extension="1001", status="ON_CALL", daily_sales=12400.0, mttr_minutes=5.2, csat_score=4.8),
        Agent(id=uuid.uuid4(), name="Jane Doe", extension="1005", status="IDLE", daily_sales=8500.0, mttr_minutes=4.8, csat_score=4.9)
    ]

@app.post("/scripts", status_code=status.HTTP_201_CREATED)
async def create_script(script: Script, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    script.id = uuid.uuid4()
    logging.info(f"New script created: {script.title}")
    return script

@app.get("/scripts", response_model=List[Script])
async def list_scripts(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return [
        Script(id=uuid.uuid4(), title="Sales: Fiber Upgrade", category="Sales", content="Targeting existing customers...", active=True),
        Script(id=uuid.uuid4(), title="Support: Troubleshooting", category="Support", content="Step-by-step guide...", active=True)
    ]

@app.get("/analytics/sentiment")
async def get_realtime_sentiment(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Return aggregated sentiment analysis for the last 60 minutes"""
    return {
        "overall_sentiment": 0.78,
        "positive_mentions": ["fast service", "helpful agent", "easy upgrade"],
        "negative_mentions": ["high price", "load shedding outage", "waiting time"],
        "alerts_count": 2,
        "critical_escalations": 1
    }

@app.post("/reports/import")
async def import_external_report(file: UploadFile = File(...)):
    """Import reports from CSV, Excel or PDF (Mock)"""
    logging.info(f"Importing report: {file.filename}")
    return {
        "status": "SUCCESS",
        "processed_records": 1500,
        "anomalies_detected": 3,
        "message": f"Report '{file.filename}' successfully integrated into Hub Intelligence."
    }

@app.get("/reports/intelligence")
async def get_hub_intelligence(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Return high-level management reports"""
    return {
        "resolution_rate": 92.0,
        "avg_talk_time_seconds": 252,
        "closed_queries": 642,
        "peak_volume_period": "17:00 - 19:00",
        "health_status": "OPTIMAL"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8011) # Unique port for this service
