"""Tenant VAT: the tenant chooses whether it charges VAT; SARS rules are enforced on what it can save and what its documents say."""
import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.common.auth import AuthContext  # noqa: E402
from services.billing import doc_service, document_render as render, invoicing, invoicing_math as im, platform_tax, tax  # noqa: E402
from services.billing.models import Invoice, Subscription  # noqa: E402
from services.billing.routes import tax as tax_routes  # noqa: E402
from services.billing.tax_store import price_lines, profile_for  # noqa: E402
from services.billing.tests import sqlite_harness as h  # noqa: E402

D = Decimal
ZA_REG = dict(country="ZA", vat_registered=True, vat_number="4123456789", rate_percent=None, prices_include_vat=False,
              legal_name="Acme Fibre (Pty) Ltd", address="1 Main Rd, Soweto", registered_since=date(2024, 3, 1))


def profile(**over):
    return tax.validate_profile(**{**ZA_REG, **over})


# ---- pure maths ---------------------------------------------------------------------------------------------

def test_not_a_vendor_charges_no_vat_whatever_the_price_means():
    p = profile(vat_registered=False)
    assert tax.split("100.00", p) == (D("100.00"), D("0.00"), D("100.00"))
    p2 = profile(vat_registered=False, prices_include_vat=True)
    assert tax.split("115.00", p2) == (D("115.00"), D("0.00"), D("115.00"))
    assert not p.charges_vat and p.document_title() == "Invoice" and p.document_title(credit_note=True) == "Credit note"


def test_exclusive_adds_vat_and_inclusive_carves_it_out():
    ex = profile()
    assert tax.split("100.00", ex) == (D("100.00"), D("15.00"), D("115.00"))
    inc = profile(prices_include_vat=True)
    assert tax.split("115.00", inc) == (D("100.00"), D("15.00"), D("115.00"))
    assert tax.split("599.00", inc) == (D("520.87"), D("78.13"), D("599.00"))         # same figures as OmniDome's own catalogue
    assert ex.document_title() == "Tax invoice" and ex.document_title(credit_note=True) == "Tax credit note"


def test_inclusive_lines_always_add_up_to_the_quoted_total():
    inc = profile(prices_include_vat=True)
    out = tax.split_lines(["100.00", "33.33", "0.01", "999.99"], inc)
    assert out["total"] == D("1133.33") and out["subtotal"] + out["vat"] == out["total"] == sum(map(D, ["100.00", "33.33", "0.01", "999.99"]))
    assert all(isinstance(n, Decimal) for n in out["nets"])
    ex = tax.split_lines(["0.10", "0.10", "0.10"], profile())
    assert ex["subtotal"] == D("0.30") and ex["vat"] == D("0.05") and ex["total"] == D("0.35")      # VAT once on the sum


def test_legacy_default_is_unchanged_fifteen_percent_added_on_top():
    p = tax.legacy_profile()
    assert not p.configured and tax.split("100.00", p) == (D("100.00"), D("15.00"), D("115.00"))


# ---- what a tenant may save -----------------------------------------------------------------------------------

def test_a_vendor_needs_name_address_and_a_valid_south_african_vat_number():
    for bad in ("123456789", "5123456789", "41234567890", "abcdefghij", ""):
        with pytest.raises(tax.TaxProfileError):
            profile(vat_number=bad)
    with pytest.raises(tax.TaxProfileError):
        profile(legal_name=" ")
    with pytest.raises(tax.TaxProfileError):
        profile(address=None)
    assert profile(vat_number="4 123 456 789").vat_number == "4123456789"


def test_south_africa_rate_is_the_statutory_rate_and_other_countries_set_their_own():
    assert profile().rate_percent == D("15")
    assert profile(rate_percent=D("15")).rate_percent == D("15")
    with pytest.raises(tax.TaxProfileError):
        profile(rate_percent=D("14"))
    with pytest.raises(tax.TaxProfileError):
        profile(country="KE", vat_number="P051234567X", rate_percent=None)
    ke = profile(country="KE", vat_number="P051234567X", rate_percent=D("16"))
    assert ke.rate_percent == D("16") and tax.split("116.00", profile(country="KE", vat_number="P051234567X", rate_percent=D("16"),
                                                                         prices_include_vat=True)) == (D("100.00"), D("16.00"), D("116.00"))


def test_not_registered_clears_the_vat_number_and_needs_no_details():
    p = tax.validate_profile(country="ZA", vat_registered=False, vat_number="4123456789", rate_percent=D("15"), prices_include_vat=True,
                             legal_name=None, address=None, registered_since=None)
    assert p.vat_number is None and p.rate == 0 and p.configured and tax.line_rate_percent(p) == 0


# ---- SARS thresholds -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("turnover,three_months,status", [
    ("50000", "10000", "below_threshold"), ("120000", "20000", "below_threshold"), ("120000.01", "20000", "may_register"),
    ("1900000", "300000", "approaching"), ("1900000", "700000", "will_exceed"),
    ("2300000", "100000", "approaching"), ("2300000.01", "100000", "must_register"),
])
def test_registration_status_follows_the_sars_thresholds(turnover, three_months, status):
    out = tax.registration_status(tax.legacy_profile() if False else profile(vat_registered=False), D(turnover), D(three_months))
    assert out["status"] == status and out["compulsory_threshold_zar"] == 2_300_000.0 and out["voluntary_threshold_zar"] == 120_000.0
    assert out["register_within_business_days"] == 21


def test_a_registered_tenant_and_other_countries_are_handled_separately():
    assert tax.registration_status(profile(), D("9000000"), D("3000000"))["status"] == "registered"
    out = tax.registration_status(profile(vat_registered=False, country="NG"), D("9000000"), D("3000000"))
    assert out["status"] == "not_applicable" and out["applicable"] is False


# ---- invoices follow the tenant's position ----------------------------------------------------------------------------

@pytest.fixture
def env(monkeypatch):
    db = h.make_session_factory()
    h.patch_sessions(monkeypatch, db)
    monkeypatch.setattr(tax_routes, "get_session", db)
    import services.billing.tax_store as ts
    monkeypatch.setattr("services.billing.database.get_session", db, raising=False)
    tenant = uuid.uuid4()
    return SimpleNamespace(db=db, tenant=tenant, ctx=AuthContext(user_id=uuid.uuid4(), tenant_id=tenant))


def save(env, **over):
    body = tax_routes.TaxProfileIn(**{**dict(country="ZA", vat_registered=True, vat_number="4123456789", prices_include_vat=False,
                                              legal_name="Acme Fibre (Pty) Ltd", address="1 Main Rd"), **over})
    return asyncio.run(tax_routes.put_profile(body, env.ctx))


def bill(env, price="100.00"):
    start = date(2026, 3, 1)
    with env.db() as s:
        sub = Subscription(id=uuid.uuid4(), tenant_id=env.tenant, customer_id=uuid.uuid4(), plan="Fibre", status="active",
                           billing_interval="monthly", base_price_zar=D(price), billing_anchor=start, current_period_start=start,
                           current_period_end=date(2026, 3, 28))
        s.add(sub)
        s.flush()
        inv, _ = invoicing.bill_period(s, sub, start)
        return inv.subtotal_zar, inv.vat_zar, inv.total_zar, inv.line_items


def test_unconfigured_tenant_keeps_the_legacy_invoice(env):
    assert bill(env)[:3] == (D("100.00"), D("15.00"), D("115.00"))
    assert asyncio.run(tax_routes.get_profile(env.ctx))["configured"] is False


def test_non_vendor_subscription_invoice_has_no_vat(env):
    save(env, vat_registered=False, vat_number=None)
    sub, vat, total, lines = bill(env)
    assert (sub, vat, total) == (D("100.00"), D("0.00"), D("100.00")) and lines[0]["total_zar"] == "100.00"


def test_vendor_with_vat_inclusive_prices_invoices_the_advertised_price(env):
    save(env, prices_include_vat=True)
    sub, vat, total, lines = bill(env, "599.00")
    assert (sub, vat, total) == (D("520.87"), D("78.13"), D("599.00")) and lines[0]["unit_price_zar"] == "599.00" and lines[0]["total_zar"] == "520.87"


def test_vendor_with_exclusive_prices_adds_vat(env):
    save(env, prices_include_vat=False)
    assert bill(env, "200.00")[:3] == (D("200.00"), D("30.00"), D("230.00"))


def test_a_changed_profile_applies_to_later_invoices_only(env):
    save(env, vat_registered=False, vat_number=None)
    bill(env)
    save(env)                                                                # now registers
    with env.db() as s:
        first = s.query(Invoice).one()
        assert first.vat_zar == D("0.00")                                    # the issued invoice keeps what it was issued with
        events = s.query(tax_routes.TaxProfileEvent).order_by(tax_routes.TaxProfileEvent.created_at).all()
        assert len(events) == 2 and events[0].before is None and events[1].before["vat_registered"] is False and events[1].after["vat_registered"] is True


def test_invalid_profiles_are_refused_with_the_reason(env):
    with pytest.raises(HTTPException) as e:
        save(env, vat_number="12345")
    assert e.value.status_code == 422 and "10 digits" in e.value.detail


# ---- builder lines, quotes and documents ----------------------------------------------------------------------------------

def test_builder_lines_cannot_carry_vat_for_a_non_vendor_whatever_the_client_sends():
    p = profile(vat_registered=False)
    lines, totals = im.build_lines([{"description": "Install", "quantity": 1, "unit_price": "1000", "tax_rate": "15"}], p)
    assert lines[0]["tax_rate"] == "0.00" and totals["vat_zar"] == D("0.00") and totals["total_zar"] == D("1000.00")
    assert lines[0]["price_includes_vat"] is False


def test_builder_lines_use_the_tenants_rate_and_inclusive_pricing():
    inc = profile(prices_include_vat=True)
    lines, totals = im.build_lines([{"description": "Router", "quantity": 2, "unit_price": "575.00"}], inc)
    assert lines[0]["tax_rate"] == "15.00" and lines[0]["price_includes_vat"] is True
    # 2 x R575 = R1,150 inclusive: net R1,000 + VAT R150
    assert totals["subtotal_zar"] == D("1000.00") and totals["vat_zar"] == D("150.00") and totals["total_zar"] == D("1150.00")
    assert lines[0]["gross_zar"] == "1150.00" and lines[0]["line_total_incl_zar"] == "1150.00"


def test_legacy_builder_behaviour_is_unchanged_without_a_profile():
    lines, totals = im.build_lines([{"description": "x", "quantity": 1, "unit_price": "100"}])
    assert totals["vat_zar"] == D("15.00") and totals["total_zar"] == D("115.00")


def fake_invoice(vat, subtotal, total, credit_note_of=None, line_tax=None):
    return SimpleNamespace(
        credit_note_of=credit_note_of, number="INV-1", status="sent", created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        due_date=date(2026, 3, 31), amount_paid_zar=D("0.00"), total_zar=total, subtotal_zar=subtotal, vat_zar=vat, notes=None,
        line_items=[{"description": "Fibre", "quantity": 1, "unit_price_zar": str(subtotal), "total_zar": str(subtotal), "tax_rate": line_tax,
                     "vat_zar": str(vat)}])


def view(vat, subtotal, total, prof, **kw):
    v = render.invoice_view(fake_invoice(vat, subtotal, total, **kw), None, render.safe_template({"company_name": None}))
    return doc_service.apply_tax_identity(v, prof)


def test_a_tax_invoice_shows_vat_and_the_suppliers_vat_number_and_name():
    p = profile()
    v = view(D("15.00"), D("100.00"), D("115.00"), p, line_tax="15.00")
    assert v["title"] == "Tax invoice" and v["template"]["vat_number"] == "4123456789" and v["template"]["company_name"] == "Acme Fibre (Pty) Ltd"
    html = render.render_fragment(v)
    assert "VAT %" in html and "VAT no. 4123456789" in html and ">VAT<" in html


def test_a_non_vendor_document_is_a_plain_invoice_with_no_vat_anything():
    p = profile(vat_registered=False)
    v = view(D("0.00"), D("100.00"), D("100.00"), p, line_tax="0.00")
    assert v["title"] == "Invoice" and v["template"]["vat_number"] is None
    html = render.render_fragment(v)
    assert "VAT %" not in html and "VAT no." not in html and ">VAT<" not in html
    credit = view(D("0.00"), D("-50.00"), D("-50.00"), p, credit_note_of=uuid.uuid4(), line_tax="0.00")
    assert credit["title"] == "Credit note"


def test_an_old_non_vat_invoice_stays_a_plain_invoice_after_the_tenant_registers():
    p = profile(registered_since=date(2026, 6, 1))                          # registered in June; the invoice is from March
    v = view(D("0.00"), D("100.00"), D("100.00"), p, line_tax="0.00")
    assert v["title"] == "Invoice"                                          # SARS accepts the word "Invoice"; no VAT was charged
    assert v["template"]["vat_number"] is None                              # issued before registration: no number


def test_a_vendors_zero_rated_invoice_still_carries_its_vat_number():
    p = profile(registered_since=date(2024, 3, 1))
    v = view(D("0.00"), D("100.00"), D("100.00"), p, line_tax="0.00")
    assert v["title"] == "Invoice" and v["template"]["vat_number"] == "4123456789"


def test_inclusive_documents_say_vat_is_included():
    v = view(D("78.13"), D("520.87"), D("599.00"), profile(prices_include_vat=True), line_tax="15.00")
    v["prices_include_vat"] = True
    assert "included in prices" in render.render_fragment(v)


# ---- API: status monitor and gateway fee VAT ------------------------------------------------------------------------------------

def test_status_endpoint_uses_the_last_twelve_months_of_invoiced_ex_vat(env):
    from services.billing.calc import today_sast
    with env.db() as s:
        for amount, when, status in (("1500000.00", today_sast(), "sent"), ("1000000.00", today_sast(), "sent"),
                                     ("5000000.00", today_sast(), "draft"), ("-100000.00", today_sast(), "credit_issued")):
            inv = h.make_invoice(s, env.tenant, status=status, subtotal=amount, vat="0.00")
    out = asyncio.run(tax_routes.registration_status(env.ctx))
    assert out["turnover_12m_zar"] == 2_400_000.0 and out["status"] == "must_register"       # drafts excluded, credit note netted off
    assert out["profile"]["configured"] is False


def test_omnidome_fees_are_vat_inclusive_and_carve_out_the_vat(env):
    # no platform tables in this database: falls back to the shipped catalogue (VAT-registered, 15%)
    with env.db() as s:
        assert platform_tax.position(s) == {"registered": True, "rate": D("0.15")}
        assert platform_tax.vat_inside(6900, s) == 900                      # R69.00 incl VAT = R60.00 + R9.00
        assert platform_tax.vat_inside(0, s) == 0
