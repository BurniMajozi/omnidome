"""Paystack webhook (services/billing/routes/paystack.py) against a real Postgres.

The webhook is public (no tenant auth): the HMAC-SHA512 signature is the only
thing that stops anyone marking an invoice paid, and Paystack redelivers
events, so both are pinned here.
"""
import hashlib
import hmac
import json
import os
import sys
import uuid
from decimal import Decimal

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.common import testdb  # noqa: E402

testdb.use_test_database()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from services.billing.main import app  # noqa: E402
from services.billing.routes import paystack  # noqa: E402

SECRET = "sk_test_webhook_secret_for_tests"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
    testdb.reset_engines()


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(paystack, "PAYSTACK_WEBHOOK_SECRET", SECRET)

    async def no_reinstate(*_a, **_k):
        return None
    monkeypatch.setattr(paystack, "_trigger_auto_reinstate", no_reinstate)


@pytest.fixture
def invoice(client):
    tenant = testdb.new_tenant("paystack test")
    h = testdb.headers(tenant)
    client.post("/subscriptions", json={"customer_id": str(uuid.uuid4()), "plan": "Fibre 100",
                                        "base_price_zar": "100.00"}, headers=h)
    inv = client.post("/invoices/generate", json={}, headers=h).json()[0]
    return tenant, inv


def charge(tenant, inv, reference="ref-1", kobo=11500) -> bytes:
    return json.dumps({"event": "charge.success", "data": {
        "reference": reference, "amount": kobo,
        "metadata": {"invoice_id": inv["id"], "tenant_id": str(tenant)}}}).encode()


def signed(body: bytes, secret: str = SECRET) -> dict:
    return {"x-paystack-signature": hmac.new(secret.encode(), body, hashlib.sha512).hexdigest(),
            "content-type": "application/json"}


def paid(client, tenant, inv):
    got = client.get(f"/invoices/{inv['id']}", headers=testdb.headers(tenant)).json()
    with testdb.sync_engine().connect() as conn:
        rows = conn.execute(text("SELECT count(*) FROM payments WHERE invoice_id = :i"), {"i": inv["id"]}).scalar()
    return got["status"], Decimal(got["amount_paid_zar"]), rows


def test_signed_charge_marks_the_invoice_paid(client, invoice):
    tenant, inv = invoice
    body = charge(tenant, inv)
    assert client.post("/payments/paystack/webhook", content=body, headers=signed(body)).status_code == 200
    assert paid(client, tenant, inv) == ("paid", Decimal("115.00"), 1)


@pytest.mark.parametrize("headers", [
    {"content-type": "application/json"},                                   # no signature header at all
    {"x-paystack-signature": "0" * 128, "content-type": "application/json"},  # forged
])
def test_unsigned_or_forged_charges_change_nothing(client, invoice, headers):
    tenant, inv = invoice
    r = client.post("/payments/paystack/webhook", content=charge(tenant, inv), headers=headers)
    assert r.status_code in (400, 401)
    assert paid(client, tenant, inv) == ("draft", Decimal("0.00"), 0)


def test_signature_made_with_another_key_is_refused(client, invoice):
    tenant, inv = invoice
    body = charge(tenant, inv)
    r = client.post("/payments/paystack/webhook", content=body, headers=signed(body, "sk_test_someone_else"))
    assert r.status_code in (400, 401) and paid(client, tenant, inv)[2] == 0


def test_without_a_configured_secret_nothing_is_accepted(client, invoice, monkeypatch):
    tenant, inv = invoice
    monkeypatch.setattr(paystack, "PAYSTACK_WEBHOOK_SECRET", "")
    body = charge(tenant, inv)
    r = client.post("/payments/paystack/webhook", content=body, headers=signed(body, ""))
    assert r.status_code == 503 and paid(client, tenant, inv)[2] == 0


def test_a_redelivered_charge_is_recorded_once(client, invoice):
    tenant, inv = invoice
    body = charge(tenant, inv, reference="ref-dup", kobo=5000)                 # R50 of R115
    for _ in range(3):
        assert client.post("/payments/paystack/webhook", content=body, headers=signed(body)).status_code == 200
    assert paid(client, tenant, inv) == ("partially_paid", Decimal("50.00"), 1)
