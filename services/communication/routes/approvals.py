"""Approval routes — CRUD and decision workflow for approval requests.

States: pending -> approved | rejected | cancelled (terminal). Deciding (approve/reject) needs the
manager/admin tier and cannot be done by the requester; the requester may cancel their own request.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.communication.access import get_visible_channel, has_tier, validate_refs, visible_clause
from services.communication.models import Approval, Channel
from services.communication.schemas import (
    ApprovalCreate,
    ApprovalDecision,
    ApprovalRead,
    PaginatedResponse,
)

router = APIRouter(prefix="/approvals", tags=["Approvals"])

APPROVAL_STATES = ("pending", "approved", "rejected", "cancelled")


@router.post("", response_model=ApprovalRead, status_code=status.HTTP_201_CREATED)
async def create_approval(
    body: ApprovalCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        await validate_refs(session, ctx, body.channel_id, body.message_id)
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
    if status_filter and status_filter not in APPROVAL_STATES:
        raise HTTPException(status_code=422, detail=f"status must be one of {', '.join(APPROVAL_STATES)}")
    async with session_scope() as session:
        vis = select(Channel.id).where(await visible_clause(session, ctx))
        stmt = select(Approval).where(Approval.tenant_id == ctx.tenant_id, Approval.channel_id.in_(vis))
        count_stmt = select(func.count(Approval.id)).where(
            Approval.tenant_id == ctx.tenant_id, Approval.channel_id.in_(vis)
        )

        if status_filter:
            stmt = stmt.where(Approval.status == status_filter)
            count_stmt = count_stmt.where(Approval.status == status_filter)

        total = (await session.execute(count_stmt)).scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = (
            stmt.order_by(Approval.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = (await session.execute(stmt)).scalars().all()

        return PaginatedResponse(
            items=[ApprovalRead.model_validate(a) for a in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


async def _load(session, ctx: AuthContext, approval_id: uuid.UUID) -> Approval:
    approval = (await session.execute(
        select(Approval).where(Approval.id == approval_id, Approval.tenant_id == ctx.tenant_id)
    )).scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    await get_visible_channel(session, ctx, approval.channel_id)
    return approval


@router.get("/{approval_id}", response_model=ApprovalRead)
async def get_approval(
    approval_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        return await _load(session, ctx, approval_id)


@router.post("/{approval_id}/decide", response_model=ApprovalRead)
async def decide_approval(
    approval_id: uuid.UUID,
    body: ApprovalDecision,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        approval = await _load(session, ctx, approval_id)
        if approval.status != "pending":
            raise HTTPException(status_code=409, detail=f"Approval is already {approval.status}")
        is_requester = ctx.user_id in (approval.created_by, approval.user_id)
        if body.status == "cancelled":
            if not is_requester:
                raise HTTPException(status_code=403, detail="Only the requester can cancel an approval")
        else:
            if is_requester:
                raise HTTPException(status_code=403, detail="You cannot decide your own approval request")
            if not await has_tier(ctx, session, "manager"):
                raise HTTPException(status_code=403, detail="Deciding approvals needs a manager or admin role")

        approval.status = body.status
        approval.decided_by = ctx.user_id
        approval.decided_at = datetime.now(timezone.utc)
        await session.flush()
        await session.refresh(approval)
        return approval
