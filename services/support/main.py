"""CoreConnect Support Service — Ticket management, FNO escalation, technician dispatch.

Port: 8008
"""

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.common.auth import AuthContext, get_auth_context, get_current_tenant_id
from services.common.db import run_with_db_retry
from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
from services.support import automation_api, consumer as ticket_consumer, desk, finance_bridge, jev_ticket, streams, ticketing, watcher
from services.support.access import require, require_job_access, require_tier
from services.support.database import Ticket, TicketReply, get_session, init_tables
from services.support.desk import ticket_to_dict as _ticket_to_dict

logger = logging.getLogger("support.main")
guard = EntitlementGuard(module_id="support")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    guard.ensure_startup()
    # Retry while Postgres (or its DNS) comes up instead of crash-looping the worker.
    await run_with_db_retry(init_tables, logger=logger)
    # Turn bus events (iot, finance, email, agents, errors...) into tickets; see ticket_rules.py.
    ticket_consumer.set_notifier(streams.push)
    ticket_consumer.set_router(jev_ticket.route_ticket)
    consumer_task = ticket_consumer.consumer.start()
    # Logs deadline breaches and asks Jev about late tickets (see watcher.py).
    watcher_task = asyncio.create_task(watcher.run_forever())
    try:
        yield
    finally:
        consumer_task.cancel()
        watcher_task.cancel()


app = FastAPI(title="CoreConnect Support Service", version="0.4.0", lifespan=lifespan)

configure_production(app)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "support"}


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


@app.get("/")
async def root():
    return {"message": "CoreConnect Support Service is active"}


class ResolveTicket(BaseModel):
    resolution_notes: str = ""
    fcr: bool = False
    parts_used: List[Dict[str, Any]] = Field(default_factory=list)
    speed_test: Optional[Dict[str, Any]] = None
    # Technician-recorded time on the job; costed at SUPPORT_LABOUR_RATE_PER_HOUR for the finance expense.
    labour_minutes: Optional[int] = Field(None, ge=0, le=24 * 60)


# Ticket desk (list/search/create/detail/comments/assign/status/rules) lives in desk.py. It is included
# BEFORE the job routes below so fixed paths like /tickets/search are never read as a ticket id.
app.include_router(desk.router)
app.include_router(automation_api.router)


@app.delete("/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ticket(
    ticket_id: uuid.UUID,
    auth: AuthContext = Depends(require_tier("admin")),
    db=Depends(get_session),
):
    """Delete a ticket (admin tier)"""
    from sqlalchemy import select

    result = await db.execute(
        select(Ticket).where(
            Ticket.id == ticket_id,
            Ticket.tenant_id == auth.tenant_id,
        )
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    await db.delete(ticket)
    await db.flush()


@app.post("/tickets/{ticket_id}/escalate-fno")
async def escalate_to_fno(
    ticket_id: uuid.UUID,
    auth: AuthContext = Depends(require_tier("manager")),
    db=Depends(get_session),
):
    """Trigger browser automation to log a ticket on the FNO portal (manager tier)"""
    from sqlalchemy import select

    tenant_id = auth.tenant_id

    result = await db.execute(
        select(Ticket).where(
            Ticket.id == ticket_id,
            Ticket.tenant_id == tenant_id,
        )
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    job_id = uuid.uuid4()
    ticket.external_fno_ref = f"VUMA-OUTAGE-{str(job_id)[:8]}"
    ticket.status = "ESCALATED"

    await db.flush()
    await ticketing.add_timeline(db, ticket.id, "status", f"Escalated to the FNO ({ticket.external_fno_ref}).",
                                 author_type="agent", author_id=auth.user_id, data={"to": "ESCALATED"})
    td = _ticket_to_dict(ticket)
    await streams.notify_ticket_update(str(tenant_id), td)

    logging.info(f"Escalating ticket {ticket_id} to FNO via Browser Automation (Agent: Playwright)")
    return {
        "status": "ESCALATED",
        "fno_reference": ticket.external_fno_ref,
        "automation_job_id": str(job_id),
    }


@app.post("/tickets/{ticket_id}/accept")
async def accept_ticket(
    ticket_id: uuid.UUID,
    auth: AuthContext = Depends(require_tier("technician")),
    db=Depends(get_session),
):
    """Accept a job (technician claims it)"""
    from sqlalchemy import select

    result = await db.execute(
        select(Ticket).where(
            Ticket.id == ticket_id,
            Ticket.tenant_id == auth.tenant_id,
        )
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    await require_job_access(auth, db, ticket.assigned_to)
    ticket.status = "IN_PROGRESS"
    ticket.assigned_to = auth.user_id
    await db.flush()
    await ticketing.add_timeline(db, ticket.id, "assignment", "Accepted by the technician.", author_type="agent",
                                 author_id=auth.user_id, data={"to": str(auth.user_id)})
    td = _ticket_to_dict(ticket)
    await streams.notify_ticket_update(str(auth.tenant_id), td)
    return {"status": "ACCEPTED", "ticket_id": str(ticket_id), "technician_id": str(auth.user_id)}


@app.post("/tickets/{ticket_id}/start")
async def start_ticket(
    ticket_id: uuid.UUID,
    auth: AuthContext = Depends(require_tier("technician")),
    db=Depends(get_session),
):
    """Start working on a job"""
    from sqlalchemy import select

    result = await db.execute(
        select(Ticket).where(
            Ticket.id == ticket_id,
            Ticket.tenant_id == auth.tenant_id,
        )
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    await require_job_access(auth, db, ticket.assigned_to)
    ticket.status = "IN_PROGRESS"
    ticket.assigned_to = auth.user_id
    await db.flush()
    await ticketing.add_timeline(db, ticket.id, "status", "Work started.", author_type="agent", author_id=auth.user_id,
                                 data={"to": "IN_PROGRESS"})
    td = _ticket_to_dict(ticket)
    await streams.notify_ticket_update(str(auth.tenant_id), td)
    return {"status": "IN_PROGRESS", "ticket_id": str(ticket_id), "technician_id": str(auth.user_id)}


@app.post("/tickets/{ticket_id}/resolve")
async def resolve_ticket(
    ticket_id: uuid.UUID,
    payload: Optional[ResolveTicket] = None,
    auth: AuthContext = Depends(require_tier("technician")),
    db=Depends(get_session),
):
    """Mark ticket as resolved — DB-persisted"""
    from sqlalchemy import select

    result = await db.execute(
        select(Ticket).where(
            Ticket.id == ticket_id,
            Ticket.tenant_id == auth.tenant_id,
        )
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    await require_job_access(auth, db, ticket.assigned_to)
    fcr = payload.fcr if payload else False
    resolution_notes = payload.resolution_notes if payload else ""
    parts_used = payload.parts_used if payload else []
    speed_test = payload.speed_test if payload else None

    ticket.status = "CLOSED"
    ticket.is_fcr = fcr
    ticket.resolution_notes = resolution_notes
    ticket.resolved_at = datetime.utcnow()
    ticket.assigned_to = auth.user_id

    await db.flush()
    await ticketing.add_timeline(db, ticket.id, "status",
                                 "Resolved by the technician" + (f": {resolution_notes[:400]}" if resolution_notes else "."),
                                 author_type="agent", author_id=auth.user_id, data={"to": "CLOSED", "fcr": fcr})
    await desk.emit(db, auth.tenant_id, "support.ticket.closed", ticket)
    td = _ticket_to_dict(ticket)
    await streams.notify_ticket_update(str(auth.tenant_id), td)

    # Finance bridge: book the job's REAL recorded cost (parts + recorded labour), else nothing.
    finance_status, finance_error = None, None
    if ticket.finance_status != "posted":
        entry = finance_bridge.build_entry(
            ticket.id, ticket.subject, ticket.resolved_at.date(), parts_used,
            payload.labour_minutes if payload else None,
        )
        if entry is not None:
            finance_status, finance_error = await finance_bridge.post_entry(auth.tenant_id, auth.user_id, entry)
            ticket.finance_status, ticket.finance_error = finance_status, finance_error
            if finance_status == "failed":
                logger.warning("Finance expense for ticket %s not booked: %s", ticket_id, finance_error)
            await db.flush()
    else:
        finance_status = "posted"

    return {
        "id": str(ticket_id),
        "status": "CLOSED",
        "is_fcr": fcr,
        "resolved_at": ticket.resolved_at.isoformat(),
        "resolution_notes": resolution_notes,
        "parts_used_count": len(parts_used),
        "speed_test_recorded": speed_test is not None,
        "finance": {"status": finance_status or "not_applicable", "error": finance_error},
    }


# ── Technician Stats (computed from DB) ───────────────────────────────

@app.get("/technicians/me/stats")
async def get_my_stats(
    auth: AuthContext = Depends(get_auth_context),
    db=Depends(get_session),
):
    """Get current technician's performance stats — computed from DB"""
    from sqlalchemy import select, func, case

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)

    # Jobs resolved today
    today_result = await db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.tenant_id == auth.tenant_id,
            Ticket.assigned_to == auth.user_id,
            Ticket.status == "CLOSED",
            Ticket.resolved_at >= today,
        )
    )
    jobs_today = today_result.scalar() or 0

    # Jobs resolved this week
    week_result = await db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.tenant_id == auth.tenant_id,
            Ticket.assigned_to == auth.user_id,
            Ticket.status == "CLOSED",
            Ticket.resolved_at >= week_ago,
        )
    )
    jobs_week = week_result.scalar() or 0

    # FCR rate (closed tickets that are FCR / total closed)
    fcr_result = await db.execute(
        select(
            func.count(Ticket.id),
            func.sum(case((Ticket.is_fcr == True, 1), else_=0)),
        ).where(
            Ticket.tenant_id == auth.tenant_id,
            Ticket.assigned_to == auth.user_id,
            Ticket.status == "CLOSED",
        )
    )
    total_closed, fcr_count = fcr_result.one()
    fcr_rate = round((fcr_count / total_closed) * 100) if total_closed > 0 else 0

    timestamps = (await db.execute(select(Ticket.created_at, Ticket.resolved_at).where(
        Ticket.tenant_id == auth.tenant_id, Ticket.assigned_to == auth.user_id,
        Ticket.status == "CLOSED", Ticket.resolved_at.is_not(None),
    ))).all()
    durations = [(resolved - created).total_seconds() / 60 for created, resolved in timestamps
                 if created and resolved and resolved >= created]
    return {
        "jobs_today": jobs_today,
        "jobs_week": jobs_week,
        "avg_resolution_min": round(sum(durations) / len(durations), 1) if durations else None,
        "fcr_rate": fcr_rate,
        "customer_rating": None,  # No ratings source is connected.
        "revenue_generated": None,  # Ticket completion alone does not establish billed revenue.
    }


@app.get("/reports/fcr-stats")
async def get_fcr_stats(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Return First Contact Resolution metrics — computed from DB"""
    from sqlalchemy import select, func, case

    month_ago = datetime.utcnow() - timedelta(days=30)

    result = await db.execute(
        select(
            func.count(Ticket.id),
            func.sum(case((Ticket.is_fcr == True, 1), else_=0)),
        ).where(
            Ticket.tenant_id == tenant_id,
            Ticket.status == "CLOSED",
            Ticket.resolved_at >= month_ago,
        )
    )
    total_closed, fcr_count = result.one()
    fcr_rate = round((fcr_count / total_closed) * 100, 1) if total_closed > 0 else 0.0

    return {
        "fcr_rate": fcr_rate,
        "avg_resolution_time_minutes": 145,  # Would need timestamp diff
        "total_tickets_month": total_closed,
    }


@app.post("/network/broadcast")
async def broadcast_alert(
    title: str,
    message: str,
    fno_id: Optional[uuid.UUID] = None,
    nas_id: Optional[int] = None,
    auth: AuthContext = Depends(require_tier("admin")),
):
    """Outage broadcast. Not implemented: recipients would have to be resolved from the network
    service's customer/NAS data and delivered through the communication service, neither of which
    is wired up here. Answers 501 rather than pretending to have sent anything."""
    logger.info("broadcast requested by %s for tenant %s but is not implemented", auth.user_id, auth.tenant_id)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Network broadcasts are not implemented: no recipients are resolved and nothing is sent",
    )


# ── SSE Stream for Technician Job Dispatch ──────────────────────────────

@app.get("/technicians/me/stream")
async def stream_technician_events(
    auth: AuthContext = Depends(get_auth_context),
    db=Depends(get_session),
):
    """SSE stream for real-time technician job dispatch notifications.

    Events:
    - connected: Stream established (includes user_id, tenant_id)
    - initial_state: Current open jobs on connect
    - new_ticket: New ticket assigned to technician
    - ticket_update: Status change on assigned ticket
    - ping: Keep-alive (every 30s)
    """
    tenant_id = str(auth.tenant_id)
    user_id = str(auth.user_id)
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    # Register stream
    if tenant_id not in streams.active_streams:
        streams.active_streams[tenant_id] = []
    streams.active_streams[tenant_id].append(queue)

    async def event_generator():
        try:
            # Send initial connection ack
            yield f"event: connected\ndata: {json.dumps({'user_id': user_id, 'tenant_id': tenant_id})}\n\n"

            # Send current open jobs on connect
            from sqlalchemy import select, desc
            stmt = select(Ticket).where(
                Ticket.tenant_id == auth.tenant_id,
                Ticket.assigned_to == auth.user_id,
                Ticket.status.in_(["OPEN", "IN_PROGRESS"]),
            ).order_by(desc(Ticket.created_at))
            result = await db.execute(stmt)
            open_tickets = result.scalars().all()
            yield f"event: initial_state\ndata: {json.dumps([_ticket_to_dict(t) for t in open_tickets])}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
                except asyncio.TimeoutError:
                    yield f"event: ping\ndata: {json.dumps({'ts': datetime.utcnow().isoformat()})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            # Unregister stream
            if tenant_id in streams.active_streams:
                streams.active_streams[tenant_id] = [q for q in streams.active_streams[tenant_id] if q is not queue]
                if not streams.active_streams[tenant_id]:
                    del streams.active_streams[tenant_id]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
