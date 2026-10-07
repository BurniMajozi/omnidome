"""Billing movements: a unified, tenant-scoped feed derived from existing tables (nothing new is stored),
the per-invoice timeline, and per-invoice suggested next actions.

Event types: invoice_issued, invoice_voided, credit_note, payment, partial_payment, payment_failed, refund,
credit, refund_due, dunning_<action>, payment_arrangement, termination_fee,
invoice_emailed / invoice_reminder_sent / invoice_delivered / invoice_bounced / invoice_viewed / ... (and the
same for quote_*), quote_created / quote_sent / quote_viewed / quote_accepted / quote_declined / quote_converted.
Each movement: {id, type, at, amount, status, invoice_id, quote_id, customer_id, actor, next_actions[], detail}.
``next_actions`` lists the ids of the invoice's CURRENT suggested actions (same ids as /timeline).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select

from services.common.auth import AuthContext, get_auth_context
from services.billing import calc, doc_service as ds
from services.billing.access import require_tier
from services.billing.database import get_session
from services.billing.models import (
    BillingFinanceOutbox, CustomerCredit, DunningAction, Invoice, Payment, PaymentArrangement, TerminationFee,
)
from services.billing.models_invoicing import DocumentDeliveryEvent, Quote

logger = logging.getLogger("billing.movements")

router = APIRouter(tags=["Movements"])

PAYABLE = ("sent", "partially_paid", "overdue")
ISSUE_SOURCES = ("billing.invoice", "billing.seat_invoice")
PENDING = "integration pending"


# ── suggested actions (pure) ─────────────────────────────────────────────────

def _act(id_: str, label: str, endpoint: Optional[str], payload: Optional[dict] = None, *, tier: Optional[str] = None,
         reason: Optional[str] = None) -> dict:
    d = {"id": id_, "label": label, "endpoint": endpoint, "payload": payload, "tier": tier}
    if endpoint is None:
        d["reason"] = reason or PENDING
    elif reason:
        d["reason"] = reason
    return d


def suggest_actions(inv: Invoice, *, today: date, has_active_arrangement: bool, open_refund_credit: bool,
                    already_emailed: bool) -> list[dict]:
    """Next actions for one invoice. Endpoints are only given where billing really has one; call-centre
    queueing, the mailer builder, upgrade/downgrade review and refund payout are 'integration pending'."""
    iid = str(inv.id)
    out: list[dict] = []
    if inv.credit_note_of is not None:
        return out
    balance = Decimal(inv.total_zar) - Decimal(inv.amount_paid_zar or 0)
    if inv.status == "draft":
        out.append(_act("issue_invoice", "Issue the invoice", f"POST /invoices/{iid}/send", {"channel": "email"}, tier="clerk"))
        if inv.subscription_id is None:
            out.append(_act("edit_draft", "Edit the draft", f"PUT /invoices/{iid}", None, tier="clerk"))
        return out
    if inv.status in PAYABLE and balance > 0:
        overdue_days = (today - inv.due_date).days
        overdue = overdue_days > 0
        out.append(_act("share_pay_link", "Create a pay link", f"POST /invoices/{iid}/share-link", {}, tier="clerk"))
        out.append(_act("record_payment", "Record a payment", "POST /payments",
                        {"invoice_id": iid, "amount_zar": str(balance), "method": "eft"}, tier="clerk"))
        if not already_emailed:
            out.append(_act("send_invoice_email", "Email the invoice", f"POST /invoices/{iid}/email", {}, tier="clerk"))
        if overdue:
            out.append(_act("send_reminder", "Send a payment reminder", f"POST /invoices/{iid}/email",
                            {"kind": "reminder"}, tier="clerk"))
            out.append(_act("queue_call", "Queue a collections call", None,
                            reason="integration pending: no billing -> call-centre queue endpoint yet"))
            out.append(_act("mailer_builder", "Build a mailer for overdue customers", None,
                            reason="integration pending: no billing -> mailer builder endpoint yet"))
            if not has_active_arrangement:
                third = (balance / Decimal("3")).quantize(Decimal("0.01"))
                out.append(_act("offer_arrangement", "Offer a payment arrangement",
                                f"POST /collections/{inv.customer_id}/arrange",
                                {"total_owed_zar": str(balance), "installment_zar": str(third), "installments_count": 3,
                                 "first_due_date": (today + timedelta(days=7)).isoformat()}, tier="admin",
                                reason="payload is a suggestion; installments_count must be 2..24"))
            if overdue_days >= 14:
                out.append(_act("suspend_service", "Suspend the customer's service",
                                f"POST /collections/{inv.customer_id}/suspend", None, tier="admin"))
            if inv.subscription_id is not None:
                out.append(_act("review_upgrade_request", "Review an upgrade/downgrade request", None,
                                reason="integration pending: no upgrade/downgrade request endpoint in billing"))
        out.append(_act("issue_credit", "Issue a credit note", f"POST /invoices/{iid}/credit-note",
                        {"reason": "<required>"}, tier="admin"))
        if not Decimal(inv.amount_paid_zar or 0) > 0:
            out.append(_act("void_invoice", "Void the invoice", f"POST /invoices/{iid}/void", None, tier="admin"))
    if open_refund_credit:
        out.append(_act("issue_refund", "Refund the customer", None,
                        reason="integration pending: refund payout has no billing endpoint; the amount is held "
                               "as a refund_required row in billing_customer_credits"))
    return out


# ── feed construction ────────────────────────────────────────────────────────

def _iso(dt: Optional[datetime]) -> Optional[str]:
    dt = ds.aware(dt)
    return dt.isoformat() if dt else None


def _move(type_: str, source_id, at: Optional[datetime], *, amount=None, status=None, invoice_id=None, quote_id=None,
          customer_id=None, actor=None, detail=None) -> dict:
    return {"id": f"{type_}:{source_id}", "type": type_, "at": ds.aware(at), "amount": None if amount is None else str(amount),
            "status": status, "invoice_id": str(invoice_id) if invoice_id else None,
            "quote_id": str(quote_id) if quote_id else None,
            "customer_id": str(customer_id) if customer_id else None, "actor": actor, "next_actions": [],
            "detail": detail or {}}


def build_movements(session, tenant_id: uuid.UUID, *, customer_id: Optional[uuid.UUID] = None,
                    invoice_id: Optional[uuid.UUID] = None, start: Optional[datetime] = None,
                    end: Optional[datetime] = None, today: Optional[date] = None) -> tuple[list[dict], dict]:
    """(movements newest first, {invoice_id: [suggested actions]}). Window filters apply to each event's own time."""
    today = today or calc.today_sast()
    out: list[dict] = []

    inv_stmt = select(Invoice).where(Invoice.tenant_id == tenant_id)
    if invoice_id:
        inv_stmt = inv_stmt.where(or_(Invoice.id == invoice_id, Invoice.credit_note_of == invoice_id))
    if customer_id:
        inv_stmt = inv_stmt.where(Invoice.customer_id == customer_id)
    if start and not invoice_id:
        inv_stmt = inv_stmt.where(Invoice.updated_at >= start - timedelta(days=1))
    invoices = session.execute(inv_stmt.order_by(Invoice.updated_at.desc()).limit(2000)).scalars().all()
    by_id = {i.id: i for i in invoices}
    real_ids = [i.id for i in invoices if i.credit_note_of is None]
    cust_ids = {i.customer_id for i in invoices}
    if not invoices:
        invoices_ids = []
    invoices_ids = list(by_id)

    outbox = {}
    if invoices_ids:
        for row in session.execute(select(BillingFinanceOutbox).where(
                BillingFinanceOutbox.tenant_id == tenant_id,
                BillingFinanceOutbox.source_id.in_([str(i) for i in invoices_ids]),
                BillingFinanceOutbox.source.in_(ISSUE_SOURCES + ("billing.void",)))).scalars().all():
            outbox.setdefault((row.source_id, row.source), row.created_at)

    for inv in invoices:
        if inv.credit_note_of is not None:
            out.append(_move("credit_note", inv.id, inv.created_at, amount=inv.total_zar, status=inv.status,
                             invoice_id=inv.credit_note_of, customer_id=inv.customer_id,
                             detail={"credit_note_id": str(inv.id), "number": inv.number}))
            continue
        if inv.status != "draft":
            at = next((outbox[(str(inv.id), s)] for s in ISSUE_SOURCES if (str(inv.id), s) in outbox), inv.created_at)
            out.append(_move("invoice_issued", inv.id, at, amount=inv.total_zar, status=inv.status, invoice_id=inv.id,
                             customer_id=inv.customer_id, detail={"number": inv.number, "due_date": inv.due_date.isoformat()}))
        if inv.status == "voided":
            out.append(_move("invoice_voided", inv.id, outbox.get((str(inv.id), "billing.void"), inv.updated_at),
                             amount=inv.total_zar, status="voided", invoice_id=inv.id, customer_id=inv.customer_id,
                             detail={"number": inv.number}))

    if real_ids:
        pays = session.execute(select(Payment).where(Payment.tenant_id == tenant_id, Payment.invoice_id.in_(real_ids))
                               .order_by(Payment.created_at)).scalars().all()
        running: dict = {}
        for p in pays:
            inv = by_id.get(p.invoice_id)
            if p.status == "completed":
                running[p.invoice_id] = running.get(p.invoice_id, Decimal("0")) + Decimal(p.amount_zar)
                partial = inv is not None and running[p.invoice_id] < Decimal(inv.total_zar)
                t = "partial_payment" if partial else "payment"
            elif p.status == "failed":
                t = "payment_failed"
            elif p.status == "refunded":
                t = "refund"
            else:
                continue
            out.append(_move(t, p.id, p.created_at, amount=p.amount_zar, status=p.status, invoice_id=p.invoice_id,
                             customer_id=p.customer_id, detail={"method": p.method, "reference": p.reference}))
        for d in session.execute(select(DunningAction).where(
                DunningAction.tenant_id == tenant_id, DunningAction.invoice_id.in_(real_ids),
                DunningAction.executed_at.is_not(None))).scalars().all():
            out.append(_move(f"dunning_{d.action_type}", d.id, d.executed_at, status="executed", invoice_id=d.invoice_id,
                             customer_id=d.customer_id, actor="dunning", detail={"step": d.step, "result": d.result}))
        for fee in session.execute(select(TerminationFee).where(
                TerminationFee.tenant_id == tenant_id, TerminationFee.invoice_id.in_(real_ids))).scalars().all():
            out.append(_move("termination_fee", fee.id, fee.created_at, amount=fee.total_etf_zar,
                             status="paid" if fee.paid_at else "invoiced", invoice_id=fee.invoice_id,
                             customer_id=fee.customer_id, detail={"paid_zar": str(fee.paid_zar)}))
        for c in session.execute(select(CustomerCredit).where(
                CustomerCredit.tenant_id == tenant_id, CustomerCredit.invoice_id.in_(real_ids))).scalars().all():
            out.append(_move("refund_due" if c.kind == "refund_required" else "credit", c.id, c.created_at,
                             amount=c.amount_zar, status=c.status, invoice_id=c.invoice_id, customer_id=c.customer_id,
                             detail={"kind": c.kind, "reason": c.reason}))

    if not invoice_id:
        arr_stmt = select(PaymentArrangement).where(PaymentArrangement.tenant_id == tenant_id)
        if customer_id:
            arr_stmt = arr_stmt.where(PaymentArrangement.customer_id == customer_id)
        elif cust_ids:
            arr_stmt = arr_stmt.where(PaymentArrangement.customer_id.in_(cust_ids))
        for a in session.execute(arr_stmt.limit(1000)).scalars().all() if (customer_id or cust_ids) else []:
            out.append(_move("payment_arrangement", a.id, a.created_at, amount=a.total_owed_zar, status=a.status,
                             customer_id=a.customer_id,
                             detail={"installments": a.installments_count, "paid": a.installments_paid}))

    # delivery events (invoice + quote)
    ev_stmt = select(DocumentDeliveryEvent).where(DocumentDeliveryEvent.tenant_id == tenant_id)
    q_stmt = select(Quote).where(Quote.tenant_id == tenant_id)
    if invoice_id:
        ev_stmt = ev_stmt.where(DocumentDeliveryEvent.doc_type == "invoice", DocumentDeliveryEvent.doc_id == invoice_id)
        q_stmt = q_stmt.where(Quote.converted_invoice_id == invoice_id)
    elif customer_id:
        q_stmt = q_stmt.where(Quote.customer_id == customer_id)
    if start:
        ev_stmt = ev_stmt.where(DocumentDeliveryEvent.created_at >= start)
    events = session.execute(ev_stmt.order_by(DocumentDeliveryEvent.created_at.desc()).limit(2000)).scalars().all()
    quotes = {q.id: q for q in session.execute(q_stmt.limit(1000)).scalars().all()}
    for e in events:
        if e.doc_type == "invoice":
            inv = by_id.get(e.doc_id)
            if invoice_id is None and inv is None:
                continue  # filtered out (other customer / not loaded)
            cust, inv_id, q_id = (inv.customer_id if inv else None), e.doc_id, None
        else:
            q = quotes.get(e.doc_id)
            if q is None:
                if invoice_id is not None or customer_id is not None:
                    continue
                q = session.get(Quote, e.doc_id)
                if q is None or q.tenant_id != tenant_id:
                    continue
                quotes[q.id] = q
            cust, inv_id, q_id = q.customer_id, q.converted_invoice_id, q.id
        label = {"sent": "reminder_sent" if e.kind == "reminder" else "emailed", "queued": "email_unconfirmed"}.get(
            e.event_type, e.event_type)
        if e.event_type == "queued" and not (e.detail or {}).get("ambiguous"):
            label = "email_pending"
        out.append(_move(f"{e.doc_type}_{label}", e.id, e.created_at, status=e.event_type, invoice_id=inv_id,
                         quote_id=q_id, customer_id=cust, actor=e.actor,
                         detail={"recipient": e.recipient, "message_id": e.message_id}))

    for q in quotes.values():
        base = dict(amount=q.total_zar, quote_id=q.id, customer_id=q.customer_id, actor=q.created_by,
                    invoice_id=q.converted_invoice_id, detail={"number": q.number, "source": q.source})
        out.append(_move("quote_created", q.id, q.created_at, status="draft", **base))
        for t, at, st in (("quote_sent", q.sent_at, "sent"), ("quote_viewed", q.viewed_at, "viewed"),
                          ("quote_accepted", q.accepted_at, "accepted"), ("quote_declined", q.declined_at, "declined"),
                          ("quote_converted", q.converted_at, "converted")):
            if at:
                out.append(_move(t, q.id, at, status=st, **base))

    # suggestions per invoice
    arr_customers = set()
    refund_invoices = set()
    emailed = set()
    if invoices_ids:
        arr_customers = set(session.execute(select(PaymentArrangement.customer_id).where(
            PaymentArrangement.tenant_id == tenant_id, PaymentArrangement.status == "active",
            PaymentArrangement.customer_id.in_(cust_ids))).scalars().all())
        refund_invoices = set(session.execute(select(CustomerCredit.invoice_id).where(
            CustomerCredit.tenant_id == tenant_id, CustomerCredit.kind == "refund_required",
            CustomerCredit.status == "open", CustomerCredit.invoice_id.in_(invoices_ids))).scalars().all())
        emailed = set(session.execute(select(DocumentDeliveryEvent.doc_id).where(
            DocumentDeliveryEvent.tenant_id == tenant_id, DocumentDeliveryEvent.doc_type == "invoice",
            DocumentDeliveryEvent.event_type == "sent", DocumentDeliveryEvent.kind == "document",
            DocumentDeliveryEvent.doc_id.in_(real_ids or [uuid.uuid4()]))).scalars().all())
    suggestions = {}
    for inv in invoices:
        if inv.credit_note_of is None:
            suggestions[inv.id] = suggest_actions(
                inv, today=today, has_active_arrangement=inv.customer_id in arr_customers,
                open_refund_credit=inv.id in refund_invoices, already_emailed=inv.id in emailed)

    if start:
        out = [m for m in out if m["at"] is not None and m["at"] >= start]
    if end:
        out = [m for m in out if m["at"] is not None and m["at"] < end]
    for m in out:
        if m["invoice_id"]:
            iid = uuid.UUID(m["invoice_id"])
            m["next_actions"] = [a["id"] for a in suggestions.get(iid, [])]
    out.sort(key=lambda m: (m["at"] or datetime.min.replace(tzinfo=timezone.utc), m["id"]), reverse=True)
    return out, suggestions


def _serialise(m: dict) -> dict:
    return {**m, "at": _iso(m["at"])}


def _bounds(from_: Optional[date], to: Optional[date]):
    start = datetime.combine(from_, time.min, tzinfo=timezone.utc) if from_ else None
    end = datetime.combine(to + timedelta(days=1), time.min, tzinfo=timezone.utc) if to else None
    return start, end


@router.get("/billing/movements", dependencies=[Depends(require_tier("reader"))])
async def billing_movements(ctx: AuthContext = Depends(get_auth_context), from_: Optional[date] = Query(None, alias="from"),
                            to: Optional[date] = None, customer_id: Optional[uuid.UUID] = None,
                            type: Optional[str] = Query(None, max_length=200, description="one type, a comma list, or a prefix ending in *"),
                            limit: int = Query(100, ge=1, le=500)):
    """Tenant-scoped feed, newest first. Window is by each event's own timestamp (UTC days)."""
    if from_ and to and to < from_:
        raise HTTPException(422, "'to' cannot be before 'from'")
    start, end = _bounds(from_, to)
    with get_session() as session:
        moves, _ = build_movements(session, ctx.tenant_id, customer_id=customer_id, start=start, end=end)
    if type:
        wanted = [t.strip() for t in type.split(",") if t.strip()]
        moves = [m for m in moves if any(m["type"] == w or (w.endswith("*") and m["type"].startswith(w[:-1])) for w in wanted)]
    return {"items": [_serialise(m) for m in moves[:limit]], "count": min(len(moves), limit), "total_matching": len(moves)}


@router.get("/invoices/{invoice_id}/timeline", dependencies=[Depends(require_tier("reader"))])
async def invoice_timeline(invoice_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    """Everything that happened to one invoice (oldest first) plus its suggested next actions."""
    with get_session() as session:
        inv = ds.load_invoice(session, ctx.tenant_id, invoice_id)
        moves, suggestions = build_movements(session, ctx.tenant_id, invoice_id=invoice_id)
        moves = [m for m in moves if m["invoice_id"] == str(invoice_id)]
        return {"invoice_id": str(inv.id), "number": inv.number, "status": inv.status,
                "events": [_serialise(m) for m in reversed(moves)],
                "suggested_actions": suggestions.get(inv.id, [])}
