"""Money math for manual invoices and quotes (pure Decimal, server side)."""
import os
import sys
from decimal import Decimal

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.billing import invoicing_math as im  # noqa: E402

D = Decimal


def L(**kw):
    base = {"description": "x", "quantity": "1", "unit_price": "100.00"}
    return {**base, **kw}


def test_default_vat_15_percent_per_line():
    lines, t = im.build_lines([L()])
    assert (t["subtotal_zar"], t["vat_zar"], t["total_zar"]) == (D("100.00"), D("15.00"), D("115.00"))
    assert lines[0]["line_total_incl_zar"] == "115.00" and lines[0]["tax_rate"] == "15.00"


def test_vat_rate_is_configurable(monkeypatch):
    monkeypatch.setenv("BILLING_VAT_RATE_PERCENT", "10")
    assert im.build_lines([L()])[1]["vat_zar"] == D("10.00")
    monkeypatch.setenv("BILLING_VAT_RATE_PERCENT", "garbage")
    assert im.default_vat_rate() == D("15")


def test_per_line_rounding_half_up_and_lines_add_up():
    # 3 x 0.335 -> net 1.005 -> 1.01 ; vat 0.1515 -> 0.15
    lines, t = im.build_lines([L(quantity="3", unit_price="0.34"), L(quantity="1", unit_price="33.33")])
    assert sum(D(l["total_zar"]) for l in lines) == t["subtotal_zar"]
    assert sum(D(l["vat_zar"]) for l in lines) == t["vat_zar"]
    assert t["total_zar"] == t["subtotal_zar"] + t["vat_zar"]
    assert im.money("2.675") == D("2.68") and im.money("2.665") == D("2.67")


def test_amount_and_percent_discounts():
    amt = im.compute_line("a", 2, "50.00", discount="10.00")
    assert (amt["gross_zar"], amt["discount_zar"], amt["total_zar"], amt["vat_zar"]) == ("100.00", "10.00", "90.00", "13.50")
    pct = im.compute_line("a", 2, "50.00", discount="12.5", discount_type="percent")
    assert pct["discount_zar"] == "12.50" and pct["total_zar"] == "87.50"


def test_zero_rated_line():
    ln = im.compute_line("zero rated", 1, "200", tax_rate=0)
    assert ln["vat_zar"] == "0.00" and ln["line_total_incl_zar"] == "200.00"


@pytest.mark.parametrize("kw", [
    {"quantity": 0}, {"quantity": -1}, {"unit_price": "-0.01"}, {"discount": "100.01"},
    {"discount": "101", "discount_type": "percent"}, {"discount": "-1"}, {"tax_rate": 101}, {"discount_type": "weird"},
])
def test_invalid_lines_are_rejected(kw):
    args = {"description": "x", "quantity": 1, "unit_price": "100.00", **kw}
    with pytest.raises(HTTPException) as e:
        im.compute_line(**args)
    assert e.value.status_code == 422


def test_line_count_and_empty_guards():
    with pytest.raises(HTTPException):
        im.build_lines([])
    with pytest.raises(HTTPException):
        im.build_lines([L()] * (im.MAX_LINES + 1))


def test_document_total_cap():
    with pytest.raises(HTTPException):
        im.build_lines([L(quantity="1000000", unit_price="1000000000")])


def test_clerk_discount_threshold(monkeypatch):
    _, ok = im.build_lines([L(discount="20.00")])
    _, big = im.build_lines([L(discount="20.01")])
    assert not im.discount_needs_admin(ok) and im.discount_needs_admin(big)
    monkeypatch.setenv("BILLING_CLERK_MAX_DISCOUNT_PERCENT", "50")
    assert not im.discount_needs_admin(big)


def test_client_totals_are_not_inputs():
    # extra keys in a line dict (e.g. a client-sent total) are simply never read
    ln = im.compute_line(**{"description": "x", "quantity": 1, "unit_price": "10.00"})
    assert ln["total_zar"] == "10.00"
    lines, t = im.build_lines([{**L(), "total_zar": "1.00", "vat_zar": "0.00"}])
    assert t["total_zar"] == D("115.00")
