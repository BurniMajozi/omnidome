"""Invoice creation / issue helpers shared by the invoice, subscription and seat routes."""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from services.billing import calc, finance_posting as fp
from services.billing.database import compute_vat, next_invoice_number
from services.billing.models import DunningAction, Invoice, Subscription, SubscriptionUsage

logger = logging.getLogger("billing.invoicing")

DEFAULT_DUE_DAYS = 30

# (action_type, step, days after due date). Step is part of the idempotency key
# (invoice_id, action_type, step).
DUNNING_STEPS = [
    ("sms_reminder", 0, 1),
    ("email_warning", 0, 7),
    ("auto_suspend", 0, 14),
    ("send_to_collections", 0, 30),
]


def anchor_day(sub: Subscription) -> Optional[int]:
    return sub.billing_anchor.day if sub.billing_anchor else None


def advance_period(sub: Subscription, period_end: date) -> None:
    """Move the subscription to the period that starts where the billed one ended."""
    sub.current_period_start = period_end
    sub.current_period_end = calc.add_interval(period_end, sub.billing_interval, anchor_day(sub))


def schedule_dunning(session, inv: Invoice) -> int:
    """Schedule the dunning ladder for an ISSUED invoice (sent/overdue). Draft invoices are never
    scheduled. Idempotent: existing (invoice, action, step) rows are left alone."""
    if inv.status not in ("sent", "overdue", "partially_paid"):
        return 0
    have = {(a, st) for a, st in session.execute(
        select(DunningAction.action_type, DunningAction.step).where(DunningAction.invoice_id == inv.id)).all()}
    added = 0
    for action_type, step, days in DUNNING_STEPS:
        if (action_type, step) in have:
            continue
        due = inv.due_date + timedelta(days=days)
        session.add(DunningAction(
            tenant_id=inv.tenant_id, invoice_id=inv.id, customer_id=inv.customer_id,
            action_type=action_type, step=step,
            scheduled_at=datetime.combine(due, time(6, 0), tzinfo=timezone.utc),  # 08:00 SAST
        ))
        added += 1
    if added:
        session.flush()
    return added


def enqueue_issue(session, inv: Invoice, source: str = "billing.invoice") -> Optional[dict]:
    """Queue the AR/revenue/VAT journal entry for an issued invoice (same transaction)."""
    entry = fp.invoice_entry(inv.id, inv.number, fp.sast_today(), inv.total_zar, inv.subtotal_zar, inv.vat_zar, source)
    return entry if fp.enqueue(session, inv.tenant_id, entry) is not None else None


def period_invoice(session, sub: Subscription, period_start: date) -> Optional[Invoice]:
    return session.execute(select(Invoice).where(
        Invoice.tenant_id == sub.tenant_id, Invoice.subscription_id == sub.id,
        Invoice.billing_period_start == period_start, Invoice.credit_note_of.is_(None),
    ).order_by(Invoice.created_at).limit(1)).scalar_one_or_none()


def covering_invoices(session, tenant_id: uuid.UUID, sub_ids: list, on: date) -> list[Invoice]:
    """Latest non-credit invoice per subscription whose period covers `on` (what a repeat
    'generate' reports as existing)."""
    if not sub_ids:
        return []
    rows = session.execute(select(Invoice).where(
        Invoice.tenant_id == tenant_id, Invoice.subscription_id.in_(sub_ids), Invoice.credit_note_of.is_(None),
        Invoice.billing_period_start <= on, Invoice.billing_period_end > on,
    ).order_by(Invoice.created_at.desc())).scalars().all()
    seen, out = set(), []
    for inv in rows:
        if inv.subscription_id not in seen:
            seen.add(inv.subscription_id)
            out.append(inv)
    return out


def bill_period(session, sub: Subscription, billing_date: date) -> tuple[Optional[Invoice], bool]:
    """Create-or-get the invoice for the subscription's CURRENT period and advance the period once.

    Returns (invoice, created). (None, False) when the period is not due on `billing_date`.
    The caller must hold a row lock on `sub` (SELECT ... FOR UPDATE); the unique index on
    (subscription_id, billing_period_start) is the backstop.
    """
    period_start = sub.current_period_start or sub.billing_anchor
    if period_start > billing_date:
        return None, False
    period_end = sub.current_period_end or calc.add_interval(period_start, sub.billing_interval, anchor_day(sub))

    existing = period_invoice(session, sub, period_start)
    if existing is not None:
        # Already billed (e.g. the prorated first invoice) but the pointer was not advanced yet.
        if (sub.current_period_start or sub.billing_anchor) == period_start:
            advance_period(sub, existing.billing_period_end or period_end)
        return existing, False

    segment = sub.segment
    if segment and sub.segment_pricing and segment in sub.segment_pricing:
        recurring = Decimal(str(sub.segment_pricing[segment]))
    else:
        recurring = sub.base_price_zar
    unbilled = session.execute(select(SubscriptionUsage).where(
        SubscriptionUsage.subscription_id == sub.id, SubscriptionUsage.billed_invoice_id.is_(None))).scalars().all()
    usage_amount = sum((u.quantity * u.unit_price_zar for u in unbilled), Decimal("0"))
    subtotal = (recurring + usage_amount).quantize(Decimal("0.01"))
    vat = compute_vat(subtotal)

    line_items = [{
        "description": f"Subscription - {sub.plan}" + (f" ({segment})" if segment else ""),
        "quantity": 1, "unit_price_zar": str(recurring), "total_zar": str(recurring),
    }]
    for u in unbilled:
        line_items.append({
            "description": f"Usage: {u.metric}" + (f" - {u.description}" if u.description else ""),
            "quantity": float(u.quantity), "unit_price_zar": str(u.unit_price_zar),
            "total_zar": str((u.quantity * u.unit_price_zar).quantize(Decimal("0.01"))),
        })

    try:
        with session.begin_nested():  # number allocation rolls back with a lost race
            inv = Invoice(
                tenant_id=sub.tenant_id, customer_id=sub.customer_id,
                billing_account_id=sub.billing_account_id, property_id=sub.property_id,
                subscription_id=sub.id, number=next_invoice_number(session, sub.tenant_id), status="draft",
                subtotal_zar=subtotal, vat_zar=vat, total_zar=subtotal + vat,
                due_date=billing_date + timedelta(days=DEFAULT_DUE_DAYS),
                billing_period_start=period_start, billing_period_end=period_end, line_items=line_items,
            )
            session.add(inv)
            session.flush()
    except IntegrityError:
        won = period_invoice(session, sub, period_start)
        if won is None:
            raise
        return won, False

    for u in unbilled:
        u.billed_invoice_id = inv.id
    advance_period(sub, period_end)
    session.flush()
    return inv, True


def apply_payment(session, inv: Invoice, amount: Decimal, method: str, *, reference: Optional[str] = None,
                  paystack_ref: Optional[str] = None, idempotency_key: Optional[str] = None,
                  metadata: Optional[dict] = None):
    """Record a completed payment against `inv` (caller validated state/amount and holds the row lock).

    A draft invoice is issued implicitly first (its AR/revenue entry is queued before the payment's,
    so the ledger never sees a payment against an invoice it has not seen). Queues the payment's
    journal entry. Returns (payment, entries_to_deliver_after_commit)."""
    from services.billing.models import Payment

    entries = []
    if inv.status == "draft":
        inv.status = "sent"
        session.flush()
        e = enqueue_issue(session, inv)
        if e:
            entries.append(e)
    payment = Payment(
        id=uuid.uuid4(), tenant_id=inv.tenant_id, invoice_id=inv.id, customer_id=inv.customer_id,
        amount_zar=amount, method=method, reference=reference, paystack_ref=paystack_ref,
        idempotency_key=idempotency_key, metadata_=metadata, status="completed",
    )
    session.add(payment)
    inv.amount_paid_zar = (inv.amount_paid_zar or Decimal("0")) + amount
    inv.status = "paid" if inv.amount_paid_zar >= inv.total_zar else "partially_paid"
    session.flush()
    pe = fp.payment_entry(payment.id, reference or paystack_ref or str(payment.id)[:8], fp.sast_today(), amount, method)
    if fp.enqueue(session, inv.tenant_id, pe) is not None:
        entries.append(pe)
    return payment, entries
