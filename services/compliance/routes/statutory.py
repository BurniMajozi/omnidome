"""
Compliance Service — EMP201 working papers (prepare / mark-filed).

This service NEVER files with SARS and holds no SARS credentials. It prepares a
working paper from real, paid payslips and records a human's confirmation that
they filed it on eFiling:

    POST /statutory/emp201/prepare          build/refresh the working paper (status PREPARED_NOT_FILED)
    POST /statutory/emp201/{id}/mark-filed  hr/finance admin pastes the REAL PRN / receipt and the filing date
    GET  /statutory/emp201[/{id}]           list / read working papers

Figures come only from payslips of PAID / PARTIALLY_PAID payroll runs of the period;
with none they are null (never estimated). Rates are config defaults flagged
rates_verified=false.
"""
import json
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext
from services.common.db import get_async_session as get_db
from services.compliance import crud, sa_calendar, statutory
from services.compliance.access import filing_ctx, sensitive_ctx, tenant_str
from services.compliance.database import Emp201Workpaper

router = APIRouter(prefix="/statutory", tags=["statutory"])

_AGGREGATE_SQL = text(
    """
    SELECT count(DISTINCT p.employee_id),
           coalesce(sum(p.gross), 0), coalesce(sum(p.tax), 0),
           coalesce(sum(p.uif), 0), coalesce(sum(p.uif_employer), 0),
           coalesce(sum(p.sdl), 0), coalesce(sum(p.net), 0),
           string_agg(DISTINCT CAST(r.id AS text), ',')
    FROM payslips p
    JOIN payroll_runs r ON r.id = p.run_id
    WHERE p.tenant_id = :tid AND r.tenant_id = :tid
      AND r.period = :period AND r.status IN ('PAID', 'PARTIALLY_PAID')
    """
)


async def fetch_period_aggregate(db: AsyncSession, tenant: str, period: str) -> dict:
    """Statutory figures for one period from real paid payroll; all None when there is none."""
    row = (await db.execute(_AGGREGATE_SQL, {"tid": tenant, "period": period})).fetchone()
    return statutory.aggregate_payslips(row)


class PrepareIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period: str = Field(description="YYYY-MM")


class MarkFiledIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prn: str = Field(description="The real payment reference number shown on SARS eFiling")
    receipt_reference: Optional[str] = Field(None, max_length=100)
    filed_at: date


def workpaper_dict(w: Emp201Workpaper) -> dict:
    def num(v):
        return None if v is None else float(v)

    return {
        "id": w.id,
        "period": w.period,
        "status": w.status,
        "due_date": w.due_date.isoformat() if w.due_date else None,
        "due_date_note": w.due_date_note,
        "employee_count": w.employee_count,
        "gross_remuneration_zar": num(w.gross_remuneration),
        "paye_zar": num(w.paye),
        "uif_employee_zar": num(w.uif_employee),
        "uif_employer_zar": num(w.uif_employer),
        "sdl_zar": num(w.sdl),
        "total_liability_zar": num(w.total_liability),
        "payroll_run_ids": json.loads(w.payroll_run_ids) if w.payroll_run_ids else [],
        "rates_verified": bool(w.rates_verified),
        "assumptions": json.loads(w.assumptions) if w.assumptions else None,
        "note": w.note,
        "prepared_by": w.prepared_by,
        "prepared_at": w.prepared_at.isoformat() if w.prepared_at else None,
        "prn": w.prn,
        "receipt_reference": w.receipt_reference,
        "filed_at": w.filed_at.isoformat() if w.filed_at else None,
        "marked_filed_by": w.marked_filed_by,
        "marked_filed_at": w.marked_filed_at.isoformat() if w.marked_filed_at else None,
        "filed_by_this_service": False,
    }


@router.post("/emp201/prepare")
async def prepare_emp201(body: PrepareIn, ctx: AuthContext = Depends(sensitive_ctx), db: AsyncSession = Depends(get_db)):
    try:
        sa_calendar.parse_period(body.period)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    tenant = tenant_str(ctx)
    figures = await fetch_period_aggregate(db, tenant, body.period)
    due, due_note = sa_calendar.emp201_due_date(body.period)

    existing = (await db.execute(
        crud.scoped_select(Emp201Workpaper, ctx, Emp201Workpaper.period == body.period)
    )).scalar_one_or_none()
    if existing is not None and existing.status == "MARKED_FILED_BY_USER":
        raise HTTPException(409, "This period is already marked as filed; it cannot be re-prepared.")

    wp = existing or Emp201Workpaper(tenant_id=tenant, period=body.period)
    wp.status = "PREPARED_NOT_FILED"
    wp.due_date, wp.due_date_note = due, due_note
    wp.employee_count = figures["employee_count"]
    wp.gross_remuneration = figures["gross_remuneration"]
    wp.paye = figures["paye"]
    wp.uif_employee = figures["uif_employee"]
    wp.uif_employer = figures["uif_employer"]
    wp.sdl = figures["sdl"]
    wp.total_liability = figures["total_liability"]
    wp.payroll_run_ids = json.dumps(figures["run_ids"])
    wp.rates_verified = False
    wp.assumptions = json.dumps(statutory.load_rates().as_dict())
    wp.note = statutory.workpaper_note(figures)
    wp.prepared_by = str(ctx.user_id)
    wp.prepared_at = datetime.utcnow()
    if existing is None:
        db.add(wp)
    await db.commit()
    await db.refresh(wp)
    return workpaper_dict(wp)


@router.post("/emp201/{workpaper_id}/mark-filed")
async def mark_emp201_filed(
    workpaper_id: int, body: MarkFiledIn,
    ctx: AuthContext = Depends(filing_ctx), db: AsyncSession = Depends(get_db),
):
    """Record that a person filed this EMP201 on SARS eFiling. hr / finance admin only."""
    wp = await crud.get_owned(db, ctx, Emp201Workpaper, workpaper_id, "Working paper")
    if wp.status == "MARKED_FILED_BY_USER":
        raise HTTPException(409, "Already marked as filed.")
    if not statutory.is_valid_prn(body.prn):
        raise HTTPException(422, "PRN must be 16-19 letters/digits, exactly as shown on SARS eFiling.")
    if body.filed_at > sa_calendar.sast_today():
        raise HTTPException(422, "filed_at cannot be in the future.")
    period_start, _ = sa_calendar.period_bounds(wp.period)
    if body.filed_at < period_start:
        raise HTTPException(422, "filed_at cannot be before the start of the return period.")
    wp.status = "MARKED_FILED_BY_USER"
    wp.prn = statutory.normalise_prn(body.prn).upper()
    wp.receipt_reference = body.receipt_reference
    wp.filed_at = body.filed_at
    wp.marked_filed_by = str(ctx.user_id)
    wp.marked_filed_at = datetime.utcnow()
    wp.note = "Marked as filed by a user from the SARS eFiling PRN/receipt they entered; not verified with SARS."
    await db.commit()
    await db.refresh(wp)
    return workpaper_dict(wp)


@router.get("/emp201")
async def list_emp201(ctx: AuthContext = Depends(sensitive_ctx), db: AsyncSession = Depends(get_db)):
    rows = await crud.list_rows(db, ctx, Emp201Workpaper, order_by=Emp201Workpaper.period.desc())
    return {"items": [workpaper_dict(w) for w in rows]}


@router.get("/emp201/{workpaper_id}")
async def get_emp201(workpaper_id: int, ctx: AuthContext = Depends(sensitive_ctx), db: AsyncSession = Depends(get_db)):
    return workpaper_dict(await crud.get_owned(db, ctx, Emp201Workpaper, workpaper_id, "Working paper"))
