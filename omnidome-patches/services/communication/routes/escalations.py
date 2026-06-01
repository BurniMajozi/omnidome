"""Escalation routes — CRUD and assignment for escalations."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.communication.models import Escalation
from services.communication.schemas import (
    EscalationCreate,
    EscalationRead,
    PaginatedResponse,
)

router = APIRouter(prefix="/escalations", tags=["Escalations"])


@router.post("", response_model=EscalationRead, status_code=status.HTTP_201_CREATED)
async def create_escalation(
    body: EscalationCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
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
    async with session_scope() as session:
        stmt = select(Escalation).where(Escalation.tenant_id == ctx.tenant_id)
        count_stmt = select(func.count(Escalation.id)).where(
            Escalation.tenant_id == ctx.tenant_id
        )

        if status_filter:
            stmt = stmt.where(Escalation.status == status_filter)
            count_stmt = count_stmt.where(Escalation.status == status_filter)

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = (
            stmt.order_by(Escalation.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

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
        stmt = select(Escalation).where(
            Escalation.id == escalation_id, Escalation.tenant_id == ctx.tenant_id
        )
        result = await session.execute(stmt)
        escalation = result.scalar_one_or_none()
        if not escalation:
            raise HTTPException(status_code=404, detail="Escalation not found")
        return escalation


@router.patch("/{escalation_id}/assign", response_model=EscalationRead)
async def assign_escalation(
    escalation_id: uuid.UUID,
    assigned_to: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(Escalation).where(
            Escalation.id == escalation_id, Escalation.tenant_id == ctx.tenant_id
        )
        result = await session.execute(stmt)
        escalation = result.scalar_one_or_none()
        if not escalation:
            raise HTTPException(status_code=404, detail="Escalation not found")

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
    async with session_scope() as session:
        stmt = select(Escalation).where(
            Escalation.id == escalation_id, Escalation.tenant_id == ctx.tenant_id
        )
        result = await session.execute(stmt)
        escalation = result.scalar_one_or_none()
        if not escalation:
            raise HTTPException(status_code=404, detail="Escalation not found")

        escalation.status = status
        await session.flush()
        await session.refresh(escalation)
        return escalation
