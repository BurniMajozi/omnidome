"""The ticket time dimension end to end against a real Postgres (TEST_DATABASE_URL, name must end in _test):
lifecycle events and counters, requester notifications, KPIs, deadline breaches, user-defined rules with
outcomes, and Jev routing / review / stage checks (Jev itself is stubbed).

    python -m pytest services/support/tests/test_ticket_lifecycle_db.py -q
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

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
from services.support import consumer as ticket_consumer, database, jev_ticket, kpi, lifecycle, ticket_rules, ticketing, watcher  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def schema():
    async def go():
        async with session_scope() as s:
            await event_bus.ensure_schema(s)
        await database.init_tables()
    testdb.reset_engines()
    asyncio.run(go())
    testdb.reset_engines()


@pytest.fixture()
def client(monkeypatch):
    from services.support import main

    async def allow(request, call_next):
        return await call_next(request)

    monkeypatch.setattr(main.guard, "middleware", allow)
    monkeypatch.setattr(main.ticket_consumer.consumer, "start", lambda: asyncio.get_event_loop().create_future())
    monkeypatch.setattr(main.watcher, "run_forever", lambda: asyncio.sleep(3600))
    testdb.reset_engines()
    database._session_factory = None
    with TestClient(main.app) as c:
        yield c
    testdb.reset_engines()
    database._session_factory = None


def run(coro):
    testdb.reset_engines()
    try:
        return asyncio.run(coro)
    finally:
        testdb.reset_engines()


async def fetch(sql, **params):
    async with session_scope() as s:
        return [dict(r) for r in (await s.execute(text(sql), params)).mappings().all()]


def types_of(events):
    return [e["event_type"] for e in events]


# ── lifecycle through the desk API ──────────────────────────────────────────

def test_every_step_of_working_a_ticket_is_logged_with_its_time(client):
    tenant = testdb.new_tenant()
    me, tech = testdb.new_user(tenant), testdb.new_user(tenant)
    H = testdb.headers(tenant, me)

    t = client.post("/tickets", headers=H, json={"subject": "No sync on the ONT", "priority": "normal", "queue": "support"}).json()
    tid = t["id"]
    assert t["first_response_at"] is None and t["assignment_count"] == 0 and t["overdue"] is False

    client.post(f"/tickets/{tid}/assign", headers=H, json={"assigned_to": str(tech)})
    client.put(f"/tickets/{tid}", headers=H, json={"priority": "HIGH", "note": "Customer is a home worker"})
    client.put(f"/tickets/{tid}", headers=H, json={"category": "TECHNICAL"})
    client.put(f"/tickets/{tid}", headers=H, json={"queue": "technical"})
    assert client.post(f"/tickets/{tid}/comments", headers=H, json={"message": "Checked the line", "is_private": True}).status_code == 201
    assert client.post(f"/tickets/{tid}/comments", headers=H, json={"message": "We found a fault on your line"}).status_code == 201
    client.post(f"/tickets/{tid}/assign", headers=H, json={"assigned_to": str(me)})
    client.put(f"/tickets/{tid}", headers=H, json={"status": "RESOLVED", "note": "Replaced the splitter"})
    client.put(f"/tickets/{tid}", headers=H, json={"status": "REOPENED"})

    events = client.get(f"/tickets/{tid}/events", headers=H).json()["items"]
    assert types_of(events) == ["created", "assigned", "status_changed", "modified", "modified", "transferred", "note_added",
                                "reply_sent", "reassigned", "resolved", "reopened"]
    by_type = {e["event_type"]: e for e in events}
    assert by_type["assigned"]["to_value"] == str(tech) and by_type["reassigned"]["from_value"] == str(tech)
    prio = [e for e in events if e["event_type"] == "modified"][0]
    assert (prio["from_value"], prio["to_value"], prio["data"]["field"], prio["note"]) == ("NORMAL", "HIGH", "priority", "Customer is a home worker")
    assert (by_type["transferred"]["from_value"], by_type["transferred"]["to_value"]) == ("support", "technical")
    assert by_type["note_added"]["visibility"] == "internal" and by_type["reply_sent"]["visibility"] == "public"
    assert by_type["resolved"]["note"] == "Replaced the splitter"
    assert all(e["created_at"] for e in events) and [e["created_at"] for e in events] == sorted(e["created_at"] for e in events)
    assert all(e["actor_name"] is not None for e in events if e["actor_type"] == "agent")

    d = client.get(f"/tickets/{tid}", headers=H).json()
    assert d["assignment_count"] == 2 and d["modification_count"] == 2 and d["transfer_count"] == 1 and d["reopen_count"] == 1
    assert d["first_assigned_at"] and d["first_response_at"] and d["last_activity_at"]
    assert d["hours_to_first_response"] is not None and d["hours_to_first_response"] >= 0
    assert [e["event_type"] for e in d["events"]] == types_of(events)


def test_first_response_is_a_persons_action_not_a_note_or_a_system_event(client):
    tenant = testdb.new_tenant()
    me = testdb.new_user(tenant)
    H = testdb.headers(tenant, me)
    tid = client.post("/tickets", headers=H, json={"subject": "Slow wifi"}).json()["id"]
    client.post(f"/tickets/{tid}/comments", headers=H, json={"message": "note to self", "is_private": True})
    assert client.get(f"/tickets/{tid}", headers=H).json()["first_response_at"] is None
    client.put(f"/tickets/{tid}", headers=H, json={"status": "IN_PROGRESS"})          # starting work is a response
    assert client.get(f"/tickets/{tid}", headers=H).json()["first_response_at"] is not None


def test_first_touch_resolution_is_set_on_close_only_when_nobody_else_touched_it(client):
    tenant = testdb.new_tenant()
    me, other = testdb.new_user(tenant), testdb.new_user(tenant)
    H = testdb.headers(tenant, me)
    one = client.post("/tickets", headers=H, json={"subject": "one touch"}).json()["id"]
    client.post(f"/tickets/{one}/assign", headers=H, json={"assigned_to": str(me)})
    assert client.put(f"/tickets/{one}", headers=H, json={"status": "CLOSED", "note": "done"}).json()["is_fcr"] is True
    two = client.post("/tickets", headers=H, json={"subject": "passed on"}).json()["id"]
    client.post(f"/tickets/{two}/assign", headers=H, json={"assigned_to": str(me)})
    client.post(f"/tickets/{two}/assign", headers=H, json={"assigned_to": str(other)})
    assert client.put(f"/tickets/{two}", headers=H, json={"status": "CLOSED", "note": "done"}).json()["is_fcr"] is False


# ── notifying the requester ─────────────────────────────────────────────────

def notified(events):
    return [e for e in events if e["event_type"] == "customer_notified"]


def test_the_requester_is_told_on_the_channel_they_used(client):
    tenant = testdb.new_tenant()
    me, tech = testdb.new_user(tenant), testdb.new_user(tenant)
    H = testdb.headers(tenant, me)
    tid = client.post("/tickets", headers=H, json={"subject": "Mail not syncing", "source": "email", "reply_ref": "thread-77"}).json()["id"]
    assert client.get(f"/tickets/{tid}", headers=H).json()["reply_channel"] == "email"

    client.post(f"/tickets/{tid}/assign", headers=H, json={"assigned_to": str(tech)})
    client.post(f"/tickets/{tid}/comments", headers=H, json={"message": "Internal only", "is_private": True})
    client.post(f"/tickets/{tid}/comments", headers=H, json={"message": "Please restart your router"})
    client.put(f"/tickets/{tid}", headers=H, json={"status": "RESOLVED", "note": "Router firmware updated"})

    sent = notified(client.get(f"/tickets/{tid}/events", headers=H).json()["items"])
    assert [(n["data"]["trigger"], n["data"]["delivery"], n["channel"]) for n in sent] == [
        ("assigned", "queued", "email"), ("note", "queued", "email"), ("resolved", "queued", "email")]
    assert all(n["visibility"] == "public" for n in sent)
    assert "Internal only" not in " ".join(n["note"] for n in sent)               # private notes never reach the requester
    assert "Please restart your router" in sent[1]["note"] and "firmware" in sent[2]["note"]

    bus = run(fetch("SELECT payload FROM domain_events WHERE tenant_id = :t AND event_type = 'support.ticket.customer_update' ORDER BY created_at",
                    t=str(tenant)))
    assert len(bus) == 3 and all(b["payload"]["reply_ref"] == "thread-77" and b["payload"]["channel"] == "email" for b in bus)
    assert bus[1]["payload"]["subject"].startswith("Re: Mail not syncing [T-")


def test_a_channel_with_no_outbound_path_is_recorded_not_faked(client):
    tenant = testdb.new_tenant()
    me, tech = testdb.new_user(tenant), testdb.new_user(tenant)
    H = testdb.headers(tenant, me)
    call = client.post("/tickets", headers=H, json={"subject": "Missed call", "source": "call_center"}).json()["id"]
    manual = client.post("/tickets", headers=H, json={"subject": "Walk-in"}).json()["id"]
    client.post(f"/tickets/{call}/assign", headers=H, json={"assigned_to": str(tech)})
    client.post(f"/tickets/{manual}/assign", headers=H, json={"assigned_to": str(tech)})
    assert notified(client.get(f"/tickets/{call}/events", headers=H).json()["items"])[0]["data"]["delivery"] == "no_outbound_path"
    assert notified(client.get(f"/tickets/{manual}/events", headers=H).json()["items"]) == []     # nobody to tell: nothing recorded
    assert run(fetch("SELECT 1 FROM domain_events WHERE tenant_id = :t AND event_type = 'support.ticket.customer_update'", t=str(tenant))) == []


def test_notifications_can_be_switched_off_and_bursts_are_throttled(client):
    tenant = testdb.new_tenant()
    me, tech = testdb.new_user(tenant), testdb.new_user(tenant)
    H = testdb.headers(tenant, me)
    tid = client.post("/tickets", headers=H, json={"subject": "Burst", "source": "email", "reply_ref": "t-1"}).json()["id"]
    for text_ in ("one", "two", "three"):
        client.post(f"/tickets/{tid}/comments", headers=H, json={"message": text_})
    assert len(notified(client.get(f"/tickets/{tid}/events", headers=H).json()["items"])) == 1       # one per trigger per 10 minutes

    assert client.get("/tickets/settings", headers=H).json()["notify_enabled"] is True
    s = client.put("/tickets/settings", headers=H, json={"notify_on_assigned": False})
    assert s.status_code == 200 and s.json()["notify_on_assigned"] is False and s.json()["notify_on_note"] is True
    client.post(f"/tickets/{tid}/assign", headers=H, json={"assigned_to": str(tech)})
    assert [n["data"]["trigger"] for n in notified(client.get(f"/tickets/{tid}/events", headers=H).json()["items"])] == ["note"]

    client.put("/tickets/settings", headers=H, json={"notify_enabled": False})
    client.put(f"/tickets/{tid}", headers=H, json={"status": "RESOLVED", "note": "fixed"})
    assert len(notified(client.get(f"/tickets/{tid}/events", headers=H).json()["items"])) == 1
    assert client.put("/tickets/settings", headers=H, json={"jev_routing_mode": "reckless"}).status_code == 422


# ── KPIs ────────────────────────────────────────────────────────────────────

def test_kpis_are_computed_from_the_timestamps_and_the_event_log():
    tenant = testdb.new_tenant()
    a, b = testdb.new_user(tenant), testdb.new_user(tenant)
    now = datetime.now(timezone.utc)

    def h(n):
        return now - timedelta(hours=n)

    async def go():
        async with session_scope() as s:
            async def add(created, *, responded=None, resolved=None, assignee=None, assignments=0, sla, status, events):
                tid = uuid.uuid4()
                await s.execute(text("""
                    INSERT INTO tickets (id, tenant_id, subject, priority, status, queue, category, created_at, updated_at,
                                         first_response_at, first_assigned_at, resolved_at, assigned_to, assignment_count, sla_due_at)
                    VALUES (:id, :t, 'k', 'NORMAL', :status, 'technical', 'TECHNICAL', :c, :c, :resp, :resp, :res, :a, :n, :sla)"""),
                    {"id": tid, "t": str(tenant), "status": status, "c": created, "resp": responded, "res": resolved, "a": assignee,
                     "n": assignments, "sla": sla})
                for etype, at, to in events:
                    await lifecycle.insert_event(s, tenant, tid, etype, to_value=to, at=at)
            await add(h(10), responded=h(9), resolved=h(6), assignee=a, assignments=1, sla=h(5), status="CLOSED",
                      events=[("created", h(10), "OPEN"), ("status_changed", h(9), "IN_PROGRESS"), ("resolved", h(6), "RESOLVED")])
            await add(h(8), responded=h(4), resolved=h(1), assignee=a, assignments=2, sla=h(2), status="CLOSED",
                      events=[("created", h(8), "OPEN"), ("status_changed", h(4), "IN_PROGRESS"), ("resolved", h(1), "RESOLVED")])
            await add(h(3), assignee=b, sla=now + timedelta(hours=5), status="OPEN", events=[("created", h(3), "OPEN")])
        async with session_scope() as s:
            return await kpi.compute(s, tenant, 30), await kpi.compute(s, tenant, 30, a)
    k, only_a = run(go())

    o = k["overall"]
    assert (o["opened"], o["resolved"], o["still_open"]) == (3, 2, 1)
    assert o["mean_hours_to_respond"] == 2.5                       # (1h + 4h) / 2; the unanswered ticket is not averaged in
    assert o["mean_hours_to_resolve"] == 5.5                       # (4h + 7h) / 2
    assert o["median_hours_to_resolve"] == 5.5
    assert o["first_touch_resolution_pct"] == 50.0                 # one of the two resolved had a single assignment
    assert o["sla_met_pct"] == 50.0                                # resolved 1h after its deadline vs 1h before
    assert k["now"]["open_now"] == 1 and k["now"]["unassigned_now"] == 0 and k["now"]["overdue_now"] == 0

    by = {r["id"]: r for r in k["by_assignee"]}
    assert by[str(a)]["resolved"] == 2 and by[str(a)]["mean_hours_to_resolve"] == 5.5 and by[str(a)]["first_touch_resolution_pct"] == 50.0
    assert by[str(b)]["resolved"] == 0 and by[str(b)]["mean_hours_to_resolve"] is None
    assert only_a["overall"]["opened"] == 2 and only_a["assignee"] == str(a)

    stages = {s["status"]: s for s in k["time_in_stage"]}
    assert stages["OPEN"]["avg_hours"] == pytest.approx(2.67, abs=0.02)         # 1h, 4h and the still-open 3h
    assert stages["IN_PROGRESS"]["avg_hours"] == pytest.approx(3.0, abs=0.02)
    assert [q["key"] for q in k["by_queue"]] == ["technical"] and k["by_queue"][0]["opened"] == 3


def test_late_tickets_lists_overdue_and_idle_ones_worst_first():
    tenant = testdb.new_tenant()
    now = datetime.now(timezone.utc)

    async def go():
        async with session_scope() as s:
            for subject, status, due, active in (("overdue", "IN_PROGRESS", now - timedelta(hours=3), now - timedelta(minutes=5)),
                                                 ("idle", "OPEN", now + timedelta(hours=20), now - timedelta(hours=30)),
                                                 ("fine", "OPEN", now + timedelta(hours=20), now - timedelta(minutes=5)),
                                                 ("done", "CLOSED", now - timedelta(hours=9), now - timedelta(hours=9))):
                await s.execute(text("""INSERT INTO tickets (id, tenant_id, subject, priority, status, created_at, updated_at, last_activity_at, sla_due_at)
                    VALUES (:id, :t, :s, 'NORMAL', :st, :c, :c, :act, :due)"""),
                    {"id": uuid.uuid4(), "t": str(tenant), "s": subject, "st": status, "c": now - timedelta(hours=40), "act": active, "due": due})
        async with session_scope() as s:
            return await kpi.late_tickets(s, tenant)
    late = run(go())
    assert [t["subject"] for t in late] == ["overdue", "idle"]
    assert late[0]["overdue"] and late[0]["hours_overdue"] >= 2.9 and not late[0]["stale"]
    assert late[1]["stale"] and not late[1]["overdue"] and late[1]["hours_idle"] >= 29


# ── deadline breaches ───────────────────────────────────────────────────────

def test_a_deadline_breach_is_logged_once_and_only_a_fresh_one_rings_the_bell():
    tenant = testdb.new_tenant()
    now = datetime.now(timezone.utc)

    async def go():
        async with session_scope() as s:
            ids = {}
            for name, due in (("fresh", now - timedelta(hours=1)), ("backlog", now - timedelta(days=3)), ("future", now + timedelta(hours=4))):
                ids[name] = uuid.uuid4()
                await s.execute(text("""INSERT INTO tickets (id, tenant_id, subject, priority, status, created_at, updated_at, sla_due_at)
                    VALUES (:id, :t, :s, 'HIGH', 'OPEN', :c, :c, :due)"""),
                    {"id": ids[name], "t": str(tenant), "s": name, "c": now - timedelta(days=4), "due": due})
        for _ in range(2):                                   # the second pass must find nothing new
            async with session_scope() as s:
                await watcher.log_breaches(s)
        return ids
    ids = run(go())
    logged = run(fetch("SELECT ticket_id::text AS t FROM ticket_events WHERE tenant_id = :t AND event_type = 'sla_breached'", t=str(tenant)))
    assert sorted(r["t"] for r in logged) == sorted([str(ids["fresh"]), str(ids["backlog"])])
    bus = run(fetch("SELECT subject_id FROM domain_events WHERE tenant_id = :t AND event_type = 'support.ticket.sla_breached'", t=str(tenant)))
    assert [b["subject_id"] for b in bus] == [str(ids["fresh"])]
    bell = run(fetch("SELECT 1 FROM notifications WHERE tenant_id = :t AND category = 'support'", t=str(tenant)))
    assert len(bell) == 1


# ── user-defined rules ──────────────────────────────────────────────────────

def test_a_tenant_can_add_a_rule_for_any_event_and_choose_what_it_creates(client):
    tenant = testdb.new_tenant()
    me, owner = testdb.new_user(tenant), testdb.new_user(tenant)
    H = testdb.headers(tenant, me)

    created = client.post("/ticket-automation", headers=H, json={
        "name": "Abandoned cart follow-up", "event_pattern": "Portal.Cart.Abandoned", "category": "sales", "priority": "high",
        "queue": "support", "source": "api", "outcome": "task", "assigned_to": str(owner),
        "title_template": "Cart abandoned by {customer.name}",
        "conditions": [{"field": "value", "op": "contains", "value": "fibre"}]})
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["event_pattern"] == "portal.cart.abandoned" and rule["category"] == "SALES" and rule["outcome"] == "task"
    assert client.get("/ticket-automation", headers=H).json()["rules"][0]["id"] == rule["id"]

    for bad, status in (({"event_pattern": "iot.home.offline"}, 422), ({"event_pattern": "support.ticket.created"}, 422),
                        ({"event_pattern": "*"}, 422), ({"outcome": "email_everyone"}, 422), ({"queue": "nowhere"}, 422),
                        ({"priority": "SEVERE"}, 422), ({"assigned_to": str(uuid.uuid4())}, 422)):
        r = client.post("/ticket-automation", headers=H, json={"name": "x", "event_pattern": "a.b.c", **bad})
        assert r.status_code == status, (bad, r.text)

    cat = client.get("/ticket-automation/events", headers=H).json()["events"]
    assert any(e["event"] == "portal.cart.abandoned" and not e["built_in"] for e in cat)
    assert any(e["event"] == "iot.home.offline" and e["built_in"] for e in cat)
    assert not any(e["event"].startswith("support.") for e in cat)

    sub = run(fetch("SELECT 1 FROM event_subscriptions WHERE consumer = :c AND event_pattern = 'portal.cart.abandoned'", c=ticket_consumer.CONSUMER_NAME))
    assert sub                                              # saving the rule subscribed the consumer

    def deliver(payload, subject_id="cart-1"):
        ev = {"id": str(uuid.uuid4()), "tenant_id": str(tenant), "type": "portal.cart.abandoned", "source": "portal",
              "subject_type": "cart", "subject_id": subject_id, "payload": payload}
        run(ticket_consumer.handle_event(ev))

    deliver({"value": "Fibre 100Mbps", "customer": {"name": "Ann"}})
    deliver({"value": "LTE router", "customer": {"name": "Bob"}}, "cart-2")           # condition not met: no ticket
    deliver({"value": "Fibre 100Mbps", "customer": {"name": "Ann"}})                  # a repeat joins the open ticket
    tickets = run(fetch("SELECT * FROM tickets WHERE tenant_id = :t", t=str(tenant)))
    assert len(tickets) == 1
    t = tickets[0]
    assert t["subject"] == "Cart abandoned by Ann" and t["category"] == "SALES" and t["priority"] == "HIGH"
    assert t["assigned_to"] == owner and t["occurrence_count"] == 2 and t["event_type"] == "portal.cart.abandoned"
    assert t["assignment_count"] == 1 and t["first_assigned_at"] is not None
    ev = types_of(run(fetch("SELECT event_type FROM ticket_events WHERE ticket_id = :i ORDER BY created_at", i=t["id"])))
    assert ev[:2] == ["created", "assigned"] and "repeated" in ev

    outcomes = run(fetch("SELECT payload FROM domain_events WHERE tenant_id = :t AND event_type = 'support.ticket.outcome_requested'", t=str(tenant)))
    assert len(outcomes) == 1 and outcomes[0]["payload"]["outcome"] == "task" and outcomes[0]["payload"]["assigned_to"] == str(owner)

    off = client.put(f"/ticket-automation/{rule['id']}", headers=H, json={"enabled": False})
    assert off.status_code == 200 and off.json()["enabled"] is False
    deliver({"value": "Fibre 100Mbps"}, "cart-3")
    assert len(run(fetch("SELECT 1 FROM tickets WHERE tenant_id = :t", t=str(tenant)))) == 1
    assert client.delete(f"/ticket-automation/{rule['id']}", headers=H).status_code == 204
    assert client.get("/ticket-automation", headers=H).json()["rules"] == []
    assert client.delete(f"/ticket-automation/{rule['id']}", headers=H).status_code == 404


def test_custom_rules_are_isolated_per_tenant(client):
    t1, t2 = testdb.new_tenant(), testdb.new_tenant()
    H1, H2 = testdb.headers(t1, testdb.new_user(t1)), testdb.headers(t2, testdb.new_user(t2))
    rid = client.post("/ticket-automation", headers=H1, json={"name": "mine", "event_pattern": "sales.lead.created"}).json()["id"]
    assert client.get("/ticket-automation", headers=H2).json()["rules"] == []
    assert client.put(f"/ticket-automation/{rid}", headers=H2, json={"enabled": False}).status_code == 404
    assert client.delete(f"/ticket-automation/{rid}", headers=H2).status_code == 404
    ev = {"id": str(uuid.uuid4()), "tenant_id": str(t2), "type": "sales.lead.created", "source": "sales", "subject_type": "lead",
          "subject_id": "l1", "payload": {"title": "New lead"}}
    run(ticket_consumer.handle_event(ev))
    assert run(fetch("SELECT 1 FROM tickets WHERE tenant_id = :t", t=str(t2))) == []        # t2 has no such rule


def test_a_built_in_rule_can_also_ask_for_an_outcome(client):
    tenant = testdb.new_tenant()
    H = testdb.headers(tenant, testdb.new_user(tenant))
    r = client.put("/ticket-rules/iot.home.offline", headers=H, json={"outcome": "escalation"})
    assert r.status_code == 200 and r.json()["outcome"] == "escalation"
    assert client.put("/ticket-rules/iot.home.offline", headers=H, json={"outcome": "pager"}).status_code == 422
    listed = {x["key"]: x for x in client.get("/ticket-rules", headers=H).json()["rules"]}
    assert listed["iot.home.offline"]["outcome"] == "escalation" and listed["email.received"]["outcome"] == "ticket"
    ev = {"id": str(uuid.uuid4()), "tenant_id": str(tenant), "type": "iot.home.offline", "source": "iot", "subject_type": "iot_home",
          "subject_id": "home-1", "payload": {"home_id": "home-1"}}
    run(ticket_consumer.handle_event(ev))
    out = run(fetch("SELECT payload FROM domain_events WHERE tenant_id = :t AND event_type = 'support.ticket.outcome_requested'", t=str(tenant)))
    assert [o["payload"]["outcome"] for o in out] == ["escalation"]


# ── Jev ─────────────────────────────────────────────────────────────────────

def stub_jev(monkeypatch, answers):
    """Replace the call to the orchestrator; `answers` maps the endpoint name to the JSON it returns."""
    calls = []

    async def fake(tenant_id, path, body):
        calls.append((path, body))
        return answers.get(path)
    monkeypatch.setattr(jev_ticket, "_ask", fake)
    return calls


async def new_ticket(tenant, **kw):
    spec = ticket_rules.TicketSpec(source="system_error", event_type="system.error.raised", subject="Fibre down for the whole street",
                                   description="Many customers report no light on the ONT", category="GENERAL", priority="NORMAL",
                                   queue="support", dedupe_key=f"jev-{uuid.uuid4()}", **kw)
    async with session_scope() as s:
        return (await ticketing.raise_ticket(s, tenant, spec)).ticket_id


async def set_mode(tenant, mode, review=True):
    async with session_scope() as s:
        await s.execute(text("""INSERT INTO ticket_settings (tenant_id, jev_routing_mode, jev_review_on_close) VALUES (:t, :m, :r)
            ON CONFLICT (tenant_id) DO UPDATE SET jev_routing_mode = :m, jev_review_on_close = :r"""), {"t": str(tenant), "m": mode, "r": review})


ROUTE = {"evaluated_by_jev": True, "reason": "ok",
         "proposal": {"queue": "technical", "category": "TECHNICAL", "priority": "URGENT", "outcome": "escalation"},
         "confidence": {"queue": 0.97, "category": 0.93, "priority": 0.72, "outcome": 0.4}}


def test_jev_in_suggest_mode_proposes_but_changes_nothing_until_a_person_applies(monkeypatch):
    tenant = testdb.new_tenant()
    user = testdb.new_user(tenant)
    calls = stub_jev(monkeypatch, {"route": ROUTE})

    async def go():
        await set_mode(tenant, "suggest")
        tid = await new_ticket(tenant)
        res = await jev_ticket.route_ticket(tenant, tid)
        async with session_scope() as s:
            row = (await s.execute(text("SELECT queue, category, priority FROM tickets WHERE id = :i"), {"i": tid})).one()
        return tid, res, tuple(row)
    tid, res, row = run(go())
    assert row == ("support", "GENERAL", "NORMAL")                      # untouched
    assert res["status"] == "routed" and res["applied"] == {}
    assert res["suggested"] == {"queue": "technical", "category": "TECHNICAL", "priority": "URGENT"}   # outcome (0.4) was dropped
    assert calls[0][0] == "route" and calls[0][1]["ticket"]["subject"].startswith("Fibre down")
    assert "customer" not in str(calls[0][1]).lower().replace("customers report", "")

    [decision] = run(fetch("SELECT * FROM ticket_jev_decisions WHERE ticket_id = :i", i=tid))
    assert decision["disposition"] == "suggested" and decision["stage"] == "route" and decision["evaluated_by_jev"]
    assert decision["confidence"]["queue"] == 0.97
    assert "jev_suggested" in types_of(run(fetch("SELECT event_type FROM ticket_events WHERE ticket_id = :i", i=tid)))

    async def accept():
        async with session_scope() as s:
            from services.support.database import Ticket
            from sqlalchemy import select
            ticket = (await s.execute(select(Ticket).where(Ticket.id == tid).with_for_update())).scalar_one()
            return await jev_ticket.apply_suggestion(s, tenant, ticket, decision["id"], user)
    assert sorted(run(accept())) == ["category", "priority", "queue"]
    after = run(fetch("SELECT queue, category, priority, sla_due_at, created_at, transfer_count, modification_count FROM tickets WHERE id = :i", i=tid))[0]
    assert (after["queue"], after["category"], after["priority"]) == ("technical", "TECHNICAL", "URGENT")
    assert after["sla_due_at"] - after["created_at"] == timedelta(hours=ticketing.SLA_HOURS["URGENT"])   # the deadline followed the priority
    assert after["transfer_count"] == 1 and after["modification_count"] == 2
    events = run(fetch("SELECT event_type, actor_type, actor_id FROM ticket_events WHERE ticket_id = :i AND event_type IN ('modified','transferred')", i=tid))
    assert events and all(e["actor_type"] == "agent" and e["actor_id"] == user for e in events)         # logged as the person who clicked
    assert run(fetch("SELECT disposition FROM ticket_jev_decisions WHERE id = :i", i=decision["id"]))[0]["disposition"] == "applied"

    async def again():
        async with session_scope() as s:
            from services.support.database import Ticket
            from sqlalchemy import select
            ticket = (await s.execute(select(Ticket).where(Ticket.id == tid))).scalar_one()
            return await jev_ticket.apply_suggestion(s, tenant, ticket, decision["id"], user)
    with pytest.raises(ValueError):
        run(again())                                                        # a decision can be taken once


def test_jev_in_auto_mode_applies_only_what_it_is_sure_of(monkeypatch):
    tenant = testdb.new_tenant()
    stub_jev(monkeypatch, {"route": ROUTE})

    async def go():
        await set_mode(tenant, "auto")
        tid = await new_ticket(tenant)
        res = await jev_ticket.route_ticket(tenant, tid)
        async with session_scope() as s:
            row = (await s.execute(text("SELECT queue, category, priority FROM tickets WHERE id = :i"), {"i": tid})).one()
        return tid, res, tuple(row)
    tid, res, row = run(go())
    assert res["applied"] == {"queue": "technical", "category": "TECHNICAL"} and res["suggested"] == {"priority": "URGENT"}
    assert row == ("technical", "TECHNICAL", "NORMAL")
    ev = run(fetch("SELECT event_type, actor_type FROM ticket_events WHERE ticket_id = :i AND actor_type = 'jev' ORDER BY created_at", i=tid))
    assert {"transferred", "modified", "jev_applied", "jev_suggested"} <= set(types_of(ev))


def test_jev_off_does_nothing_and_unavailable_jev_leaves_no_trace(monkeypatch):
    tenant = testdb.new_tenant()
    calls = stub_jev(monkeypatch, {"route": None})

    async def go():
        await set_mode(tenant, "off")
        tid = await new_ticket(tenant)
        off = await jev_ticket.route_ticket(tenant, tid)
        await set_mode(tenant, "suggest")
        down = await jev_ticket.route_ticket(tenant, tid)
        return tid, off, down
    tid, off, down = run(go())
    assert off == {"status": "off"} and calls and len(calls) == 1          # off never called Jev
    assert down["status"] == "unavailable"
    assert run(fetch("SELECT 1 FROM ticket_jev_decisions WHERE ticket_id = :i", i=tid)) == []


def test_asking_jev_by_hand_works_even_when_the_mode_is_off(monkeypatch):
    tenant = testdb.new_tenant()
    stub_jev(monkeypatch, {"route": ROUTE})

    async def go():
        await set_mode(tenant, "off")
        tid = await new_ticket(tenant)
        return await jev_ticket.route_ticket(tenant, tid, force=True)
    res = run(go())
    assert res["applied"] == {} and "queue" in res["suggested"]            # a manual ask is only ever a suggestion when mode is off


def test_jev_reviews_a_closed_ticket_and_flags_a_vague_resolution(monkeypatch):
    tenant = testdb.new_tenant()
    stub_jev(monkeypatch, {"review": {"evaluated_by_jev": True, "resolved_properly": 0.8, "resolution_specific": 0.1}})

    async def go():
        await set_mode(tenant, "suggest")
        tid = await new_ticket(tenant)
        async with session_scope() as s:
            await s.execute(text("UPDATE tickets SET status='CLOSED', resolved_at=now(), resolution_notes='fixed' WHERE id=:i"), {"i": tid})
        return tid, await jev_ticket.review_closed(tenant, tid)
    tid, res = run(go())
    assert res["status"] == "flagged"
    ev = run(fetch("SELECT to_value, note FROM ticket_events WHERE ticket_id = :i AND event_type = 'jev_review'", i=tid))
    assert ev[0]["to_value"] == "flagged"
    assert run(fetch("SELECT disposition FROM ticket_jev_decisions WHERE ticket_id = :i AND stage = 'review'", i=tid))[0]["disposition"] == "flagged"
    assert len(run(fetch("SELECT 1 FROM notifications WHERE tenant_id = :t", t=str(tenant)))) >= 1       # someone is told it may need another look


def test_jev_review_skips_tickets_without_a_resolution_note_and_respects_the_switch(monkeypatch):
    tenant = testdb.new_tenant()
    calls = stub_jev(monkeypatch, {"review": {"evaluated_by_jev": True, "resolved_properly": 0.9, "resolution_specific": 0.9}})

    async def go():
        await set_mode(tenant, "suggest")
        tid = await new_ticket(tenant)
        async with session_scope() as s:
            await s.execute(text("UPDATE tickets SET status='CLOSED', resolved_at=now() WHERE id=:i"), {"i": tid})
        no_note = await jev_ticket.review_closed(tenant, tid)
        async with session_scope() as s:
            await s.execute(text("UPDATE tickets SET resolution_notes='Replaced the faulty splitter and re-tested the line' WHERE id=:i"), {"i": tid})
        await set_mode(tenant, "suggest", review=False)
        switched_off = await jev_ticket.review_closed(tenant, tid)
        await set_mode(tenant, "suggest", review=True)
        passed = await jev_ticket.review_closed(tenant, tid)
        return no_note, switched_off, passed
    no_note, switched_off, passed = run(go())
    assert no_note["status"] == "skipped" and switched_off == {"status": "off"} and passed["status"] == "passed"
    assert len(calls) == 1


def test_a_late_ticket_is_escalated_by_jev_only_in_auto_mode_and_only_when_sure(monkeypatch):
    tenant = testdb.new_tenant()
    answers = {"stage": {"evaluated_by_jev": True, "should_escalate": 0.95}}
    calls = stub_jev(monkeypatch, answers)

    async def make(mode):
        await set_mode(tenant, mode)
        tid = await new_ticket(tenant)
        async with session_scope() as s:
            await s.execute(text("UPDATE tickets SET sla_due_at = now() - interval '5 hours', last_activity_at = now() - interval '9 hours' WHERE id=:i"), {"i": tid})
        return tid

    async def go():
        suggest_id = await make("suggest")
        s1 = await jev_ticket.check_stage(tenant, suggest_id, "suggest")
        auto_id = await make("auto")
        s2 = await jev_ticket.check_stage(tenant, auto_id, "auto")
        s3 = await jev_ticket.check_stage(tenant, auto_id, "auto")           # already escalated: nothing to do
        answers["stage"] = {"evaluated_by_jev": True, "should_escalate": 0.2}
        unsure_id = await make("auto")
        s4 = await jev_ticket.check_stage(tenant, unsure_id, "auto")
        return suggest_id, auto_id, unsure_id, (s1, s2, s3, s4)
    suggest_id, auto_id, unsure_id, outcome = run(go())
    assert outcome == ("suggest", "apply", "skipped", "ignore")
    status = {r["id"]: r["status"] for r in run(fetch("SELECT id, status FROM tickets WHERE tenant_id = :t", t=str(tenant)))}
    assert status[suggest_id] == "OPEN" and status[auto_id] == "ESCALATED" and status[unsure_id] == "OPEN"
    assert "escalated" in types_of(run(fetch("SELECT event_type FROM ticket_events WHERE ticket_id = :i", i=auto_id)))
    timing = [c[1]["timing"] for c in calls]
    assert timing[0]["hours_past_deadline"] >= 4.9 and timing[0]["hours_since_activity"] >= 8.9


def test_jev_is_not_asked_again_about_the_same_ticket_within_the_recheck_window(monkeypatch):
    tenant = testdb.new_tenant()
    calls = stub_jev(monkeypatch, {"stage": {"evaluated_by_jev": True, "should_escalate": 0.7}})

    async def go():
        await set_mode(tenant, "suggest")
        tid = await new_ticket(tenant)
        return [await jev_ticket.check_stage(tenant, tid, "suggest") for _ in range(3)]
    assert run(go()) == ["suggest", "skipped", "skipped"] and len(calls) == 1
