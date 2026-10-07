"""Quote business logic: line replacement, state transitions and the idempotent quote -> invoice conversion.

Statuses: draft -> sent -> viewed -> accepted | declined | expired -> converted.
Expiry is lazy (``doc_service.refresh_expiry``): a sent/viewed quote past ``valid_until`` reads as expired.
Sync-session functions; the caller owns the transaction and holds the row lock where noted.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from services.billing import calc, doc_service as ds, invoicing_math as im
from services.billing.database import next_invoice_number
from services.billing.models import Invoice
from services.billing.models_invoicing import InvoiceMeta, Quote, QuoteLine

DEFAULT_VALID_DAYS = 30
OPEN_STATES = ("draft", "sent", "viewed")


def replace_lines(q: Quote, lines: list[dict], totals: dict) -> None:
    q.lines.clear()
    for pos, ln in enumerate(lines):
        q.lines.append(QuoteLine(
            tenant_id=q.tenant_id, position=pos,
            catalog_item_id=uuid.UUID(ln["catalog_item_id"]) if ln.get("catalog_item_id") else None,
            description=ln["description"], quantity=Decimal(ln["quantity"]), unit_price_zar=Decimal(ln["unit_price_zar"]),
            discount_zar=Decimal(ln["discount_zar"]), tax_rate=Decimal(ln["tax_rate"]),
            net_zar=Decimal(ln["total_zar"]), vat_zar=Decimal(ln["vat_zar"]), total_zar=Decimal(ln["total_zar"])))
    q.subtotal_zar, q.vat_zar, q.total_zar = totals["subtotal_zar"], totals["vat_zar"], totals["total_zar"]
    q.discount_total_zar = totals["discount_total_zar"]


def quote_lines_as_dicts(q: Quote) -> list[dict]:
    return [im.compute_line(l.description, l.quantity, l.unit_price_zar, l.discount_zar, "amount", l.tax_rate,
                            l.catalog_item_id) for l in q.lines]


def quote_out(q: Quote) -> dict:
    return {
        "id": str(q.id), "number": q.number, "status": q.status,
        "customer_id": str(q.customer_id) if q.customer_id else None,
        "prospect": {"name": q.prospect_name, "email": q.prospect_email, "phone": q.prospect_phone,
                     "address": q.prospect_address},
        "issue_date": q.issue_date.isoformat(), "valid_until": q.valid_until.isoformat(),
        "lines": [{"line_id": str(l.id), "position": l.position,
                   "catalog_item_id": str(l.catalog_item_id) if l.catalog_item_id else None,
                   "description": l.description, "quantity": format(l.quantity.normalize(), "f"),
                   "unit_price_zar": str(l.unit_price_zar), "discount_zar": str(l.discount_zar),
                   "tax_rate": str(l.tax_rate), "total_zar": str(l.net_zar), "vat_zar": str(l.vat_zar),
                   "line_total_incl_zar": str(l.net_zar + l.vat_zar)} for l in q.lines],
        "subtotal_zar": str(q.subtotal_zar), "discount_total_zar": str(q.discount_total_zar),
        "vat_zar": str(q.vat_zar), "total_zar": str(q.total_zar), "currency": "ZAR",
        "notes": q.notes, "terms": q.terms, "po_number": q.po_number, "source": q.source, "created_by": q.created_by,
        "template_id": str(q.template_id) if q.template_id else None,
        "converted_invoice_id": str(q.converted_invoice_id) if q.converted_invoice_id else None,
        "sent_at": q.sent_at.isoformat() if q.sent_at else None,
        "viewed_at": q.viewed_at.isoformat() if q.viewed_at else None,
        "accepted_at": q.accepted_at.isoformat() if q.accepted_at else None,
        "declined_at": q.declined_at.isoformat() if q.declined_at else None,
        "converted_at": q.converted_at.isoformat() if q.converted_at else None,
        "decision_note": q.decision_note,
        "created_at": q.created_at.isoformat() if q.created_at else None,
    }


def mark_sent(q: Quote) -> None:
    if q.status == "draft":
        q.status, q.sent_at = "sent", ds.utcnow()
    elif q.status not in ("sent", "viewed"):
        raise HTTPException(409, f"A {q.status} quote cannot be sent")


def mark_viewed(q: Quote) -> bool:
    """First view of a sent quote. Returns True when the status changed."""
    if q.status == "sent":
        q.status, q.viewed_at = "viewed", ds.utcnow()
        return True
    if q.viewed_at is None and q.status in ("viewed", "accepted"):
        q.viewed_at = ds.utcnow()
    return False


def apply_decision(q: Quote, decision: str, note: Optional[str], *, internal: bool) -> None:
    """accept/decline. Public (customer) decisions need sent/viewed; staff may also record one on a draft."""
    if decision not in ("accept", "decline"):
        raise HTTPException(422, "decision must be accept or decline")
    ds.refresh_expiry(q)
    allowed = ("draft", "sent", "viewed") if internal else ("sent", "viewed")
    if q.status in ("accepted", "declined") and (
            (q.status == "accepted") == (decision == "accept")):
        return  # repeating the same decision is a no-op (idempotent)
    if q.status not in allowed:
        raise HTTPException(409, f"This quote is {q.status} and cannot be {decision}ed")
    now = ds.utcnow()
    if q.sent_at is None:
        q.sent_at = now
    if decision == "accept":
        q.status, q.accepted_at = "accepted", now
    else:
        q.status, q.declined_at = "declined", now
    q.decision_note = (note or "").strip()[:500] or None


def convert_to_invoice(session, q: Quote, *, customer_id: Optional[uuid.UUID], due_date, created_by: str,
                       force: bool) -> tuple[Invoice, InvoiceMeta, bool]:
    """Create (or return) the DRAFT invoice for a quote. Idempotent: the quote row lock plus the unique
    invoice_meta.quote_id mean a repeat or racing call returns the same invoice with created=False.
    The caller must hold the quote row lock."""
    if q.converted_invoice_id is not None:
        inv = ds.load_invoice(session, q.tenant_id, q.converted_invoice_id)
        return inv, ds.get_meta(session, inv.id), False
    if q.status == "declined":
        raise HTTPException(409, "A declined quote cannot be converted")
    if q.status != "accepted" and not force:
        raise HTTPException(409, f"Quote is {q.status}: it must be accepted before it is converted")
    cust = q.customer_id or customer_id
    if cust is None:
        raise HTTPException(422, "customer_id is required to convert a prospect quote")
    lines = quote_lines_as_dicts(q)
    if not lines:
        raise HTTPException(409, "Quote has no lines")
    totals = im.compute_totals(lines)
    tmpl = ds.get_template(session, q.tenant_id, q.template_id)
    issue = calc.today_sast()
    due = due_date or issue + timedelta(days=tmpl.default_due_days if tmpl else 30)
    if due < issue:
        raise HTTPException(422, "due_date cannot be in the past")
    try:
        with session.begin_nested():
            inv = Invoice(
                id=uuid.uuid4(), tenant_id=q.tenant_id, customer_id=cust,
                number=next_invoice_number(session, q.tenant_id), status="draft", amount_paid_zar=Decimal("0.00"),
                due_date=due, notes=q.notes, line_items=lines, subtotal_zar=totals["subtotal_zar"],
                vat_zar=totals["vat_zar"], total_zar=totals["total_zar"])
            session.add(inv)
            session.flush()
            meta = InvoiceMeta(
                invoice_id=inv.id, tenant_id=q.tenant_id, issue_date=issue, po_number=q.po_number,
                source_type=q.source if q.source in ("field_sales", "technician", "web") else "manual",
                created_by=created_by, terms=q.terms, discount_total_zar=totals["discount_total_zar"],
                template_id=q.template_id, quote_id=q.id,
                bill_to={"name": q.prospect_name, "email": q.prospect_email, "phone": q.prospect_phone,
                         "address": q.prospect_address})
            session.add(meta)
            session.flush()
    except IntegrityError:  # lost a race on uq_invoice_meta_quote
        meta = session.execute(select(InvoiceMeta).where(InvoiceMeta.quote_id == q.id)).scalar_one()
        inv = ds.load_invoice(session, q.tenant_id, meta.invoice_id)
        q.converted_invoice_id = inv.id
        q.status = "converted"
        return inv, meta, False
    q.customer_id = cust
    q.converted_invoice_id = inv.id
    q.converted_at = ds.utcnow()
    q.status = "converted"
    return inv, meta, True
