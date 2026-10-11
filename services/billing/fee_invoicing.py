"""Issue OmniDome's monthly tax invoice to a tenant for the fees it was charged.

Covers every fee not yet invoiced up to the end of the period: card-collection commission (billing_gateway_charges) and payout fees
(billing_payout_items), each already stored VAT-exclusive with the VAT added on top at the time it was charged. A fee that arrives
after its month was invoiced simply rolls into the next invoice. A payout that fails after its fee was invoiced returns that fee to the
wallet (see routes/payouts.py), and the return appears as a negative adjustment line on the next invoice, so the tenant is never
invoiced for a fee it got back. If the net amount is not positive nothing is issued and the adjustment carries forward.

The document is immutable and sequentially numbered (ODF-<year>-<serial>). Supplier (OmniDome) and customer (the tenant) details are
snapshotted when it is issued. It is a "Tax invoice" only when OmniDome is a VAT vendor with a VAT number; otherwise a plain "Invoice"
(no VAT) or a "Pro forma invoice" when OmniDome's own details are incomplete.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from services.billing import calc, gateway, platform_tax
from services.billing.models_fee_invoices import FeeInvoice, FeeInvoiceSequence
from services.billing.models_gateway import GatewayCharge
from services.billing.models_payouts import PayoutBatch, PayoutItem
from services.billing.tax_store import profile_for

logger = logging.getLogger("billing.fee_invoicing")

FULL_INVOICE_ABOVE_CENTS = 500_000      # SARS: a full tax invoice (with the recipient's name and address) above R5,000


def previous_period(today: Optional[date] = None) -> str:
    today = today or calc.today_sast()
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return f"{year:04d}-{month:02d}"


def _json(value):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value) if value else {}
    except (TypeError, ValueError):
        return {}


def supplier_snapshot(session) -> dict:
    """OmniDome's details as they should appear on the document (the platform invoice settings, else the shipped catalogue default)."""
    from services.common.platform_pricing import catalog
    profile = dict(catalog().get("supplier") or {})
    try:
        with session.begin_nested():
            row = session.execute(text("SELECT profile FROM platform_invoice_supplier WHERE singleton = true")).scalar()
        if row:
            profile = _json(row)
    except Exception:  # noqa: BLE001  (table absent in this environment)
        pass
    return {"name": profile.get("name") or "", "address": profile.get("address") or "", "vat_number": profile.get("vat_number") or None,
            "vat_registered": bool(profile.get("vat_registered", False))}


def customer_snapshot(session, tenant_id) -> dict:
    """The tenant as the invoice recipient: its VAT profile when it has chosen one, else the platform billing details it entered."""
    name, address, vat_number = None, None, None
    try:
        with session.begin_nested():
            row = session.execute(text("SELECT name, settings FROM tenants WHERE id = :t"), {"t": str(tenant_id)}).first()
        if row:
            name = row[0]
            billing = _json(row[1]).get("platform_billing") or {}
            name, address = billing.get("name") or name, billing.get("address")
            vat_number = billing.get("vat_number") if billing.get("vat_registered") else None
    except Exception:  # noqa: BLE001
        pass
    profile = profile_for(session, tenant_id)
    if profile.configured:
        name = profile.legal_name or name
        address = profile.address or address
        vat_number = profile.vat_number if profile.vat_registered else vat_number
    return {"name": name or "Tenant", "address": address, "vat_number": vat_number}


def next_number(session, issue: date) -> str:
    seq = session.execute(select(FeeInvoiceSequence).where(FeeInvoiceSequence.year == issue.year).with_for_update()).scalar_one_or_none()
    if seq is None:
        try:
            with session.begin_nested():
                session.add(FeeInvoiceSequence(year=issue.year, last_number=0))
                session.flush()
        except IntegrityError:
            pass
        seq = session.execute(select(FeeInvoiceSequence).where(FeeInvoiceSequence.year == issue.year).with_for_update()).scalar_one()
    seq.last_number += 1
    session.flush()
    return f"ODF-{issue.year}-{seq.last_number:06d}"


def _line(description: str, quantity: int, net_cents: int, vat_cents: int, note: Optional[str] = None) -> dict:
    return {"description": description, "quantity": quantity, "net_cents": net_cents, "vat_cents": vat_cents, "note": note}


def generate(session, tenant_id, period: str, *, today: Optional[date] = None) -> Optional[FeeInvoice]:
    """Issue (or return) the fee invoice for `period`. None when there is nothing to invoice. Idempotent per (tenant, period)."""
    existing = session.execute(select(FeeInvoice).where(FeeInvoice.tenant_id == tenant_id, FeeInvoice.period == period)).scalar_one_or_none()
    if existing is not None:
        return existing

    charges = session.execute(select(GatewayCharge).where(
        GatewayCharge.tenant_id == tenant_id, GatewayCharge.status == "succeeded", GatewayCharge.fee_invoice_id.is_(None),
        GatewayCharge.period <= period, GatewayCharge.commission_cents > 0).with_for_update()).scalars().all()
    billed_items = session.execute(select(PayoutItem).join(PayoutBatch, PayoutBatch.id == PayoutItem.batch_id).where(
        PayoutItem.tenant_id == tenant_id, PayoutItem.status.in_(("processing", "success")), PayoutItem.fee_invoice_id.is_(None),
        PayoutBatch.period <= period, PayoutItem.fee_cents > 0).with_for_update()).scalars().all()
    returned = session.execute(select(PayoutItem).where(
        PayoutItem.tenant_id == tenant_id, PayoutItem.status == "failed", PayoutItem.fee_invoice_id.is_not(None),
        PayoutItem.fee_credit_invoice_id.is_(None), PayoutItem.fee_cents > 0).with_for_update()).scalars().all()

    lines = []
    if charges:
        lines.append(_line(f"Payment gateway fee: {len(charges)} card payment(s) totalling R{sum(c.gross_cents for c in charges) / 100:,.2f}",
                           len(charges), sum(c.commission_cents for c in charges), sum(c.commission_vat_cents for c in charges),
                           "Tiered rate on monthly volume, excluding VAT"))
    if billed_items:
        lines.append(_line(f"Payout fee: {len(billed_items)} payout(s) totalling R{sum(i.amount_cents for i in billed_items) / 100:,.2f}",
                           len(billed_items), sum(i.fee_cents for i in billed_items), sum(i.fee_vat_cents for i in billed_items),
                           "Payroll and supplier payments, excluding VAT"))
    if returned:
        lines.append(_line(f"Adjustment: fees returned on {len(returned)} payout(s) that failed after they were invoiced", len(returned),
                           -sum(i.fee_cents for i in returned), -sum(i.fee_vat_cents for i in returned), "Credit"))
    if not lines:
        return None
    subtotal = sum(l["net_cents"] for l in lines)
    vat = sum(l["vat_cents"] for l in lines)
    total = subtotal + vat
    if total <= 0:
        return None                                    # a credit alone is not an invoice: it carries forward to the next one

    issue = today or calc.today_sast()
    supplier, customer = supplier_snapshot(session), customer_snapshot(session, tenant_id)
    vendor = supplier["vat_registered"]
    supplier_ok = bool(supplier["name"] and supplier["address"] and (not vendor or supplier["vat_number"]))
    if not supplier_ok:
        doc_type = "Pro forma invoice"
    else:
        doc_type = "Tax invoice" if (vendor and vat > 0) else "Invoice"
    complete = supplier_ok and (total <= FULL_INVOICE_ABOVE_CENTS or bool(customer["name"] and customer["address"]))

    try:
        with session.begin_nested():
            inv = FeeInvoice(tenant_id=tenant_id, period=period, number=next_number(session, issue), issue_date=issue, doc_type=doc_type,
                             complete=complete, supplier=supplier, customer=customer, lines=lines, subtotal_cents=subtotal,
                             vat_cents=vat, total_cents=total)
            session.add(inv)
            session.flush()
    except IntegrityError:                              # another worker issued this period first
        return session.execute(select(FeeInvoice).where(FeeInvoice.tenant_id == tenant_id, FeeInvoice.period == period)).scalar_one()
    for row in charges + billed_items:
        row.fee_invoice_id = inv.id
    for row in returned:
        row.fee_credit_invoice_id = inv.id
    session.flush()
    logger.info("fee invoice %s issued tenant=%s period=%s total=%s", inv.number, tenant_id, period, total)
    return inv


def tenants_with_fees(session, period: str) -> list:
    ids = set(session.execute(select(GatewayCharge.tenant_id).where(
        GatewayCharge.status == "succeeded", GatewayCharge.fee_invoice_id.is_(None), GatewayCharge.period <= period)).scalars())
    ids |= set(session.execute(select(PayoutItem.tenant_id).where(
        PayoutItem.status.in_(("processing", "success", "failed")), PayoutItem.fee_cents > 0,
        (PayoutItem.fee_invoice_id.is_(None)) | (PayoutItem.fee_credit_invoice_id.is_(None)))).scalars())
    return sorted(ids, key=str)


def to_dict(inv: FeeInvoice) -> dict:
    return {"id": str(inv.id), "number": inv.number, "period": inv.period, "issue_date": inv.issue_date.isoformat(), "doc_type": inv.doc_type,
            "complete": inv.complete, "subtotal_zar": inv.subtotal_cents / 100, "vat_zar": inv.vat_cents / 100, "total_zar": inv.total_cents / 100,
            "supplier": inv.supplier, "customer": inv.customer,
            "lines": [{"description": l["description"], "quantity": l["quantity"], "net_zar": l["net_cents"] / 100,
                       "vat_zar": l["vat_cents"] / 100, "note": l.get("note")} for l in inv.lines]}


def render_view(inv: FeeInvoice) -> dict:
    """The view document_render.render_html expects (escaping and print layout are shared with every other billing document)."""
    from services.billing import document_render as render
    rate = None
    rows = []
    for l in inv.lines:
        net = Decimal(l["net_cents"]) / 100
        vat = Decimal(l["vat_cents"]) / 100
        pct = f"{(vat / net * 100).quantize(Decimal('0.01'))}" if net else "0.00"
        rows.append({"line_id": None, "description": l["description"], "quantity": str(l["quantity"]), "unit_price": f"{net:.2f}",
                     "discount": "0.00", "tax_rate": pct, "price_includes_vat": False, "net": f"{net:.2f}", "vat": f"{vat:.2f}",
                     "total": f"{net + vat:.2f}"})
    sup, cust = inv.supplier, inv.customer
    notes = None if inv.complete else ("Add your registered address under Billing > VAT & tax so future invoices carry everything a tax "
                                       "invoice requires." if not cust.get("address") else "This document is incomplete: OmniDome's details are missing.")
    return {"kind": "invoice", "title": inv.doc_type, "prices_include_vat": False, "number": inv.number, "status": "issued",
            "issue_date": inv.issue_date, "due_date": None, "valid_until": None, "po_number": None,
            "bill_to": {"name": cust.get("name"), "address": cust.get("address"), "email": None, "phone": None,
                        "vat_number": cust.get("vat_number")},
            "lines": rows, "subtotal": f"{Decimal(inv.subtotal_cents) / 100:.2f}", "discount_total": "0.00",
            "vat": f"{Decimal(inv.vat_cents) / 100:.2f}", "total": f"{Decimal(inv.total_cents) / 100:.2f}", "paid": None, "balance": None,
            "notes": ("Deducted from your settlements and payout wallet as each payment was processed." + (f" {notes}" if notes else "")),
            "terms": None,
            "template": render.safe_template({"company_name": sup.get("name"), "company_address": sup.get("address"),
                                              "vat_number": sup.get("vat_number") if sup.get("vat_registered") else None,
                                              "show_payment_details": False, "show_terms": False})}
