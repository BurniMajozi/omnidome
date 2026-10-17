"""Ticket cards and the ticket desk digest: what the knowledge base tells agents about how tickets are going.
No database; test_ticket_cards_db.py runs the same sources against Postgres."""
from datetime import datetime, timedelta, timezone

from services.tenant_memory.knowledge.cards import builders as B
from services.tenant_memory.knowledge.cards.base import stable_text

NOW = datetime.now(timezone.utc)


def h(n):
    return NOW - timedelta(hours=n)


def ticket(**kw):
    base = {"id": "t-1", "customer_id": None, "subject": "Router keeps dropping", "description": "Since Monday", "priority": "HIGH",
            "status": "IN_PROGRESS", "category": "TECHNICAL", "is_fcr": False, "created_at": h(30), "updated_at": h(1), "resolved_at": None,
            "ticket_no": 12, "source": "email", "queue": "technical", "occurrence_count": 1, "assigned_to": "u-1",
            "sla_due_at": NOW + timedelta(hours=6), "first_response_at": h(29), "first_assigned_at": h(29), "last_activity_at": h(2),
            "escalated_at": None, "assignment_count": 2, "modification_count": 1, "transfer_count": 1, "reopen_count": 0}
    base.update(kw)
    return base


def ev(et, hours_ago, **kw):
    return {"id": f"e-{et}-{hours_ago}", "event_type": et, "actor_type": "agent", "created_at": h(hours_ago), "visibility": "internal", **kw}


def test_card_says_who_has_it_when_it_is_due_and_how_it_has_been_handled():
    md = B.ticket_card(ticket(), [], NOW, [], "Sipho Dlamini").markdown
    assert "Assigned to: Sipho Dlamini" in md
    assert "Resolution deadline:" in md and "PAST DEADLINE" not in md
    assert "First response: 1.0 h after opening" in md
    assert "2 assignment(s), 1 queue transfer(s), 1 change(s), 0 reopen(s)" in md
    assert "Last activity:" in md


def test_an_overdue_unassigned_ticket_is_tagged_and_important():
    card = B.ticket_card(ticket(assigned_to=None, sla_due_at=h(3), first_response_at=None, priority="NORMAL"), [], NOW)
    assert "PAST DEADLINE when indexed" in card.markdown and "Assigned to: nobody (unassigned)" in card.markdown
    assert "First response: none yet" in card.markdown
    assert "overdue" in card.markdown.split("tags:")[1] and "unassigned" in card.markdown.split("tags:")[1]
    assert card.importance == B.IMPORTANCE["high"]                       # lateness lifts a NORMAL ticket
    assert B.ticket_card(ticket(priority="NORMAL"), [], NOW).importance == B.IMPORTANCE["normal"]


def test_a_closed_ticket_is_never_overdue_and_shows_its_time_to_resolve():
    md = B.ticket_card(ticket(status="CLOSED", sla_due_at=h(20), resolved_at=h(10)), [], NOW).markdown
    assert "PAST DEADLINE" not in md and "Time to resolve: 20.0 h" in md and "Last activity" not in md


def test_the_lifecycle_is_listed_but_internal_note_text_is_not():
    events = [ev("created", 30, to_value="OPEN", actor_type="system"),
              ev("assigned", 29), ev("modified", 20, from_value="NORMAL", to_value="HIGH"),
              ev("transferred", 10, from_value="support", to_value="technical"),
              ev("note_added", 5, note="Customer is rude, refund them R500 quietly", visibility="internal"),
              ev("reply_sent", 4, note="We found a fault on your line, call 0821234567", visibility="public"),
              ev("customer_notified", 4, channel="email", actor_type="system")]
    md = B.ticket_card(ticket(), [], NOW, events).markdown
    assert "## What has happened to this ticket (oldest first)" in md
    assert "opened as OPEN" in md and "assigned to a team member" in md and "changed NORMAL to HIGH" in md
    assert "moved queue support to technical" in md and "requester notified (email)" in md
    assert "internal note added" in md and "refund them" not in md and "rude" not in md          # internal text never indexed
    assert "We found a fault on your line" in md and "0821234567" not in md                       # public text, scrubbed
    assert md.index("opened as OPEN") < md.index("changed NORMAL to HIGH") < md.index("moved queue")


def test_only_the_last_twelve_events_are_kept():
    md = B.ticket_card(ticket(), [], NOW, [ev("modified", 40 - i, from_value=str(i), to_value=str(i + 1)) for i in range(20)]).markdown
    assert md.count("changed ") == 12 and "changed 19 to 20" in md and "changed 0 to 1" not in md


def test_jev_events_are_described_for_agents():
    md = B.ticket_card(ticket(), [], NOW, [ev("jev_suggested", 3, to_value="queue", actor_type="jev"),
                                           ev("jev_review", 2, to_value="flagged", actor_type="jev")]).markdown
    assert "Jev suggested queue" in md and "Jev review of the resolution: flagged" in md


def test_a_row_from_an_older_schema_still_renders_without_timing_lines():
    row = {k: v for k, v in ticket().items() if k in ("id", "customer_id", "subject", "description", "priority", "status", "category",
                                                         "is_fcr", "created_at", "updated_at", "resolved_at")}
    md = B.ticket_card(row, [], NOW).markdown
    assert "Ticket: Router keeps dropping" in md and "Resolution deadline" not in md and "Handling:" not in md


def test_the_card_is_deterministic_for_an_unchanged_ticket():
    events = [ev("created", 30, to_value="OPEN"), ev("assigned", 29)]
    a, b = B.ticket_card(ticket(), [], NOW, events, "Sipho").markdown, B.ticket_card(ticket(), [], NOW + timedelta(minutes=5), events, "Sipho").markdown
    assert stable_text(a) == stable_text(b)                      # a rebuild that changes only the timestamp is not re-embedded


# ── the desk digest ─────────────────────────────────────────────────────────

def digest_data(**kw):
    d = {"days": 30, "now": {"total": 40, "open": 9, "unassigned": 2, "escalated": 1, "overdue": 3, "stale": 4},
         "kpi": {"opened": 30, "resolved": 21, "still_open": 9, "mean_respond": 1.5, "mean_assign": 0.9, "mean_resolve": 26.4,
                 "first_touch": 14, "sla_judged": 20, "sla_met": 15},
         "stages": [{"status": "IN_PROGRESS", "avg_hours": 9.2, "tickets": 8}, {"status": "OPEN", "avg_hours": 2.5, "tickets": 12}],
         "queues": [{"queue": "technical", "open": 5, "overdue": 2, "unassigned": 1}],
         "people": [{"name": "Sipho Dlamini", "open": 4, "overdue": 1, "resolved": 12, "mean_resolve": 20.0}],
         "late": [{"id": "t-9", "ticket_no": 9, "subject": "Fibre down in Rosebank, call 0821234567", "priority": "URGENT", "status": "IN_PROGRESS",
                   "queue": "technical", "assignee": "Sipho Dlamini", "hours_overdue": 5, "hours_idle": 7},
                  {"id": "t-3", "ticket_no": 3, "subject": "Billing question", "priority": "LOW", "status": "OPEN", "queue": None,
                   "assignee": None, "hours_overdue": 0, "hours_idle": 40}],
         "flagged": [{"id": "t-5", "ticket_no": 5, "subject": "Replaced router"}]}
    d.update(kw)
    return d


def test_digest_answers_how_many_are_late_who_has_them_and_how_fast_the_team_is():
    card = B.ticket_digest(digest_data(), NOW)
    md = card.markdown
    assert card.source_type == "ticket_digest" and card.source_id == "desk" and card.module == "support"
    assert "Open tickets: 9  |  Unassigned: 2  |  Escalated: 1" in md and "Past their deadline: 3" in md and "stale): 4" in md
    assert "Mean time to first response: 1.5 h" in md and "to resolution: 26 h" in md
    assert "First-touch resolution: 66.7%" in md and "Resolved within deadline: 75.0%" in md
    assert "In Progress: 9.2 h (8 tickets)" in md
    assert "technical: 5 open, 2 past deadline, 1 unassigned" in md
    assert "Sipho Dlamini: 4 open (1 past deadline), resolved 12 in 30 days, mean time to resolve 20 h" in md
    assert "T-9 Fibre down in Rosebank" in md and "5 h past deadline" in md and "[[ticket:t-9]]" in md
    assert "T-3 Billing question (LOW, open, no queue, unassigned): idle 40 h" in md
    assert "T-5 Replaced router" in md and "possibly not properly resolved" in md
    assert "0821234567" not in md                                                          # scrubbed like every card
    assert card.importance == B.IMPORTANCE["high"] and {(e.dst_id, e.relation) for e in card.edges} == {("t-9", "late"), ("t-3", "late")}


def test_digest_is_stable_for_an_unchanged_desk_and_omits_empty_sections():
    d = digest_data(late=[], flagged=[], stages=[], queues=[], people=[], now={"total": 3, "open": 0, "unassigned": 0, "escalated": 0, "overdue": 0, "stale": 0})
    a, b = B.ticket_digest(d, NOW), B.ticket_digest(d, NOW + timedelta(hours=1))
    assert stable_text(a.markdown) == stable_text(b.markdown)
    for section in ("Late or stale", "Who is carrying what", "Open work by queue", "Average time spent", "Jev flagged"):
        assert section not in a.markdown
    assert a.importance == B.IMPORTANCE["normal"]


def test_digest_thresholds_follow_the_support_service():
    from services.support import kpi
    from services.tenant_memory.knowledge.cards import sources
    assert sources.STALE_HOURS == kpi.STALE_HOURS
