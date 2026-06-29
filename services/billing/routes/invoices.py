"""Invoice Management routes — generation, listing, detail, send, credit notes.

All routes use async SQLAlchemy (session.execute(select(...))).
"""

import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.common.http_client import service_post
from services.billing.database import compute_vat, get_session, next_invoice_number
from services.billing.models import DunningAction, Invoice, Subscription, SubscriptionUsage
from services.billing.routes.subscriptions import _add_interval
from services.billing.schemas import (
    CreditNoteRequest,
    InvoiceGenerateRequest,
    InvoiceRead,
    InvoiceSendRequest,
    LineItem,
    PaginatedResponse,
)

logger = logging.getLogger("billing.invoices")

router = APIRouter(prefix="/invoices", tags=["Invoices"])

DEFAULT_DUE_DAYS = 30


# ---------------------------------------------------------------------------
# POST /invoices/generate — Batch-generate monthly invoices
# ---------------------------------------------------------------------------

@router.post("/generate", response_model=list[InvoiceRead], status_code=status.HTTP_201_CREATED)
async def generate_invoices(
    body: InvoiceGenerateRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Batch-generate invoices from active subscriptions.

    For each active subscription, looks up the subscription's pricing
    (base_price_zar + segment_pricing), rolls up unbilled usage, and
    creates a linked invoice. Skips subscriptions still in trial.
    """
    with get_session() as session:
        # Resolve target subscriptions
        sub_stmt = select(Subscription).where(
            Subscription.tenant_id == ctx.tenant_id,
            Subscription.status.in_(["active", "trial"]),
        )
        if body.customer_ids:
            sub_stmt = sub_stmt.where(Subscription.customer_id.in_(body.customer_ids))

        sub_result = session.execute(sub_stmt)
        subscriptions = sub_result.scalars().all()

        created: list[Invoice] = []
        for sub in subscriptions:
            # Skip trial subscriptions
            if sub.is_in_trial():
                continue

            # Resolve segment pricing
            segment = sub.segment
            if segment and sub.segment_pricing and segment in sub.segment_pricing:
                recurring = Decimal(str(sub.segment_pricing[segment]))
            else:
                recurring = sub.base_price_zar

            # Roll up unbilled usage
            usage_result = session.execute(
                select(SubscriptionUsage).where(
                    SubscriptionUsage.subscription_id == sub.id,
                    SubscriptionUsage.billed_invoice_id.is_(None),
                )
            )
            unbilled = usage_result.scalars().all()
            usage_amount = sum(u.quantity * u.unit_price_zar for u in unbilled)

            subtotal = recurring + usage_amount
            vat = compute_vat(subtotal)
            total = subtotal + vat

            period_start = sub.current_period_start or sub.billing_anchor
            period_end = sub.current_period_end or _add_interval(period_start, sub.billing_interval)

            line_items = [{
                "description": f"Subscription — {sub.plan}" + (f" ({segment})" if segment else ""),
                "quantity": 1,
                "unit_price_zar": str(recurring),
                "total_zar": str(recurring),
            }]
            for u in unbilled:
                line_items.append({
                    "description": f"Usage: {u.metric}" + (f" — {u.description}" if u.description else ""),
                    "quantity": float(u.quantity),
                    "unit_price_zar": str(u.unit_price_zar),
                    "total_zar": str((u.quantity * u.unit_price_zar).quantize(Decimal("0.01"))),
                })

            number = next_invoice_number(session, ctx.tenant_id)
            inv = Invoice(
                tenant_id=ctx.tenant_id,
                customer_id=sub.customer_id,
                billing_account_id=sub.billing_account_id,
                property_id=sub.property_id,
                subscription_id=sub.id,
                number=number,
                status="draft",
                subtotal_zar=subtotal.quantize(Decimal("0.01")),
                vat_zar=vat,
                total_zar=total.quantize(Decimal("0.01")),
                due_date=body.billing_date + timedelta(days=DEFAULT_DUE_DAYS),
                billing_period_start=period_start,
                billing_period_end=period_end,
                line_items=line_items,
            )
            session.add(inv)
            session.flush()
            session.refresh(inv)

            # Mark usage as billed
            for u in unbilled:
                u.billed_invoice_id = inv.id

            # Advance billing period
            sub.current_period_start = period_end
            sub.current_period_end = _add_interval(period_end, sub.billing_interval)

            _schedule_dunning(session, inv)
            created.append(inv)

        return [InvoiceRead.model_validate(i) for i in created]


async def _post_invoice_to_gl(inv: Invoice, ctx: AuthContext) -> None:
    """Push a GL revenue-recognition entry to finance the moment an invoice is sent.

    Uses the same source="BILLING"/source_id=<invoice id> convention finance's
    own /billing/sync-invoices pull job already keys off, so that pull job
    remains a safe reconciliation fallback if this call fails (finance down,
    network blip, etc.) — it'll just pick up anything this push missed on its
    next run instead of double-posting.
    """
    try:
        await service_post(
            "finance", "/journal-entries",
            tenant_id=ctx.tenant_id, user_id=getattr(ctx, "user_id", None),
            json={
                "entry_date": date.today().isoformat(),
                "description": f"Revenue recognition - Invoice {inv.number}",
                "source": "BILLING",
                "source_id": str(inv.id),
                "lines": [
                    {
                        "account_code": "1100", "account_name": "Accounts Receivable",
                        "description": f"AR - Customer {str(inv.customer_id)[:8]}",
                        "debit": float(inv.total_zar), "credit": 0,
                    },
                    {
                        "account_code": "4000", "account_name": "Revenue - FTTH Subscriptions",
                        "description": f"Revenue - Invoice {inv.number}",
                        "debit": 0, "credit": float(inv.total_zar),
                    },
                ],
            },
        )
    except Exception as exc:
        logger.warning(
            "Failed to post GL entry for invoice %s to finance (%s) — "
            "finance's /billing/sync-invoices reconciliation job will catch it later",
            inv.number, exc,
        )


def _schedule_dunning(session, inv: Invoice) -> None:
    """Pre-schedule the dunning workflow for an invoice."""
    due = inv.due_date
    steps = [
        ("sms_reminder", timedelta(days=1)),
        ("email_warning", timedelta(days=7)),
        ("auto_suspend", timedelta(days=14)),
        ("send_to_collections", timedelta(days=30)),
    ]
    for action_type, delta in steps:
        session.add(DunningAction(
            tenant_id=inv.tenant_id,
            invoice_id=inv.id,
            customer_id=inv.customer_id,
            action_type=action_type,
            scheduled_at=due + delta,
        ))


# ---------------------------------------------------------------------------
# GET /invoices — List with filters and pagination
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse)
async def list_invoices(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    customer_id: Optional[uuid.UUID] = Query(None),
    due_from: Optional[date] = Query(None),
    due_to: Optional[date] = Query(None),
    min_amount: Optional[Decimal] = Query(None),
    max_amount: Optional[Decimal] = Query(None),
):
    with get_session() as session:
        stmt = select(Invoice).where(Invoice.tenant_id == ctx.tenant_id)
        count_stmt = select(func.count(Invoice.id)).where(Invoice.tenant_id == ctx.tenant_id)

        if status_filter:
            stmt = stmt.where(Invoice.status == status_filter)
            count_stmt = count_stmt.where(Invoice.status == status_filter)
        if customer_id:
            stmt = stmt.where(Invoice.customer_id == customer_id)
            count_stmt = count_stmt.where(Invoice.customer_id == customer_id)
        if due_from:
            stmt = stmt.where(Invoice.due_date >= due_from)
            count_stmt = count_stmt.where(Invoice.due_date >= due_from)
        if due_to:
            stmt = stmt.where(Invoice.due_date <= due_to)
            count_stmt = count_stmt.where(Invoice.due_date <= due_to)
        if min_amount is not None:
            stmt = stmt.where(Invoice.total_zar >= min_amount)
            count_stmt = count_stmt.where(Invoice.total_zar >= min_amount)
        if max_amount is not None:
            stmt = stmt.where(Invoice.total_zar <= max_amount)
            count_stmt = count_stmt.where(Invoice.total_zar <= max_amount)

        total_result = session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = stmt.order_by(Invoice.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        items_result = session.execute(stmt)
        items = items_result.scalars().all()

        return PaginatedResponse(
            items=[InvoiceRead.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


# ---------------------------------------------------------------------------
# GET /invoices/{id} — Detail
# ---------------------------------------------------------------------------

@router.get("/{invoice_id}", response_model=InvoiceRead)
async def get_invoice(
    invoice_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        result = session.execute(
            select(Invoice).where(
                Invoice.id == invoice_id,
                Invoice.tenant_id == ctx.tenant_id,
            )
        )
        inv = result.scalar_one_or_none()
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        return InvoiceRead.model_validate(inv)


# ---------------------------------------------------------------------------
# POST /invoices/{id}/send — Send invoice via email/SMS
# ---------------------------------------------------------------------------

@router.post("/{invoice_id}/send", response_model=InvoiceRead)
async def send_invoice(
    invoice_id: uuid.UUID,
    body: InvoiceSendRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        result = session.execute(
            select(Invoice).where(
                Invoice.id == invoice_id,
                Invoice.tenant_id == ctx.tenant_id,
            )
        )
        inv = result.scalar_one_or_none()
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if inv.status == "voided":
            raise HTTPException(status_code=400, detail="Cannot send a voided invoice")

        logger.info("Sending invoice %s via %s to customer %s", inv.number, body.channel, inv.customer_id)

        if inv.status == "draft":
            inv.status = "sent"
            session.flush()
            session.refresh(inv)
            await _post_invoice_to_gl(inv, ctx)

        return InvoiceRead.model_validate(inv)


# ---------------------------------------------------------------------------
# POST /invoices/{id}/credit-note — Issue credit note
# ---------------------------------------------------------------------------

@router.post("/{invoice_id}/credit-note", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED)
async def create_credit_note(
    invoice_id: uuid.UUID,
    body: CreditNoteRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        result = session.execute(
            select(Invoice).where(
                Invoice.id == invoice_id,
                Invoice.tenant_id == ctx.tenant_id,
            )
        )
        original = result.scalar_one_or_none()
        if not original:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if original.status == "voided":
            raise HTTPException(status_code=400, detail="Cannot credit a voided invoice")

        if body.line_items:
            li_dicts = [li.model_dump(mode="json") for li in body.line_items]
            subtotal = sum(
                Decimal(str(li.unit_price_zar)) * li.quantity for li in body.line_items
            )
        else:
            li_dicts = original.line_items or []
            subtotal = original.subtotal_zar

        vat = compute_vat(subtotal)
        total = subtotal + vat

        number = next_invoice_number(session, ctx.tenant_id)

        cn = Invoice(
            tenant_id=ctx.tenant_id,
            customer_id=original.customer_id,
            number=f"CN-{number}",
            status="paid",
            subtotal_zar=-subtotal,
            vat_zar=-vat,
            total_zar=-total,
            amount_paid_zar=Decimal("0.00"),
            due_date=date.today(),
            line_items=li_dicts,
            notes=f"Credit note for {original.number}: {body.reason}",
            credit_note_of=original.id,
        )
        session.add(cn)

        if abs(total) >= original.total_zar:
            original.status = "voided"

        session.flush()
        session.refresh(cn)
        return InvoiceRead.model_validate(cn)
