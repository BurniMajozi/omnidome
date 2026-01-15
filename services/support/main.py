from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid
from datetime import datetime
import logging

app = FastAPI(title="CoreConnect Support Service", version="0.1.0")

# --- Models ---
class TicketCreate(BaseModel):
    customer_id: uuid.UUID
    subject: str
    description: str
    category: str
    priority: str = "NORMAL"

class TicketReplyCreate(BaseModel):
    message: str
    is_private: bool = False

class TicketStatusUpdate(BaseModel):
    status: str

# --- IAM Middleware (Stub) ---
async def get_current_tenant_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000000")

# --- Routes ---
@app.get("/")
async def root():
    return {"message": "CoreConnect Support Service is active"}

@app.post("/tickets", status_code=status.HTTP_201_CREATED)
async def create_ticket(ticket: TicketCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return {"id": uuid.uuid4(), "status": "OPEN", **ticket.dict()}

@app.get("/tickets")
async def list_tickets(status: Optional[str] = None, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return [
        {
            "id": uuid.uuid4(),
            "subject": "Router not connecting",
            "customer_name": "Thabo Molefe",
            "status": "OPEN",
            "priority": "HIGH",
            "created_at": datetime.now()
        }
    ]

@app.post("/tickets/{ticket_id}/escalate-fno")
async def escalate_to_fno(ticket_id: uuid.UUID):
    """Trigger browser automation to log a ticket on the FNO portal"""
    logging.info(f"Escalating ticket {ticket_id} to FNO via Browser Automation (Agent: Playwright)")
    # Mocking a Playwright job ID from the Network Hub
    job_id = uuid.uuid4()
    return {
        "status": "ESCALATED",
        "fno_reference": f"VUMA-OUTAGE-{str(job_id)[:8]}",
        "automation_job_id": job_id
    }

@app.post("/tickets/{ticket_id}/resolve")
async def resolve_ticket(ticket_id: uuid.UUID, fcr: bool = False):
    """Mark ticket as resolved and track if it was First Contact Resolution (FCR)"""
    return {
        "id": ticket_id,
        "status": "CLOSED",
        "is_fcr": fcr,
        "resolved_at": datetime.now()
    }

@app.get("/reports/fcr-stats")
async def get_fcr_stats(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Return First Contact Resolution metrics for the dashboard"""
    return {
        "fcr_rate": 68.5,
        "avg_resolution_time_minutes": 145,
        "total_tickets_month": 1240
    }

@app.post("/network/broadcast")
async def broadcast_alert(title: str, message: str, fno_id: Optional[uuid.UUID] = None, nas_id: Optional[int] = None):
    """Notify specific customers of an outage based on their network path"""
    if nas_id:
        logging.info(f"TARGETED BROADCAST: {title} sent to customers on NAS Hardware #{nas_id}")
    elif fno_id:
        logging.info(f"FNO BROADCAST: {title} sent to customers on FNO Portal {fno_id}")
    else:
        logging.info(f"GENERAL BROADCAST: {title} sent to all active subscribers")
    
    return {"status": "SENT", "recipients_count": "CALCULATED_DYNAMICALLY"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8009)
