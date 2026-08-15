"""Approval routes — CRUD and decision workflow for approval requests."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.communication.models import Approval
from services.communication.schemas import (
    ApprovalCreate,
    ApprovalDecision,
    ApprovalRead,
    PaginatedResponse,
)

router = APIRouter(prefix="/approvals", tags=["Approvals"])


@router.post("", response_model=ApprovalRead, status_code=status.HTTP_201_CREATED)
async def create_approval(
    body: ApprovalCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        approval = Approval(
            tenant_id=ctx.tenant_id,
            channel_id=body.channel_id,
            message_id=body.message_id,
            user_id=ctx.user_id,
            title=body.title,
            description=body.description,
            created_by=ctx.user_id,
        )
        session.add(approval)
        await session.flush()
        await session.refresh(approval)
        return approval


@router.get("", response_model=PaginatedResponse)
async def list_approvals(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    async with session_scope() as session:
        stmt = select(Approval).where(Approval.tenant_id == ctx.tenant_id)
        count_stmt = select(func.count(Approval.id)).where(
            Approval.tenant_id == ctx.tenant_id
        )

        if status_filter:
            stmt = stmt.where(Approval.status == status_filter)
            count_stmt = count_stmt.where(Approval.status == status_filter)

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = (
            stmt.order_by(Approval.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

        return PaginatedResponse(
            items=[ApprovalRead.model_validate(a) for a in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


@router.get("/{approval_id}", response_model=ApprovalRead)
async def get_approval(
    approval_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(Approval).where(
            Approval.id == approval_id, Approval.tenant_id == ctx.tenant_id
        )
        result = await session.execute(stmt)
        approval = result.scalar_one_or_none()
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")
        return approval


@router.post("/{approval_id}/decide", response_model=ApprovalRead)
async def decide_approval(
    approval_id: uuid.UUID,
    body: ApprovalDecision,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(Approval).where(
            Approval.id == approval_id, Approval.tenant_id == ctx.tenant_id
        )
        result = await session.execute(stmt)
        approval = result.scalar_one_or_none()
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")

        approval.status = body.status
        approval.decided_by = ctx.user_id
        approval.decided_at = datetime.now(timezone.utc)
        await session.flush()
        await session.refresh(approval)
        return approval
