"""Collections & Dunning routes - overdue queue, arrangements, suspend/reinstate.

The dunning runner itself lives in services/billing/dunning.py.
"""

import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func

from services.common.auth import AuthContext, get_auth_context
from services.common.http_client import service_post
from services.billing import finance_posting as fp
from services.billing.access import require_tier
from services.billing.database import get_session
from services.billing.models import DunningAction, Invoice, PaymentArrangement
from services.billing.schemas import (
    ArrangementCreate,
    ArrangementRead,
    CollectionsQueueItem,
    DunningActionRead,
)

logger = logging.getLogger("billing.collections")

router = APIRouter(tags=["Collections"])


# ---------------------------------------------------------------------------
# GET /collections/queue - List overdue accounts
# ---------------------------------------------------------------------------

@router.get("/collections/queue", response_model=list[CollectionsQueueItem],
            dependencies=[Depends(require_tier("reader"))])
def collections_queue(
    ctx: AuthContext = Depends(get_auth_context),
    min_days: int = Query(1, ge=0),
):
    with get_session() as session:
        today = date.today()
        overdue_invoices = (
            session.query(
                Invoice.customer_id,
                func.sum(Invoice.total_zar - Invoice.amount_paid_zar).label("total_overdue"),
                func.min(Invoice.due_date).label("oldest_due"),
                func.count(Invoice.id).label("inv_count"),
            )
            .filter(
                Invoice.tenant_id == ctx.tenant_id,
                Invoice.status.in_(["sent", "partially_paid", "overdue"]),
                Invoice.due_date < today,
            )
            .group_by(Invoice.customer_id)
            .all()
        )

        items = []
        for row in overdue_invoices:
            days_overdue = (today - row.oldest_due).days
            if days_overdue < min_days:
                continue

            # Determine dunning stage
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
        return items


# ---------------------------------------------------------------------------
# POST /collections/{customer_id}/arrange - Set up payment arrangement
# ---------------------------------------------------------------------------

@router.post(
    "/collections/{customer_id}/arrange",
    response_model=ArrangementRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_tier("admin"))],
)
def create_arrangement(
    customer_id: uuid.UUID,
    body: ArrangementCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        # Verify customer has overdue invoices
        overdue = (
            session.query(func.sum(Invoice.total_zar - Invoice.amount_paid_zar))
            .filter(
                Invoice.tenant_id == ctx.tenant_id,
                Invoice.customer_id == customer_id,
                Invoice.status.in_(["sent", "partially_paid", "overdue"]),
            )
            .scalar()
        ) or Decimal("0.00")

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
        session.flush()
        session.refresh(arrangement)
        return ArrangementRead.model_validate(arrangement)


# ---------------------------------------------------------------------------
# POST /collections/{customer_id}/suspend - Manual suspend
# ---------------------------------------------------------------------------

@router.post("/collections/{customer_id}/suspend", dependencies=[Depends(require_tier("admin"))])
async def manual_suspend(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    if not await suspend_customer(ctx.tenant_id, customer_id):
        # Never report 'suspended' when the network call failed.
        raise HTTPException(status_code=502, detail="The network service did not confirm the suspension")

    # Mark overdue invoices
    with get_session() as session:
        (
            session.query(Invoice)
            .filter(
                Invoice.tenant_id == ctx.tenant_id,
                Invoice.customer_id == customer_id,
                Invoice.status.in_(["sent", "partially_paid"]),
                Invoice.due_date < date.today(),
            )
            .update({"status": "overdue"}, synchronize_session="fetch")
        )

    return {"status": "suspended", "customer_id": str(customer_id)}


# ---------------------------------------------------------------------------
# POST /collections/{customer_id}/reinstate - Reinstate after payment
# ---------------------------------------------------------------------------

@router.post("/collections/{customer_id}/reinstate", dependencies=[Depends(require_tier("admin"))])
async def reinstate_customer(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    if not await _reinstate_customer(ctx.tenant_id, customer_id):
        raise HTTPException(status_code=502, detail="The network service did not confirm the reinstatement")
    return {"status": "reinstated", "customer_id": str(customer_id)}


# ---------------------------------------------------------------------------
# GET /collections/dunning - List dunning actions
# ---------------------------------------------------------------------------

@router.get("/collections/dunning", response_model=list[DunningActionRead],
            dependencies=[Depends(require_tier("reader"))])
def list_dunning_actions(
    ctx: AuthContext = Depends(get_auth_context),
    customer_id: Optional[uuid.UUID] = Query(None),
    action_type: Optional[str] = Query(None),
    pending_only: bool = Query(False),
):
    with get_session() as session:
        q = session.query(DunningAction).filter(DunningAction.tenant_id == ctx.tenant_id)
        if customer_id:
            q = q.filter(DunningAction.customer_id == customer_id)
        if action_type:
            q = q.filter(DunningAction.action_type == action_type)
        if pending_only:
            q = q.filter(DunningAction.executed_at.is_(None))

        items = q.order_by(DunningAction.scheduled_at.asc()).limit(200).all()
        return [DunningActionRead.model_validate(d) for d in items]


# ---------------------------------------------------------------------------
# Network service integration helpers (return True only on a confirmed success)
# ---------------------------------------------------------------------------

async def _network_call(path: str, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> bool:
    try:
        await service_post(
            "network", path, json={"customer_id": str(customer_id)},
            tenant_id=tenant_id, user_id=uuid.UUID(fp.service_user_id()), timeout=5.0,
        )
        logger.info("%s for customer %s: OK", path, customer_id)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("%s failed for customer %s: %s", path, customer_id, exc)
        return False


async def suspend_customer(tenant_id: uuid.UUID, customer_id: uuid.UUID) -> bool:
    """Ask the network service to suspend all services for a customer."""
    return await _network_call("/services/suspend-by-customer", tenant_id, customer_id)


async def _reinstate_customer(tenant_id: uuid.UUID, customer_id: uuid.UUID) -> bool:
    """Ask the network service to reinstate all services for a customer."""
    return await _network_call("/services/reinstate-by-customer", tenant_id, customer_id)
