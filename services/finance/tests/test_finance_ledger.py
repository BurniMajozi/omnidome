"""Finance ledger rules on SQLite (no Postgres needed): no demo data, statements, journal
integrity, auto_post, idempotency, reversal, period lock, VAT split, roles, billing sync.

    PYTHONPATH=. python -m pytest services/finance/tests -q
"""
import asyncio
import os
import sys
import tempfile
import uuid
from datetime import date

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

_db = os.path.join(tempfile.mkdtemp(), "finance_test.db")
os.environ.update({
    "DATABASE_URL": f"sqlite+aiosqlite:///{_db}", "AUTH_MODE": "header", "AUTH_ENFORCE_MODULES": "false",
    "AUTH_ENFORCE_RBAC": "false", "FINANCE_ENFORCE_ROLES": "true", "INTERNAL_SERVICE_KEY": "i" * 40,
})

from fastapi.testclient import TestClient  # noqa: E402

from services.common import db as common_db  # noqa: E402
from services.finance import main as fmain  # noqa: E402
from services.finance.database import init_tables  # noqa: E402

asyncio.run(init_tables())
for fn in (common_db.get_async_engine, common_db._get_async_session_factory):
    fn.cache_clear()
import services.finance.database as fdb  # noqa: E402

fdb._session_factory = None
INTERNAL = {"x-internal-key": "i" * 40}


@pytest.fixture(scope="module")
def client():
    with TestClient(fmain.app) as c:
        yield c


@pytest.fixture
def tenant():
    return str(uuid.uuid4())


def h(tenant, roles="finance_admin", **extra):
    out = {"X-Tenant-Id": tenant, "X-User-Id": str(uuid.uuid4()), **extra}
    if roles:
        out["X-Roles"] = roles
    return out


def je(lines=None, **kw):
    lines = lines or [{"account_code": "1100", "debit": "100.00", "credit": "0"},
                      {"account_code": "4000", "debit": "0", "credit": "100.00"}]
    return {"date": date.today().isoformat(), "description": "t", "lines": lines, **kw}


def test_fresh_tenant_reads_are_empty_and_write_nothing(client, tenant):
    hd = h(tenant)
    assert client.get("/journal-entries", headers=hd).json() == []
    assert client.get("/trial-balance", headers=hd).json()["accounts"] == []
    assert client.get("/records", headers=hd).json() == []
    assert client.get("/overview", headers=hd).json()["kpis"]["revenue"] == 0
    assert client.get("/cash-flow", headers=hd).status_code == 200
    st = client.get("/statements", headers=hd).json()
    assert st["income_statement"][0]["amount"] == 0
    assert client.get("/journal-entries", headers=hd).json() == []  # still nothing seeded


def test_statements_with_posted_expense_does_not_crash(client, tenant):
    hd = h(tenant)
    for lines in (
        [{"account_code": "1000", "debit": "1000", "credit": "0"}, {"account_code": "4000", "debit": "0", "credit": "1000"}],
        [{"account_code": "5000", "debit": "300", "credit": "0"}, {"account_code": "2000", "debit": "0", "credit": "300"}],
        [{"account_code": "6000", "debit": "200", "credit": "0"}, {"account_code": "1000", "debit": "0", "credit": "200"}],
    ):
        assert client.post("/journal-entries", json=je(lines, auto_post=True), headers=hd).status_code == 200
    r = client.get("/statements", headers=hd)
    assert r.status_code == 200, r.text
    inc = {l["line"]: l["amount"] for l in r.json()["income_statement"]}
    assert inc["Revenue"] == 1000 and inc["Cost of Service"] == -300 and inc["Gross Profit"] == 700
    assert inc["Operating Expenses"] == -200 and inc["Net Income"] == 500


def test_imbalance_of_one_cent_rejected(client, tenant):
    r = client.post("/journal-entries", json=je([{"account_code": "1100", "debit": "100.01", "credit": "0"},
                                                 {"account_code": "4000", "debit": "0", "credit": "100.00"}]), headers=h(tenant))
    assert r.status_code == 400


def test_line_rules(client, tenant):
    hd = h(tenant)
    both = je([{"account_code": "1100", "debit": "5", "credit": "5"}, {"account_code": "4000", "debit": "0", "credit": "0"}])
    assert client.post("/journal-entries", json=both, headers=hd).status_code == 422
    zero = je([{"account_code": "1100", "debit": "0", "credit": "0"}, {"account_code": "4000", "debit": "0", "credit": "0"}])
    assert client.post("/journal-entries", json=zero, headers=hd).status_code == 422
    neg = je([{"account_code": "1100", "debit": "-5", "credit": "0"}, {"account_code": "4000", "debit": "0", "credit": "-5"}])
    assert client.post("/journal-entries", json=neg, headers=hd).status_code == 422
    one = je([{"account_code": "1100", "debit": "5", "credit": "0"}])
    assert client.post("/journal-entries", json=one, headers=hd).status_code == 422


def test_unknown_account_422(client, tenant):
    r = client.post("/journal-entries", json=je([{"account_code": "1100", "debit": "1", "credit": "0"},
                                                 {"account_code": "4999", "debit": "0", "credit": "1"}]), headers=h(tenant))
    assert r.status_code == 422 and "4999" in r.text


def test_structural_accounts_exist(client, tenant):
    codes = {a["code"] for a in client.get("/accounts", headers=h(tenant)).json()}
    assert {"1000", "1010", "1100", "2200", "2210", "4000"} <= codes


def test_auto_post_posts_and_appears_in_trial_balance(client, tenant):
    hd = h(tenant)
    r = client.post("/journal-entries", json=je(auto_post=True), headers=hd)
    assert r.json()["status"] == "posted" and r.json()["is_posted"] is True
    tb = client.get("/trial-balance", headers=hd).json()
    assert tb["is_balanced"] and tb["total_debits"] == 100.0
    draft = client.post("/journal-entries", json=je(), headers=hd).json()
    assert draft["is_posted"] is False
    assert client.get("/trial-balance", headers=hd).json()["total_debits"] == 100.0  # drafts excluded


def test_vat_split_entry(client, tenant):
    hd = h(tenant)
    lines = [{"account_code": "1100", "debit": "115.00", "credit": "0"},
             {"account_code": "4000", "debit": "0", "credit": "100.00"},
             {"account_code": "2200", "debit": "0", "credit": "15.00"}]
    r = client.post("/journal-entries", json=je(lines, auto_post=True, source="billing.invoice", source_id="inv-1"), headers=hd)
    assert r.status_code == 200
    tb = {a["account_code"]: a for a in client.get("/trial-balance", headers=hd).json()["accounts"]}
    assert tb["2200"]["credit_total"] == 15.0 and tb["4000"]["credit_total"] == 100.0 and tb["1100"]["debit_total"] == 115.0


def test_duplicate_source_is_idempotent(client, tenant):
    hd = h(tenant)
    first = client.post("/journal-entries", json=je(source="billing.invoice", source_id="A1", auto_post=True), headers=hd)
    second = client.post("/journal-entries", json=je(source="billing.invoice", source_id="A1", auto_post=True), headers=hd)
    assert second.status_code == 200 and second.json()["status"] == "duplicate" and second.json()["id"] == first.json()["id"]
    assert len(client.get("/journal-entries", headers=hd).json()) == 1


def test_posted_entries_are_immutable_and_reversal_is_idempotent(client, tenant):
    hd = h(tenant)
    e = client.post("/journal-entries", json=je(auto_post=True), headers=hd).json()
    assert client.delete(f"/journal-entries/{e['id']}", headers=hd).status_code == 400
    assert client.post(f"/journal-entries/{e['id']}/post", headers=hd).status_code == 400
    r1 = client.post(f"/journal-entries/{e['id']}/reverse", headers=hd)
    r2 = client.post(f"/journal-entries/{e['id']}/reverse", headers=hd)
    assert r1.status_code == 200 and r1.json()["source"] == "finance.reversal" and r1.json()["is_posted"]
    assert r2.json()["status"] == "duplicate" and r2.json()["id"] == r1.json()["id"]
    tb = client.get("/trial-balance", headers=hd).json()
    assert tb["total_debits"] == 200.0 and all(a["balance"] == 0 for a in tb["accounts"])
    draft = client.post("/journal-entries", json=je(), headers=hd).json()
    assert client.post(f"/journal-entries/{draft['id']}/reverse", headers=hd).status_code == 400


def test_closed_period_is_409_and_reopen_allows(client, tenant):
    hd = h(tenant)
    p = date.today().strftime("%Y-%m")
    assert client.post(f"/periods/{p}/close", headers=hd).status_code == 200
    assert client.post("/journal-entries", json=je(auto_post=True), headers=hd).status_code == 409
    d = client.post("/journal-entries", json=je(), headers=hd).json()  # drafts may still be saved
    assert client.post(f"/journal-entries/{d['id']}/post", headers=hd).status_code == 409
    assert client.post(f"/periods/{p}/reopen", headers=hd).status_code == 200
    assert client.post("/journal-entries", json=je(auto_post=True), headers=hd).status_code == 200
    assert client.post("/periods/2026-13/close", headers=hd).status_code == 422


def test_role_tiers(client, tenant):
    assert client.get("/journal-entries", headers=h(tenant, roles="viewer")).status_code == 403
    assert client.get("/journal-entries", headers=h(tenant, roles="billing")).status_code == 200
    clerk = h(tenant, roles="accountant")
    assert client.post("/journal-entries", json=je(), headers=clerk).status_code == 200  # draft ok
    assert client.post("/journal-entries", json=je(auto_post=True), headers=clerk).status_code == 403
    e = client.post("/journal-entries", json=je(auto_post=True), headers=h(tenant)).json()
    assert client.post(f"/journal-entries/{e['id']}/reverse", headers=clerk).status_code == 403
    assert client.post("/periods/2026-01/close", headers=clerk).status_code == 403
    assert client.post("/billing/sync-invoices", headers=clerk).status_code == 403
    assert client.post("/records", json={"record_type": "x", "amount": "5"}, headers=h(tenant, roles="billing")).status_code == 403
    assert client.post("/records", json={"record_type": "x", "amount": "-5"}, headers=clerk).status_code == 422


def test_internal_key_allows_auto_post_without_roles(client, tenant):
    r = client.post("/journal-entries", json=je(auto_post=True, source="sales.commission", source_id="c1"),
                    headers=h(tenant, roles=None, **INTERNAL))
    assert r.status_code == 200 and r.json()["is_posted"] is True
    wrong = client.post("/journal-entries", json=je(auto_post=True), headers=h(tenant, roles=None, **{"x-internal-key": "no"}))
    assert wrong.status_code == 403


def test_sync_invoices_paginates_and_is_idempotent(client, tenant, monkeypatch):
    invoices = [{"id": f"inv-{i}", "invoice_number": f"INV-{i}", "total_zar": "10.00", "customer_id": str(uuid.uuid4())}
                for i in range(230)]
    seen = []

    class R:
        status_code = 200

        def __init__(self, body):
            self._b = body

        def json(self):
            return self._b

    class C:
        async def get(self, url, headers=None, params=None):
            seen.append((params["offset"], headers))
            o, n = params["offset"], params["limit"]
            return R({"items": invoices[o:o + n], "total": len(invoices)})

    auth = type("A", (), {"user_id": uuid.uuid4(), "roles": []})()
    assert asyncio.run(fmain.fetch_billing_invoices(C(), uuid.UUID(tenant), auth)) == invoices
    assert [o for o, _ in seen] == [0, 100, 200]
    assert seen[0][1]["x-tenant-id"] == tenant and seen[0][1]["x-user-id"]

    async def fake_fetch(client_, tid, auth_):
        return invoices

    monkeypatch.setattr(fmain, "fetch_billing_invoices", fake_fetch)
    hd = h(tenant)
    assert client.post("/billing/sync-invoices", headers=hd).json()["invoices_synced"] == 230
    again = client.post("/billing/sync-invoices", headers=hd).json()
    assert again["invoices_synced"] == 0 and again["already_synced"] == 230
    entries = client.get("/journal-entries", params={"limit": 500}, headers=hd).json()
    assert len(entries) == 230
