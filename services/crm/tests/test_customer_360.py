"""Customer 360: per-section fallbacks, bounded concurrent upstream calls, no fabricated defaults."""
import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal

from services.crm.routes import customer_360 as c360
from services.crm.routes import customers as cust_routes
from services.crm.tests.conftest import TENANT_A, headers
from services.crm.tests.test_crm_behaviour import _customer, _seed


class UndefinedTableError(Exception):
    pass


class FakeSession:
    def __init__(self):
        self.savepoints = 0

    @asynccontextmanager
    async def begin_nested(self):
        self.savepoints += 1
        yield


def test_section_failure_degrades_to_none_with_code():
    sess = FakeSession()
    sec = c360._Sections(sess, uuid.uuid4())

    async def missing():
        raise UndefinedTableError('relation "orders" does not exist')

    async def fine():
        return [1]

    async def go():
        return await sec.run("orders", missing), await sec.run("tickets", fine)

    orders, tickets = asyncio.run(go())
    assert orders is None and tickets == [1]
    assert sec.errors == {"orders": "table_missing"} and sec.partial is True
    assert sess.savepoints == 2  # every section runs in its own SAVEPOINT


def test_360_endpoints_return_200_when_other_services_tables_are_missing(crm_env):
    client, factory = crm_env  # SQLite has none of the billing/journey/sales/support tables
    c = _customer()
    _seed(factory, [c])
    h = headers()

    d = client.get(f"/customers/{c.id}/360/details", headers=h)
    assert d.status_code == 200, d.text
    body = d.json()
    assert body["partial"] is True and body["customer"]["id"] == str(c.id)
    assert body["subscriptions"] is None and body["section_errors"]["subscriptions"] == "table_missing"

    cx = client.get(f"/customers/{c.id}/360/cx", headers=h)
    assert cx.status_code == 200, cx.text
    assert cx.json()["orders"] is None and cx.json()["section_errors"]["orders"] == "table_missing"

    crm = client.get(f"/customers/{c.id}/360/crm", headers=h)
    assert crm.status_code == 200 and crm.json()["partial"] is True

    cvm = client.get(f"/customers/{c.id}/360/cvm", headers=h)
    assert cvm.status_code == 200, cvm.text
    cj = cvm.json()
    assert cj["financial_summary"] is None and cj["cvm_summary"] is None  # nothing invented
    assert cj["partial"] is True and "invoices" in cj["section_errors"]


def test_360_details_masks_id_for_non_admin(crm_env):
    client, factory = crm_env
    c = _customer()
    _seed(factory, [c])
    r = client.get(f"/customers/{c.id}/360/details", headers=headers(roles="sales_agent"))
    assert r.status_code == 200 and "8001015009087" not in r.text


def test_cvm_summary_not_assessed_without_data():
    s = c360.build_cvm_summary(Decimal("0"), Decimal("0"), 0, 0, None)
    assert s.customer_tier == "NOT_ASSESSED" and s.recommended_action is None
    assert s.value_segment == "NOT_ASSESSED"
    real = c360.build_cvm_summary(Decimal("2500"), Decimal("60000"), 12, 1, Decimal("0.05"))
    assert real.customer_tier == "PLATINUM" and real.recommended_action == "UPSELL"
    assert c360.build_cvm_summary(Decimal("100"), Decimal("0"), 3, 1, None).recommended_action == "CROSS_SELL"


def test_customer_view_runs_upstreams_concurrently_with_partial(crm_env, monkeypatch):
    client, factory = crm_env
    c = _customer()
    _seed(factory, [c])
    monkeypatch.setattr(cust_routes, "UPSTREAM_TIMEOUT_SECONDS", 0.3)

    async def fake_get(service, path, **kw):
        if service == "network":
            await asyncio.sleep(5)  # hangs: must be cut at the timeout
        if service == "support":
            raise RuntimeError("down")
        if service == "lifecycle" and path.startswith("/lifecycle/customer/"):
            return {"lifecycle": {"current_stage": "Active", "health_score": 70, "churn_probability": 0.1}}
        if service == "lifecycle":
            return {"events": [{"to_stage": "Active"}]}
        return [{"id": "inv-1"}]

    monkeypatch.setattr(cust_routes, "service_get", fake_get)
    t0 = time.monotonic()
    r = client.get(f"/customers/{c.id}", headers=headers())
    elapsed = time.monotonic() - t0
    assert r.status_code == 200, r.text
    j = r.json()
    assert elapsed < 2.0  # five calls in parallel, bounded: not 5 x 5s
    assert j["partial"] is True
    assert j["section_errors"] == {"network": "timeout", "support": "upstream_error"}
    assert j["network"] is None and j["support"] is None and j["billing"] == [{"id": "inv-1"}]
    assert j["lifecycle_data"]["current_stage"] == "Active" and j["lifecycle_data"]["history"] == [{"to_stage": "Active"}]
