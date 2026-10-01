"""Dunning honesty: nothing is reported as sent unless it was, drafts are never scheduled or
suspended, arrangements stop dunning, failures retry, actions are idempotent."""
import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.billing import dunning, invoicing  # noqa: E402
from services.billing.models import DunningAction  # noqa: E402
from services.billing.tests import sqlite_harness as h  # noqa: E402

NOW = datetime(2026, 4, 20, 6, 0, tzinfo=timezone.utc)
TODAY = date(2026, 4, 20)


def action(kind):
    return SimpleNamespace(action_type=kind, result=None, executed_at=None, attempts=0, last_error=None, next_attempt_at=None)


def invoice(status="sent", due=date(2026, 4, 1)):
    return SimpleNamespace(status=status, due_date=due, number="INV-1", total_zar=Decimal("115.00"),
                           amount_paid_zar=Decimal("0.00"), billing_account_id=None)


class Spy:
    def __init__(self, email="a@b.co", suppressed=False, configured=True, send_error=None, suspend_ok=True, arrangement=False):
        self.sent, self.suspended = [], 0
        self.email, self.suppressed, self.configured = email, suppressed, configured
        self.send_error, self.suspend_ok, self.arrangement = send_error, suspend_ok, arrangement

    def deps(self):
        async def get_email(): return self.email
        async def is_suppressed(e): return self.suppressed
        async def send(to, subject, html):
            if self.send_error:
                raise RuntimeError(self.send_error)
            self.sent.append((to, subject))
        async def suspend():
            self.suspended += 1
            return self.suspend_ok
        return dunning.Deps(today=TODAY, now=NOW, has_arrangement=lambda: self.arrangement, get_email=get_email,
                            is_suppressed=is_suppressed, send_email=send, email_configured=lambda: self.configured,
                            suspend=suspend)


def run(kind, inv, spy):
    a = action(kind)
    asyncio.run(dunning.run_action(a, inv, spy.deps()))
    return a


def test_sms_is_never_claimed_sent():
    spy = Spy()
    a = run("sms_reminder", invoice(), spy)
    assert a.result == "skipped_no_provider" and a.executed_at == NOW and spy.sent == []


def test_email_is_really_sent_then_recorded():
    spy = Spy()
    a = run("email_warning", invoice(), spy)
    assert a.result == "email_sent" and spy.sent == [("a@b.co", "Payment reminder: invoice INV-1")]


def test_suppressed_email_is_skipped_before_sending():
    spy = Spy(suppressed=True)
    a = run("email_warning", invoice(), spy)
    assert a.result == "skipped_suppressed" and spy.sent == []


@pytest.mark.parametrize("kwargs,result", [({"email": None}, "skipped_no_email"), ({"configured": False}, "skipped_no_provider")])
def test_email_without_address_or_provider_is_not_reported_sent(kwargs, result):
    spy = Spy(**kwargs)
    a = run("email_warning", invoice(), spy)
    assert a.result == result and spy.sent == []


def test_provider_failure_is_recorded_and_retried_later_then_finalised():
    spy = Spy(send_error="smtp down")
    a = action("email_warning")
    asyncio.run(dunning.run_action(a, invoice(), spy.deps()))
    assert a.result == "failed" and "smtp down" in a.last_error
    assert a.executed_at is None and a.attempts == 1 and a.next_attempt_at > NOW        # stays pending
    for _ in range(dunning.MAX_ATTEMPTS):
        asyncio.run(dunning.run_action(a, invoice(), spy.deps()))
    assert a.executed_at == NOW and a.result == "failed"                                # gives up, still honest


@pytest.mark.parametrize("status", ["draft", "paid", "voided", "credit_issued"])
def test_draft_paid_voided_invoices_are_skipped_and_never_suspended(status):
    for kind in ("sms_reminder", "email_warning", "auto_suspend", "send_to_collections"):
        spy = Spy()
        a = run(kind, invoice(status), spy)
        assert a.result == f"skipped_{status}" and spy.suspended == 0 and spy.sent == []


def test_partially_paid_gets_reminders_but_is_not_auto_suspended():
    spy = Spy()
    assert run("email_warning", invoice("partially_paid"), spy).result == "email_sent"
    assert run("auto_suspend", invoice("partially_paid"), spy).result == "skipped_partially_paid" and spy.suspended == 0


def test_arrangement_stops_dunning_and_defers():
    spy = Spy(arrangement=True)
    for kind in ("email_warning", "auto_suspend", "send_to_collections"):
        a = run(kind, invoice(), spy)
        assert a.result == "deferred_arrangement" and a.executed_at is None and a.next_attempt_at > NOW
    assert spy.suspended == 0 and spy.sent == []


def test_auto_suspend_needs_a_past_due_date():
    spy = Spy()
    a = run("auto_suspend", invoice(due=TODAY), spy)           # due today is not past due
    assert a.result == "skipped_not_overdue" and spy.suspended == 0


def test_auto_suspend_reports_suspended_only_when_the_network_call_succeeded():
    ok, bad = Spy(), Spy(suspend_ok=False)
    inv_ok, inv_bad = invoice(), invoice()
    a = run("auto_suspend", inv_ok, ok)
    assert a.result == "suspended" and inv_ok.status == "overdue"
    b = run("auto_suspend", inv_bad, bad)
    assert b.result == "failed" and b.executed_at is None and inv_bad.status == "sent"     # no false 'suspended'


def test_collections_step_is_flagged_not_pretended_sent():
    assert run("send_to_collections", invoice(), Spy()).result == "flagged_for_collections"


# ── scheduling + idempotency + the real processor against SQLite ────────────

def test_only_issued_invoices_are_scheduled_and_scheduling_is_idempotent():
    db = h.make_session_factory()
    tenant = uuid.uuid4()
    with db() as s:
        draft = h.make_invoice(s, tenant, status="draft")
        sent = h.make_invoice(s, tenant, status="sent")
        assert invoicing.schedule_dunning(s, draft) == 0
        assert invoicing.schedule_dunning(s, sent) == 4
        assert invoicing.schedule_dunning(s, sent) == 0                     # (invoice, action, step) is unique
        assert s.query(DunningAction).count() == 4


def test_process_runs_each_action_once_with_its_own_session():
    db = h.make_session_factory()
    tenant = uuid.uuid4()
    with db() as s:
        inv = h.make_invoice(s, tenant, status="sent", due=date(2020, 1, 1))
        invoicing.schedule_dunning(s, inv)
        inv_id = inv.id
    spy = Spy()

    def factory(session, act, inv):
        return spy.deps()
    out = asyncio.run(dunning.process_pending_dunning(session_factory=db, deps_factory=factory))
    assert out["processed"] == 4
    assert out["results"] == {"skipped_no_provider": 1, "email_sent": 1, "suspended": 1, "flagged_for_collections": 1}
    again = asyncio.run(dunning.process_pending_dunning(session_factory=db, deps_factory=factory))
    assert again["processed"] == 0 and len(spy.sent) == 1 and spy.suspended == 1
    with db() as s:
        from services.billing.models import Invoice
        assert s.get(Invoice, inv_id).status == "overdue"


def test_process_can_be_limited_to_one_tenant():
    db = h.make_session_factory()
    a, b = uuid.uuid4(), uuid.uuid4()
    with db() as s:
        for t in (a, b):
            invoicing.schedule_dunning(s, h.make_invoice(s, t, due=date(2020, 1, 1)))
    spy = Spy()
    out = asyncio.run(dunning.process_pending_dunning(a, session_factory=db, deps_factory=lambda *x: spy.deps()))
    assert out["processed"] == 4
    with db() as s:
        assert s.query(DunningAction).filter(DunningAction.executed_at.is_(None)).count() == 4   # the other tenant's
