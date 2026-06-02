"""Subscription Management routes — create, cancel, reactivate, usage, invoice generation."""

import logging
import uuid
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.common.auth import AuthContext, get_auth_context
from services.billing.database import compute_vat, get_session, next_invoice_number
from services.billing.models import Invoice, Subscription, SubscriptionUsage
from services.billing.schemas import (
    CreateSubscriptionRequest,
    InvoicePreviewResponse,
    InvoiceRead,
    ProratedSubscriptionRequest,
    ProrationResponse,
    RecordUsageRequest,
    SubscriptionRead,
    SubscriptionUsageRead,
)

logger = logging.getLogger("billing.subscriptions")

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])

DEFAULT_DUE_DAYS = 30


# ---------------------------------------------------------------------------
# POST /subscriptions — Create a new subscription
# ---------------------------------------------------------------------------

@router.post("", response_model=SubscriptionRead, status_code=status.HTTP_201_CREATED)
def create_subscription(
    body: CreateSubscriptionRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create a new customer subscription."""
    with get_session() as session:
        now = datetime.now(tz=timezone.utc)
        trial_ends_at = None
        if body.trial_days > 0:
            trial_ends_at = now + timedelta(days=body.trial_days)

        billing_anchor = body.billing_anchor or date.today()
        period_start = billing_anchor
        period_end = _add_interval(billing_anchor, body.billing_interval)

        sub = Subscription(
            tenant_id=ctx.tenant_id,
            customer_id=body.customer_id,
            plan=body.plan,
            segment=body.segment,
            status="trial" if trial_ends_at else "active",
            billing_interval=body.billing_interval,
            base_price_zar=body.base_price_zar,
            segment_pricing=body.segment_pricing,
            billing_anchor=billing_anchor,
            current_period_start=period_start,
            current_period_end=period_end,
            trial_ends_at=trial_ends_at,
        )
        session.add(sub)
        session.flush()
        session.refresh(sub)
        logger.info("Created subscription %s for customer %s", sub.id, sub.customer_id)
        return SubscriptionRead.model_validate(sub)


# ---------------------------------------------------------------------------
# POST /subscriptions/prorated — Create with prorated first month
# ---------------------------------------------------------------------------

@router.post("/prorated", response_model=ProrationResponse, status_code=status.HTTP_201_CREATED)
def create_prorated_subscription(
    body: ProratedSubscriptionRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create a subscription with a prorated first billing period.

    Calculates the prorated amount from *start_date* to the next billing
    anchor (*billing_anchor*).  The subscription is created with the
    prorated first invoice.
    """
    with get_session() as session:
        # Determine the effective price (segment override or base)
        effective_price = body.base_price_zar
        if body.segment_pricing and body.segment and body.segment in body.segment_pricing:
            effective_price = Decimal(str(body.segment_pricing[body.segment]))

        # Calculate proration
        billing_period_end = _add_interval(body.billing_anchor, body.billing_interval)
        days_in_period = (billing_period_end - body.start_date).days
        total_days = (billing_period_end - body.billing_anchor).days
        if total_days <= 0:
            raise HTTPException(status_code=400, detail="billing_anchor must be before period end")

        prorated = (effective_price * Decimal(days_in_period) / Decimal(total_days)).quantize(Decimal("0.01"))

        # Create subscription
        sub = Subscription(
            tenant_id=ctx.tenant_id,
            customer_id=body.customer_id,
            plan=body.plan,
            segment=body.segment,
            status="active",
            billing_interval=body.billing_interval,
            base_price_zar=body.base_price_zar,
            segment_pricing=body.segment_pricing,
            billing_anchor=body.billing_anchor,
            current_period_start=body.start_date,
            current_period_end=billing_period_end,
        )
        session.add(sub)
        session.flush()
        session.refresh(sub)

        # Generate prorated invoice
        vat = compute_vat(prorated)
        total = prorated + vat
        number = next_invoice_number(session, ctx.tenant_id)

        inv = Invoice(
            tenant_id=ctx.tenant_id,
            customer_id=body.customer_id,
            subscription_id=sub.id,
            number=number,
            status="draft",
            subtotal_zar=prorated,
            vat_zar=vat,
            total_zar=total,
            due_date=date.today() + timedelta(days=DEFAULT_DUE_DAYS),
            billing_period_start=body.start_date,
            billing_period_end=billing_period_end,
            line_items=[{
                "description": f"Prorated subscription — {body.plan}"
                              + (f" ({body.segment})" if body.segment else ""),
                "quantity": days_in_period,
                "unit_price_zar": str(effective_price / Decimal(total_days)),
                "total_zar": str(prorated),
            }],
            notes=f"Prorated first invoice: {days_in_period} of {total_days} days",
        )
        session.add(inv)
        session.flush()

        logger.info(
            "Created prorated subscription %s, invoice %s for R%s",
            sub.id, inv.number, prorated,
        )

        return ProrationResponse(
            prorated_amount_zar=prorated,
            days_remaining=days_in_period,
            days_in_month=total_days,
            full_price_zar=effective_price,
            billing_period_start=body.start_date,
            billing_period_end=billing_period_end,
        )


# ---------------------------------------------------------------------------
# GET /subscriptions/{id} — Get subscription detail
# ---------------------------------------------------------------------------

@router.get("/{subscription_id}", response_model=SubscriptionRead)
def get_subscription(
    subscription_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        sub = (
            session.query(Subscription)
            .filter(Subscription.id == subscription_id, Subscription.tenant_id == ctx.tenant_id)
            .first()
        )
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")
        return SubscriptionRead.model_validate(sub)


# ---------------------------------------------------------------------------
# POST /subscriptions/{id}/cancel — Soft-cancel
# ---------------------------------------------------------------------------

@router.post("/{subscription_id}/cancel", response_model=SubscriptionRead)
def cancel_subscription(
    subscription_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    at_period_end: bool = Query(False, description="Defer cancellation to end of billing period"),
):
    """Soft-cancel a subscription.

    Sets status to *cancelled* (or *cancel_at_period_end* if deferred).
    """
    with get_session() as session:
        sub = (
            session.query(Subscription)
            .filter(Subscription.id == subscription_id, Subscription.tenant_id == ctx.tenant_id)
            .first()
        )
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")
        if sub.status == "cancelled":
            raise HTTPException(status_code=400, detail="Subscription is already cancelled")

        if at_period_end:
            sub.cancel_at_period_end = True
        else:
            sub.status = "cancelled"
            sub.cancelled_at = datetime.now(tz=timezone.utc)

        session.flush()
        session.refresh(sub)
        logger.info("Cancelled subscription %s (at_period_end=%s)", sub.id, at_period_end)
        return SubscriptionRead.model_validate(sub)


# ---------------------------------------------------------------------------
# POST /subscriptions/{id}/reactivate — Reactivate
# ---------------------------------------------------------------------------

@router.post("/{subscription_id}/reactivate", response_model=SubscriptionRead)
def reactivate_subscription(
    subscription_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Reactivate a cancelled or paused subscription."""
    with get_session() as session:
        sub = (
            session.query(Subscription)
            .filter(Subscription.id == subscription_id, Subscription.tenant_id == ctx.tenant_id)
            .first()
        )
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")
        if sub.status not in ("cancelled", "paused", "expired"):
            raise HTTPException(status_code=400, detail=f"Cannot reactivate a {sub.status} subscription")

        sub.status = "active"
        sub.cancelled_at = None
        sub.cancel_at_period_end = False
        session.flush()
        session.refresh(sub)
        logger.info("Reactivated subscription %s", sub.id)
        return SubscriptionRead.model_validate(sub)


# ---------------------------------------------------------------------------
# POST /subscriptions/{id}/usage — Record usage
# ---------------------------------------------------------------------------

@router.post("/{subscription_id}/usage", response_model=SubscriptionUsageRead, status_code=status.HTTP_201_CREATED)
def record_usage(
    subscription_id: uuid.UUID,
    body: RecordUsageRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Record usage for usage-based billing.  Usage rolls up into the next invoice."""
    with get_session() as session:
        sub = (
            session.query(Subscription)
            .filter(Subscription.id == subscription_id, Subscription.tenant_id == ctx.tenant_id)
            .first()
        )
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")
        if sub.status in ("cancelled", "expired"):
            raise HTTPException(status_code=400, detail=f"Cannot record usage for a {sub.status} subscription")

        usage = SubscriptionUsage(
            subscription_id=sub.id,
            metric=body.metric,
            quantity=body.quantity,
            unit_price_zar=body.unit_price_zar,
            description=body.description,
        )
        session.add(usage)
        session.flush()
        session.refresh(usage)
        logger.info(
            "Recorded usage for subscription %s: %s %s @ R%s/unit",
            sub.id, body.quantity, body.metric, body.unit_price_zar,
        )
        return SubscriptionUsageRead.model_validate(usage)


# ---------------------------------------------------------------------------
# GET /subscriptions/{id}/invoice-preview — Preview next invoice
# ---------------------------------------------------------------------------

@router.get("/{subscription_id}/invoice-preview", response_model=InvoicePreviewResponse)
def preview_invoice(
    subscription_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Generate a preview of the next invoice for a subscription (no DB write)."""
    with get_session() as session:
        sub = (
            session.query(Subscription)
            .filter(Subscription.id == subscription_id, Subscription.tenant_id == ctx.tenant_id)
            .first()
        )
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")

        return _build_invoice_preview(session, sub)


# ---------------------------------------------------------------------------
# POST /subscriptions/{id}/generate-invoice — Generate actual invoice
# ---------------------------------------------------------------------------

@router.post("/{subscription_id}/generate-invoice", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED)
def generate_invoice(
    subscription_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Generate an actual invoice from the subscription.

    Skips if the subscription is still in its trial period.
    Rolls up any unbilled usage into the invoice.
    """
    with get_session() as session:
        sub = (
            session.query(Subscription)
            .filter(Subscription.id == subscription_id, Subscription.tenant_id == ctx.tenant_id)
            .first()
        )
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")

        # Trial check
        if sub.is_in_trial():
            raise HTTPException(
                status_code=400,
                detail=f"Cannot generate invoice during trial. Trial ends at {sub.trial_ends_at}",
            )

        if sub.status in ("cancelled", "expired"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot generate invoice for a {sub.status} subscription",
            )

        preview = _build_invoice_preview(session, sub)

        # Create the invoice
        number = next_invoice_number(session, ctx.tenant_id)
        inv = Invoice(
            tenant_id=ctx.tenant_id,
            customer_id=sub.customer_id,
            subscription_id=sub.id,
            number=number,
            status="draft",
            subtotal_zar=preview.subtotal_zar,
            vat_zar=preview.vat_zar,
            total_zar=preview.total_zar,
            due_date=date.today() + timedelta(days=DEFAULT_DUE_DAYS),
            billing_period_start=preview.billing_period_start,
            billing_period_end=preview.billing_period_end,
            line_items=preview.line_items,
        )
        session.add(inv)
        session.flush()
        session.refresh(inv)

        # Mark usage as billed
        unbilled_usage = (
            session.query(SubscriptionUsage)
            .filter(
                SubscriptionUsage.subscription_id == sub.id,
                SubscriptionUsage.billed_invoice_id.is_(None),
            )
            .all()
        )
        for u in unbilled_usage:
            u.billed_invoice_id = inv.id

        # Advance billing period
        sub.current_period_start = preview.billing_period_end
        sub.current_period_end = _add_interval(preview.billing_period_end, sub.billing_interval)

        session.flush()
        session.refresh(inv)

        logger.info(
            "Generated invoice %s for subscription %s: R%s",
            inv.number, sub.id, inv.total_zar,
        )
        return InvoiceRead.model_validate(inv)


# ---------------------------------------------------------------------------
# GET /subscriptions — List subscriptions
# ---------------------------------------------------------------------------

@router.get("", response_model=list[SubscriptionRead])
def list_subscriptions(
    ctx: AuthContext = Depends(get_auth_context),
    customer_id: Optional[uuid.UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    plan: Optional[str] = Query(None),
):
    with get_session() as session:
        q = session.query(Subscription).filter(Subscription.tenant_id == ctx.tenant_id)
        if customer_id:
            q = q.filter(Subscription.customer_id == customer_id)
        if status_filter:
            q = q.filter(Subscription.status == status_filter)
        if plan:
            q = q.filter(Subscription.plan == plan)

        items = q.order_by(Subscription.created_at.desc()).limit(200).all()
        return [SubscriptionRead.model_validate(s) for s in items]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _add_interval(start: date, interval: str) -> date:
    """Return *start* plus the given billing interval."""
    months = {"monthly": 1, "quarterly": 3, "semi_annual": 6, "annual": 12}.get(interval, 1)
    # Add months, clamping to last valid day
    month = start.month + months
    year = start.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    max_day = monthrange(year, month)[1]
    day = min(start.day, max_day)
    return date(year, month, day)


def _build_invoice_preview(session, sub: Subscription) -> InvoicePreviewResponse:
    """Build an InvoicePreviewResponse for a subscription without writing to DB."""
    # Determine effective recurring price
    segment = sub.segment
    if segment:
        recurring = sub.get_segment_price(segment, sub.base_price_zar)
    else:
        recurring = sub.base_price_zar

    # Gather unbilled usage
    unbilled_usage = (
        session.query(SubscriptionUsage)
        .filter(
            SubscriptionUsage.subscription_id == sub.id,
            SubscriptionUsage.billed_invoice_id.is_(None),
        )
        .all()
    )
    usage_amount = sum(u.quantity * u.unit_price_zar for u in unbilled_usage)

    subtotal = recurring + usage_amount
    vat = compute_vat(subtotal)
    total = subtotal + vat

    # Determine billing period
    period_start = sub.current_period_start or sub.billing_anchor
    period_end = sub.current_period_end or _add_interval(period_start, sub.billing_interval)

    line_items = [{
        "description": f"Subscription — {sub.plan}" + (f" ({segment})" if segment else ""),
        "quantity": 1,
        "unit_price_zar": str(recurring),
        "total_zar": str(recurring),
    }]
    for u in unbilled_usage:
        line_items.append({
            "description": f"Usage: {u.metric}" + (f" — {u.description}" if u.description else ""),
            "quantity": float(u.quantity),
            "unit_price_zar": str(u.unit_price_zar),
            "total_zar": str((u.quantity * u.unit_price_zar).quantize(Decimal("0.01"))),
        })

    return InvoicePreviewResponse(
        subscription_id=sub.id,
        customer_id=sub.customer_id,
        plan=sub.plan,
        segment=segment,
        recurring_amount_zar=recurring,
        usage_amount_zar=usage_amount.quantize(Decimal("0.01")),
        subtotal_zar=subtotal.quantize(Decimal("0.01")),
        vat_zar=vat,
        total_zar=total.quantize(Decimal("0.01")),
        billing_period_start=period_start,
        billing_period_end=period_end,
        line_items=line_items,
        unbilled_usage=[SubscriptionUsageRead.model_validate(u) for u in unbilled_usage],
        is_in_trial=sub.is_in_trial(),
        trial_ends_at=sub.trial_ends_at,
    )
