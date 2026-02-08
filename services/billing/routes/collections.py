"""Collections & Dunning routes — overdue queue, arrangements, suspend/reinstate."""

import logging
import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func

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

logger = logging.getLogger("billing.collections")

router = APIRouter(tags=["Collections"])

NETWORK_URL = os.getenv("NETWORK_SERVICE_URL", "http://network:8005")


# ---------------------------------------------------------------------------
# GET /collections/queue — List overdue accounts
# ---------------------------------------------------------------------------

@router.get("/collections/queue", response_model=list[CollectionsQueueItem])
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
# POST /collections/{customer_id}/arrange — Set up payment arrangement
# ---------------------------------------------------------------------------

@router.post(
    "/collections/{customer_id}/arrange",
    response_model=ArrangementRead,
    status_code=status.HTTP_201_CREATED,
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
# POST /collections/{customer_id}/suspend — Manual suspend
# ---------------------------------------------------------------------------

@router.post("/collections/{customer_id}/suspend")
def manual_suspend(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    _suspend_customer(ctx.tenant_id, customer_id)

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
# POST /collections/{customer_id}/reinstate — Reinstate after payment
# ---------------------------------------------------------------------------

@router.post("/collections/{customer_id}/reinstate")
def reinstate_customer(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    _reinstate_customer(ctx.tenant_id, customer_id)
    return {"status": "reinstated", "customer_id": str(customer_id)}


# ---------------------------------------------------------------------------
# GET /collections/dunning — List dunning actions
# ---------------------------------------------------------------------------

@router.get("/collections/dunning", response_model=list[DunningActionRead])
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
# Network service integration helpers
# ---------------------------------------------------------------------------

def _forward_headers(tenant_id: uuid.UUID) -> dict:
    return {
        "X-User-Id": "00000000-0000-0000-0000-000000000000",
        "X-Tenant-Id": str(tenant_id),
    }


def _suspend_customer(tenant_id: uuid.UUID, customer_id: uuid.UUID) -> None:
    """Call network service to suspend all services for a customer."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                f"{NETWORK_URL}/services/suspend-by-customer",
                json={"customer_id": str(customer_id)},
                headers=_forward_headers(tenant_id),
            )
            logger.info(
                "Suspend request for customer %s: status=%s", customer_id, resp.status_code
            )
    except Exception as exc:
        logger.error("Suspend call failed for customer %s: %s", customer_id, exc)


def _reinstate_customer(tenant_id: uuid.UUID, customer_id: uuid.UUID) -> None:
    """Call network service to reinstate all services for a customer."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                f"{NETWORK_URL}/services/reinstate-by-customer",
                json={"customer_id": str(customer_id)},
                headers=_forward_headers(tenant_id),
            )
            logger.info(
                "Reinstate request for customer %s: status=%s", customer_id, resp.status_code
            )
    except Exception as exc:
        logger.error("Reinstate call failed for customer %s: %s", customer_id, exc)


# ---------------------------------------------------------------------------
# Dunning processor (called by scheduler / background task)
# ---------------------------------------------------------------------------

def process_pending_dunning() -> int:
    """Execute all pending dunning actions whose scheduled_at has passed.

    Returns the number of actions executed.  In production this would be
    triggered by a cron job or background scheduler (e.g. APScheduler).
    """
    executed = 0
    now = datetime.utcnow()

    with get_session() as session:
        pending = (
            session.query(DunningAction)
            .filter(
                DunningAction.executed_at.is_(None),
                DunningAction.scheduled_at <= now,
            )
            .order_by(DunningAction.scheduled_at.asc())
            .all()
        )

        for action in pending:
            try:
                if action.action_type == "sms_reminder":
                    logger.info("SMS reminder for invoice %s", action.invoice_id)
                    action.result = "sms_sent"

                elif action.action_type == "email_warning":
                    logger.info("Email warning for invoice %s", action.invoice_id)
                    action.result = "email_sent"

                elif action.action_type == "auto_suspend":
                    # Check if invoice is still unpaid
                    inv = session.query(Invoice).filter(Invoice.id == action.invoice_id).first()
                    if inv and inv.status not in ("paid", "voided"):
                        _suspend_customer(action.tenant_id, action.customer_id)
                        inv.status = "overdue"
                        action.result = "suspended"
                    else:
                        action.result = "skipped_paid"

                elif action.action_type == "send_to_collections":
                    logger.info("Sending customer %s to collections", action.customer_id)
                    action.result = "sent_to_collections"

                action.executed_at = now
                executed += 1
            except Exception as exc:
                logger.error("Dunning action %s failed: %s", action.id, exc)
                action.result = f"error: {exc}"
                action.executed_at = now

    return executed
