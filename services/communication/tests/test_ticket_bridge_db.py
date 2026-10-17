"""The communication side of the ticket desk against a real Postgres (TEST_DATABASE_URL, name ends in _test):
tasks / escalations / schedule items created for a ticket, and requester emails sent for a ticket update.
The mail provider is stubbed.

    python -m pytest services/communication/tests/test_ticket_bridge_db.py -q
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.common import testdb  # noqa: E402

testdb.use_test_database()
os.environ["LICENSE_ENFORCEMENT"] = "warn"

import pytest  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from services.common import ticket_events as E  # noqa: E402
from services.common.db import session_scope  # noqa: E402
from services.communication import ticket_bridge as bridge  # noqa: E402
from services.communication.database import get_session  # noqa: E402
from services.communication.models import Channel, Escalation, ScheduleEvent, Task  # noqa: E402


def run(coro):
    testdb.reset_engines()
    try:
        return asyncio.run(coro)
    finally:
        testdb.reset_engines()


def outcome_event(tenant, ticket_id, outcome, **payload):
    return {"id": str(uuid.uuid4()), "tenant_id": str(tenant), "type": E.EVENT_OUTCOME_REQUESTED,
            "payload": {"ticket_id": str(ticket_id), "outcome": outcome, "title": "Router keeps dropping",
                        "description": "Customer reports drops", "priority": "HIGH", **payload}}


async def count(model, tenant):
    async with get_session() as s:
        return len((await s.execute(select(model).where(model.tenant_id == tenant))).scalars().all())


def test_each_outcome_creates_its_item_once_in_a_shared_tickets_channel():
    tenant = testdb.new_tenant()
    me, assignee = testdb.new_user(tenant), testdb.new_user(tenant)
    tid = uuid.uuid4()

    async def go():
        made = []
        for outcome in ("task", "escalation", "schedule"):
            made.append(await bridge.create_outcome(outcome_event(tenant, tid, outcome, assigned_to=str(assignee))))
        again = [await bridge.create_outcome(outcome_event(tenant, tid, o, assigned_to=str(assignee))) for o in ("task", "escalation", "schedule")]
        async with get_session() as s:
            channels = (await s.execute(select(Channel).where(Channel.tenant_id == tenant))).scalars().all()
            task = (await s.execute(select(Task).where(Task.tenant_id == tenant))).scalar_one()
            esc = (await s.execute(select(Escalation).where(Escalation.tenant_id == tenant))).scalar_one()
            sched = (await s.execute(select(ScheduleEvent).where(ScheduleEvent.tenant_id == tenant))).scalar_one()
        return made, again, channels, task, esc, sched
    made, again, channels, task, esc, sched = run(go())

    assert made == ["task", "escalation", "schedule"] and again == [None, None, None]     # redelivery creates nothing new
    assert [c.name for c in channels] == ["Tickets"] and channels[0].is_private is False
    assert task.title.startswith("Ticket: Router keeps dropping") and task.assignee_id == assignee and f"ticket:{tid}" in task.description
    assert task.channel_id == esc.channel_id == sched.channel_id == channels[0].id
    due_in = (task.due_date - datetime.now(timezone.utc)).total_seconds() / 3600
    assert 7 < due_in < 9                                                                  # HIGH priority: due in 8h
    assert esc.ticket_id == str(tid) and esc.assigned_to == assignee and esc.status == "open"
    assert sched.type == "follow_up" and sched.user_id == assignee and sched.end_time - sched.start_time == timedelta(minutes=30)
    assert 1.5 < (sched.start_time - datetime.now(timezone.utc)).total_seconds() / 3600 < 2.5   # HIGH: follow up in 2h


def test_without_an_assignee_the_item_is_attributed_to_a_workspace_member():
    tenant = testdb.new_tenant()
    member = testdb.new_user(tenant)
    run(bridge.create_outcome(outcome_event(tenant, uuid.uuid4(), "task")))

    async def read():
        async with get_session() as s:
            return (await s.execute(select(Task).where(Task.tenant_id == tenant))).scalar_one()
    task = run(read())
    assert task.created_by == member and task.assignee_id is None


def test_an_unknown_outcome_or_an_empty_workspace_creates_nothing():
    tenant = testdb.new_tenant()                                  # no users at all
    assert run(bridge.create_outcome(outcome_event(tenant, uuid.uuid4(), "task"))) is None
    testdb.new_user(tenant)
    assert run(bridge.create_outcome(outcome_event(tenant, uuid.uuid4(), "pager"))) is None
    assert run(bridge.create_outcome(outcome_event(tenant, "", "task"))) is None
    assert run(count(Task, tenant)) == 0 and run(count(Channel, tenant)) == 0


def test_items_are_never_created_in_another_tenants_channel():
    t1, t2 = testdb.new_tenant(), testdb.new_tenant()
    testdb.new_user(t1), testdb.new_user(t2)
    run(bridge.create_outcome(outcome_event(t1, uuid.uuid4(), "task")))
    run(bridge.create_outcome(outcome_event(t2, uuid.uuid4(), "task")))
    assert run(count(Task, t1)) == 1 and run(count(Task, t2)) == 1
    assert run(count(Channel, t1)) == 1 and run(count(Channel, t2)) == 1


# ── requester emails ────────────────────────────────────────────────────────

def update_event(tenant, **payload):
    base = {"ticket_id": str(uuid.uuid4()), "ticket_ref": "T-12", "channel": "email", "reply_ref": "thread-1", "trigger": "assigned",
            "subject": "Re: Router keeps dropping [T-12]", "body": "Your request T-12 has been picked up.", "event_id": str(uuid.uuid4())}
    base.update(payload)
    return {"id": str(uuid.uuid4()), "tenant_id": str(tenant), "type": E.EVENT_CUSTOMER_UPDATE, "payload": base}


@pytest.fixture()
def mail_stub(monkeypatch):
    """Stub the thread lookup and the provider; `sent` records every outbound email."""
    from services.communication.routes import mail as M
    state = SimpleNamespace(sent=[], inbound=SimpleNamespace(
        sender="Ann Customer <ann@example.com>", mailbox_id=uuid.uuid4(), message_id="<m1@example.com>", subject="Router keeps dropping",
        headers={"thread_id": "prov-1"}), already=False, thread={"id": "x", "provider_thread_id": "prov-1"}, status="sent")

    async def resolve(session, tenant_id, ref):
        return state.thread

    async def last_inbound(session, tenant_id, thread):
        return state.inbound

    async def already(session, tenant_id, event_id):
        return state.already

    async def deliver(tenant_id, mailbox_id, to, cc, bcc, subject, body, html, reply_to, **kw):
        state.sent.append({"to": to, "subject": subject, "body": body, "reply_to": reply_to, **kw})
        return SimpleNamespace(status=state.status)

    monkeypatch.setattr(bridge, "_resolve_thread", resolve)
    monkeypatch.setattr(bridge, "_last_inbound", last_inbound)
    monkeypatch.setattr(bridge, "_already_sent", already)
    monkeypatch.setattr(M, "_deliver_and_store", deliver)
    return state


def test_the_requester_gets_one_email_in_their_thread(mail_stub):
    tenant = testdb.new_tenant()
    ev = update_event(tenant)
    run(bridge.deliver_customer_update(ev))
    [mail] = mail_stub.sent
    assert mail["to"] == ["ann@example.com"] and mail["subject"] == "Re: Router keeps dropping [T-12]"
    assert mail["body"] == "Your request T-12 has been picked up." and mail["reply_to"] == "<m1@example.com>"
    assert mail["thread_id"] == "prov-1"
    assert mail["extra_headers"]["ticket_update_event"] == ev["payload"]["event_id"] and mail["extra_headers"]["ticket_ref"] == "T-12"
    assert mail["actor"]["kind"] == "system"


def test_a_redelivered_event_does_not_send_twice(mail_stub):
    mail_stub.already = True
    run(bridge.deliver_customer_update(update_event(testdb.new_tenant())))
    assert mail_stub.sent == []


@pytest.mark.parametrize("change", [
    {"channel": "call"}, {"reply_ref": ""}, {"body": ""}, {"body": "your password is hunter2 and api_key=sk-abcdefghijklmnopqrstuvwxyz0123456789"},
])
def test_nothing_is_sent_for_other_channels_empty_or_secret_text(mail_stub, change):
    run(bridge.deliver_customer_update(update_event(testdb.new_tenant(), **change)))
    assert mail_stub.sent == []


def test_nothing_is_sent_to_an_auto_responder_or_a_missing_thread(mail_stub):
    mail_stub.inbound.sender = "No Reply <no-reply@example.com>"
    run(bridge.deliver_customer_update(update_event(testdb.new_tenant())))
    mail_stub.inbound.sender = "Ann <ann@example.com>"
    mail_stub.thread = None
    run(bridge.deliver_customer_update(update_event(testdb.new_tenant())))
    assert mail_stub.sent == []


def test_a_provider_failure_raises_so_the_bus_retries(mail_stub):
    mail_stub.status = "failed"
    with pytest.raises(RuntimeError):
        run(bridge.deliver_customer_update(update_event(testdb.new_tenant())))
