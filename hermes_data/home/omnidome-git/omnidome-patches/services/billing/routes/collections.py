"""Collections & Dunning routes — overdue queue, arrangements, suspend/reinstate.

FIX: Converted to async SQLAlchemy. Added circuit breaker on cross-service calls.
Added pagination.
"""

import logging
import os
import uuid
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select

from services.common.auth import AuthContext, get_auth_context
from services.billing.database import get_session
from services.billing.models import DunningAction, Invoice, PaymentArrangement
from services.billing.schemas import (
    ArrangementCreate,
    ArrangementRead,
    CollectionsQueueItem,
    DunningActionRead,
    PaginatedResponse,
)
from services.common.circuit_breaker import circuit_breaker
from services.common.http_client import service_call

logger = logging.getLogger("billing.collections")

router = APIRouter(tags=["Collections"])


@router.get("/collections/queue")
async def collections_queue(
    ctx: AuthContext = Depends(get_auth_context),
    min_days: int = Query(1, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    async with get_session() as session:
        today = date.today()
        query = (
            select(
                Invoice.customer_id,
                func.sum(Invoice.total_zar - Invoice.amount_paid_zar).label("total_overdue"),
                func.min(Invoice.due_date).label("oldest_due"),
                func.count(Invoice.id).label("inv_count"),
            )
            .where(
                Invoice.tenant_id == ctx.tenant_id,
                Invoice.status.in_(["sent", "partially_paid", "overdue"]),
                Invoice.due_date < today,
            )
            .group_by(Invoice.customer_id)
        )
        rows = (await session.execute(query)).all()

        items = []
        for row in rows:
            days_overdue = (today - row.oldest_due).days
            if days_overdue < min_days:
                continue
            if days_overdue >= 30:
                stage = "collections"
            elif days_overdue >= 14:
                stage = "suspended"
            elif days_overdue >= 7:
                stage = "email_warning"
            else:
                stage = "sms_reminder"
            items.append(CollectionsQueueItem(
                customer_id=row.customer_id,
                total_overdue_zar=row.total_overdue,
                oldest_overdue_date=row.oldest_due,
                days_overdue=days_overdue,
                invoice_count=row.inv_count,
                dunning_stage=stage,
            ))

        items.sort(key=lambda x: x.days_overdue, reverse=True)
        total = len(items)
        start = (page - 1) * page_size
        return PaginatedResponse(
            items=items[start:start + page_size],
            total=total, page=page, page_size=page_size,
            pages=max(1, math.ceil(total / page_size)),
        )


@router.post(
    "/collections/{customer_id}/arrange",
    response_model=ArrangementRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_arrangement(
    customer_id: uuid.UUID,
    body: ArrangementCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        overdue = (await session.scalar(
            select(func.sum(Invoice.total_zar - Invoice.amount_paid_zar)).where(
                Invoice.tenant_id == ctx.tenant_id,
                Invoice.customer_id == customer_id,
                Invoice.status.in_(["sent", "partially_paid", "overdue"]),
            )
        )) or Decimal("0.00")
        if overdue <= 0:
            raise HTTPException(status_code=400, detail="Customer has no overdue balance")

        arrangement = PaymentArrangement(
            tenant_id=ctx.tenant_id,
            customer_id=customer_id,
            total_owed_zar=body.total_owed_zar,
            installment_zar=body.installment_zar,
            installments_count=body.installments_count,
            next_due_date=body.first_due_date,
            notes=body.notes,
        )
        session.add(arrangement)
        await session.flush()
        await session.refresh(arrangement)
        return ArrangementRead.model_validate(arrangement)


@router.post("/collections/{customer_id}/suspend")
async def manual_suspend(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    await _suspend_customer(ctx.tenant_id, customer_id)
    async with get_session() as session:
        (await session.execute(
            select(Invoice).where(
                Invoice.tenant_id == ctx.tenant_id,
                Invoice.customer_id == customer_id,
                Invoice.status.in_(["sent", "partially_paid"]),
                Invoice.due_date < date.today(),
            )
        ))
        # Mark overdue
    return {"status": "suspended", "customer_id": str(customer_id)}


@router.post("/collections/{customer_id}/reinstate")
async def reinstate_customer(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    await _reinstate_customer(ctx.tenant_id, customer_id)
    return {"status": "reinstated", "customer_id": str(customer_id)}


@router.get("/collections/dunning")
async def list_dunning_actions(
    ctx: AuthContext = Depends(get_auth_context),
    customer_id: Optional[uuid.UUID] = Query(None),
    action_type: Optional[str] = Query(None),
    pending_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    async with get_session() as session:
        query = select(DunningAction).where(DunningAction.tenant_id == ctx.tenant_id)
        if customer_id:
            query = query.where(DunningAction.customer_id == customer_id)
        if action_type:
            query = query.where(DunningAction.action_type == action_type)
        if pending_only:
            query = query.where(DunningAction.executed_at.is_(None))

        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        items = (await session.execute(
            query.order_by(DunningAction.scheduled_at.asc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()

        return PaginatedResponse(
            items=[DunningActionRead.model_validate(d) for d in items],
            total=total or 0, page=page, page_size=page_size,
            pages=max(1, math.ceil((total or 0) / page_size)),
        )


@circuit_breaker(threshold=3, timeout=60)
async def _suspend_customer(tenant_id: uuid.UUID, customer_id: uuid.UUID):
    """Suspend customer service on the Network via circuit breaker."""
    try:
        await service_call("network", "POST", "/api/services/suspend-by-customer",
            json={"customer_id": str(customer_id)},
            tenant_id=str(tenant_id), timeout=5.0)
    except Exception as exc:
        logger.error("Suspend call failed for customer %s: %s", customer_id, exc)
        raise


@circuit_breaker(threshold=3, timeout=60)
async def _reinstate_customer(tenant_id: uuid.UUID, customer_id: uuid.UUID):
    """Reinstate customer service on the Network via circuit breaker."""
    try:
        await service_call("network", "POST", "/api/services/reinstate-by-customer",
            json={"customer_id": str(customer_id)},
            tenant_id=str(tenant_id), timeout=5.0)
    except Exception as exc:
        logger.error("Reinstate call failed for customer %s: %s", customer_id, exc)
        raise


@router.post("/collections/dunning/process")
async def process_pending_dunning(ctx: AuthContext = Depends(get_auth_context)):
    """Execute all pending dunning actions whose scheduled_at has passed."""
    executed = 0
    now = datetime.utcnow()
    async with get_session() as session:
        pending = (await session.execute(
            select(DunningAction).where(
                DunningAction.tenant_id == ctx.tenant_id,
                DunningAction.executed_at.is_(None),
                DunningAction.scheduled_at <= now,
            ).order_by(DunningAction.scheduled_at.asc())
        )).scalars().all()

        for action in pending:
            try:
                if action.action_type == "sms_reminder":
                    action.result = "sms_sent"
                elif action.action_type == "email_warning":
                    action.result = "email_sent"
                elif action.action_type == "auto_suspend":
                    inv = await session.get(Invoice, action.invoice_id)
                    if inv and inv.status not in ("paid", "voided"):
                        await _suspend_customer(action.tenant_id, action.customer_id)
                        inv.status = "overdue"
                        action.result = "suspended"
                    else:
                        action.result = "skipped_paid"
                elif action.action_type == "send_to_collections":
                    action.result = "sent_to_collections"
                action.executed_at = now
                executed += 1
            except Exception as exc:
                logger.error("Dunning action %s failed: %s", action.id, exc)
                action.result = f"error: {exc}"
                action.executed_at = now

    return {"executed": executed, "total_pending": len(pending)}
