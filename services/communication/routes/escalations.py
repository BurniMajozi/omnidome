"""Escalation routes — CRUD, assignment and a guarded status workflow.

States: open, in_progress, resolved, closed (closed is terminal). Invalid state strings -> 422,
disallowed transitions -> 409.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.communication.access import (
    get_visible_channel,
    has_tier,
    validate_refs,
    validate_tenant_users,
    visible_clause,
)
from services.communication.models import Channel, Escalation
from services.communication.schemas import (
    EscalationCreate,
    EscalationRead,
    PaginatedResponse,
)

router = APIRouter(prefix="/escalations", tags=["Escalations"])

ESCALATION_STATES = ("open", "in_progress", "resolved", "closed")
ESCALATION_TRANSITIONS = {
    "open": {"in_progress", "resolved", "closed"},
    "in_progress": {"open", "resolved", "closed"},
    "resolved": {"open", "closed"},
    "closed": set(),
}


async def _load(session, ctx: AuthContext, escalation_id: uuid.UUID) -> Escalation:
    escalation = (await session.execute(
        select(Escalation).where(Escalation.id == escalation_id, Escalation.tenant_id == ctx.tenant_id)
    )).scalar_one_or_none()
    if not escalation:
        raise HTTPException(status_code=404, detail="Escalation not found")
    await get_visible_channel(session, ctx, escalation.channel_id)
    return escalation


@router.post("", response_model=EscalationRead, status_code=http_status.HTTP_201_CREATED)
async def create_escalation(
    body: EscalationCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        await validate_refs(session, ctx, body.channel_id)
        if body.assigned_to and await validate_tenant_users(session, ctx.tenant_id, [body.assigned_to]):
            raise HTTPException(status_code=422, detail="Assignee does not belong to this tenant")
        escalation = Escalation(
            tenant_id=ctx.tenant_id,
            channel_id=body.channel_id,
            ticket_id=body.ticket_id,
            reason=body.reason,
            assigned_to=body.assigned_to,
            created_by=ctx.user_id,
        )
        session.add(escalation)
        await session.flush()
        await session.refresh(escalation)
        return escalation


@router.get("", response_model=PaginatedResponse)
async def list_escalations(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    if status_filter and status_filter not in ESCALATION_STATES:
        raise HTTPException(status_code=422, detail=f"status must be one of {', '.join(ESCALATION_STATES)}")
    async with session_scope() as session:
        vis = select(Channel.id).where(await visible_clause(session, ctx))
        stmt = select(Escalation).where(Escalation.tenant_id == ctx.tenant_id, Escalation.channel_id.in_(vis))
        count_stmt = select(func.count(Escalation.id)).where(
            Escalation.tenant_id == ctx.tenant_id, Escalation.channel_id.in_(vis)
        )

        if status_filter:
            stmt = stmt.where(Escalation.status == status_filter)
            count_stmt = count_stmt.where(Escalation.status == status_filter)

        total = (await session.execute(count_stmt)).scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = (
            stmt.order_by(Escalation.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = (await session.execute(stmt)).scalars().all()

        return PaginatedResponse(
            items=[EscalationRead.model_validate(e) for e in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


@router.get("/{escalation_id}", response_model=EscalationRead)
async def get_escalation(
    escalation_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        return await _load(session, ctx, escalation_id)


@router.patch("/{escalation_id}/assign", response_model=EscalationRead)
async def assign_escalation(
    escalation_id: uuid.UUID,
    assigned_to: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        escalation = await _load(session, ctx, escalation_id)
        if not await has_tier(ctx, session, "manager"):
            raise HTTPException(status_code=403, detail="Assigning escalations needs a manager or admin role")
        if await validate_tenant_users(session, ctx.tenant_id, [assigned_to]):
            raise HTTPException(status_code=422, detail="Assignee does not belong to this tenant")
        escalation.assigned_to = assigned_to
        await session.flush()
        await session.refresh(escalation)
        return escalation


@router.patch("/{escalation_id}/status", response_model=EscalationRead)
async def update_escalation_status(
    escalation_id: uuid.UUID,
    status: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    if status not in ESCALATION_STATES:
        raise HTTPException(status_code=422, detail=f"status must be one of {', '.join(ESCALATION_STATES)}")
    async with session_scope() as session:
        escalation = await _load(session, ctx, escalation_id)
        involved = ctx.user_id in (escalation.assigned_to, escalation.created_by)
        if not involved and not await has_tier(ctx, session, "manager"):
            raise HTTPException(status_code=403, detail="Only the assignee, creator or a manager can change the status")
        if status != escalation.status and status not in ESCALATION_TRANSITIONS.get(escalation.status, set()):
            raise HTTPException(
                status_code=409, detail=f"Cannot move an escalation from {escalation.status} to {status}"
            )
        escalation.status = status
        await session.flush()
        await session.refresh(escalation)
        return escalation
