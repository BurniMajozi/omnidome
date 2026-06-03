from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid
from datetime import datetime
import logging
from services.common.entitlements import EntitlementGuard
from services.common.auth import AuthContext, get_auth_context, get_current_tenant_id

app = FastAPI(title="CoreConnect Support Service", version="0.1.0")
guard = EntitlementGuard(module_id="support")


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)

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

# --- Routes ---
@app.get("/")
async def root():
    return {"message": "CoreConnect Support Service is active"}

@app.post("/tickets", status_code=status.HTTP_201_CREATED)
async def create_ticket(ticket: TicketCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return {"id": uuid.uuid4(), "status": "OPEN", **ticket.dict()}

@app.get("/tickets")
async def list_tickets(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Support mobile app job queue — returns ticket-based jobs for technicians"""
    # Sample tickets for mobile app demo
    sample_jobs = [
        {
            "id": "ticket-001",
            "subject": "ONT No Light",
            "description": "Customer reports no lights on ONT. Likely fibre cut or power issue.",
            "customer_name": "Lerato Khumalo",
            "customer_phone": "+27 82 123 4567",
            "customer_address": "14 Main Rd, Cape Town, 8001",
            "priority": "HIGH",
            "status": "OPEN",
            "category": "FIBRE_FAULT",
            "created_at": "2026-06-03T08:30:00",
            "fno_reference": "VUMA-2026-0012",
        },
        {
            "id": "ticket-002",
            "subject": "Slow Speeds",
            "description": "Customer getting 10Mbps on 100Mbps plan. Signal degradation suspected.",
            "customer_name": "Sipho Dlamini",
            "customer_phone": "+27 72 456 7890",
            "customer_address": "42 Long St, Johannesburg, 2001",
            "priority": "NORMAL",
            "status": "OPEN",
            "category": "SPEED_ISSUE",
            "created_at": "2026-06-03T09:15:00",
            "fno_reference": None,
        },
        {
            "id": "ticket-003",
            "subject": "New Installation",
            "description": "FTTH Installation at new premises. Pre-wired, ONT needed.",
            "customer_name": "Amara Okafor",
            "customer_phone": "+27 83 789 0123",
            "customer_address": "8 Beach Rd, Durban, 4001",
            "priority": "NORMAL",
            "status": "IN_PROGRESS",
            "category": "INSTALLATION",
            "created_at": "2026-06-03T07:00:00",
            "fno_reference": "OPEN-2026-0045",
        },
        {
            "id": "ticket-004",
            "subject": "Router Reboot Request",
            "description": "Customer unable to connect. Remote reboot failed. On-site visit required.",
            "customer_name": "Pieter van der Merwe",
            "customer_phone": "+27 84 321 6547",
            "customer_address": "23 Park St, Pretoria, 0002",
            "priority": "LOW",
            "status": "OPEN",
            "category": "EQUIPMENT",
            "created_at": "2026-06-03T10:00:00",
            "fno_reference": None,
        },
    ]

    # Map ticket_id to support actions
    for job in sample_jobs:
        job["ticket_id"] = job["id"]

    # Apply filters
    result = sample_jobs
    if status:
        result = [j for j in result if j["status"] == status.upper()]
    if priority:
        result = [j for j in result if j["priority"] == priority.upper()]
    if category:
        result = [j for j in result if j["category"] == category.upper()]

    return result

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


@app.post("/tickets/{ticket_id}/accept")
async def accept_ticket(
    ticket_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
):
    """Accept a job (technician claims it)"""
    return {"status": "ACCEPTED", "ticket_id": str(ticket_id), "technician_id": str(auth.user_id)}


@app.post("/tickets/{ticket_id}/start")
async def start_ticket(
    ticket_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
):
    """Start working on a job"""
    return {"status": "IN_PROGRESS", "ticket_id": str(ticket_id), "technician_id": str(auth.user_id)}


@app.post("/tickets/{ticket_id}/resolve")
async def resolve_ticket(
    ticket_id: uuid.UUID,
    payload: dict = None,
    auth: AuthContext = Depends(get_auth_context),
):
    """Mark ticket as resolved. Accepts optional resolution data from mobile app."""
    fcr = payload.get("fcr", False) if payload else False
    resolution_notes = payload.get("resolution_notes", "") if payload else ""
    parts_used = payload.get("parts_used", []) if payload else []
    speed_test = payload.get("speed_test") if payload else None

    return {
        "id": str(ticket_id),
        "status": "CLOSED",
        "is_fcr": fcr,
        "resolved_at": datetime.utcnow().isoformat(),
        "resolution_notes": resolution_notes,
        "parts_used_count": len(parts_used),
        "speed_test_recorded": speed_test is not None,
    }


# ── Technician Stats (for mobile app) ─────────────────────────────────

@app.get("/technicians/me/stats")
async def get_my_stats(
    auth: AuthContext = Depends(get_current_tenant_id),
):
    """Get current technician's performance stats"""
    return {
        "jobs_today": 3,
        "jobs_week": 12,
        "avg_resolution_min": 45,
        "fcr_rate": 75,
        "customer_rating": 4.5,
        "revenue_generated": 15000,
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
    uvicorn.run(app, host="0.0.0.0", port=8008)
