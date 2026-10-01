"""Dunning runner: honest, idempotent, async end to end.

Every action ends in a result that says what REALLY happened:

    email_sent | skipped_suppressed | skipped_no_email | skipped_no_provider
    skipped_no_provider (sms: no SMS provider is configured for billing)
    suspended | flagged_for_collections
    skipped_<invoice status> (paid/voided/draft...) | skipped_not_overdue
    deferred_arrangement (an active payment arrangement stops dunning; the action waits)
    failed (provider/network error: kept pending with backoff, finalised after MAX_ATTEMPTS)

``run_action`` works on plain objects through an injected ``Deps`` so it is unit-testable without
a database; ``process_pending_dunning`` wires the real dependencies and gives every action its own
DB session (no session is shared across awaits, no asyncio.run inside a running loop).
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

from sqlalchemy import select

from services.billing import calc, finance_posting as fp
from services.billing.models import DunningAction, Invoice, PaymentArrangement

logger = logging.getLogger("billing.dunning")

MAX_ATTEMPTS = 5
REMINDER_STATUSES = ("sent", "overdue", "partially_paid")
SUSPEND_STATUSES = ("sent", "overdue")


@dataclass
class Deps:
    today: date
    now: datetime
    has_arrangement: Callable[[], bool]
    get_email: Callable[[], Awaitable[Optional[str]]]
    is_suppressed: Callable[[str], Awaitable[bool]]
    send_email: Callable[[str, str, str], Awaitable[None]]      # (to, subject, html); raises on failure
    email_configured: Callable[[], bool]
    suspend: Callable[[], Awaitable[bool]]                       # True only when the network call succeeded


def _final(action, result: str, now: datetime) -> None:
    action.result, action.executed_at, action.last_error = result, now, None


def _retry(action, err: str, now: datetime) -> None:
    action.attempts = (action.attempts or 0) + 1
    action.last_error = err[:500]
    action.result = "failed"
    if action.attempts >= MAX_ATTEMPTS:
        action.executed_at = now            # give up; result stays 'failed' with the error
    else:
        action.next_attempt_at = now + timedelta(seconds=min(300 * 2 ** (action.attempts - 1), 86400))


async def run_action(action, inv, deps: Deps) -> None:
    """Execute one dunning action against `inv`. Mutates `action`/`inv`; never raises provider errors."""
    now = deps.now
    kind = action.action_type
    if inv is None:
        return _final(action, "skipped_no_invoice", now)
    allowed = SUSPEND_STATUSES if kind == "auto_suspend" else REMINDER_STATUSES
    if inv.status not in allowed:            # re-check at execution: paid/voided/draft/credited
        return _final(action, f"skipped_{inv.status}", now)
    if deps.has_arrangement():
        action.result = "deferred_arrangement"
        action.next_attempt_at = now + timedelta(days=1)
        return

    if kind == "sms_reminder":
        return _final(action, "skipped_no_provider", now)          # nothing is sent, so nothing is claimed

    if kind == "email_warning":
        email = await deps.get_email()
        if not email:
            return _final(action, "skipped_no_email", now)
        if await deps.is_suppressed(email):                        # opt-out BEFORE sending
            return _final(action, "skipped_suppressed", now)
        if not deps.email_configured():
            return _final(action, "skipped_no_provider", now)
        due = inv.due_date.isoformat()
        subject = f"Payment reminder: invoice {inv.number}"
        html = (f"<p>Our records show invoice {inv.number} (due {due}) still has an outstanding balance of "
                f"R{inv.total_zar - inv.amount_paid_zar:.2f}.</p><p>Please make payment, or contact us if you have "
                f"already paid or need to arrange payment.</p>")
        try:
            await deps.send_email(email, subject, html)
        except Exception as exc:  # noqa: BLE001
            return _retry(action, f"{type(exc).__name__}: {exc}", now)
        return _final(action, "email_sent", now)

    if kind == "auto_suspend":
        if inv.due_date >= deps.today:
            return _final(action, "skipped_not_overdue", now)
        ok = await deps.suspend()
        if not ok:
            return _retry(action, "network service did not confirm the suspension", now)
        inv.status = "overdue"
        return _final(action, "suspended", now)

    if kind == "send_to_collections":
        # No external collections agency integration: the account is surfaced in /collections/queue.
        return _final(action, "flagged_for_collections", now)

    _final(action, f"skipped_unknown_action:{kind}", now)


# ---------------------------------------------------------------------------
# Real dependencies + the batch processor
# ---------------------------------------------------------------------------

async def _suspend_call(tenant_id, customer_id) -> bool:
    from services.billing.routes.collections import suspend_customer
    return await suspend_customer(tenant_id, customer_id)


def _real_deps(session, action, inv) -> Deps:
    from services.billing.contacts import resolve_customer_email
    from services.common import agentmail

    async def get_email():
        return await resolve_customer_email(action.tenant_id, action.customer_id, inv.billing_account_id if inv else None)

    async def is_suppressed(email: str) -> bool:
        from services.common.db import session_scope
        from services.common.suppression import is_suppressed as _is
        async with session_scope(action.tenant_id) as db:
            return await _is(db, action.tenant_id, email)

    async def send_email(to: str, subject: str, html: str) -> None:
        headers = {}
        unsub = os.getenv("BILLING_LIST_UNSUBSCRIBE", "").strip()
        if unsub:
            headers["List-Unsubscribe"] = f"<{unsub}>"
        await agentmail.send_email(to, subject, html, headers=headers or None)

    def has_arrangement() -> bool:
        return session.execute(select(PaymentArrangement.id).where(
            PaymentArrangement.tenant_id == action.tenant_id, PaymentArrangement.customer_id == action.customer_id,
            PaymentArrangement.status == "active").limit(1)).first() is not None

    return Deps(
        today=calc.today_sast(), now=datetime.now(timezone.utc), has_arrangement=has_arrangement,
        get_email=get_email, is_suppressed=is_suppressed, send_email=send_email,
        email_configured=agentmail.is_configured,
        suspend=lambda: _suspend_call(action.tenant_id, action.customer_id),
    )


async def process_pending_dunning(tenant_id: Optional[uuid.UUID] = None, limit: int = 200,
                                  deps_factory=None, session_factory=None) -> dict:
    """Run due actions (one tenant, or every tenant when tenant_id is None). Each action gets its own
    session and row lock (SKIP LOCKED), so two schedulers never run the same action twice."""
    if session_factory is None:
        from services.billing.database import get_session as session_factory  # noqa: N813
    deps_factory = deps_factory or _real_deps
    now = datetime.now(timezone.utc)

    with session_factory() as s:
        q = select(DunningAction.id, DunningAction.tenant_id).where(
            DunningAction.executed_at.is_(None), DunningAction.scheduled_at <= now,
            (DunningAction.next_attempt_at.is_(None)) | (DunningAction.next_attempt_at <= now))
        if tenant_id is not None:
            q = q.where(DunningAction.tenant_id == tenant_id)
        ids = s.execute(q.order_by(DunningAction.tenant_id, DunningAction.scheduled_at).limit(limit)).all()

    counts: dict = {}
    for action_id, _tenant in ids:
        with session_factory() as s:
            action = s.execute(select(DunningAction).where(DunningAction.id == action_id)
                               .with_for_update(skip_locked=True)).scalar_one_or_none()
            if action is None or action.executed_at is not None:
                continue
            inv = s.get(Invoice, action.invoice_id)
            try:
                await run_action(action, inv, deps_factory(s, action, inv))
            except Exception as exc:  # noqa: BLE001
                logger.exception("dunning action %s crashed", action_id)
                _retry(action, f"{type(exc).__name__}: {exc}", datetime.now(timezone.utc))
            counts[action.result] = counts.get(action.result, 0) + 1
    return {"processed": sum(counts.values()), "results": counts}
