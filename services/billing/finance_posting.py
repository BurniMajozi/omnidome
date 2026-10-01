"""Posting contract: billing -> finance journal entries, via a durable outbox.

Revenue is posted from INVOICES ONLY. Entry builders are pure and balanced by construction
(the last credit/debit is derived so debits == credits to the cent). Delivery is
at-least-once: the entry is enqueued in the SAME DB transaction as the business change, and
delivered after commit; finance de-duplicates on (source, source_id) and answers 200.

Payload sent to POST {FINANCE_SERVICE_URL or http://finance:8004}/journal-entries:

    {"date": "YYYY-MM-DD", "description": str,
     "source": "billing.invoice|billing.payment|billing.credit_note|billing.void|billing.seat_invoice",
     "source_id": "<uuid>", "auto_post": true,
     "lines": [{"account_code": "1100", "debit": "115.00", "credit": "0.00"}, ...]}

Headers: x-tenant-id (the invoice's tenant), x-user-id (BILLING_SERVICE_USER_ID); the identity is
signed by services.common.internal_auth's httpx patch.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Awaitable, Callable, Iterable, Optional

import httpx
from sqlalchemy import select

from services.billing.models import BillingFinanceOutbox

logger = logging.getLogger("billing.finance_posting")

AR, BANK, PAYSTACK_CLEARING, VAT_OUTPUT, REVENUE = "1100", "1000", "1010", "2200", "4000"
SOURCES = ("billing.invoice", "billing.payment", "billing.credit_note", "billing.void", "billing.seat_invoice")
MAX_ERROR = 500
_CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)


def _s(value: Decimal) -> str:
    return f"{money(value):.2f}"


def _line(code: str, debit: Decimal = Decimal("0"), credit: Decimal = Decimal("0")) -> dict:
    return {"account_code": code, "debit": _s(debit), "credit": _s(credit)}


def _entry(source: str, source_id, on: date, description: str, lines: list[dict]) -> dict:
    lines = [l for l in lines if Decimal(l["debit"]) or Decimal(l["credit"])]
    d = sum(Decimal(l["debit"]) for l in lines)
    c = sum(Decimal(l["credit"]) for l in lines)
    if d != c:  # builders derive the balancing leg, so this is a programming error
        raise ValueError(f"unbalanced entry for {source} {source_id}: debit {d} credit {c}")
    return {"date": on.isoformat(), "description": description, "source": source,
            "source_id": str(source_id), "auto_post": True, "lines": lines}


def _split(total, subtotal, vat) -> tuple[Decimal, Decimal, Decimal]:
    """(total, revenue, vat), all positive. Revenue is the subtotal unless subtotal + vat != total
    (legacy rounding), in which case it is total - vat so the entry still balances."""
    total, subtotal, vat = money(abs(Decimal(str(total)))), money(abs(Decimal(str(subtotal)))), money(abs(Decimal(str(vat))))
    revenue = subtotal if subtotal + vat == total else total - vat
    if revenue < 0:
        raise ValueError("VAT exceeds invoice total")
    return total, revenue, vat


def invoice_entry(invoice_id, number: str, on: date, total, subtotal, vat, source: str = "billing.invoice") -> dict:
    """Dr 1100 AR = total; Cr 4000 Revenue = subtotal (ex VAT); Cr 2200 VAT Output = vat."""
    total, revenue, vat = _split(total, subtotal, vat)
    return _entry(source, invoice_id, on, f"Invoice {number}",
                  [_line(AR, debit=total), _line(REVENUE, credit=revenue), _line(VAT_OUTPUT, credit=vat)])


def payment_entry(payment_id, reference: str, on: date, amount, method: str = "eft") -> dict:
    """Dr 1000 Bank (1010 Paystack clearing for card payments) / Cr 1100 AR."""
    amount = money(amount)
    if amount <= 0:
        raise ValueError("payment amount must be positive")
    bank = PAYSTACK_CLEARING if str(method).lower() == "card" else BANK
    return _entry("billing.payment", payment_id, on, f"Payment {reference}",
                  [_line(bank, debit=amount), _line(AR, credit=amount)])


def credit_note_entry(credit_note_id, number: str, on: date, total, subtotal, vat) -> dict:
    """Reverse the revenue/VAT credited: Dr 4000, Dr 2200, Cr 1100 (magnitudes of the negative note)."""
    total, revenue, vat = _split(total, subtotal, vat)
    return _entry("billing.credit_note", credit_note_id, on, f"Credit note {number}",
                  [_line(REVENUE, debit=revenue), _line(VAT_OUTPUT, debit=vat), _line(AR, credit=total)])


def void_entry(invoice_id, number: str, on: date, total, subtotal, vat) -> dict:
    """Full reversal of the invoice entry."""
    total, revenue, vat = _split(total, subtotal, vat)
    return _entry("billing.void", invoice_id, on, f"Void invoice {number}",
                  [_line(REVENUE, debit=revenue), _line(VAT_OUTPUT, debit=vat), _line(AR, credit=total)])


def sast_today() -> date:
    return (datetime.now(timezone.utc) + timedelta(hours=2)).date()


# ---------------------------------------------------------------------------
# Outbox
# ---------------------------------------------------------------------------

def enqueue(session, tenant_id: uuid.UUID, entry: dict) -> Optional[BillingFinanceOutbox]:
    """Queue ``entry`` inside the caller's transaction. Idempotent per (tenant, source, source_id):
    returns None when it is already queued/sent."""
    existing = session.execute(select(BillingFinanceOutbox.id).where(
        BillingFinanceOutbox.tenant_id == tenant_id,
        BillingFinanceOutbox.source == entry["source"],
        BillingFinanceOutbox.source_id == entry["source_id"])).first()
    if existing:
        return None
    row = BillingFinanceOutbox(tenant_id=tenant_id, source=entry["source"], source_id=entry["source_id"],
                               payload=entry, status="pending", attempts=0, next_attempt_at=None)
    session.add(row)
    session.flush()
    return row


def finance_url() -> str:
    return (os.getenv("FINANCE_SERVICE_URL") or "http://finance:8004").rstrip("/")


def service_user_id() -> str:
    return os.getenv("BILLING_SERVICE_USER_ID", "00000000-0000-0000-0000-000000000001")


Poster = Callable[[uuid.UUID, dict], Awaitable[None]]


async def post_entry(tenant_id: uuid.UUID, entry: dict) -> None:
    """POST one entry to finance. Raises on transport errors AND on any non-2xx response."""
    timeout = float(os.getenv("BILLING_FINANCE_TIMEOUT", "8"))
    headers = {"x-tenant-id": str(tenant_id), "x-user-id": service_user_id(), "content-type": "application/json"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{finance_url()}/journal-entries", json=entry, headers=headers)
    if not 200 <= resp.status_code < 300:
        raise RuntimeError(f"finance returned HTTP {resp.status_code}: {resp.text[:200]}")


def backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(30 * (2 ** max(attempts - 1, 0)), 3600))


async def deliver(tenant_id: Optional[uuid.UUID] = None, *, only: Optional[Iterable[tuple]] = None,
                  force: bool = False, limit: int = 50, poster: Optional[Poster] = None,
                  session_factory=None) -> dict:
    """Attempt delivery of pending/failed outbox rows. Never raises for delivery problems.

    only   : iterable of (source, source_id) to restrict to (used right after commit).
    force  : ignore next_attempt_at (manual retry endpoint).
    Each row is claimed, posted and updated in its own short session (no DB transaction is held
    across the HTTP call); a duplicate delivery is harmless because finance is idempotent.
    """
    if session_factory is None:
        from services.billing.database import get_session as session_factory  # noqa: N813
    poster = poster or post_entry
    now = datetime.now(timezone.utc)

    with session_factory() as s:
        q = select(BillingFinanceOutbox.id, BillingFinanceOutbox.tenant_id, BillingFinanceOutbox.payload,
                   BillingFinanceOutbox.attempts, BillingFinanceOutbox.source, BillingFinanceOutbox.source_id
                   ).where(BillingFinanceOutbox.status.in_(["pending", "failed"]))
        if tenant_id is not None:
            q = q.where(BillingFinanceOutbox.tenant_id == tenant_id)
        if not force:
            q = q.where((BillingFinanceOutbox.next_attempt_at.is_(None)) | (BillingFinanceOutbox.next_attempt_at <= now))
        rows = [r for r in s.execute(q.order_by(BillingFinanceOutbox.created_at).limit(limit * 4)).all()]
    if only is not None:
        wanted = {(a, str(b)) for a, b in only}
        rows = [r for r in rows if (r.source, r.source_id) in wanted]
    rows = rows[:limit]

    sent = failed = 0
    for r in rows:
        err = None
        try:
            await poster(r.tenant_id, r.payload)
        except Exception as exc:  # noqa: BLE001 - recorded, retried later
            err = f"{type(exc).__name__}: {exc}"[:MAX_ERROR]
        with session_factory() as s:
            row = s.get(BillingFinanceOutbox, r.id)
            if row is None:
                continue
            row.attempts = (row.attempts or 0) + 1
            if err is None:
                row.status, row.last_error, row.next_attempt_at = "sent", None, None
                sent += 1
            else:
                row.status, row.last_error = "failed", err
                row.next_attempt_at = datetime.now(timezone.utc) + backoff(row.attempts)
                failed += 1
                logger.warning("finance outbox %s %s failed (attempt %s): %s", r.source, r.source_id, row.attempts, err)
    return {"attempted": len(rows), "sent": sent, "failed": failed}


async def deliver_after_commit(tenant_id: uuid.UUID, entries: Iterable[dict], **kw) -> None:
    """Best-effort immediate delivery of entries that were just committed to the outbox."""
    only = [(e["source"], e["source_id"]) for e in entries]
    if not only:
        return
    try:
        await deliver(tenant_id, only=only, force=True, **kw)
    except Exception:  # noqa: BLE001 - the worker/retry endpoint will pick the rows up
        logger.exception("immediate finance delivery failed; rows stay in the outbox")


def worker_enabled() -> bool:
    return os.getenv("BILLING_OUTBOX_WORKER_ENABLED", "false").strip().lower() == "true"


async def worker_loop(interval_seconds: int = 60) -> None:
    import asyncio
    logger.info("finance outbox worker started (every %ss)", interval_seconds)
    while True:
        try:
            await deliver()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("finance outbox pass failed")
        await asyncio.sleep(interval_seconds)
