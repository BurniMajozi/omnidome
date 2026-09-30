"""Seat reconcile + endpoints against a real Postgres (skipped without TEST_DATABASE_URL)."""
import os
import sys
from decimal import Decimal

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.common import testdb  # noqa: E402

testdb.use_test_database()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from services.billing.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
    testdb.reset_engines()


def _admin_headers(tenant):
    return {**testdb.headers(tenant), "X-Roles": "platform_admin"}


def _snap(current, events):
    return {"current_seats": current, "events": events}


def _reconcile(client, tenant, snap, period="2026-06"):
    r = client.post("/billing/seats/reconcile", headers=_admin_headers(tenant),
                    json={"tenant_id": str(tenant), "period": period, "unit_price": 300, "seat_snapshot": snap})
    assert r.status_code == 200, r.text
    return r.json()


def test_reconcile_creates_invoice_and_is_idempotent(client):
    tenant = testdb.new_tenant()
    snap = _snap(4, [{"user_id": "a", "delta": 2, "reason": "add", "at": "2026-06-10T08:00:00Z"},
                     {"user_id": "b", "delta": -1, "reason": "deact", "at": "2026-06-20T08:00:00Z"}])
    first = _reconcile(client, tenant, snap)
    assert first["created"] is True and first["peak_seats"] == 5 and first["status"] == "invoiced"
    second = _reconcile(client, tenant, snap)
    assert second["created"] is False and second["id"] == first["id"]
    with testdb.sync_engine().begin() as conn:
        n = conn.execute(text("select count(*) from invoices where tenant_id=:t"), {"t": tenant}).scalar()
    assert n == 1


def test_prorated_addition_is_credited_not_double_charged(client):
    tenant = testdb.new_tenant()
    r = client.post("/billing/seats/prorate", headers=_admin_headers(tenant),
                    json={"tenant_id": str(tenant), "added_seats": 2, "on": "2026-06-15", "unit_price": 300})
    assert r.status_code == 200 and Decimal(r.json()["amount_ex_vat"]) == Decimal("320.00")
    snap = _snap(5, [{"user_id": "a", "delta": 2, "reason": "add", "at": "2026-06-15T08:00:00Z"}])
    run = _reconcile(client, tenant, snap)
    assert run["peak_seats"] == 5 and Decimal(run["amount"]) == Decimal("1180.00")


def test_zero_seat_tenant_is_skipped_without_invoice(client):
    tenant = testdb.new_tenant()
    run = _reconcile(client, tenant, _snap(0, []))
    assert run["status"] == "skipped" and run["invoice_id"] is None


def test_reconcile_requires_operator_and_preview(client):
    tenant = testdb.new_tenant()
    r = client.post("/billing/seats/reconcile", headers=testdb.headers(tenant), json={"tenant_id": str(tenant)})
    assert r.status_code == 403
    admin = {**testdb.headers(tenant), "X-Roles": "org_admin"}
    p = client.post("/billing/seats/proration-preview", headers=admin,
                    json={"added_seats": 1, "on": "2026-06-30", "unit_price": 300})
    assert p.status_code == 200 and p.json()["amount_ex_vat"] == "10.00"
    runs = client.get("/billing/seats/runs", headers=admin)
    assert runs.status_code == 200 and runs.json() == []


def test_runs_and_preview_refuse_plain_members(client):
    tenant = testdb.new_tenant()
    member = {**testdb.headers(tenant), "X-Roles": "org_user"}
    assert client.get("/billing/seats/runs", headers=member).status_code == 403
    assert client.get("/billing/seats/runs", headers=testdb.headers(tenant)).status_code == 403
    r = client.post("/billing/seats/proration-preview", headers=member, json={"added_seats": 1, "unit_price": 300})
    assert r.status_code == 403


@pytest.mark.parametrize("price", [-1, -0.01, 100001, 10.123, "abc"])
def test_bad_unit_price_is_rejected(client, price):
    tenant = testdb.new_tenant()
    r = client.post("/billing/seats/reconcile", headers=_admin_headers(tenant),
                    json={"tenant_id": str(tenant), "period": "2026-06", "unit_price": price, "seat_snapshot": _snap(2, [])})
    assert r.status_code == 422
    r = client.post("/billing/seats/prorate", headers=_admin_headers(tenant),
                    json={"tenant_id": str(tenant), "added_seats": 1, "on": "2026-06-15", "unit_price": price})
    assert r.status_code == 422
    with testdb.sync_engine().begin() as conn:
        assert conn.execute(text("select count(*) from invoices where tenant_id=:t"), {"t": tenant}).scalar() == 0


def test_prorate_idempotency_key_replays_same_charge(client):
    tenant = testdb.new_tenant()
    body = {"tenant_id": str(tenant), "added_seats": 2, "on": "2026-06-15", "unit_price": 300}
    h = {**_admin_headers(tenant), "Idempotency-Key": "abc-123"}
    first = client.post("/billing/seats/prorate", headers=h, json=body)
    second = client.post("/billing/seats/prorate", headers=h, json=body)
    assert first.status_code == 200 and second.status_code == 200
    assert second.json() == first.json()
    other = client.post("/billing/seats/prorate", headers={**_admin_headers(tenant), "Idempotency-Key": "other"}, json=body)
    assert other.json()["charge_id"] != first.json()["charge_id"]
    with testdb.sync_engine().begin() as conn:
        assert conn.execute(text("select count(*) from seat_proration_charges where tenant_id=:t"), {"t": tenant}).scalar() == 2
        assert conn.execute(text("select count(*) from invoices where tenant_id=:t"), {"t": tenant}).scalar() == 2


def test_concurrent_reconcile_creates_exactly_one_invoice(client):
    from concurrent.futures import ThreadPoolExecutor

    tenant = testdb.new_tenant()
    snap = _snap(3, [])
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: _reconcile(client, tenant, snap, period="2026-05"), range(6)))
    assert sum(1 for r in results if r["created"]) == 1
    assert len({r["id"] for r in results}) == 1
    with testdb.sync_engine().begin() as conn:
        assert conn.execute(text("select count(*) from invoices where tenant_id=:t"), {"t": tenant}).scalar() == 1
        assert conn.execute(text("select count(*) from seat_billing_runs where tenant_id=:t"), {"t": tenant}).scalar() == 1
