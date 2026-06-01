"""Support ticket routes — full CRUD, assignment, notes, SLA tracking."""

import uuid
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.common.auth import AuthContext, get_auth_context
from support.database import session_scope
from support.models import SupportTicket, SupportTicketNote
from support.schemas import (
    PaginatedResponse, TicketCreate, TicketNoteCreate, TicketNoteRead,
    TicketRead, TicketUpdate,
)
from sqlalchemy import select, func, and_

router = APIRouter(prefix="/tickets", tags=["Support Tickets"])


def _sla_deadline(priority: str, created_at: datetime) -> datetime:
    offsets = {"critical": timedelta(hours=4), "high": timedelta(hours=24), "normal": timedelta(hours=72), "low": timedelta(weeks=1)}
    return created_at + offsets.get(priority, timedelta(hours=72))


@router.post("", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
async def create_ticket(body: TicketCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        now = datetime.now(timezone.utc)
        ticket = SupportTicket(
            tenant_id=ctx.tenant_id, customer_id=body.customer_id,
            subject=body.subject, description=body.description,
            category=body.category, priority=body.priority,
            sla_deadline=_sla_deadline(body.priority, now),
            created_by=ctx.user_id,
        )
        await session.add(ticket)
        await session.flush()
        await session.refresh(ticket)
        return TicketRead.model_validate(ticket)


@router.get("", response_model=PaginatedResponse)
async def list_tickets(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    priority: Optional[str] = Query(None),
    assigned_to: Optional[uuid.UUID] = Query(None),
    customer_id: Optional[uuid.UUID] = Query(None),
):
    async with session_scope() as session:
        query = select(SupportTicket).where(SupportTicket.tenant_id == ctx.tenant_id)
        if status_filter:
            query = query.where(SupportTicket.status == status_filter)
        if priority:
            query = query.where(SupportTicket.priority == priority)
        if assigned_to:
            query = query.where(SupportTicket.assigned_to == assigned_to)
        if customer_id:
            query = query.where(SupportTicket.customer_id == customer_id)

        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        items = (await session.execute(query.order_by(SupportTicket.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()

        return PaginatedResponse(
            items=[TicketRead.model_validate(i) for i in items],
            total=total or 0, page=page, page_size=page_size,
            pages=max(1, math.ceil((total or 0) / page_size)),
        )


@router.get("/{ticket_id}", response_model=TicketRead)
async def get_ticket(ticket_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        if not ticket or ticket.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Ticket not found")
        return TicketRead.model_validate(ticket)


@router.put("/{ticket_id}", response_model=TicketRead)
async def update_ticket(ticket_id: uuid.UUID, body: TicketUpdate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        if not ticket or ticket.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Ticket not found")
        update = body.model_dump(exclude_unset=True)
        if "status" in update and update["status"] == "resolved":
            update["resolved_at"] = datetime.now(timezone.utc)
        for k, v in update.items():
            setattr(ticket, k, v)
        await session.flush()
        await session.refresh(ticket)
        return TicketRead.model_validate(ticket)


@router.patch("/{ticket_id}/assign")
async def assign_ticket(ticket_id: uuid.UUID, assignee_id: uuid.UUID = Query(...), ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        if not ticket or ticket.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Ticket not found")
        ticket.assigned_to = assignee_id
        ticket.status = "in_progress"
        await session.flush()
        return {"ticket_id": str(ticket_id), "assigned_to": str(assignee_id)}


@router.patch("/{ticket_id}/status")
async def update_status(ticket_id: uuid.UUID, new_status: str = Query(...), ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        if not ticket or ticket.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Ticket not found")
        ticket.status = new_status
        if new_status == "resolved":
            ticket.resolved_at = datetime.now(timezone.utc)
        await session.flush()
        return {"ticket_id": str(ticket_id), "status": new_status}


@router.post("/{ticket_id}/notes", response_model=TicketNoteRead, status_code=status.HTTP_201_CREATED)
async def add_note(ticket_id: uuid.UUID, body: TicketNoteCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        if not ticket or ticket.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Ticket not found")
        note = SupportTicketNote(
            tenant_id=ctx.tenant_id, ticket_id=ticket_id,
            author_id=ctx.user_id, content=body.content, is_internal=body.is_internal,
        )
        session.add(note)
        await session.flush()
        await session.refresh(note)
        return TicketNoteRead.model_validate(note)


@router.get("/{ticket_id}/notes")
async def list_notes(ticket_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        notes = (await session.execute(
            select(SupportTicketNote).where(
                SupportTicketNote.ticket_id == ticket_id,
                SupportTicketNote.tenant_id == ctx.tenant_id,
            ).order_by(SupportTicketNote.created_at.desc())
        )).scalars().all()
        return [TicketNoteRead.model_validate(n) for n in notes]


@router.get("/sla/breached")
async def sla_breaches(ctx: AuthContext = Depends(get_auth_context)):
    """List tickets past their SLA deadline."""
    async with session_scope() as session:
        now = datetime.now(timezone.utc)
        tickets = (await session.execute(
            select(SupportTicket).where(
                SupportTicket.tenant_id == ctx.tenant_id,
                SupportTicket.status.notin_(["resolved", "closed"]),
                SupportTicket.sla_deadline < now,
            ).order_by(SupportTicket.sla_deadline.asc())
        )).scalars().all()
        result = []
        for t in tickets:
            hours_over = (now - t.sla_deadline).total_seconds() / 3600
            result.append({
                "ticket_id": str(t.id), "subject": t.subject,
                "priority": t.priority, "sla_deadline": t.sla_deadline.isoformat(),
                "hours_overdue": round(hours_over, 1),
            })
        return result
