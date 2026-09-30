"""Per-seat billing orchestration: admin-service client, reconcile, worker.

Seat data comes from the admin service over HTTP (never its DB):

  GET {ADMIN_SERVICE_URL}/tenants/{tenant_id}/seats  (header x-internal-key)
      -> {"tenant_id": str, "current_seats": int,
          "events": [{"user_id": str, "delta": int, "reason": str, "at": iso}]}
     current_seats = active users + pending invites right now. `events` must
     cover at least the period being billed up to now (append-only seat_events).
  GET {ADMIN_SERVICE_URL}/platform/seat-usage
      -> list, or {"items"|"tenants": [...]}, of rows carrying "tenant_id".

Everything below the HTTP helpers takes a `seat_snapshot` dict of the first
shape so it can be tested without the admin service.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

import httpx
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from services.billing import seat_billing as sb
from services.billing.database import compute_vat, get_session, next_invoice_number
from services.billing.models import BillingPlan, Invoice, SeatBillingRun, SeatProrationCharge

logger = logging.getLogger("billing.seats")

DEFAULT_DUE_DAYS = 30
_WORKER_LOCK_KEY = 0x0B111_5EA8


def _admin_url() -> str:
    return os.getenv("ADMIN_SERVICE_URL", "http://admin:8013").rstrip("/")


def _headers() -> dict[str, str]:
    return {"x-internal-key": os.getenv("INTERNAL_SERVICE_KEY", "")}


def autocharge_enabled() -> bool:
    return os.getenv("SEAT_BILLING_AUTOCHARGE", "false").strip().lower() == "true"


def worker_enabled() -> bool:
    return os.getenv("SEAT_BILLING_WORKER_ENABLED", "false").strip().lower() == "true"


# ---------------------------------------------------------------------------
# Admin service client
# ---------------------------------------------------------------------------

async def fetch_seat_snapshot(tenant_id: uuid.UUID, timeout: float = 10.0) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"{_admin_url()}/tenants/{tenant_id}/seats", headers=_headers())
    resp.raise_for_status()
    return resp.json()


async def fetch_seat_tenants(timeout: float = 15.0) -> list[uuid.UUID]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"{_admin_url()}/platform/seat-usage", headers=_headers())
    resp.raise_for_status()
    data = resp.json()
    rows = data if isinstance(data, list) else (data.get("items") or data.get("tenants") or [])
    return [uuid.UUID(str(r["tenant_id"])) for r in rows if r.get("tenant_id")]


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

def resolve_unit_price(session, tenant_id: uuid.UUID) -> Decimal:
    """Per-seat unit price (ZAR/seat/cycle): the tenant's own active per_seat
    plan, else the platform's (tenant_id NULL) active per_seat plan, else env
    SEAT_UNIT_PRICE_ZAR, else 0 (which produces a 'skipped' run)."""
    for scope in (BillingPlan.tenant_id == tenant_id, BillingPlan.tenant_id.is_(None)):
        plan = session.execute(
            select(BillingPlan).where(
                scope, BillingPlan.pricing_model == "per_seat", BillingPlan.is_active.is_(True)
            ).order_by(BillingPlan.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        if plan is not None:
            return sb.money(plan.price)
    return sb.money(os.getenv("SEAT_UNIT_PRICE_ZAR", "0") or "0")


def peak_from_snapshot(snapshot: dict, period_start: date, period_end: date) -> int:
    events = snapshot.get("events") or []
    initial = sb.initial_seats_from_current(int(snapshot.get("current_seats", 0)), events, period_start)
    return sb.compute_peak_seats(events, initial, period_start, period_end)


# ---------------------------------------------------------------------------
# Reconcile
# ---------------------------------------------------------------------------

def run_to_dict(run: SeatBillingRun) -> dict:
    return {
        "id": str(run.id), "tenant_id": str(run.tenant_id),
        "period_start": run.period_start.isoformat(), "period_end": run.period_end.isoformat(),
        "peak_seats": run.peak_seats, "unit_price": str(run.unit_price), "amount": str(run.amount),
        "status": run.status, "invoice_id": str(run.invoice_id) if run.invoice_id else None,
    }


def _maybe_autocharge(invoice: Invoice) -> bool:
    """Hook for charging the tenant's saved Paystack authorization. OFF by
    default (SEAT_BILLING_AUTOCHARGE). No authorization code is stored on
    Subscription today, so even when enabled this only logs; wire the
    charge_authorization call here once one is."""
    if not autocharge_enabled():
        return False
    logger.warning("SEAT_BILLING_AUTOCHARGE on but no charge path wired; invoice %s left unpaid", invoice.number)
    return False


def reconcile_tenant(
    session,
    tenant_id: uuid.UUID,
    period_start: date,
    period_end: date,
    seat_snapshot: dict,
    unit_price: Optional[Decimal] = None,
    today: Optional[date] = None,
) -> tuple[SeatBillingRun, bool]:
    """Bill one tenant's cycle. Returns (run, created). A second call for the
    same tenant+period returns the existing run untouched (created=False)."""
    existing = session.execute(
        select(SeatBillingRun).where(
            SeatBillingRun.tenant_id == tenant_id, SeatBillingRun.period_start == period_start
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    unit = sb.money(unit_price) if unit_price is not None else resolve_unit_price(session, tenant_id)
    peak = peak_from_snapshot(seat_snapshot, period_start, period_end)

    charges = session.execute(
        select(SeatProrationCharge.amount).where(
            SeatProrationCharge.tenant_id == tenant_id, SeatProrationCharge.period_start == period_start
        )
    ).scalars().all()
    lines = sb.build_cycle_invoice_lines(peak, unit, period_start, period_end, charges)

    run = SeatBillingRun(
        tenant_id=tenant_id, period_start=period_start, period_end=period_end,
        peak_seats=peak, unit_price=unit, amount=sb.lines_total(lines), status="skipped",
    )
    if lines:
        subtotal = sb.lines_total(lines)
        invoice = Invoice(
            tenant_id=tenant_id,
            customer_id=tenant_id,  # OmniDome's customer is the tenant itself
            number=next_invoice_number(session, tenant_id),
            status="sent",  # issued, unpaid
            subtotal_zar=subtotal,
            vat_zar=compute_vat(subtotal),
            total_zar=subtotal + compute_vat(subtotal),
            due_date=(today or date.today()) + timedelta(days=DEFAULT_DUE_DAYS),
            billing_period_start=period_start,
            billing_period_end=period_end,
            line_items=[l.as_dict() for l in lines],
            notes="Per-seat billing: peak seats for the cycle",
        )
        session.add(invoice)
        session.flush()
        run.invoice_id = invoice.id
        run.status = "invoiced"
        _maybe_autocharge(invoice)
    try:
        with session.begin_nested():
            session.add(run)
            session.flush()
    except IntegrityError:  # concurrent worker won the race; its run stands
        won = session.execute(
            select(SeatBillingRun).where(
                SeatBillingRun.tenant_id == tenant_id, SeatBillingRun.period_start == period_start
            )
        ).scalar_one()
        return won, False
    return run, True


def record_proration_charge(
    session, tenant_id: uuid.UUID, added_seats: int, unit: Decimal,
    period_start: date, period_end: date, on: date,
) -> tuple[SeatProrationCharge, Optional[Invoice]]:
    """Invoice (issued, unpaid) and record the pro rata charge for added seats."""
    amount = sb.prorate_addition(unit, added_seats, period_start, period_end, on)
    invoice = None
    if amount > 0:
        vat = compute_vat(amount)
        rem = sb.remaining_days(period_start, period_end, on)
        invoice = Invoice(
            tenant_id=tenant_id, customer_id=tenant_id,
            number=next_invoice_number(session, tenant_id), status="sent",
            subtotal_zar=amount, vat_zar=vat, total_zar=amount + vat,
            due_date=on + timedelta(days=DEFAULT_DUE_DAYS),
            billing_period_start=on, billing_period_end=period_end,
            line_items=[{
                "description": f"OmniDome seats - {added_seats} added seat(s), pro rata {rem}/{sb.cycle_days(period_start, period_end)} days",
                "quantity": added_seats, "unit_price_zar": str(unit), "total_zar": str(amount),
                "line_type": "seat_proration",
                "period_start": on.isoformat(), "period_end": period_end.isoformat(),
            }],
            notes="Per-seat billing: pro rata charge for seats added mid-cycle",
        )
        session.add(invoice)
        session.flush()
        _maybe_autocharge(invoice)
    charge = SeatProrationCharge(
        tenant_id=tenant_id, period_start=period_start, period_end=period_end,
        added_seats=added_seats, unit_price=unit, amount=amount, charged_on=on,
        invoice_id=invoice.id if invoice else None,
    )
    session.add(charge)
    session.flush()
    return charge, invoice


# ---------------------------------------------------------------------------
# Scheduler (off by default). Billing has no in-process worker; its existing
# pattern is a cron-callable endpoint (/dunning/process). This loop is the same
# job on a timer: it opens its own session per tenant, is idempotent (run per
# tenant+period), and takes a Postgres advisory lock so only one uvicorn
# worker runs a pass.
# ---------------------------------------------------------------------------

async def run_reconcile_pass(today: Optional[date] = None) -> list[dict]:
    period_start, period_end = sb.previous_month_period(today or date.today())
    results: list[dict] = []
    for tenant_id in await fetch_seat_tenants():
        try:
            snapshot = await fetch_seat_snapshot(tenant_id)
            with get_session() as session:  # own session per tenant
                run, created = reconcile_tenant(session, tenant_id, period_start, period_end, snapshot, today=today)
                results.append({**run_to_dict(run), "created": created})
        except Exception:
            logger.exception("seat reconcile failed for tenant %s", tenant_id)
    return results


def _try_worker_lock() -> bool:
    from services.common.db import get_engine

    engine = get_engine()
    if engine.dialect.name != "postgresql":
        return True
    with engine.connect() as conn:
        # xact-scoped lock would release at once; a session lock is dropped when this connection closes,
        # which is fine: it only guards the instant of the check, idempotency covers the rest.
        got = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _WORKER_LOCK_KEY}).scalar()
        if got:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _WORKER_LOCK_KEY})
        conn.commit()
    return bool(got)


async def worker_loop(interval_seconds: int = 6 * 3600) -> None:
    """Every few hours: on the 1st-3rd of a month reconcile the month just ended."""
    logger.info("seat billing worker started (interval %ss)", interval_seconds)
    while True:
        try:
            today = datetime.now(timezone.utc).date()
            if today.day <= 3 and _try_worker_lock():
                out = await run_reconcile_pass(today)
                logger.info("seat billing pass: %d tenants", len(out))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("seat billing worker pass failed")
        await asyncio.sleep(interval_seconds)
