"""The ticket sources against a real Postgres (TEST_DATABASE_URL, name ends in _test): the cards and the desk digest
the indexer builds from the support service's tables, including the fallbacks for an older schema.

    python -m pytest services/tenant_memory/knowledge/tests/test_ticket_cards_db.py -q
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO_ROOT)

from services.common import testdb  # noqa: E402

testdb.use_test_database()

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from services.common import event_bus  # noqa: E402
from services.common.db import session_scope  # noqa: E402
from services.support import database as support_db, lifecycle  # noqa: E402
from services.tenant_memory.knowledge.cards import sources  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def schema():
    async def go():
        async with session_scope() as s:
            await event_bus.ensure_schema(s)
        await support_db.init_tables()
    testdb.reset_engines()
    asyncio.run(go())
    testdb.reset_engines()


def run(coro):
    testdb.reset_engines()
    try:
        return asyncio.run(coro)
    finally:
        testdb.reset_engines()


async def seed(tenant, user):
    now = datetime.now(timezone.utc)
    h = lambda n: now - timedelta(hours=n)  # noqa: E731
    ids = {}
    async with session_scope() as s:
        await s.execute(text("UPDATE users SET full_name = 'Sipho Dlamini' WHERE id = :u"), {"u": str(user)})
        rows = [("late", "URGENT", "IN_PROGRESS", user, h(30), h(3), h(2), h(29)),
                ("idle", "NORMAL", "OPEN", None, h(40), now + timedelta(hours=20), h(30), None),
                ("fine", "NORMAL", "OPEN", user, h(2), now + timedelta(hours=20), h(1), h(1)),
                ("done", "NORMAL", "CLOSED", user, h(12), h(2), h(6), h(11))]
        for name, prio, status, owner, created, due, active, responded in rows:
            ids[name] = uuid.uuid4()
            await s.execute(text("""INSERT INTO tickets (id, tenant_id, subject, description, priority, status, category, queue, assigned_to, created_at, updated_at,
                    sla_due_at, last_activity_at, first_response_at, first_assigned_at, resolved_at, assignment_count, resolution_notes)
                VALUES (:id, :t, :s, 'desc', :p, :st, 'TECHNICAL', 'technical', :o, :c, :c, :due, :act, :resp, :resp,
                        :resolved, :assignments, :resolution)"""),
                {"id": ids[name], "t": str(tenant), "s": f"ticket {name}", "p": prio, "st": status, "o": owner, "c": created, "due": due,
                 "act": active, "resp": responded, "resolved": active if status == "CLOSED" else None,
                 "assignments": 0 if owner is None else 1, "resolution": "Replaced the PSU" if status == "CLOSED" else None})
        await lifecycle.insert_event(s, tenant, ids["late"], "created", to_value="OPEN", at=h(30), actor_type="system")
        await lifecycle.insert_event(s, tenant, ids["late"], "assigned", to_value=str(user), at=h(29), actor_id=user, actor_type="agent")
        await lifecycle.insert_event(s, tenant, ids["late"], "note_added", note="internal: customer is difficult", at=h(5), actor_id=user, actor_type="agent")
        await lifecycle.insert_event(s, tenant, ids["late"], "reply_sent", note="We are on it", visibility="public", at=h(4), actor_id=user, actor_type="agent")
        await s.execute(text("""INSERT INTO ticket_jev_decisions (id, tenant_id, ticket_id, stage, proposal, confidence, disposition, evaluated_by_jev)
            VALUES (:i, :t, :tk, 'review', '{"flagged": true}', '{}', 'flagged', true)"""), {"i": uuid.uuid4(), "t": str(tenant), "tk": ids["done"]})
    return ids


def test_ticket_cards_carry_assignee_deadline_and_lifecycle_but_not_internal_notes():
    tenant = testdb.new_tenant()
    user = testdb.new_user(tenant)
    ids = run(seed(tenant, user))

    async def go():
        async with session_scope() as s:
            return await sources.fetch_tickets(s, str(tenant), None, 50)
    page = run(go())
    cards = {c.source_id: c for c in page.cards}
    late = cards[str(ids["late"])].markdown
    assert "Assigned to: Sipho Dlamini" in late and "PAST DEADLINE when indexed" in late
    assert "assigned to a team member" in late and "customer-visible reply sent: We are on it" in late
    assert "internal note added" in late and "customer is difficult" not in late
    assert "Assigned to: nobody (unassigned)" in cards[str(ids["idle"])].markdown
    assert "PAST DEADLINE" not in cards[str(ids["fine"])].markdown and "PAST DEADLINE" not in cards[str(ids["done"])].markdown
    assert "Time to resolve" in cards[str(ids["done"])].markdown


def test_the_desk_digest_lists_late_tickets_and_the_team_workload():
    tenant = testdb.new_tenant()
    user = testdb.new_user(tenant)
    ids = run(seed(tenant, user))

    async def go():
        async with session_scope() as s:
            return await sources.fetch_ticket_digests(s, str(tenant), None, 10)
    page = run(go())
    [card] = page.cards
    md = card.markdown
    assert card.source_id == "desk" and "Open tickets: 3  |  Unassigned: 1  |  Escalated: 0" in md
    assert "Past their deadline: 1" in md and "stale): 2" in md                     # "late" is past deadline; "late" (URGENT, 2h) and "idle" (30h) are idle
    late_section = md.split("## Late or stale tickets, worst first")[1].split("##")[0]
    assert late_section.index("ticket late") < late_section.index("ticket idle") and "ticket fine" not in late_section
    assert f"[[ticket:{ids['late']}]]" in late_section and "past deadline" in late_section and "unassigned" in late_section
    assert "Sipho Dlamini: 2 open (1 past deadline), resolved 1 in 30 days" in md
    assert "ticket done" in md.split("possibly not properly resolved")[1]
    assert "Open: " in md.split("Average time spent in each stage")[1]


def test_a_tenant_with_no_tickets_gets_no_digest_and_digests_are_per_tenant():
    empty, other = testdb.new_tenant(), testdb.new_tenant()
    user = testdb.new_user(other)
    run(seed(other, user))

    async def go(t):
        async with session_scope() as s:
            return await sources.fetch_ticket_digests(s, str(t), None, 10)
    assert run(go(empty)).cards == []
    assert "ticket late" not in "".join(c.markdown for c in run(go(empty)).cards)
    assert len(run(go(other)).cards) == 1
