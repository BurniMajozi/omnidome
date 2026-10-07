"""Server-side document money math (invoices and quotes). Decimal only; client totals are never read.

Per line:   gross = qty * unit_price
            discount = amount (<= gross) or percent of gross
            net = gross - discount           (rounded half-up to cents; this is the line's ex-VAT total)
            vat = net * tax_rate / 100       (rounded half-up per line, so the printed lines add up exactly)
            total = net + vat
Document:   subtotal = sum(net), discount_total = sum(discount), vat = sum(vat), total = subtotal + vat.
"""
from __future__ import annotations

import os
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable, Optional

from fastapi import HTTPException

CENT = Decimal("0.01")
MAX_LINES = 200
MAX_DOC_TOTAL = Decimal("9999999999.99")  # Numeric(12, 2)


def money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def default_vat_rate() -> Decimal:
    """Tenant-wide default VAT percent (BILLING_VAT_RATE_PERCENT, default 15)."""
    try:
        rate = Decimal(os.getenv("BILLING_VAT_RATE_PERCENT", "15"))
    except Exception:  # noqa: BLE001
        rate = Decimal("15")
    return rate if Decimal("0") <= rate <= Decimal("100") else Decimal("15")


def compute_line(description: str, quantity: Any, unit_price: Any, discount: Any = 0,
                 discount_type: str = "amount", tax_rate: Optional[Any] = None,
                 catalog_item_id: Optional[Any] = None, line_id: Optional[str] = None) -> dict:
    qty = Decimal(str(quantity))
    price = Decimal(str(unit_price))
    if qty <= 0:
        raise HTTPException(422, "Line quantity must be greater than zero")
    if price < 0:
        raise HTTPException(422, "Line unit price cannot be negative")
    rate = Decimal(str(tax_rate)) if tax_rate is not None else default_vat_rate()
    if not (Decimal("0") <= rate <= Decimal("100")):
        raise HTTPException(422, "tax_rate must be between 0 and 100")
    gross = money(qty * price)
    disc_in = Decimal(str(discount or 0))
    if disc_in < 0:
        raise HTTPException(422, "Discount cannot be negative")
    if discount_type == "percent":
        if disc_in > 100:
            raise HTTPException(422, "Percent discount cannot exceed 100")
        disc = money(gross * disc_in / Decimal("100"))
    elif discount_type == "amount":
        disc = money(disc_in)
    else:
        raise HTTPException(422, "discount_type must be 'amount' or 'percent'")
    if disc > gross:
        raise HTTPException(422, "Line discount cannot exceed the line amount")
    net = money(gross - disc)
    vat = money(net * rate / Decimal("100"))
    return {
        "line_id": line_id or str(uuid.uuid4()),
        "description": (description or "").strip()[:500],
        "quantity": format(qty.normalize(), "f"),
        "unit_price_zar": str(money(price)),
        "gross_zar": str(gross),
        "discount_zar": str(disc),
        "tax_rate": str(rate.quantize(CENT)),
        "total_zar": str(net),            # line total EX VAT (matches subscription lines' convention)
        "vat_zar": str(vat),
        "line_total_incl_zar": str(net + vat),
        "catalog_item_id": str(catalog_item_id) if catalog_item_id else None,
    }


def compute_totals(lines: Iterable[dict]) -> dict:
    subtotal = discount = vat = gross = Decimal("0")
    for ln in lines:
        subtotal += Decimal(ln["total_zar"])
        discount += Decimal(ln["discount_zar"])
        vat += Decimal(ln["vat_zar"])
        gross += Decimal(ln.get("gross_zar") or ln["total_zar"])
    subtotal, discount, vat, gross = money(subtotal), money(discount), money(vat), money(gross)
    total = subtotal + vat
    if total > MAX_DOC_TOTAL:
        raise HTTPException(422, "Document total is too large")
    return {"subtotal_zar": subtotal, "discount_total_zar": discount, "vat_zar": vat,
            "total_zar": total, "gross_zar": gross}


def build_lines(raw_lines: list) -> tuple[list[dict], dict]:
    """Validated request lines (pydantic models or dicts) -> (computed lines, totals)."""
    if not raw_lines:
        raise HTTPException(422, "At least one line is required")
    if len(raw_lines) > MAX_LINES:
        raise HTTPException(422, f"At most {MAX_LINES} lines")
    out = []
    for raw in raw_lines:
        d = raw if isinstance(raw, dict) else raw.model_dump()
        out.append(compute_line(
            d["description"], d["quantity"], d["unit_price"], d.get("discount") or 0,
            d.get("discount_type") or "amount", d.get("tax_rate"), d.get("catalog_item_id"), d.get("line_id")))
    return out, compute_totals(out)


def clerk_discount_limit_pct() -> Decimal:
    try:
        return Decimal(os.getenv("BILLING_CLERK_MAX_DISCOUNT_PERCENT", "20"))
    except Exception:  # noqa: BLE001
        return Decimal("20")


def discount_needs_admin(totals: dict) -> bool:
    """A discount above BILLING_CLERK_MAX_DISCOUNT_PERCENT of the gross amount needs an admin."""
    gross = totals.get("gross_zar") or Decimal("0")
    if gross <= 0:
        return False
    return (totals["discount_total_zar"] * Decimal("100") / gross) > clerk_discount_limit_pct()
