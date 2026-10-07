"""Customer-app endpoints: a customer's invoices, quotes and statement.

AUTHENTICATION GAP (documented, not papered over): billing has no end-customer identity. access.py states
"There is no customer<->user linkage in this service", and neither portal nor the shared auth library issues
an end-customer token. So these endpoints are tenant-scoped and require a billing ``reader`` identity (a
signed service-to-service identity from the portal/customer-app backend works the same way staff do) and
``customer_id`` is MANDATORY: the calling backend is trusted to pass only the logged-in customer's id.
Customers themselves reach a single document through the share-token flow (/public/...), which needs no
login. When an end-customer token exists, replace the dependency here with it and bind customer_id to it.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from services.common.auth import AuthContext, get_auth_context
from services.billing import calc, doc_service as ds
from services.billing.access import require_tier
from services.billing.database import get_session
from services.billing.models import CustomerCredit, Invoice, Payment
from services.billing.models_invoicing import Quote
from services.billing import quotes as ql

router = APIRouter(prefix="/customer-app", tags=["Customer app"], dependencies=[Depends(require_tier("reader"))])

PAYABLE = ("sent", "partially_paid", "overdue")
MAX_LINKS = 25


def _inv(inv: Invoice, today: date) -> dict:
    total, paid = Decimal(inv.total_zar), Decimal(inv.amount_paid_zar or 0)
    balance = total - paid
    payable = inv.status in PAYABLE and inv.credit_note_of is None and balance > 0
    return {"id": str(inv.id), "number": inv.number, "status": inv.status, "is_credit_note": inv.credit_note_of is not None,
            "due_date": inv.due_date.isoformat(), "total_zar": str(total), "amount_paid_zar": str(paid),
            "balance_zar": str(balance), "overdue": payable and inv.due_date < today, "payable": payable,
            "pay_link": None, "links": {
                "document": f"/invoices/{inv.id}/document", "create_pay_link": f"POST /invoices/{inv.id}/share-link"}}


@router.get("/invoices")
async def customer_invoices(customer_id: uuid.UUID = Query(...), ctx: AuthContext = Depends(get_auth_context),
                            status_filter: Optional[str] = Query(None, alias="status"),
                            include_links: bool = Query(False, description="Mint a fresh expiring pay link per payable invoice"),
                            limit: int = Query(50, ge=1, le=200)):
    """Issued invoices (drafts are never shown) with balances. ``include_links=true`` creates a NEW share link
    for each payable invoice (max 25) and returns it in ``pay_link`` (token shown once, hash stored)."""
    today = calc.today_sast()
    with get_session() as session:
        stmt = select(Invoice).where(Invoice.tenant_id == ctx.tenant_id, Invoice.customer_id == customer_id,
                                     Invoice.status != "draft")
        if status_filter:
            stmt = stmt.where(Invoice.status == status_filter)
        rows = session.execute(stmt.order_by(Invoice.due_date.desc(), Invoice.created_at.desc()).limit(limit)).scalars().all()
        items = [_inv(i, today) for i in rows]
        if include_links:
            minted = 0
            for item in items:
                if item["payable"] and minted < MAX_LINKS:
                    token, row = ds.mint_link(session, ctx.tenant_id, "invoice", uuid.UUID(item["id"]), "customer-app")
                    item["pay_link"] = ds.link_payload(token, row)
                    minted += 1
        payable = [i for i in items if i["payable"]]
        return {"customer_id": str(customer_id), "currency": "ZAR", "items": items,
                "outstanding_zar": str(sum((Decimal(i["balance_zar"]) for i in payable), Decimal("0"))),
                "overdue_zar": str(sum((Decimal(i["balance_zar"]) for i in payable if i["overdue"]), Decimal("0")))}


@router.get("/quotes")
async def customer_quotes(customer_id: uuid.UUID = Query(...), ctx: AuthContext = Depends(get_auth_context),
                          limit: int = Query(50, ge=1, le=200)):
    """The customer's quotes except drafts (a draft is not yet offered to the customer)."""
    with get_session() as session:
        rows = session.execute(select(Quote).where(
            Quote.tenant_id == ctx.tenant_id, Quote.customer_id == customer_id, Quote.status != "draft")
            .order_by(Quote.created_at.desc()).limit(limit)).scalars().all()
        for q in rows:
            ds.refresh_expiry(q)
        return {"customer_id": str(customer_id), "items": [
            {k: v for k, v in ql.quote_out(q).items() if k in (
                "id", "number", "status", "issue_date", "valid_until", "total_zar", "vat_zar", "subtotal_zar",
                "converted_invoice_id", "accepted_at", "declined_at")}
            | {"actionable": q.status in ("sent", "viewed"), "links": {"document": f"/quotes/{q.id}/document",
                                                                       "create_accept_link": f"POST /quotes/{q.id}/share-link"}}
            for q in rows]}


@router.get("/statement")
async def customer_statement(customer_id: uuid.UUID = Query(...), ctx: AuthContext = Depends(get_auth_context),
                             from_: Optional[date] = Query(None, alias="from"), to: Optional[date] = None):
    """Chronological ledger: invoices and credit notes (debit/credit), completed payments, with an opening
    and closing balance for the window (everything before ``from`` is rolled into the opening balance)."""
    if from_ and to and to < from_:
        raise HTTPException(422, "'to' cannot be before 'from'")
    start = datetime.combine(from_, time.min, tzinfo=timezone.utc) if from_ else None
    with get_session() as session:
        invs = session.execute(select(Invoice).where(
            Invoice.tenant_id == ctx.tenant_id, Invoice.customer_id == customer_id,
            Invoice.status.notin_(("draft", "voided")))).scalars().all()
        inv_ids = [i.id for i in invs]
        pays = session.execute(select(Payment).where(
            Payment.tenant_id == ctx.tenant_id, Payment.customer_id == customer_id, Payment.status == "completed")
        ).scalars().all() if inv_ids else []
        entries = []
        for i in invs:
            d = ds.aware(i.created_at).date() if i.created_at else i.due_date
            amt = Decimal(i.total_zar)
            entries.append({"date": d, "kind": "credit_note" if i.credit_note_of else "invoice", "reference": i.number,
                            "debit": amt if amt > 0 else Decimal("0"), "credit": -amt if amt < 0 else Decimal("0")})
        for p in pays:
            entries.append({"date": ds.aware(p.created_at).date(), "kind": "payment", "reference": p.reference or str(p.id)[:8],
                            "debit": Decimal("0"), "credit": Decimal(p.amount_zar)})
        entries.sort(key=lambda e: (e["date"], e["kind"]))
        opening = sum((e["debit"] - e["credit"] for e in entries if from_ and e["date"] < from_), Decimal("0"))
        window = [e for e in entries if (not from_ or e["date"] >= from_) and (not to or e["date"] <= to)]
        running, lines = opening, []
        for e in window:
            running += e["debit"] - e["credit"]
            lines.append({"date": e["date"].isoformat(), "kind": e["kind"], "reference": e["reference"],
                          "debit_zar": str(e["debit"]), "credit_zar": str(e["credit"]), "balance_zar": str(running)})
        unapplied = session.execute(select(CustomerCredit).where(
            CustomerCredit.tenant_id == ctx.tenant_id, CustomerCredit.customer_id == customer_id,
            CustomerCredit.status == "open")).scalars().all()
        return {"customer_id": str(customer_id), "currency": "ZAR", "from": from_.isoformat() if from_ else None,
                "to": to.isoformat() if to else None, "opening_balance_zar": str(opening), "lines": lines,
                "closing_balance_zar": str(running),
                "open_credits_zar": str(sum((Decimal(c.amount_zar) for c in unapplied), Decimal("0")))}
