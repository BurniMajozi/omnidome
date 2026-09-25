"""FastAPI routes for agent approval gate (spec A8 `approval-gate`)."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.agent_orchestrator.approvals import (
    decide_approval,
    get_approval,
    list_approvals,
)

router = APIRouter()


class ApproveRequest(BaseModel):
    notes: Optional[str] = None


class RejectRequest(BaseModel):
    reason: Optional[str] = None


@router.get("")
async def get_approvals(
    status: Optional[str] = Query(None, description="pending, approved, rejected, expired"),
    agent: Optional[str] = Query(None, description="Filter by agent type"),
    limit: int = Query(50, ge=1, le=200),
    ctx: AuthContext = Depends(get_auth_context),
):
    """List agent approvals for the tenant."""
    async with session_scope() as session:
        items = await list_approvals(
            session=session,
            tenant_id=ctx.tenant_id,
            status=status,
            agent_type=agent,
            limit=limit,
        )
        pending = sum(1 for i in items if i.get("status") == "pending")
        return {"items": items, "pending_count": pending}


@router.get("/{approval_id}")
async def get_single_approval(
    approval_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Retrieve an approval by ID."""
    async with session_scope() as session:
        item = await get_approval(session, ctx.tenant_id, approval_id)
        if not item:
            raise HTTPException(status_code=404, detail="Approval not found")
        return item


@router.post("/{approval_id}/approve")
async def approve(
    approval_id: uuid.UUID,
    body: Optional[ApproveRequest] = None,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Approve a pending agent action proposal."""
    async with session_scope() as session:
        try:
            return await decide_approval(
                session=session,
                tenant_id=ctx.tenant_id,
                approval_id=approval_id,
                decision="approved",
                decided_by=str(ctx.user_id),
                reason=(body.notes if body else None),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{approval_id}/reject")
async def reject(
    approval_id: uuid.UUID,
    body: Optional[RejectRequest] = None,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Reject a pending agent action proposal."""
    async with session_scope() as session:
        try:
            return await decide_approval(
                session=session,
                tenant_id=ctx.tenant_id,
                approval_id=approval_id,
                decision="rejected",
                decided_by=str(ctx.user_id),
                reason=(body.reason if body else "Rejected by user"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
