"""Jev for tickets (jev_ticket.py + routes/jev_tickets.py): the gates, what is sent, and how answers are parsed.
Jev itself is never called: `_ask` is stubbed."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator import jev_ticket as J  # noqa: E402
from services.agent_orchestrator.config import settings  # noqa: E402


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def jev_on(monkeypatch):
    monkeypatch.setattr(settings, "jev_gate_enabled", True, raising=False)
    monkeypatch.setattr(J, "_get_credentials", lambda: ("typesafe", "test-key", "https://jev.invalid"))
    monkeypatch.setenv("JEV_DATA_EGRESS", "true")


def stub(monkeypatch, answers=None, boom=None):
    sent = []

    async def fake(state, questions, tenant_id):
        sent.append((state, questions))
        if boom:
            raise boom
        return answers or {}, {"provider": "typesafe"}
    monkeypatch.setattr(J, "_ask", fake)
    return sent


TICKET = {"ref": "T-9", "subject": "Fibre down", "description": "No light on the ONT", "priority": "NORMAL", "queue": "support", "category": "GENERAL"}


# ── gates ───────────────────────────────────────────────────────────────────

def test_jev_is_not_asked_when_it_is_disabled_or_has_no_key(monkeypatch):
    monkeypatch.setattr(settings, "jev_gate_enabled", False, raising=False)
    sent = stub(monkeypatch)
    out = run(J.route_ticket(TICKET, [], "t1"))
    assert out["evaluated_by_jev"] is False and out["proposal"] == {} and sent == []
    monkeypatch.setattr(settings, "jev_gate_enabled", True, raising=False)
    monkeypatch.setattr(J, "_get_credentials", lambda: ("none", "", ""))
    assert run(J.review_closed_ticket(TICKET, "t1"))["evaluated_by_jev"] is False
    assert run(J.check_stage(TICKET, {"hours_open": 1}, "t1"))["evaluated_by_jev"] is False
    assert sent == []


def test_tenant_data_never_leaves_when_egress_is_off(monkeypatch, jev_on):
    monkeypatch.setenv("JEV_DATA_EGRESS", "false")
    sent = stub(monkeypatch)
    out = run(J.route_ticket(TICKET, [], "t1"))
    assert out["evaluated_by_jev"] is False and "JEV_DATA_EGRESS" in out["reason"] and sent == []


def test_a_jev_failure_is_no_opinion_not_an_error(monkeypatch, jev_on):
    stub(monkeypatch, boom=RuntimeError("Jev returned HTTP 503"))
    for call in (J.route_ticket(TICKET, [], "t1"), J.review_closed_ticket(TICKET, "t1"), J.check_stage(TICKET, {"hours_open": 1}, "t1")):
        out = run(call)
        assert out["evaluated_by_jev"] is False and "unavailable" in out["reason"].lower()


# ── parsing untrusted answers ───────────────────────────────────────────────

def test_choices_outside_the_offered_options_are_dropped():
    assert J.parse_choice({"choice": "technical", "confidence": 0.9, "probabilities": {"technical": 0.9, "finance": 0.1}}, list(J.QUEUE_CRITERIA)) \
        == ("technical", 0.9, {"technical": 0.9, "finance": 0.1})
    assert J.parse_choice({"choice": "hr", "confidence": 0.99}, list(J.QUEUE_CRITERIA))[0] is None
    assert J.parse_choice({"choice": ["technical"]}, list(J.QUEUE_CRITERIA))[0] is None
    assert J.parse_choice("technical", list(J.QUEUE_CRITERIA)) == (None, 0.0, {})
    assert J.parse_choice(None, []) == (None, 0.0, {})


def test_probabilities_are_clamped_and_junk_becomes_zero():
    assert J.parse_choice({"choice": "support", "confidence": 7}, ["support"])[1] == 1.0
    assert J.parse_choice({"choice": "support", "confidence": -3}, ["support"])[1] == 0.0
    assert J.parse_choice({"choice": "support", "confidence": "high"}, ["support"])[1] == 0.0
    assert J.parse_choice({"choice": "support", "confidence": float("nan")}, ["support"])[1] == 0.0
    assert J.parse_noul({"noul": 0.42}) == 0.42 and J.parse_noul({"noul": 9}) == 1.0 and J.parse_noul({"noul": "x"}) == 0.0
    assert J.parse_noul(0.3) == 0.3 and J.parse_noul(None, 0.5) == 0.5 and J.parse_noul({"probability": 0.7}) == 0.7


# ── routing ─────────────────────────────────────────────────────────────────

ANSWERS = {
    "queue": {"choice": "technical", "confidence": 0.95, "probabilities": {"technical": 0.95, "support": 0.05}},
    "category": {"choice": "TECHNICAL", "confidence": 0.9},
    "priority": {"choice": "URGENT", "confidence": 0.8},
    "outcome": {"choice": "escalation", "confidence": 0.7},
}


def test_routing_returns_a_validated_proposal_with_confidences(monkeypatch, jev_on):
    sent = stub(monkeypatch, {**ANSWERS, "priority": {"choice": "SEVERE", "confidence": 0.99}})      # SEVERE is not offered
    out = run(J.route_ticket(TICKET, [], "t1"))
    assert out["evaluated_by_jev"] is True
    assert out["proposal"] == {"queue": "technical", "category": "TECHNICAL", "outcome": "escalation"}
    assert out["confidence"] == {"queue": 0.95, "category": 0.9, "outcome": 0.7}
    state, questions = sent[0]
    assert set(questions) == {"queue", "category", "priority", "outcome"}                            # no assignee question without candidates
    assert state == {"ticket": TICKET}


def test_assignee_candidates_are_opaque_ids_and_none_is_not_a_proposal(monkeypatch, jev_on):
    cands = [{"id": "u-1", "open": 3, "resolved_30d": 12, "top_categories": ["TECHNICAL"]}, {"id": "u-2", "open": 0, "resolved_30d": 1}]
    sent = stub(monkeypatch, {**ANSWERS, "assignee": {"choice": "u-1", "confidence": 0.92}})
    out = run(J.route_ticket(TICKET, cands, "t1"))
    assert out["proposal"]["assignee"] == "u-1" and out["confidence"]["assignee"] == 0.92
    q = sent[0][1]["assignee"]
    assert q["options"] == ["u-1", "u-2", "none"]
    assert "Open tickets: 3" in q["criteria"]["u-1"] and "TECHNICAL" in q["criteria"]["u-1"] and "no history yet" in q["criteria"]["u-2"]
    assert "@" not in str(sent[0])                                                                    # nothing that identifies a person

    stub(monkeypatch, {**ANSWERS, "assignee": {"choice": "none", "confidence": 0.99}})
    assert "assignee" not in run(J.route_ticket(TICKET, cands, "t1"))["proposal"]
    stub(monkeypatch, {**ANSWERS, "assignee": {"choice": "u-99", "confidence": 0.99}})                # not one of the candidates
    assert "assignee" not in run(J.route_ticket(TICKET, cands, "t1"))["proposal"]


def test_only_a_bounded_number_of_candidates_is_sent(monkeypatch, jev_on):
    many = [{"id": f"u-{i}"} for i in range(100)]
    sent = stub(monkeypatch, ANSWERS)
    run(J.route_ticket(TICKET, many, "t1"))
    assert len(sent[0][1]["assignee"]["options"]) == J.MAX_CANDIDATES + 1


def test_empty_fields_are_not_sent_to_jev(monkeypatch, jev_on):
    sent = stub(monkeypatch, ANSWERS)
    run(J.route_ticket({"subject": "x", "description": None, "resolution": None, "unexpected": "dropped"}, [], "t1"))
    assert sent[0][0] == {"ticket": {"subject": "x"}}


# ── review and stage ────────────────────────────────────────────────────────

def test_review_returns_both_probabilities(monkeypatch, jev_on):
    sent = stub(monkeypatch, {"resolved_properly": {"noul": 0.85}, "resolution_specific": {"noul": 0.2}})
    out = run(J.review_closed_ticket({**TICKET, "resolution": "fixed"}, "t1"))
    assert out["evaluated_by_jev"] and (out["resolved_properly"], out["resolution_specific"]) == (0.85, 0.2)
    assert sent[0][0]["ticket"]["resolution"] == "fixed" and set(sent[0][1]) == {"resolved_properly", "resolution_specific"}


def test_stage_check_sends_timing_and_returns_the_escalation_probability(monkeypatch, jev_on):
    sent = stub(monkeypatch, {"should_escalate": {"noul": 0.93}})
    timing = {"hours_open": 30, "hours_since_activity": 12, "hours_past_deadline": 6, "times_reassigned": 2, "escalated_already": False}
    out = run(J.check_stage(TICKET, timing, "t1"))
    assert out["should_escalate"] == 0.93 and sent[0][0]["timing"] == timing


# ── the HTTP surface ────────────────────────────────────────────────────────

def test_request_models_bound_what_a_caller_can_make_the_service_send():
    from pydantic import ValidationError
    from services.agent_orchestrator.routes import jev_tickets as R
    R.RouteRequest(ticket=R.TicketPayload(subject="ok"), candidates=[])
    with pytest.raises(ValidationError):
        R.TicketPayload(subject="x" * 301)
    with pytest.raises(ValidationError):
        R.TicketPayload(subject="x", description="d" * 2501)
    with pytest.raises(ValidationError):
        R.RouteRequest(ticket=R.TicketPayload(subject="x"), candidates=[R.Candidate(id=str(i)) for i in range(J.MAX_CANDIDATES + 1)])
    with pytest.raises(ValidationError):
        R.Timing(hours_open=-1, hours_since_activity=0)
    with pytest.raises(ValidationError):
        R.Candidate(id="x", open=-5)
