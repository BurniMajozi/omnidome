"""Pure-logic tests for the sales service (no DB, no network).

Run with cwd = services/sales:  python -m pytest tests/ -q
Covers: quote totals, discounts, contract value, commission tiers,
notes-contact parsing, item serialization round-trip.
"""

import sys
import os
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import (  # noqa: E402
    QuoteItem,
    apply_discount,
    calculate_quote_totals,
    deal_value_from_quote,
    deserialize_items,
    fallback_commission_rate,
    serialize_items,
    _parse_notes_contact,
)


def qi(desc="Item", qty=1, price="100", charge="monthly"):
    return QuoteItem(description=desc, quantity=qty,
                     unit_price_zar=Decimal(price), charge_type=charge)


# ── quote totals ─────────────────────────────────────────────────────────

def test_totals_monthly_and_once_off():
    items = [qi("Fibre", 1, "899", "monthly"), qi("Install", 1, "1500", "once_off")]
    totals = calculate_quote_totals(items)
    assert totals["total_monthly"] == Decimal("899")
    assert totals["total_once_off"] == Decimal("1500")


def test_totals_quantity_multiplies():
    totals = calculate_quote_totals([qi("Seat", 10, "145", "monthly")])
    assert totals["total_monthly"] == Decimal("1450")


def test_totals_empty():
    totals = calculate_quote_totals(None)
    assert totals == {"total_monthly": Decimal("0"), "total_once_off": Decimal("0")}


def test_totals_mobile_alias_shape():
    # field-sales mobile sends { name, monthly_price, qty } — must resolve.
    items = [QuoteItem(name="Home Broadband", monthly_price=Decimal("899"), qty=2)]
    totals = calculate_quote_totals(items)
    assert totals["total_monthly"] == Decimal("1798")


# ── discounts ────────────────────────────────────────────────────────────

def test_discount_none_passthrough():
    assert apply_discount(Decimal("1000"), None) == Decimal("1000")
    assert apply_discount(Decimal("1000"), Decimal("0")) == Decimal("1000")


def test_discount_ten_percent():
    assert apply_discount(Decimal("1000"), Decimal("10")) == Decimal("900.00")


def test_discount_invalid_passthrough():
    assert apply_discount(Decimal("1000"), "not-a-number") == Decimal("1000")


# ── contract value ───────────────────────────────────────────────────────

def test_contract_value_full_term():
    # 899/mo x 12 + 1500 install = 12288 (production main.py rule)
    assert deal_value_from_quote(Decimal("899"), Decimal("1500"), 12) == Decimal("12288.00")


def test_contract_value_zero_term_defaults_12():
    assert deal_value_from_quote(Decimal("100"), Decimal("0"), 0) == Decimal("1200.00")


# ── commission tiers ─────────────────────────────────────────────────────

def test_commission_tier_boundaries():
    assert fallback_commission_rate(0) == Decimal("5.0")
    assert fallback_commission_rate(9) == Decimal("5.0")
    assert fallback_commission_rate(10) == Decimal("7.0")
    assert fallback_commission_rate(19) == Decimal("7.0")
    assert fallback_commission_rate(20) == Decimal("10.0")
    assert fallback_commission_rate(100) == Decimal("10.0")


# ── notes contact parsing ────────────────────────────────────────────────

def test_notes_contact_full():
    hints = _parse_notes_contact("Walk-in | Contact: John Doe | Email: j@x.co.za | Phone: 0821234567")
    assert hints["first_name"] == "John"
    assert hints["last_name"] == "Doe"
    assert hints["email"] == "j@x.co.za"
    assert hints["phone"] == "0821234567"


def test_notes_contact_defaults():
    hints = _parse_notes_contact(None)
    assert hints["first_name"] == "Walk-in"
    assert hints["last_name"] == "Customer"


def test_notes_contact_single_name():
    hints = _parse_notes_contact("Contact: Madonna |")
    assert hints["first_name"] == "Madonna"
    assert hints["last_name"] == "Customer"


# ── item serialization ───────────────────────────────────────────────────

def test_serialize_round_trip():
    items = [qi("Fibre 200", 2, "1199", "monthly")]
    assert deserialize_items(serialize_items(items))[0].description == "Fibre 200"


def test_deserialize_mobile_alias():
    raw = [{"name": "PBX", "monthly_price": 1450, "qty": 1, "charge_type": "monthly"}]
    items = deserialize_items(raw)
    assert items[0].resolved_description() == "PBX"
    assert items[0].resolved_unit_price() == Decimal("1450")


def test_serialize_none():
    assert serialize_items(None) is None
    assert deserialize_items(None) is None
