"""Unified ticketing against a real Postgres (TEST_DATABASE_URL, database name must end in _test).

Dedupe under concurrency, repeat comments and escalation, closed-then-recurs, the event consumer end to
end, tenant isolation, and the desk API (create / search / comment / assign / close / reopen / rules).

    TEST_DATABASE_URL=postgresql://…/omnidome_test
    python -m pytest services/support/tests/test_ticketing_db.py -q
"""
import asyncio
import os
import sys
import types
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.common import testdb  # noqa: E402

testdb.use_test_database()
os.environ["SUPPORT_ENFORCE_ROLES"] = "false"
os.environ["SUPPORT_VERIFY_CUSTOMER"] = "false"
os.environ["LICENSE_ENFORCEMENT"] = "warn"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from services.common import event_bus  # noqa: E402
from services.common.db import session_scope  # noqa: E402
from services.support import consumer as ticket_consumer, database, ticket_rules, ticketing  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def schema():
    async def go():
        async with session_scope() as s:
            await event_bus.ensure_schema(s)
        await database.init_tables()
    testdb.reset_engines()
    asyncio.run(go())
    testdb.reset_engines()


def spec(key="k1", **kw):
    base = dict(source="system_error", event_type="system.error.raised", subject="[x] Boom", description="d", category="SYSTEM",
                priority="NORMAL", queue="platform", dedupe_key=key, ref_type="error_fingerprint", ref_id="f", repeat_comment="again")
    base.update(kw)
    return ticket_rules.TicketSpec(**base)


async def rows(tenant, key=None):
    async with session_scope() as s:
        q = "SELECT * FROM tickets WHERE tenant_id = :t" + (" AND dedupe_key = :k" if key else "") + " ORDER BY created_at"
        return [dict(r) for r in (await s.execute(text(q), {"t": str(tenant), "k": key})).mappings().all()]


async def timeline(ticket_id):
    async with session_scope() as s:
        return [dict(r) for r in (await s.execute(text(
            "SELECT kind, message, is_private FROM ticket_replies WHERE ticket_id = :i ORDER BY created_at"), {"i": ticket_id})).mappings().all()]


def run(coro):
    testdb.reset_engines()
    try:
        return asyncio.run(coro)
    finally:
        testdb.reset_engines()


def test_repeat_folds_into_one_open_ticket_with_capped_comments():
    tenant = testdb.new_tenant()

    async def go():
        first = None
        for i in range(25):
            async with session_scope() as s:
                res = await ticketing.raise_ticket(s, tenant, spec())
            first = first or res
            assert res.ticket_id == first.ticket_id
        return first
    first = run(go())
    assert first.created
    [t] = run(rows(tenant))
    assert t["occurrence_count"] == 25 and t["status"] == "OPEN" and t["source"] == "system_error"
    assert t["sla_due_at"] is not None and t["ticket_no"]
    notes = run(timeline(t["id"]))
    repeats = [n for n in notes if n["message"].startswith("again")]
    # occurrences 2..5, then every 10th (10, 20): 6 comments, not 24
    assert len(repeats) == 6
    assert t["priority"] == "HIGH"       # escalated at 10 occurrences
    assert any("Priority raised" in n["message"] for n in notes)


def test_concurrent_events_create_exactly_one_ticket():
    tenant = testdb.new_tenant()

    async def one():
        async with session_scope() as s:
            return await ticketing.raise_ticket(s, tenant, spec("race"))

    async def go():
        return await asyncio.gather(*[one() for _ in range(8)])
    results = run(go())
    assert sum(1 for r in results if r.created) == 1
    [t] = run(rows(tenant, "race"))
    assert t["occurrence_count"] == 8


def test_closed_ticket_is_not_reopened_by_a_recurrence():
    tenant = testdb.new_tenant()

    async def go():
        async with session_scope() as s:
            a = await ticketing.raise_ticket(s, tenant, spec("again"))
        async with session_scope() as s:
            await s.execute(text("UPDATE tickets SET status='CLOSED', resolved_at=now() WHERE id=:i"), {"i": a.ticket_id})
        async with session_scope() as s:
            b = await ticketing.raise_ticket(s, tenant, spec("again"))
        return a, b
    a, b = run(go())
    assert b.created and b.ticket_id != a.ticket_id
    both = run(rows(tenant, "again"))
    assert [r["status"] for r in both] == ["CLOSED", "OPEN"]
    assert both[1]["context"]["previous_ticket_id"] == str(a.ticket_id)


def test_comment_only_adds_to_the_open_ticket_or_does_nothing():
    tenant = testdb.new_tenant()

    async def go():
        async with session_scope() as s:
            none = await ticketing.raise_ticket(s, tenant, spec("c1", comment_only=True, repeat_comment="back online"))
        async with session_scope() as s:
            a = await ticketing.raise_ticket(s, tenant, spec("c1"))
        async with session_scope() as s:
            c = await ticketing.raise_ticket(s, tenant, spec("c1", comment_only=True, repeat_comment="back online"))
        return none, a, c
    none, a, c = run(go())
    assert none.skipped and c.commented and c.ticket_id == a.ticket_id
    assert any(n["message"] == "back online" for n in run(timeline(a.ticket_id)))
    [t] = run(rows(tenant, "c1"))
    assert t["occurrence_count"] == 1


def test_tenants_never_share_a_dedupe_key():
    t1, t2 = testdb.new_tenant(), testdb.new_tenant()

    async def go():
        async with session_scope() as s:
            a = await ticketing.raise_ticket(s, t1, spec("same"))
        async with session_scope() as s:
            b = await ticketing.raise_ticket(s, t2, spec("same"))
        return a, b
    a, b = run(go())
    assert a.created and b.created and a.ticket_id != b.ticket_id


def test_text_is_redacted_on_the_way_in():
    tenant = testdb.new_tenant()

    async def go():
        async with session_scope() as s:
            return await ticketing.raise_ticket(s, tenant, spec(
                "pii", subject="Failed for jane@example.com", description="password=hunter2hunter2 call 0821234567",
                context={"api_key": "abc", "note": "id 8001015009087"}))
    run(go())
    [t] = run(rows(tenant, "pii"))
    blob = t["subject"] + t["description"] + repr(t["context"])
    for leak in ("jane@example.com", "hunter2hunter2", "0821234567", "8001015009087", "'abc'"):
        assert leak not in blob


def test_consumer_turns_events_into_tickets_per_tenant_rules():
    tenant = testdb.new_tenant()
    home = str(uuid.uuid4())

    def event(type_, payload):
        return {"id": str(uuid.uuid4()), "tenant_id": str(tenant), "type": type_, "source": "t", "payload": payload,
                "subject_type": None, "subject_id": None}

    async def go():
        await ticket_consumer.handle_event(event("iot.home.offline", {"home_id": home}))
        await ticket_consumer.handle_event(event("iot.home.offline", {"home_id": home}))
        await ticket_consumer.handle_event(event("iot.home.recovered", {"home_id": home}))
        await ticket_consumer.handle_event(event("system.health.checked", {}))            # noise
        await ticket_consumer.handle_event(event("sales.lead.created", {}))               # unmapped
        # tenant turns finance failures off
        async with session_scope() as s:
            await s.execute(text("INSERT INTO ticket_rule_overrides (tenant_id, rule_key, enabled) VALUES (:t, 'finance.payment.failed', false)"),
                            {"t": str(tenant)})
        await ticket_consumer.handle_event(event("finance.payment.failed", {"invoice_id": "i1"}))
        # and re-prioritises reconciliation
        async with session_scope() as s:
            await s.execute(text("INSERT INTO ticket_rule_overrides (tenant_id, rule_key, priority, queue) VALUES (:t, 'finance.reconciliation.exception', 'URGENT', 'calls')"),
                            {"t": str(tenant)})
        await ticket_consumer.handle_event(event("finance.reconciliation.exception", {"statement_ref": "b1"}))
    run(go())
    all_rows = run(rows(tenant))
    by_src = {r["event_type"]: r for r in all_rows}
    assert set(by_src) == {"iot.home.offline", "finance.reconciliation.exception"}
    off = by_src["iot.home.offline"]
    assert off["occurrence_count"] == 2 and off["source_ref_id"] == home and off["category"] == "HOMEDOME"
    assert off["source_link"] == "/dashboard/home-dome"
    assert any("back online" in n["message"] for n in run(timeline(off["id"])))
    rec = by_src["finance.reconciliation.exception"]
    assert (rec["priority"], rec["queue"]) == ("URGENT", "calls")


def test_ticket_events_reach_the_bus_for_automations_and_the_bell():
    tenant = testdb.new_tenant()

    async def go():
        async with session_scope() as s:
            await ticketing.raise_ticket(s, tenant, spec("bus", priority="HIGH"))
        async with session_scope() as s:
            await ticketing.raise_ticket(s, tenant, spec("bus", priority="HIGH"))
        async with session_scope() as s:
            ev = (await s.execute(text("SELECT event_type, count(*) c FROM domain_events WHERE tenant_id=:t GROUP BY 1"), {"t": str(tenant)})).all()
            n = (await s.execute(text("SELECT count(*) FROM notifications WHERE tenant_id=:t AND category='support'"), {"t": str(tenant)})).scalar()
        return dict(ev), n
    events, notified = run(go())
    assert events == {"support.ticket.created": 1, "support.ticket.repeated": 1}
    assert notified == 1                 # one bell item for the new HIGH ticket, not one per repeat


# ── desk API ────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(monkeypatch):
    from services.support import main
    async def allow(request, call_next):         # module entitlements have their own tests
        return await call_next(request)

    monkeypatch.setattr(main.guard, "middleware", allow)
    monkeypatch.setattr(main.ticket_consumer.consumer, "start", lambda: asyncio.get_event_loop().create_future())
    testdb.reset_engines()
    database._session_factory = None             # the cached session factory is bound to the previous test's engine/loop
    with TestClient(main.app) as c:
        yield c
    testdb.reset_engines()
    database._session_factory = None


def test_desk_create_search_comment_assign_close_reopen(client):
    tenant = testdb.new_tenant()
    me, other = testdb.new_user(tenant), testdb.new_user(tenant)
    H = testdb.headers(tenant, me)

    r = client.post("/tickets", headers=H, json={"subject": "Router keeps rebooting", "description": "since Monday",
                                                 "category": "technical", "priority": "high", "source": "manual", "queue": "technical"})
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["status"] == "OPEN" and t["priority"] == "HIGH" and t["category"] == "TECHNICAL" and t["customer_id"] is None
    assert t["ticket_ref"].startswith("T-") and t["sla_state"] == "ok" and t["source"] == "manual"
    tid = t["id"]

    assert client.post("/tickets", headers=H, json={"subject": "x", "priority": "bogus"}).status_code == 422
    assert client.post("/tickets", headers=H, json={"subject": "x", "assigned_to": str(uuid.uuid4())}).status_code == 422

    s = client.get("/tickets/search", headers=H, params={"q": "rebooting"}).json()
    assert s["total"] == 1 and s["items"][0]["id"] == tid
    assert client.get("/tickets/search", headers=H, params={"q": t["ticket_ref"]}).json()["total"] == 1
    assert client.get("/tickets/search", headers=H, params={"assigned": "unassigned"}).json()["total"] == 1
    assert client.get("/tickets/search", headers=H, params={"status": "CLOSED"}).json()["total"] == 0

    c = client.post(f"/tickets/{tid}/comments", headers=H, json={"message": "Called the customer on 0821234567"})
    assert c.status_code == 201 and "0821234567" not in c.json()["message"]
    assert client.post(f"/tickets/{tid}/comments", headers=H, json={"message": "internal", "is_private": True}).status_code == 201

    a = client.post(f"/tickets/{tid}/assign", headers=H, json={"assigned_to": str(other)})
    assert a.status_code == 200 and a.json()["assigned_to"] == str(other) and a.json()["status"] == "IN_PROGRESS"
    assert client.get("/tickets/search", headers=H, params={"assigned": str(other)}).json()["total"] == 1
    assert client.post(f"/tickets/{tid}/assign", headers=H, json={"assigned_to": str(uuid.uuid4())}).status_code == 422

    done = client.put(f"/tickets/{tid}", headers=H, json={"status": "CLOSED", "note": "Replaced the PSU"})
    assert done.status_code == 200 and done.json()["status"] == "CLOSED" and done.json()["resolved_at"]
    assert done.json()["sla_state"] in {"met", "missed"}
    assert client.get("/tickets/search", headers=H, params={"open_only": True}).json()["total"] == 0

    back = client.put(f"/tickets/{tid}", headers=H, json={"status": "REOPENED"})
    assert back.status_code == 200 and back.json()["status"] == "OPEN" and back.json()["resolved_at"] is None
    assert client.put(f"/tickets/{tid}", headers=H, json={}).status_code == 422
    assert client.put(f"/tickets/{tid}", headers=H, json={"status": "NOPE"}).status_code == 422

    detail = client.get(f"/tickets/{tid}", headers=H).json()
    kinds = [e["kind"] for e in detail["timeline"]]
    assert kinds.count("comment") == 2 and "assignment" in kinds and kinds.count("status") >= 2
    assert detail["first_response_at"]                       # first public comment recorded it

    summary = client.get("/tickets/summary", headers=H).json()
    assert summary["open"] == 1 and summary["total"] == 1

    # another tenant sees nothing and cannot touch it
    H2 = testdb.headers(testdb.new_tenant())
    assert client.get(f"/tickets/{tid}", headers=H2).status_code == 404
    assert client.put(f"/tickets/{tid}", headers=H2, json={"status": "CLOSED"}).status_code == 404
    assert client.get("/tickets/search", headers=H2).json()["total"] == 0


def test_desk_rules_api_and_system_ticket_visible(client):
    tenant = testdb.new_tenant()
    me = testdb.new_user(tenant)
    H = testdb.headers(tenant, me)

    rid = uuid.uuid4()
    with testdb.sync_engine().begin() as conn:      # a system-raised ticket: no customer, source system_error
        conn.execute(text("INSERT INTO tickets (id, tenant_id, subject, status, priority, category, source, dedupe_key, occurrence_count) "
                          "VALUES (:i, :t, '[billing] KeyError in create_invoice', 'OPEN', 'NORMAL', 'SYSTEM', 'system_error', 'sys:abc', 1)"),
                     {"i": rid, "t": tenant})
    res = types.SimpleNamespace(ticket_id=rid)
    listed = client.get("/tickets/search", headers=H, params={"source": "system_error"}).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == str(res.ticket_id)
    assert listed["items"][0]["customer_id"] is None and listed["items"][0]["occurrence_count"] == 1

    rules = client.get("/ticket-rules", headers=H).json()["rules"]
    assert {r["key"] for r in rules} == set(ticket_rules.RULES)
    off = client.put("/ticket-rules/iot.home.offline", headers=H, json={"priority": "urgent", "enabled": False})
    assert off.status_code == 200 and off.json()["priority"] == "URGENT" and off.json()["enabled"] is False
    assert client.put("/ticket-rules/nope.nothing", headers=H, json={"enabled": False}).status_code == 404
    assert client.put("/ticket-rules/iot.home.offline", headers=H, json={"queue": "bogus"}).status_code == 422
    reset = client.put("/ticket-rules/iot.home.offline", headers=H, json={"reset": True}).json()
    assert reset["overridden"] is False and reset["enabled"] is True and reset["priority"] == "HIGH"
    # rules are per tenant
    other = {r["key"]: r for r in client.get("/ticket-rules", headers=testdb.headers(testdb.new_tenant())).json()["rules"]}
    assert other["iot.home.offline"]["overridden"] is False


def test_legacy_routes_still_work(client):
    tenant = testdb.new_tenant()
    me = testdb.new_user(tenant)
    H = testdb.headers(tenant, me)
    tid = client.post("/tickets", headers=H, json={"subject": "Legacy flow"}).json()["id"]
    assert isinstance(client.get("/tickets", headers=H).json(), list)
    assert client.post(f"/tickets/{tid}/accept", headers=H).json()["status"] == "ACCEPTED"
    assert client.post(f"/tickets/{tid}/resolve", headers=H, json={"resolution_notes": "fixed", "fcr": True}).json()["status"] == "CLOSED"
    assert client.get(f"/tickets/{tid}", headers=H).json()["status"] == "CLOSED"
    assert client.get("/tickets/meta", headers=H).json()["queues"]
