"""Per-seat billing routes: reconcile a cycle, list runs, preview/charge pro rata.

Sync session pattern like the sibling billing routes: `get_session()` is the
sync context manager (commit on exit); handlers are `async def` only so they
can await the admin-service HTTP call, which is made BEFORE opening a session.
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from services.billing import seat_billing as sb
from services.billing import seat_runs
from services.billing.database import get_session
from services.billing.models import SeatBillingRun
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("billing.seats")

router = APIRouter(prefix="/billing/seats", tags=["Seat billing"])


def _is_operator(request: Request, ctx: AuthContext) -> bool:
    """platform_admin, or a caller presenting the internal service key."""
    if ctx.is_platform_admin:
        return True
    expected = os.getenv("INTERNAL_SERVICE_KEY", "")
    provided = request.headers.get("x-internal-key") or ""
    return bool(expected) and secrets.compare_digest(provided, expected)


# Roles allowed to read a tenant's seat billing (runs, proration quotes) besides operators.
_BILLING_READ_ROLES = {"owner", "org_admin", "admin", "tenant_admin", "billing", "billing_admin", "platform_admin"}


def _can_read_billing(request: Request, ctx: AuthContext) -> bool:
    return _is_operator(request, ctx) or bool({str(r).lower() for r in ctx.roles} & _BILLING_READ_ROLES)


def _require_billing_reader(request: Request, ctx: AuthContext) -> None:
    if not _can_read_billing(request, ctx):
        raise HTTPException(status_code=403, detail="Tenant admin, billing role or platform_admin required")


# Per-seat price: never negative, sane ceiling (ZAR per seat per cycle), cents precision.
def UnitPrice():
    return Field(default=None, ge=0, le=Decimal("100000"), max_digits=12, decimal_places=2)


def _require_operator(request: Request, ctx: AuthContext) -> None:
    if not _is_operator(request, ctx):
        raise HTTPException(status_code=403, detail="platform_admin or internal service key required")


def _period(value: Optional[str]) -> tuple[date, date]:
    try:
        return sb.parse_period(value) if value else sb.previous_month_period(date.today())
    except Exception:
        raise HTTPException(status_code=422, detail="period must be YYYY-MM")


async def _snapshot(tenant_id: uuid.UUID, provided: Optional[dict]) -> dict:
    if provided is not None:
        return provided
    try:
        return await seat_runs.fetch_seat_snapshot(tenant_id)
    except httpx.HTTPError as exc:
        logger.warning("admin seat fetch failed for %s: %s", tenant_id, exc)
        raise HTTPException(status_code=502, detail="Could not read seat data from the admin service")


class ReconcileRequest(BaseModel):
    tenant_id: Optional[uuid.UUID] = None   # omitted: every tenant the admin service reports
    period: Optional[str] = Field(default=None, description="YYYY-MM; default = previous calendar month")
    seat_snapshot: Optional[dict[str, Any]] = Field(default=None, description="Override admin data (tests)")
    unit_price: Optional[Decimal] = UnitPrice()


@router.post("/reconcile")
async def reconcile(body: ReconcileRequest, request: Request, ctx: AuthContext = Depends(get_auth_context)):
    """Bill the cycle's peak seats. Idempotent per tenant+period."""
    _require_operator(request, ctx)
    period_start, period_end = _period(body.period)
    unit = None if body.unit_price is None else sb.money(body.unit_price)

    if body.tenant_id is None:
        if body.seat_snapshot is not None:
            raise HTTPException(status_code=422, detail="seat_snapshot needs a tenant_id")
        try:
            tenants = await seat_runs.fetch_seat_tenants()
        except httpx.HTTPError:
            raise HTTPException(status_code=502, detail="Could not read seat usage from the admin service")
        out = []
        for tid in tenants:
            snap = await _snapshot(tid, None)
            with get_session() as session:
                run, created = seat_runs.reconcile_tenant(session, tid, period_start, period_end, snap, unit)
                out.append({**seat_runs.run_to_dict(run), "created": created})
        return {"runs": out}

    snap = await _snapshot(body.tenant_id, body.seat_snapshot)
    with get_session() as session:
        run, created = seat_runs.reconcile_tenant(session, body.tenant_id, period_start, period_end, snap, unit)
        return {**seat_runs.run_to_dict(run), "created": created}


@router.get("/runs")
async def list_runs(
    request: Request,
    tenant_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    ctx: AuthContext = Depends(get_auth_context),
):
    _require_billing_reader(request, ctx)
    target = ctx.tenant_id
    if tenant_id and tenant_id != ctx.tenant_id:
        _require_operator(request, ctx)
        target = tenant_id
    with get_session() as session:
        rows = session.execute(
            select(SeatBillingRun).where(SeatBillingRun.tenant_id == target)
            .order_by(SeatBillingRun.period_start.desc()).limit(limit)
        ).scalars().all()
        return [seat_runs.run_to_dict(r) for r in rows]


class ProrationRequest(BaseModel):
    tenant_id: Optional[uuid.UUID] = None
    added_seats: int = Field(gt=0)
    on: Optional[date] = None               # default today
    unit_price: Optional[Decimal] = UnitPrice()
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=128)


def _proration_target(body: ProrationRequest, request: Request, ctx: AuthContext) -> uuid.UUID:
    if body.tenant_id and body.tenant_id != ctx.tenant_id:
        _require_operator(request, ctx)
        return body.tenant_id
    return ctx.tenant_id


@router.post("/proration-preview")
async def proration_preview(body: ProrationRequest, request: Request, ctx: AuthContext = Depends(get_auth_context)):
    """What adding seats today would cost pro rata (ex VAT). Writes nothing."""
    _require_billing_reader(request, ctx)
    tenant_id = _proration_target(body, request, ctx)
    on = body.on or date.today()
    period_start, period_end = sb.month_period(on.year, on.month)
    with get_session() as session:
        unit = sb.money(body.unit_price) if body.unit_price is not None else seat_runs.resolve_unit_price(session, tenant_id)
    amount = sb.prorate_addition(unit, body.added_seats, period_start, period_end, on)
    return {
        "tenant_id": str(tenant_id), "added_seats": body.added_seats, "unit_price": str(unit),
        "period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
        "remaining_days": sb.remaining_days(period_start, period_end, on),
        "cycle_days": sb.cycle_days(period_start, period_end),
        "amount_ex_vat": str(amount),
    }


@router.post("/prorate")
async def prorate_charge(
    body: ProrationRequest,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", max_length=128),
):
    """Invoice (issued, unpaid) and record the pro rata charge for seats added
    now; the cycle invoice later credits it. Operator only (called by admin
    when it adds seats). Send an Idempotency-Key header (or body idempotency_key) so a retry
    returns the original charge instead of billing twice."""
    _require_operator(request, ctx)
    tenant_id = _proration_target(body, request, ctx)
    on = body.on or date.today()
    period_start, period_end = sb.month_period(on.year, on.month)
    with get_session() as session:
        unit = sb.money(body.unit_price) if body.unit_price is not None else seat_runs.resolve_unit_price(session, tenant_id)
        charge, invoice = seat_runs.record_proration_charge(
            session, tenant_id, body.added_seats, unit, period_start, period_end, on,
            idempotency_key=idempotency_key or body.idempotency_key)
        return {
            "charge_id": str(charge.id), "amount_ex_vat": str(charge.amount),
            "invoice_id": str(invoice.id) if invoice else None,
            "invoice_number": invoice.number if invoice else None,
        }
