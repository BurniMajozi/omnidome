"""Event -> ticket mapping: categories, priorities, dedupe keys, noise, tenant overrides, redaction."""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import pytest  # noqa: E402

from services.common import ticket_events as E  # noqa: E402
from services.support import ticket_rules as R  # noqa: E402

TENANT = str(uuid.uuid4())
HOME = str(uuid.uuid4())


def ev(type_, payload=None, **kw):
    return {"id": str(uuid.uuid4()), "tenant_id": TENANT, "type": type_, "source": "t", "payload": payload or {}, **kw}


def test_every_rule_key_is_a_valid_bus_event_type():
    from services.common.event_bus import normalise_event_type
    for key in R.RULES:
        assert normalise_event_type(key) == key
    assert set(R.SUBSCRIPTIONS) == set(R.RULES)


@pytest.mark.parametrize("event,source,category,priority,queue", [
    (ev("iot.home.offline", {"home_id": HOME}), "iot", "HOMEDOME", "HIGH", "technical"),
    (ev("iot.support.requested", {"home_id": HOME}), "iot", "HOMEDOME", "HIGH", "technical"),
    (ev("iot.gateway.failed", {"home_id": HOME, "reason": "timeout"}), "iot", "HOMEDOME", "NORMAL", "technical"),
    (ev("iot.integration.failed", {"home_id": HOME, "integration": "imou"}), "iot", "HOMEDOME", "NORMAL", "technical"),
    (ev("finance.payment.failed", {"invoice_id": "i1", "amount": 499.0, "reason": "insufficient funds"}), "finance", "BILLING", "HIGH", "finance"),
    (ev("finance.reconciliation.exception", {"statement_ref": "b1", "amount": 10}), "finance", "BILLING", "NORMAL", "finance"),
    (ev("platform.billing.payment.review", {"order_id": "o1"}), "finance", "BILLING", "HIGH", "finance"),
    (ev("email.received", {"direction": "inbound", "subject": "No internet", "thread_id": "t1", "from_address": "c@x.co"}), "email", "GENERAL", "NORMAL", "support"),
    (ev("agents.run.failed", {"agent": "billing", "run_id": "r1", "error": "tool timeout"}), "agent_task", "AGENT", "NORMAL", "agents"),
    (ev("agents.approval.requested", {"agent_type": "billing", "approval_id": "a1", "tool_name": "refund"}), "agent_task", "AGENT", "NORMAL", "agents"),
    (ev("callcenter.call.missed", {"call_id": "c1", "caller_ref": "abc", "direction": "INBOUND"}), "call_center", "CALLS", "NORMAL", "calls"),
    (ev("callcenter.callback.requested", {"callback_id": "cb1"}), "call_center", "CALLS", "NORMAL", "calls"),
    (ev("system.error.raised", {"service": "billing", "exception_type": "KeyError", "fingerprint": "f1", "location": "x:y", "kind": "request"}),
     "system_error", "SYSTEM", "NORMAL", "platform"),
])
def test_mapping(event, source, category, priority, queue):
    spec = R.resolve(event)
    assert spec is not None
    assert (spec.source, spec.category, spec.priority, spec.queue) == (source, category, priority, queue)
    assert spec.dedupe_key and spec.subject and spec.event_id == event["id"]


def test_links_back_to_the_originating_record():
    s = R.resolve(ev("iot.home.offline", {"home_id": HOME}))
    assert (s.ref_type, s.ref_id) == ("iot_home", HOME) and s.link == "/dashboard/home-dome"
    s = R.resolve(ev("finance.payment.failed", {"invoice_id": "inv-9", "amount": 1.5}))
    assert (s.ref_type, s.ref_id) == ("invoice", "inv-9") and s.link.startswith("/dashboard?section=billing")
    s = R.resolve(ev("email.received", {"thread_id": "th-1", "subject": "Hi"}))
    assert (s.ref_type, s.ref_id) == ("email_thread", "th-1")
    s = R.resolve(ev("system.error.raised", {"service": "hr", "fingerprint": "ff", "exception_type": "E", "location": "a:b"}))
    assert (s.ref_type, s.ref_id) == ("error_fingerprint", "ff")


def test_dedupe_keys_fold_repeats_and_split_distinct_problems():
    a = R.resolve(ev("iot.home.offline", {"home_id": HOME}))
    b = R.resolve(ev("iot.home.offline", {"home_id": HOME}))
    other = R.resolve(ev("iot.home.offline", {"home_id": str(uuid.uuid4())}))
    assert a.dedupe_key == b.dedupe_key != other.dedupe_key
    # one open ticket per invoice, however many retries fail
    f1 = R.resolve(ev("finance.payment.failed", {"invoice_id": "i1", "attempt": 1}))
    f2 = R.resolve(ev("finance.payment.failed", {"invoice_id": "i1", "attempt": 2}))
    assert f1.dedupe_key == f2.dedupe_key
    # the same caller ringing twice is one ticket; a different caller is another
    c1 = R.resolve(ev("callcenter.call.missed", {"call_id": "c1", "caller_ref": "aaa"}))
    c2 = R.resolve(ev("callcenter.call.missed", {"call_id": "c2", "caller_ref": "aaa"}))
    c3 = R.resolve(ev("callcenter.call.missed", {"call_id": "c3", "caller_ref": "bbb"}))
    assert c1.dedupe_key == c2.dedupe_key != c3.dedupe_key
    # agent failures group by agent + error class, ignoring ids in the message
    g1 = R.resolve(ev("agents.run.failed", {"agent": "billing", "run_id": "r1", "error": "timeout for run 3f2a9c1e-aaaa-bbbb"}))
    g2 = R.resolve(ev("agents.run.failed", {"agent": "billing", "run_id": "r2", "error": "timeout for run 99999999-cccc-dddd"}))
    g3 = R.resolve(ev("agents.run.failed", {"agent": "sales", "run_id": "r3", "error": "timeout for run 3f2a9c1e-aaaa-bbbb"}))
    assert g1.dedupe_key == g2.dedupe_key != g3.dedupe_key
    # the error hook's fingerprint is the key
    s1 = R.resolve(ev("system.error.raised", {"service": "x", "fingerprint": "abc", "exception_type": "E", "location": "l"}))
    assert s1.dedupe_key == "sys:abc"


def test_recovery_comments_on_the_offline_ticket_and_never_opens_one():
    off = R.resolve(ev("iot.home.offline", {"home_id": HOME}))
    rec = R.resolve(ev("iot.home.recovered", {"home_id": HOME}))
    assert rec.comment_only and rec.dedupe_key == off.dedupe_key


@pytest.mark.parametrize("event", [
    ev("system.health.checked", {"service": "x"}),
    ev("billing.worker.heartbeat"),
    ev("iot.gateway.activated", {"home_id": HOME}),          # informational, no rule
    ev("iot.integration.connected", {"home_id": HOME}),
    ev("sales.lead.created", {}),                            # not ours
    ev("system.error.raised", {"level": "debug", "service": "x", "fingerprint": "f", "exception_type": "E"}),
    ev("email.received", {"direction": "outbound", "subject": "Hi"}),
    ev("email.received", {"direction": "inbound", "subject": "Out of office", "from_address": "a@b.co"}),
    ev("email.received", {"direction": "inbound", "subject": "Your invoice", "from_address": "no-reply@x.co"}),
    ev("email.received", {"direction": "inbound", "subject": "Newsletter", "precedence": "bulk"}),
    ev("system.error.raised", {"service": "x"}),             # no fingerprint: unusable
])
def test_noise_and_unmapped_events_make_no_ticket(event):
    assert R.resolve(event) is None


def test_tenant_overrides_change_priority_queue_category_and_can_disable():
    event = ev("iot.home.offline", {"home_id": HOME})
    me = str(uuid.uuid4())
    spec = R.resolve(event, {"iot.home.offline": {"priority": "URGENT", "queue": "calls", "category": "TECHNICAL", "assigned_to": me}})
    assert (spec.priority, spec.queue, spec.category) == ("URGENT", "calls", "TECHNICAL") and str(spec.assigned_to) == me
    assert R.resolve(event, {"iot.home.offline": {"enabled": False}}) is None
    # other tenants' / other rules' overrides do not leak in
    assert R.resolve(event, {"finance.payment.failed": {"enabled": False}}).priority == "HIGH"
    eff = R.effective_rule(R.RULES["iot.home.offline"], {"priority": "LOW"})
    assert eff["priority"] == "LOW" and eff["overridden"] and R.effective_rule(R.RULES["iot.home.offline"], None)["overridden"] is False


def test_explicit_request_event():
    spec = R.resolve(ev(E.EVENT_TICKET_REQUESTED, {"source": "api", "title": "Look at this", "dedupe_key": "k1", "priority": "high",
                                                  "category": "billing", "link": "/dashboard?section=billing", "ref_type": "x", "ref_id": "9"}))
    assert (spec.priority, spec.category, spec.dedupe_key, spec.link) == ("HIGH", "BILLING", "req:k1", "/dashboard?section=billing")
    assert R.resolve(ev(E.EVENT_TICKET_REQUESTED, {"title": "", "dedupe_key": "k"})) is None
    assert R.resolve(ev(E.EVENT_TICKET_REQUESTED, {"title": "t", "dedupe_key": "k", "link": "https://evil.example/x"})).link is None
    assert R.resolve(ev(E.EVENT_TICKET_REQUESTED, {"title": "t", "dedupe_key": "k", "priority": "bogus"})).priority == "NORMAL"


def test_ticket_text_is_redacted_whatever_the_source():
    spec = R.resolve(ev("system.error.raised", {
        "service": "billing", "exception_type": "RuntimeError", "fingerprint": "ff", "location": "a:b", "kind": "request",
        "message": "failed for jane@example.com using Bearer abcdefghijklmnop1234 password=hunter2hunter2",
        "route": "/x", "method": "POST", "frames": ["a.py:1 in f"]}))
    blob = spec.subject + spec.description + repr(spec.context)
    for leak in ("jane@example.com", "abcdefghijklmnop1234", "hunter2hunter2"):
        assert leak not in blob
    mail = R.resolve(ev("email.received", {"direction": "inbound", "subject": "Call me on 0821234567", "thread_id": "t",
                                           "body_preview": "My id is 8001015009087 and card 4111 1111 1111 1111",
                                           "from_address": "x@y.co"}))
    blob = mail.subject + mail.description
    assert "0821234567" not in blob and "8001015009087" not in blob and "4111 1111 1111 1111" not in blob


def test_call_ticket_never_contains_the_phone_number():
    spec = R.resolve(ev("callcenter.call.missed", {"call_id": "c1", "number": "+27821234567", "caller_ref": "abc", "caller_hint": "…567"}))
    assert "821234567" not in spec.subject + spec.description + spec.dedupe_key


def test_priority_escalates_with_repeats_but_never_drops():
    assert R.escalated_priority("NORMAL", 1) == "NORMAL"
    assert R.escalated_priority("NORMAL", 10) == "HIGH"
    assert R.escalated_priority("NORMAL", 50) == "URGENT"
    assert R.escalated_priority("URGENT", 10) == "URGENT"
    assert R.escalated_priority("HIGH", 3) == "HIGH"
