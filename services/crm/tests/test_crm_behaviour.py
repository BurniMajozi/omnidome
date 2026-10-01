"""Behaviour tests for the CRM routes (SQLite-backed, no Postgres)."""
import asyncio
import uuid

from services.crm import access
from services.crm.models import Customer, Lead
from services.crm.tests.conftest import TENANT_A, TENANT_B, headers

VALID_ID = "8001015009087"


def _seed(factory, objs):
    async def run():
        async with factory() as s:
            s.add_all(objs)
            await s.commit()
    asyncio.run(run())


def _customer(tenant=TENANT_A, **kw):
    base = dict(id=uuid.uuid4(), tenant_id=tenant, first_name="Al", last_name="Ho",
                email=f"{uuid.uuid4().hex[:6]}@x.co", account_number=f"ACC-{uuid.uuid4().hex[:8]}",
                status="active", id_number=VALID_ID)
    base.update(kw)
    return Customer(**base)


def _lead(tenant=TENANT_A, status="NEW", **kw):
    base = dict(id=uuid.uuid4(), tenant_id=tenant, first_name="Le", last_name="Ad", status=status)
    base.update(kw)
    return Lead(**base)


# ------------------------------------------------------------------ role tiers + masking

def test_org_user_cannot_mutate(crm_env):
    client, _ = crm_env
    h = headers(roles="org_user")
    body = {"first_name": "A", "last_name": "B", "email": "a@b.co"}
    assert client.post("/customers", json=body, headers=h).status_code == 403
    assert client.post("/leads", json={"first_name": "A", "last_name": "B"}, headers=h).status_code == 403
    rule = {"field": "status", "operator": "eq", "value": "active"}
    assert client.post("/segments", json={"name": "s", "rules": [rule]}, headers=h).status_code == 403
    assert client.post("/companies", json={"name": "Co"}, headers=h).status_code == 403
    assert client.get("/customers", headers=h).status_code == 200  # reads stay open to members


def test_agent_can_write_and_enforcement_can_be_disabled(crm_env, monkeypatch):
    client, _ = crm_env
    body = {"first_name": "A", "last_name": "B", "email": "a@b.co"}
    assert client.post("/customers", json=body, headers=headers(roles="sales_agent")).status_code == 201
    monkeypatch.setenv("CRM_ENFORCE_ROLES", "false")
    r = client.post("/customers", json={**body, "email": "c@d.co"}, headers=headers(roles="org_user"))
    assert r.status_code == 201


def test_id_number_masked_for_non_admin_only(crm_env):
    client, factory = crm_env
    c = _customer()
    _seed(factory, [c])
    agent = client.get("/customers", headers=headers(roles="sales_agent")).json()["items"][0]
    assert agent["id_number"] == "*********" + VALID_ID[-4:]
    admin = client.get("/customers", headers=headers(roles="org_admin")).json()["items"][0]
    assert admin["id_number"] == VALID_ID
    one = client.get(f"/customers/{c.id}", headers=headers(roles="org_user"))
    assert one.status_code == 200 and one.json()["id_number"].endswith(VALID_ID[-4:]) and VALID_ID not in one.text


def test_redaction_helper_drops_bank_fields():
    out = access.redact_customer({"id_number": VALID_ID, "bank_account": "123", "x": 1}, is_admin=False)
    assert "bank_account" not in out and out["x"] == 1 and out["id_number"].endswith("9087")
    assert access.redact_customer({"id_number": VALID_ID}, True)["id_number"] == VALID_ID


def test_mass_assignment_rejected(crm_env):
    client, _ = crm_env
    h = headers()
    body = {"first_name": "A", "last_name": "B", "email": "a@b.co", "tenant_id": str(TENANT_B)}
    assert client.post("/customers", json=body, headers=h).status_code == 422
    assert client.post("/leads", json={"first_name": "A", "last_name": "B", "created_at": "2020-01-01"},
                       headers=h).status_code == 422


def test_customer_status_validated(crm_env):
    client, factory = crm_env
    c = _customer()
    _seed(factory, [c])
    assert client.put(f"/customers/{c.id}", json={"status": "bogus"}, headers=headers()).status_code == 422
    assert client.put(f"/customers/{c.id}", json={"status": "suspended"}, headers=headers()).status_code == 200


def test_tenant_isolation(crm_env):
    client, factory = crm_env
    c = _customer(tenant=TENANT_B)
    _seed(factory, [c])
    assert client.get(f"/customers/{c.id}", headers=headers(TENANT_A)).status_code == 404
    assert client.get("/customers", headers=headers(TENANT_A)).json()["total"] == 0


# ------------------------------------------------------------------ lead status

def test_lead_status_filter_case_insensitive_and_total(crm_env):
    client, factory = crm_env
    _seed(factory, [_lead(status="NEW"), _lead(status="new"), _lead(status="Contacted"), _lead(status="LOST")])
    h = headers()
    r = client.get("/leads?status=new", headers=h).json()
    assert r["total"] == 2 and len(r["items"]) == 2
    assert client.get("/leads?status=CONTACTED", headers=h).json()["total"] == 1
    assert client.get("/leads", headers=h).json()["total"] == 4
    assert client.get("/leads?status=nonsense", headers=h).status_code == 422


def test_lead_update_stores_uppercase(crm_env):
    client, factory = crm_env
    lead = _lead()
    _seed(factory, [lead])
    r = client.put(f"/leads/{lead.id}", json={"status": "contacted"}, headers=headers())
    assert r.status_code == 200 and r.json()["status"] == "CONTACTED"
    assert client.put(f"/leads/{lead.id}", json={"status": "nope"}, headers=headers()).status_code == 422


def test_convert_lead_idempotent_and_refuses_lost(crm_env):
    client, factory = crm_env
    lead = _lead(status="qualified", phone="082 123 4567", email=None)
    lost = _lead(status="Lost", phone="0831112222")
    sales_converted = _lead(status="CONVERTED", phone="0844445555")
    _seed(factory, [lead, lost, sales_converted])
    h = headers()

    first = client.post(f"/leads/{lead.id}/convert", headers=h)
    assert first.status_code == 201, first.text
    cust = first.json()
    assert cust["email"] is None  # NULL, never ''

    again = client.post(f"/leads/{lead.id}/convert", headers=h)
    assert again.status_code == 409
    assert again.json()["detail"]["customer_id"] == cust["id"]
    assert client.get("/customers", headers=h).json()["total"] == 1  # no duplicate customer

    assert client.post(f"/leads/{lost.id}/convert", headers=h).status_code == 400
    assert client.post(f"/leads/{sales_converted.id}/convert", headers=h).status_code == 409
    assert client.get("/customers", headers=h).json()["total"] == 1


def test_dashboard_counts_mixed_case(crm_env):
    client, factory = crm_env
    _seed(factory, [_lead(status="NEW"), _lead(status="new"), _lead(status="CONTACTED"), _lead(status="Qualified"),
                    _lead(status="CONVERTED"), _lead(status="converted"), _lead(status="WON"), _lead(status="LOST"),
                    _customer(status="active"), _customer(status="churned")])
    r = client.get("/customers/dashboard-summary", headers=headers())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["activeLeads"] == 4
    assert d["convertedLeads"] == 3 and d["won_from_leads"] == 1
    assert d["active_customers"] == 1 and d["totalCustomers"] == 2
    assert d["conversionRate"] == round(3 / 8 * 100, 1)
    assert len(d["customerData"]) == 6 and len(d["leadData"]) == 4


# ------------------------------------------------------------------ dedupe

def test_create_customer_dedupe_409_and_merge(crm_env):
    client, _ = crm_env
    h = headers()
    first = client.post("/customers", json={"first_name": "A", "last_name": "B", "email": "Jane@X.co",
                                            "phone": "0821234567"}, headers=h)
    assert first.status_code == 201
    cid = first.json()["id"]

    same_phone = client.post("/customers", json={"first_name": "C", "last_name": "D", "email": "other@x.co",
                                                 "phone": "+27 82 123 4567"}, headers=h)
    assert same_phone.status_code == 409
    assert same_phone.json()["detail"]["existing_customer_id"] == cid
    same_email = client.post("/customers", json={"first_name": "C", "last_name": "D", "email": " jane@x.CO"},
                             headers=h)
    assert same_email.status_code == 409

    merged = client.post("/customers?merge=true", json={"first_name": "C", "last_name": "D", "email": "jane@x.co",
                                                        "address": "1 Main Rd"}, headers=h)
    assert merged.status_code == 201 and merged.json()["id"] == cid
    assert merged.json()["address"] == "1 Main Rd" and merged.json()["first_name"] == "A"  # fill-only
    other = client.post("/customers", json={"first_name": "A", "last_name": "B", "email": "jane@x.co",
                                            "phone": "0821234567"}, headers=headers(TENANT_B))
    assert other.status_code == 201  # another tenant may reuse the same phone/e-mail


def test_update_into_duplicate_is_409(crm_env):
    client, factory = crm_env
    a, b = _customer(phone="0821234567", phone_normalized="+27821234567"), _customer()
    _seed(factory, [a, b])
    r = client.put(f"/customers/{b.id}", json={"phone": "082 123 4567"}, headers=headers())
    assert r.status_code == 409 and r.json()["detail"]["existing_customer_id"] == str(a.id)


# ------------------------------------------------------------------ pagination / limits

def test_list_queries_have_id_tiebreak(crm_env):
    from sqlalchemy import event

    client, factory = crm_env
    _seed(factory, [_customer(), _lead()])
    seen = []
    event.listen(factory.kw["bind"].sync_engine, "before_cursor_execute",
                 lambda conn, cur, stmt, *a: seen.append(stmt))
    h = headers()
    client.get("/customers", headers=h)
    client.get("/leads", headers=h)
    client.get("/customers/activities", headers=h)
    ordered = [q for q in seen if "ORDER BY" in q]
    assert any("ORDER BY customers.created_at DESC, customers.id" in q for q in ordered)
    assert any("ORDER BY leads.created_at DESC, leads.id" in q for q in ordered)
    assert any("activity_events.created_at DESC, activity_events.id" in q for q in ordered)


def test_limits_capped(crm_env):
    client, _ = crm_env
    h = headers()
    assert client.get("/customers/activities?limit=100000", headers=h).status_code == 422
    assert client.get("/tasks?limit=100000", headers=h).status_code == 422
    assert client.get("/customers/activities?limit=200", headers=h).status_code == 200


def test_segment_rule_validation(crm_env):
    client, _ = crm_env
    h = headers()
    ok = {"name": "s", "rules": [{"field": "status", "operator": "in", "value": ["active", "churned"]}]}
    assert client.post("/segments", json=ok, headers=h).status_code == 201
    for rule in ({"field": "password", "operator": "eq", "value": "x"},
                 {"field": "status", "operator": "eq", "value": "weird"},
                 {"field": "email", "operator": "contains", "value": "x" * 101},
                 {"field": "email", "operator": "in", "value": "notalist"},
                 {"field": "email", "operator": "in", "value": list("a" * 101)},
                 {"field": "email", "operator": "eq", "value": {"$ne": 1}}):
        assert client.post("/segments", json={"name": "s", "rules": [rule]}, headers=h).status_code == 422, rule


# ------------------------------------------------------------------ journey sync

def test_status_change_triggers_sync_with_old_status(crm_env, monkeypatch):
    client, factory = crm_env
    import services.crm.routes.customers as cr

    calls = []

    async def fake_sync(session, customer, source_event="status_change"):
        calls.append((source_event, customer.status))

    monkeypatch.setattr(cr, "_sync_customer_to_journey_engine", fake_sync)
    c = _customer(status="active")
    _seed(factory, [c])
    assert client.put(f"/customers/{c.id}", json={"status": "churned"}, headers=headers()).status_code == 200
    assert calls == [("churn_risk", "churned")]
    client.put(f"/customers/{c.id}", json={"status": "churned"}, headers=headers())  # unchanged: no sync
    client.put(f"/customers/{c.id}", json={"address": "x"}, headers=headers())  # not a status change
    assert len(calls) == 1


def test_detect_sync_event_uses_old_status():
    from services.crm.routes.customers import _detect_sync_event
    from services.crm.schemas import CustomerUpdate

    assert _detect_sync_event(CustomerUpdate(status="suspended"), "active") == "churn_risk"
    assert _detect_sync_event(CustomerUpdate(status="active"), "suspended") == "status_change"
    assert _detect_sync_event(CustomerUpdate(status="active"), "active") is None
    assert _detect_sync_event(CustomerUpdate(address="x"), "active") is None


def test_sync_payload_has_no_id_number_and_failures_are_logged(monkeypatch, caplog):
    import services.common.http_client as hc
    from services.crm.routes import customers as cr

    sent = {}

    async def fake_post(service, path, **kw):
        sent.update(kw["json"])

    monkeypatch.setattr(hc, "service_post", fake_post)

    class S:
        async def execute(self, stmt):
            class R:
                def scalar(self):
                    return 0

                def all(self):
                    return []
            return R()

    c = Customer(id=uuid.uuid4(), tenant_id=TENANT_A, first_name="A", last_name="B", email="a@b.co",
                 id_number=VALID_ID, account_number="X", status="active")
    asyncio.run(cr._sync_customer_to_journey_engine(S(), c, "status_change"))
    assert "id_number" not in sent["snapshot_data"] and sent["customer_id"] == str(c.id)

    async def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(hc, "service_post", boom)
    with caplog.at_level("WARNING"):
        asyncio.run(cr._sync_customer_to_journey_engine(S(), c, "status_change"))
    assert any("journey-engine sync failed" in r.message and str(c.id) in r.message for r in caplog.records)
