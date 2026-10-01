"""billing service against a real Postgres (TEST_DATABASE_URL).

Money paths: invoice generation (VAT, numbering, usage roll-up, trials,
dunning), payments (partial/full/overpay, concurrent payments), credit notes,
subscription lifecycle and tenant isolation. Each test uses a fresh tenant.

    TEST_DATABASE_URL=postgresql://…/omnidome_test python scripts/setup_test_db.py
    cd services/billing && python -m pytest tests -q
"""
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.common import testdb  # noqa: E402

testdb.use_test_database()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from services.billing.main import app  # noqa: E402

D = Decimal


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
    testdb.reset_engines()


@pytest.fixture
def tenant():
    return testdb.new_tenant("billing test")


def subscribe(client, tenant, price="500.00", **fields):
    body = {"customer_id": str(uuid.uuid4()), "plan": "Fibre 100", "base_price_zar": price, **fields}
    r = client.post("/subscriptions", json=body, headers=testdb.headers(tenant))
    assert r.status_code == 201, r.text
    return r.json()


def generate(client, tenant, **body):
    r = client.post("/invoices/generate", json=body, headers=testdb.headers(tenant))
    assert r.status_code == 201, r.text
    return r.json()


def invoice_for(client, tenant, price="500.00"):
    subscribe(client, tenant, price=price)
    return generate(client, tenant)[0]


def pay(client, tenant, invoice_id, amount, method="eft"):
    return client.post("/payments", json={"invoice_id": invoice_id, "amount_zar": str(amount), "method": method},
                       headers=testdb.headers(tenant))


# ── Invoice generation ──────────────────────────────────────────────────────

def test_invoice_adds_15_percent_vat(client, tenant):
    inv = invoice_for(client, tenant, price="499.00")
    assert D(inv["subtotal_zar"]) == D("499.00")
    assert D(inv["vat_zar"]) == D("74.85")
    assert D(inv["total_zar"]) == D("573.85")
    assert inv["status"] == "draft"


def test_invoice_numbers_are_sequential_per_tenant(client, tenant):
    for _ in range(3):
        subscribe(client, tenant)
    numbers = sorted(i["number"] for i in generate(client, tenant))
    prefix = str(tenant).split("-")[0].upper()[:4]
    assert numbers == [f"INV-{prefix}-00000{n}" for n in (1, 2, 3)]
    other = testdb.new_tenant("other")
    assert invoice_for(client, other)["number"].endswith("-000001")    # each tenant starts at 1


def test_usage_is_billed_once_and_the_period_advances(client, tenant):
    sub = subscribe(client, tenant, price="100.00")
    h = testdb.headers(tenant)
    r = client.post(f"/subscriptions/{sub['id']}/usage", headers=h,
                    json={"metric": "static_ip", "quantity": "2", "unit_price_zar": "25.00"})
    assert r.status_code == 201, r.text
    first = generate(client, tenant)[0]
    assert D(first["subtotal_zar"]) == D("150.00") and len(first["line_items"]) == 2
    second = generate(client, tenant, billing_date=first["billing_period_end"])[0]
    assert D(second["subtotal_zar"]) == D("100.00")                     # usage not billed twice
    assert second["billing_period_start"] == first["billing_period_end"]


def test_trial_subscriptions_are_not_invoiced(client, tenant):
    subscribe(client, tenant, trial_days=14)
    assert generate(client, tenant) == []


def test_segment_pricing_overrides_the_base_price(client, tenant):
    subscribe(client, tenant, price="500.00", segment="business", segment_pricing={"business": 899.0})
    assert D(generate(client, tenant)[0]["subtotal_zar"]) == D("899.00")


def test_each_issued_invoice_gets_the_dunning_schedule(client, tenant):
    inv = invoice_for(client, tenant)
    with testdb.sync_engine().connect() as conn:       # drafts are never dunned
        assert conn.execute(text("SELECT count(*) FROM dunning_actions WHERE invoice_id = :i"), {"i": inv["id"]}).scalar() == 0
    assert client.post(f"/invoices/{inv['id']}/send", json={}, headers=testdb.headers(tenant)).status_code == 200
    with testdb.sync_engine().connect() as conn:
        steps = conn.execute(text("SELECT action_type FROM dunning_actions WHERE invoice_id = :i ORDER BY scheduled_at"),
                             {"i": inv["id"]}).scalars().all()
    assert steps == ["sms_reminder", "email_warning", "auto_suspend", "send_to_collections"]


# ── Payments ────────────────────────────────────────────────────────────────

def test_partial_then_full_payment(client, tenant):
    inv = invoice_for(client, tenant, price="100.00")                   # total 115.00
    assert pay(client, tenant, inv["id"], "15.00").status_code == 201
    h = testdb.headers(tenant)
    assert client.get(f"/invoices/{inv['id']}", headers=h).json()["status"] == "partially_paid"
    assert pay(client, tenant, inv["id"], "100.00").status_code == 201
    done = client.get(f"/invoices/{inv['id']}", headers=h).json()
    assert done["status"] == "paid" and D(done["amount_paid_zar"]) == D("115.00")
    assert pay(client, tenant, inv["id"], "1.00").status_code == 400     # already paid


def test_overpayment_and_bad_input_are_refused(client, tenant):
    inv = invoice_for(client, tenant, price="100.00")
    assert pay(client, tenant, inv["id"], "115.01").status_code == 400
    assert pay(client, tenant, inv["id"], "0").status_code == 422
    assert pay(client, tenant, inv["id"], "10.00", method="bitcoin").status_code == 422
    assert pay(client, tenant, str(uuid.uuid4()), "10.00").status_code == 404


def test_concurrent_payments_cannot_overpay_an_invoice(client, tenant, monkeypatch):
    # Five clients each try to settle the full balance at the same moment
    # (one TestClient per thread so the requests really overlap). Locally the
    # requests are too quick to overlap on their own, so the gap between
    # "check the balance" and "write" is widened; without a row lock all five
    # succeeded (R575 taken on a R115 invoice).
    import threading
    import time
    from sqlalchemy.orm import Session
    inv = invoice_for(client, tenant, price="100.00")
    real_flush = Session.flush

    def slow_flush(self, *a, **k):
        time.sleep(0.2)
        return real_flush(self, *a, **k)
    monkeypatch.setattr(Session, "flush", slow_flush)
    start = threading.Barrier(5)

    def settle(_):
        with TestClient(app) as own:
            start.wait()
            return pay(own, tenant, inv["id"], "115.00").status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        codes = sorted(pool.map(settle, range(5)))
    done = client.get(f"/invoices/{inv['id']}", headers=testdb.headers(tenant)).json()
    with testdb.sync_engine().connect() as conn:
        taken = conn.execute(text("SELECT coalesce(sum(amount_zar), 0) FROM payments WHERE invoice_id = :i"),
                             {"i": inv["id"]}).scalar()
    assert codes == [201, 400, 400, 400, 400]
    assert D(taken) == D("115.00") and D(done["amount_paid_zar"]) == D("115.00")


# ── Credit notes ────────────────────────────────────────────────────────────

def test_full_credit_note_voids_the_invoice(client, tenant):
    inv = invoice_for(client, tenant, price="100.00")
    h = testdb.headers(tenant)
    client.post(f"/invoices/{inv['id']}/send", json={}, headers=h)
    cn = client.post(f"/invoices/{inv['id']}/credit-note", json={"reason": "outage"}, headers=h).json()
    assert D(cn["total_zar"]) == D("-115.00") and cn["number"].startswith("CN-")
    assert client.get(f"/invoices/{inv['id']}", headers=h).json()["status"] == "voided"
    again = client.post(f"/invoices/{inv['id']}/credit-note", json={"reason": "again"}, headers=h)
    assert again.status_code == 400


def test_partial_credit_notes_cannot_add_up_to_more_than_the_invoice(client, tenant):
    inv = invoice_for(client, tenant, price="100.00")                   # total 115.00
    h = testdb.headers(tenant)
    client.post(f"/invoices/{inv['id']}/send", json={}, headers=h)
    part = {"reason": "partial", "line_items": [{"description": "credit", "quantity": 1,
                                                 "unit_price_zar": "60.00", "total_zar": "60.00"}]}
    first = client.post(f"/invoices/{inv['id']}/credit-note", json=part, headers=h)
    assert first.status_code == 201 and D(first.json()["total_zar"]) == D("-69.00")
    second = client.post(f"/invoices/{inv['id']}/credit-note", json=part, headers=h)
    assert second.status_code == 409                                     # would credit 138.00 of 115.00


# ── Subscriptions ───────────────────────────────────────────────────────────

def test_cancel_now_or_at_period_end(client, tenant):
    h = testdb.headers(tenant)
    now = subscribe(client, tenant)
    later = subscribe(client, tenant)
    r = client.post(f"/subscriptions/{now['id']}/cancel", headers=h).json()
    assert r["status"] == "cancelled"
    r = client.post(f"/subscriptions/{later['id']}/cancel", params={"at_period_end": "true"}, headers=h).json()
    assert r["status"] == "active" and r["cancel_at_period_end"] is True
    assert client.post(f"/subscriptions/{now['id']}/cancel", headers=h).status_code == 400
    usage = client.post(f"/subscriptions/{now['id']}/usage", headers=h,
                        json={"metric": "x", "quantity": "1", "unit_price_zar": "1"})
    assert usage.status_code == 400


def test_invalid_subscriptions_are_rejected(client, tenant):
    h = testdb.headers(tenant)
    base = {"customer_id": str(uuid.uuid4()), "plan": "Fibre"}
    assert client.post("/subscriptions", json={**base, "base_price_zar": "0"}, headers=h).status_code == 422
    assert client.post("/subscriptions", json={**base, "base_price_zar": "10", "billing_interval": "hourly"},
                       headers=h).status_code == 422


# ── Tenant isolation ────────────────────────────────────────────────────────

def test_other_tenants_cannot_see_or_touch_invoices_and_subscriptions(client, tenant):
    sub = subscribe(client, tenant)
    inv = generate(client, tenant)[0]
    other = testdb.new_tenant("other")
    h = testdb.headers(other)
    assert client.get(f"/invoices/{inv['id']}", headers=h).status_code == 404
    assert client.get("/invoices", headers=h).json()["items"] == []
    assert pay(client, other, inv["id"], "1.00").status_code == 404
    assert client.post(f"/invoices/{inv['id']}/credit-note", json={"reason": "x"}, headers=h).status_code == 404
    assert client.post(f"/subscriptions/{sub['id']}/cancel", headers=h).status_code == 404
    assert generate(client, other) == []                                 # never bills another tenant's subscriptions
