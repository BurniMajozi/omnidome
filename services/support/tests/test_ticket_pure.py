"""Pure-function tests for the ticket time dimension, notifications, user-defined rules and Jev decisions.
No database: see test_ticket_lifecycle_db.py for the end-to-end behaviour."""
import os
import sys
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

import pytest  # noqa: E402

from services.support import custom_rules, jev_ticket, kpi, lifecycle, notify, ticket_rules  # noqa: E402

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


# ── time dimension ──────────────────────────────────────────────────────────

def test_status_event_types():
    assert lifecycle.status_event_type("OPEN", "IN_PROGRESS") == "status_changed"
    assert lifecycle.status_event_type("IN_PROGRESS", "RESOLVED") == "resolved"
    assert lifecycle.status_event_type("RESOLVED", "CLOSED") == "closed"
    assert lifecycle.status_event_type("CLOSED", "OPEN") == "reopened"
    assert lifecycle.status_event_type("RESOLVED", "IN_PROGRESS") == "reopened"
    assert lifecycle.status_event_type("IN_PROGRESS", "ESCALATED") == "escalated"
    assert lifecycle.status_event_type("ESCALATED", "ON_HOLD") == "status_changed"


def test_first_touch_resolution_needs_one_person_no_transfer_no_reopen():
    assert lifecycle.first_touch_resolution(1, 0, 0)
    assert lifecycle.first_touch_resolution(0, 0, 0)          # resolved straight from the queue
    assert not lifecycle.first_touch_resolution(2, 0, 0)      # passed between two people
    assert not lifecycle.first_touch_resolution(1, 1, 0)      # moved queue
    assert not lifecycle.first_touch_resolution(1, 0, 1)      # came back


def test_every_event_type_is_known_and_unknown_is_rejected():
    for et in ("created", "assigned", "reassigned", "transferred", "modified", "note_added", "customer_notified",
               "resolved", "sla_breached", "jev_suggested"):
        assert et in lifecycle.EVENT_TYPES
    assert "mystery" not in lifecycle.EVENT_TYPES


def test_overdue_and_stale_are_computed_not_stored():
    past, future = NOW - timedelta(hours=1), NOW + timedelta(hours=1)
    assert kpi.is_overdue("OPEN", past, NOW)
    assert not kpi.is_overdue("OPEN", future, NOW)
    assert not kpi.is_overdue("RESOLVED", past, NOW)           # closed tickets are never overdue
    assert not kpi.is_overdue("OPEN", None, NOW)
    # URGENT goes stale after 2h without activity, LOW after 36h
    assert kpi.is_stale("OPEN", "URGENT", NOW - timedelta(hours=3), NOW)
    assert not kpi.is_stale("OPEN", "URGENT", NOW - timedelta(hours=1), NOW)
    assert not kpi.is_stale("OPEN", "LOW", NOW - timedelta(hours=20), NOW)
    assert kpi.is_stale("IN_PROGRESS", "LOW", NOW - timedelta(hours=40), NOW)
    assert not kpi.is_stale("CLOSED", "URGENT", NOW - timedelta(days=9), NOW)


def test_hours_between_ignores_missing_and_backwards_times():
    assert kpi.hours_between(NOW, NOW + timedelta(minutes=90)) == 1.5
    assert kpi.hours_between(None, NOW) is None
    assert kpi.hours_between(NOW, None) is None
    assert kpi.hours_between(NOW, NOW - timedelta(hours=1)) is None
    naive = datetime(2026, 10, 17, 12, 0)
    assert kpi.hours_between(naive, NOW + timedelta(hours=2)) == 2.0   # naive is treated as UTC


# ── requester notifications ─────────────────────────────────────────────────

def test_notification_wording_is_fixed_and_carries_no_internal_detail():
    subject, body = notify.render("assigned", ref="T-12", subject="Router keeps dropping")
    assert subject == "Re: Router keeps dropping [T-12]"
    assert "T-12" in body and "being worked on" in body
    _, body = notify.render("modified", ref="T-12", subject="x", detail="Its priority is now High.")
    assert "priority is now High" in body
    _, body = notify.render("resolved", ref="T-12", subject="x", detail="Replaced the PSU")
    assert "Replaced the PSU" in body and "reply to this message" in body
    with pytest.raises(ValueError):
        notify.render("queue_moved", ref="T-1", subject="x")


def test_notification_text_is_redacted():
    _, body = notify.render("note", ref="T-1", subject="x", detail="Call me on 0821234567 please")
    assert "0821234567" not in body


def test_only_email_has_a_delivery_path_and_every_source_maps_to_a_channel():
    assert notify.DELIVERABLE_CHANNELS == {"email"}
    assert notify.channel_for_source("email") == "email"
    assert notify.channel_for_source("call_center") == "call"
    assert notify.channel_for_source("manual") is None
    assert set(notify.TRIGGERS) == set(notify.TRIGGER_COLUMN)


# ── user-defined rules ──────────────────────────────────────────────────────

@pytest.mark.parametrize("pattern", ["portal.cart.abandoned", "sales.lead.*", "PORTAL.Cart.Abandoned"])
def test_valid_custom_patterns(pattern):
    assert custom_rules.validate_pattern(pattern) == pattern.lower()


@pytest.mark.parametrize("pattern,why", [
    ("*", "everything"), ("portal", "one part"), ("", "empty"), (".*", "no namespace"),
    ("support.ticket.created", "would loop"), ("ticket.requested", "would loop"), ("support.*", "would loop"),
    ("system.health.ping", "noise"), ("iot.home.offline", "built-in"), ("iot.*", "covers a built-in"),
    ("Bad Event!", "not dotted words"),
])
def test_invalid_custom_patterns_are_refused(pattern, why):
    with pytest.raises(custom_rules.RuleError):
        custom_rules.validate_pattern(pattern)


def test_conditions_are_validated():
    assert custom_rules.validate_conditions(None) == []
    ok = custom_rules.validate_conditions([{"field": "customer.tier", "op": "EQ", "value": " gold "}, {"field": "amount", "op": "exists"}])
    assert ok == [{"field": "customer.tier", "op": "eq", "value": "gold"}, {"field": "amount", "op": "exists", "value": None}]
    for bad in ([{"field": "a b", "op": "eq", "value": "x"}], [{"field": "a", "op": "regex", "value": "x"}],
                [{"field": "a", "op": "eq"}], [{"field": "a", "op": "eq", "value": "x"}] * 6, "nope", ["x"]):
        with pytest.raises(custom_rules.RuleError):
            custom_rules.validate_conditions(bad)


def rule(**kw):
    base = dict(id="11111111-aaaa-bbbb-cccc-222222222222", name="Cart rule", event_pattern="portal.cart.abandoned",
                conditions=[], source="api", category="SALES", priority="HIGH", queue="support", outcome="task")
    base.update(kw)
    return custom_rules.CustomRule(**base)


def event(et="portal.cart.abandoned", **payload):
    return {"id": "e1", "tenant_id": "t", "type": et, "subject_type": "cart", "subject_id": "cart-9", "payload": payload}


def test_matching_by_pattern_and_conditions():
    r = rule(conditions=[{"field": "value", "op": "contains", "value": "fibre"}, {"field": "customer.tier", "op": "eq", "value": "Gold"}])
    assert custom_rules.matches(r, event(value="Fibre 100", customer={"tier": "gold"}))
    assert not custom_rules.matches(r, event(value="Fibre 100", customer={"tier": "silver"}))
    assert not custom_rules.matches(r, event(value="LTE"))
    assert not custom_rules.matches(rule(event_pattern="portal.*"), event("sales.lead.created"))
    assert custom_rules.matches(rule(event_pattern="portal.*"), event("portal.cart.abandoned"))
    assert not custom_rules.matches(rule(enabled=False), event())
    assert custom_rules.matches(rule(conditions=[{"field": "tier", "op": "neq", "value": "x"}]), event())   # missing field: neq holds
    assert not custom_rules.matches(rule(conditions=[{"field": "tier", "op": "exists", "value": None}]), event())


def test_a_custom_rule_never_matches_ticket_events_built_ins_or_noise():
    pattern_rule = rule(event_pattern="support.*")      # could only exist by writing the table directly
    assert not custom_rules.matches(pattern_rule, event("support.ticket.created"))
    assert not custom_rules.matches(rule(event_pattern="iot.home.offline"), event("iot.home.offline"))
    assert not custom_rules.matches(rule(event_pattern="portal.cart.heartbeat"), event("portal.cart.heartbeat"))


def test_title_templates_fill_fields_and_nothing_else():
    assert custom_rules.render_title("Cart {customer.name} abandoned {value}", {"customer": {"name": "Ann"}, "value": "R499"}, "x.y") == "Cart Ann abandoned R499"
    assert custom_rules.render_title("{__class__} {missing}", {}, "portal.cart.abandoned") == "Portal cart abandoned"   # falls back
    assert custom_rules.render_title(None, {"title": "From payload"}, "a.b") == "From payload"
    assert custom_rules.render_title("{obj}", {"obj": {"a": 1}}, "a.b_c") == "A b c"                                   # objects are not dumped
    assert "0821234567" not in custom_rules.render_title("Call {phone}", {"phone": "0821234567"}, "a.b")


def test_spec_carries_the_rule_routing_and_dedupes_per_subject():
    r = rule()
    spec = custom_rules.resolve_custom([r], event(title="Cart abandoned", description="Left 3 items"))
    assert spec.subject == "Cart abandoned" and spec.category == "SALES" and spec.priority == "HIGH"
    assert spec.queue == "support" and spec.outcome == "task" and spec.source == "api"
    assert spec.ref_type == "cart" and spec.ref_id == "cart-9" and "Left 3 items" in spec.description
    again = custom_rules.resolve_custom([r], event(title="Cart abandoned"))
    assert again.dedupe_key == spec.dedupe_key
    other = custom_rules.resolve_custom([r], {**event(title="Cart abandoned"), "subject_id": "cart-10"})
    assert other.dedupe_key != spec.dedupe_key
    assert custom_rules.resolve_custom([r], event("sales.lead.created")) is None


def test_built_in_rules_carry_an_outcome():
    eff = ticket_rules.effective_rule(ticket_rules.RULES["iot.home.offline"], {"outcome": "escalation"})
    assert eff["outcome"] == "escalation"
    assert ticket_rules.effective_rule(ticket_rules.RULES["iot.home.offline"], None)["outcome"] == "ticket"
    ev = {"id": "e", "type": "iot.home.offline", "subject_id": "h1", "payload": {"home_id": "h1"}}
    assert ticket_rules.resolve(ev, {"iot.home.offline": {"outcome": "schedule"}}).outcome == "schedule"
    assert ticket_rules.resolve(ev, {}).outcome == "ticket"


# ── Jev decisions ───────────────────────────────────────────────────────────

CURRENT = {"queue": "support", "category": "GENERAL", "priority": "NORMAL", "outcome": "ticket", "assignee": None}


def test_off_mode_decides_nothing():
    assert jev_ticket.decide({"queue": "technical"}, {"queue": 0.99}, "off", CURRENT) == {"apply": {}, "suggest": {}, "ignored": {}}


def test_suggest_mode_never_applies_by_itself():
    out = jev_ticket.decide({"queue": "technical", "priority": "high"}, {"queue": 0.99, "priority": 0.7}, "suggest", CURRENT)
    assert out["apply"] == {} and out["suggest"] == {"queue": "technical", "priority": "HIGH"}


def test_auto_mode_applies_only_above_the_apply_threshold():
    out = jev_ticket.decide({"queue": "technical", "priority": "HIGH", "category": "BILLING"},
                            {"queue": 0.95, "priority": 0.75, "category": 0.2}, "auto", CURRENT)
    assert out["apply"] == {"queue": "technical"}
    assert out["suggest"] == {"priority": "HIGH"}
    assert out["ignored"] == {"category": "BILLING"}


def test_a_proposal_equal_to_the_present_value_is_not_a_change():
    assert jev_ticket.decide({"queue": "support"}, {"queue": 0.99}, "auto", CURRENT)["apply"] == {}


def test_values_outside_the_allowed_lists_are_dropped_whatever_the_confidence():
    out = jev_ticket.decide({"queue": "hr", "priority": "SEVERE", "outcome": "delete"}, {"queue": 1, "priority": 1, "outcome": 1}, "auto", CURRENT)
    assert out == {"apply": {}, "suggest": {}, "ignored": {}}


def test_an_assignee_must_be_one_of_the_offered_candidates():
    who = "00000000-0000-0000-0000-0000000000aa"
    offered = {who}
    assert jev_ticket.decide({"assignee": who}, {"assignee": 0.95}, "auto", CURRENT, offered)["apply"] == {"assignee": who}
    assert jev_ticket.decide({"assignee": "someone-else"}, {"assignee": 0.99}, "auto", CURRENT, offered)["apply"] == {}
    assert jev_ticket.decide({"assignee": who}, {"assignee": 0.99}, "auto", CURRENT, None)["apply"] == {}      # none offered


def test_review_and_stage_dispositions():
    assert jev_ticket.review_flagged(0.9, 0.2) and jev_ticket.review_flagged(0.1, 0.9)
    assert not jev_ticket.review_flagged(0.9, 0.8)
    assert jev_ticket.stage_disposition(0.95, "auto") == "apply"
    assert jev_ticket.stage_disposition(0.95, "suggest") == "suggest"     # suggest mode never escalates by itself
    assert jev_ticket.stage_disposition(0.7, "auto") == "suggest"
    assert jev_ticket.stage_disposition(0.3, "auto") == "ignore"
    assert jev_ticket.stage_disposition(0.99, "off") == "ignore"
