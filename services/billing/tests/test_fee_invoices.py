"""OmniDome's monthly tax invoice to a tenant for the gateway commission and payout fees it was charged."""
import asyncio
import os
import sys
import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.common.auth import AuthContext  # noqa: E402
from services.billing import fee_invoicing as fi  # noqa: E402
from services.billing.models_fee_invoices import FeeInvoice  # noqa: E402
from services.billing.models_gateway import GatewayCharge  # noqa: E402
from services.billing.models_payouts import PayoutBatch, PayoutItem  # noqa: E402
from services.billing.models_tax import TaxProfileRow  # noqa: E402
from services.billing.routes import fee_invoices as routes  # noqa: E402
from services.billing.tests import sqlite_harness as h  # noqa: E402

D = Decimal
ISSUE = date(2026, 4, 2)
SUPPLIER = {"name": "OmniDome (Pty) Ltd", "address": "9 Short Road, Zandspruit", "vat_number": "4000000000", "vat_registered": True}


@pytest.fixture
def env(monkeypatch):
    db = h.make_session_factory()
    h.patch_sessions(monkeypatch, db)
    monkeypatch.setattr(routes, "get_session", db)
    monkeypatch.setattr(fi, "supplier_snapshot", lambda session: dict(SUPPLIER))
    tenant, other = uuid.uuid4(), uuid.uuid4()
    return SimpleNamespace(db=db, tenant=tenant, other=other, ctx=AuthContext(user_id=uuid.uuid4(), tenant_id=tenant),
                           admin=AuthContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=["platform_admin"]))


def charge(env, ref, period="2026-03", gross=115_000, fee=6_900, vat=1_035, tenant=None, status="succeeded"):
    with env.db() as s:
        s.add(GatewayCharge(tenant_id=tenant or env.tenant, reference=ref, subaccount_code="ACCT", period=period, gross_cents=gross,
                            commission_cents=fee, commission_vat_cents=vat, status=status))


def payout(env, ref, period="2026-03", amount=100_000, fee=6_000, vat=900, status="success", tenant=None):
    with env.db() as s:
        b = PayoutBatch(tenant_id=tenant or env.tenant, kind="payroll", source_id=ref, period=period, total_cents=amount, fee_cents=fee, fee_vat_cents=vat)
        s.add(b)
        s.flush()
        s.add(PayoutItem(batch_id=b.id, tenant_id=tenant or env.tenant, kind="payroll", item_ref=ref, recipient_code="RCP", amount_cents=amount,
                         fee_cents=fee, fee_vat_cents=vat, reference=f"payroll-{ref}", status=status))


def issue(env, period="2026-03", tenant=None):
    with env.db() as s:
        inv = fi.generate(s, tenant or env.tenant, period, today=ISSUE)
        return None if inv is None else (inv.id, inv.number, inv.doc_type, inv.subtotal_cents, inv.vat_cents, inv.total_cents, inv.complete, list(inv.lines))


def test_invoice_adds_up_every_fee_and_the_vat_added_on_top(env):
    charge(env, "c1")
    charge(env, "c2")
    payout(env, "p1")
    _, number, doc, subtotal, vat, total, complete, lines = issue(env)
    assert number == "ODF-2026-000001" and doc == "Tax invoice" and complete
    assert subtotal == 2 * 6_900 + 6_000 and vat == 2 * 1_035 + 900 and total == subtotal + vat == 22_770
    assert [l["quantity"] for l in lines] == [2, 1] and "2 card payment(s) totalling R2,300.00" in lines[0]["description"]
    with env.db() as s:
        assert {c.fee_invoice_id for c in s.query(GatewayCharge)} == {s.query(FeeInvoice).one().id}
        assert s.query(PayoutItem).one().fee_invoice_id is not None


def test_issuing_is_idempotent_and_numbers_are_sequential_across_tenants(env):
    charge(env, "c1")
    charge(env, "c2", tenant=env.other)
    first = issue(env)
    again = issue(env)
    assert again[0] == first[0] and again[1] == first[1]
    second = issue(env, tenant=env.other)
    assert second[1] == "ODF-2026-000002"
    with env.db() as s:
        assert s.query(FeeInvoice).count() == 2


def test_nothing_to_bill_means_no_invoice_and_pending_or_failed_fees_are_not_billed(env):
    assert issue(env) is None
    charge(env, "c-init", status="initialized")
    charge(env, "c-failed", status="failed")
    payout(env, "p-failed", status="failed")
    assert issue(env) is None


def test_late_fees_and_later_periods_roll_forward_exactly_once(env):
    charge(env, "c1", period="2026-03")
    first = issue(env, "2026-03")
    charge(env, "c-late", period="2026-03")                       # its success arrived after March was invoiced
    charge(env, "c-april", period="2026-04")
    april = issue(env, "2026-04")
    assert april[1] == "ODF-2026-000002" and april[3] == 2 * 6_900 and april[0] != first[0]
    assert issue(env, "2026-05") is None                          # nothing left


def test_a_payout_that_fails_after_it_was_invoiced_is_credited_on_the_next_invoice_or_carried_forward(env):
    payout(env, "p1", fee=6_000, vat=900)
    issue(env, "2026-03")
    with env.db() as s:
        s.query(PayoutItem).update({"status": "failed"})          # the transfer was reversed; billing already returned fee + VAT to the wallet
    assert issue(env, "2026-04") is None                          # a credit alone is not an invoice
    charge(env, "c-april", period="2026-04", fee=20_000, vat=3_000)
    inv = issue(env, "2026-04")
    assert inv[3] == 20_000 - 6_000 and inv[4] == 3_000 - 900
    lines = inv[7]
    assert lines[-1]["net_cents"] == -6_000 and lines[-1]["vat_cents"] == -900 and "failed after they were invoiced" in lines[-1]["description"]
    assert issue(env, "2026-05") is None                          # credited once, never again


def test_an_unregistered_omnidome_issues_a_plain_invoice_with_no_vat(env, monkeypatch):
    monkeypatch.setattr(fi, "supplier_snapshot", lambda s: {**SUPPLIER, "vat_registered": False})
    charge(env, "c1", vat=0)
    _, number, doc, subtotal, vat, total, complete, _ = issue(env)
    assert doc == "Invoice" and vat == 0 and total == subtotal == 6_900 and complete


def test_missing_supplier_details_make_it_a_pro_forma(env, monkeypatch):
    monkeypatch.setattr(fi, "supplier_snapshot", lambda s: {**SUPPLIER, "vat_number": None})
    charge(env, "c1")
    _, _, doc, _, _, _, complete, _ = issue(env)
    assert doc == "Pro forma invoice" and complete is False


def test_a_full_invoice_needs_the_recipients_address_and_flags_it_when_missing(env):
    charge(env, "big", gross=10_000_000, fee=600_000, vat=90_000)             # total R6,900 > R5,000
    inv = issue(env)
    assert inv[2] == "Tax invoice" and inv[6] is False
    charge(env, "big2", period="2026-04", gross=10_000_000, fee=600_000, vat=90_000)
    with env.db() as s:
        s.add(TaxProfileRow(tenant_id=env.tenant, country="ZA", vat_registered=True, vat_number="4123456789", rate_percent=D("15"),
                            prices_include_vat=False, legal_name="Acme Fibre (Pty) Ltd", address="1 Main Rd, Soweto"))
    complete = issue(env, "2026-04")
    assert complete[6] is True
    with env.db() as s:
        cust = s.query(FeeInvoice).filter_by(period="2026-04").one().customer
        assert cust == {"name": "Acme Fibre (Pty) Ltd", "address": "1 Main Rd, Soweto", "vat_number": "4123456789"}


def test_the_printable_document_is_escaped_and_carries_the_tax_invoice_details(env):
    with env.db() as s:
        s.add(TaxProfileRow(tenant_id=env.tenant, country="ZA", vat_registered=True, vat_number="4123456789", rate_percent=D("15"),
                            prices_include_vat=False, legal_name="<script>alert(1)</script> Fibre", address="1 Main Rd"))
    charge(env, "c1")
    iid = issue(env)[0]
    with env.db() as s:
        html = routes.render.render_html(fi.render_view(s.get(FeeInvoice, iid)))
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "Tax invoice" in html and "VAT no. 4000000000" in html and "VAT no. 4123456789" in html and "ODF-2026-000001" in html
    assert "VAT %" in html and "9 Short Road, Zandspruit" in html


# ---- endpoints ----------------------------------------------------------------------------------------------------------------

def test_a_tenant_sees_only_its_own_invoices_and_html_comes_with_a_strict_csp(env):
    charge(env, "c1")
    charge(env, "c2", tenant=env.other)
    mine = issue(env)[0]
    theirs = issue(env, tenant=env.other)[0]
    listing = asyncio.run(routes.list_invoices(False, env.ctx))["invoices"]
    assert [i["id"] for i in listing] == [str(mine)]
    with pytest.raises(HTTPException) as e:
        asyncio.run(routes.list_invoices(True, env.ctx))
    assert e.value.status_code == 403
    assert len(asyncio.run(routes.list_invoices(True, env.admin))["invoices"]) == 2
    with pytest.raises(HTTPException) as e:
        asyncio.run(routes.get_invoice(theirs, "json", env.ctx))
    assert e.value.status_code == 404
    page = asyncio.run(routes.get_invoice(mine, "html", env.ctx))
    assert "default-src 'none'" in page.headers["content-security-policy"] and b"ODF-2026-000001" in page.body
    assert asyncio.run(routes.get_invoice(mine, "json", env.ctx))["total_zar"] == 79.35
    assert asyncio.run(routes.get_invoice(theirs, "json", env.admin))["number"] == "ODF-2026-000002"


def test_generate_is_platform_admin_only_and_reports_what_it_issued(env):
    charge(env, "c1")
    charge(env, "c2", tenant=env.other)
    with pytest.raises(HTTPException) as e:
        asyncio.run(routes.generate(routes.GenerateIn(period="2026-03"), env.ctx))
    assert e.value.status_code == 403
    out = asyncio.run(routes.generate(routes.GenerateIn(period="2026-03"), env.admin))
    assert out["period"] == "2026-03" and sorted(i["number"] for i in out["issued"]) == ["ODF-%d-00000%d" % (fi.calc.today_sast().year, n) for n in (1, 2)]
    again = asyncio.run(routes.generate(routes.GenerateIn(period="2026-03"), env.admin))
    assert again["issued"] == []                                   # idempotent


def test_previous_period_and_the_worker_default():
    assert fi.previous_period(date(2026, 1, 15)) == "2025-12" and fi.previous_period(date(2026, 4, 2)) == "2026-03"
    assert not routes.worker_enabled()
