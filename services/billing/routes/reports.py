"""Billing Reports - revenue, aging, collections.

Conventions (all documented here because they change what the numbers mean):
  * Calendar months are stepped properly and bounded in Africa/Johannesburg (SAST, UTC+2): a month's
    window is [00:00 SAST on the 1st, 00:00 SAST on the next 1st) converted to UTC instants.
  * "Invoiced" counts invoices that were actually issued: sent, partially_paid, overdue, paid.
    Draft and voided invoices are excluded. Credit notes are subtracted in the month they are
    issued, except those against a VOIDED invoice (that invoice is already excluded in full).
  * Collection rate = collected_in_period / invoiced_in_period over the SAME cohort (invoices created
    in the month); clamped to 0..100 and null when nothing was invoiced.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import aliased

from services.common.auth import AuthContext, get_auth_context
from services.billing import calc
from services.billing.access import require_tier
from services.billing.database import get_session
from services.billing.models import DunningAction, Invoice, Payment, PaymentArrangement
from services.billing.schemas import AgingBucket, CollectionsReportItem, RevenueReportItem

router = APIRouter(prefix="/reports", tags=["Reports"], dependencies=[Depends(require_tier("reader"))])

ISSUED = ["sent", "partially_paid", "overdue", "paid"]
ZERO = Decimal("0.00")


def _sum(session, expr, *filters) -> Decimal:
    return session.query(func.coalesce(func.sum(expr), 0)).filter(*filters).scalar() or ZERO


def invoiced_net(session, tenant_id, lo, hi) -> Decimal:
    gross = _sum(session, Invoice.total_zar, Invoice.tenant_id == tenant_id, Invoice.status.in_(ISSUED),
                 Invoice.credit_note_of.is_(None), Invoice.created_at >= lo, Invoice.created_at < hi)
    orig = aliased(Invoice)
    credits = (
        session.query(func.coalesce(func.sum(Invoice.total_zar), 0))
        .join(orig, orig.id == Invoice.credit_note_of)
        .filter(Invoice.tenant_id == tenant_id, Invoice.credit_note_of.isnot(None),
                Invoice.status.in_(["paid", "credit_issued"]), orig.status != "voided",
                Invoice.created_at >= lo, Invoice.created_at < hi)
        .scalar()
    ) or ZERO
    return gross + credits  # credit note totals are negative


# ---------------------------------------------------------------------------
# GET /reports/revenue - Revenue by period
# ---------------------------------------------------------------------------

@router.get("/revenue", response_model=list[RevenueReportItem])
def revenue_report(
    ctx: AuthContext = Depends(get_auth_context),
    months: int = Query(6, ge=1, le=24),
):
    with get_session() as session:
        results = []
        for first in calc.month_starts(calc.today_sast(), months):
            lo, hi = calc.month_bounds_utc(first)
            invoiced = invoiced_net(session, ctx.tenant_id, lo, hi)
            paid = _sum(session, Payment.amount_zar, Payment.tenant_id == ctx.tenant_id,
                        Payment.status == "completed", Payment.created_at >= lo, Payment.created_at < hi)
            results.append(RevenueReportItem(
                period=first.strftime("%Y-%m"),
                total_invoiced_zar=invoiced,
                total_paid_zar=paid,
                total_outstanding_zar=max(ZERO, invoiced - paid),
            ))
        return results


# ---------------------------------------------------------------------------
# GET /reports/aging - Accounts receivable aging
# ---------------------------------------------------------------------------

def bucket_totals(rows, today) -> dict:
    """rows: iterable of (due_date, outstanding). Returns {key: {count,total}} for new + legacy keys."""
    buckets = {k: {"count": 0, "total": ZERO} for k in calc.AGING_KEYS}
    for due, outstanding in rows:
        for key in calc.aging_keys((today - due).days):
            buckets[key]["count"] += 1
            buckets[key]["total"] += outstanding
    return buckets


@router.get("/aging", response_model=list[AgingBucket])
def aging_report(
    ctx: AuthContext = Depends(get_auth_context),
):
    """New distinct buckets (current, 1_30, 31_60, 61_90, 90_plus) plus the legacy keys
    (30_days, 60_days, 90_days_plus = over 60) flagged legacy=true. Do not add legacy and new rows."""
    with get_session() as session:
        unpaid = (
            session.query(Invoice.due_date, Invoice.total_zar - Invoice.amount_paid_zar)
            .filter(
                Invoice.tenant_id == ctx.tenant_id,
                Invoice.status.in_(["sent", "partially_paid", "overdue"]),
                Invoice.total_zar > Invoice.amount_paid_zar,
            )
            .all()
        )
        buckets = bucket_totals(unpaid, calc.today_sast())
        legacy = {"30_days", "60_days", "90_days_plus"}
        return [AgingBucket(bucket=k, count=v["count"], total_zar=v["total"], legacy=k in legacy)
                for k, v in buckets.items()]


# ---------------------------------------------------------------------------
# GET /reports/collections - Collection success rate
# ---------------------------------------------------------------------------

@router.get("/collections", response_model=list[CollectionsReportItem])
def collections_report(
    ctx: AuthContext = Depends(get_auth_context),
    months: int = Query(6, ge=1, le=24),
):
    with get_session() as session:
        results = []
        for first in calc.month_starts(calc.today_sast(), months):
            lo, hi = calc.month_bounds_utc(first)
            cohort = [Invoice.tenant_id == ctx.tenant_id, Invoice.status.in_(ISSUED),
                      Invoice.credit_note_of.is_(None), Invoice.created_at >= lo, Invoice.created_at < hi]
            invoiced = _sum(session, Invoice.total_zar, *cohort)
            # Collected from the same cohort: payments on invoices created in this month.
            collected = (
                session.query(func.coalesce(func.sum(Payment.amount_zar), 0))
                .join(Invoice, Invoice.id == Payment.invoice_id)
                .filter(Payment.tenant_id == ctx.tenant_id, Payment.status == "completed", *cohort)
                .scalar()
            ) or ZERO
            still_owed = _sum(session, Invoice.total_zar - Invoice.amount_paid_zar, *cohort,
                              Invoice.status.in_(["sent", "partially_paid", "overdue"]))

            suspensions = (
                session.query(func.count(DunningAction.id))
                .filter(DunningAction.tenant_id == ctx.tenant_id, DunningAction.action_type == "auto_suspend",
                        DunningAction.result == "suspended",
                        DunningAction.executed_at >= lo, DunningAction.executed_at < hi)
                .scalar()
            ) or 0
            arrangements = (
                session.query(func.count(PaymentArrangement.id))
                .filter(PaymentArrangement.tenant_id == ctx.tenant_id,
                        PaymentArrangement.created_at >= lo, PaymentArrangement.created_at < hi)
                .scalar()
            ) or 0

            results.append(CollectionsReportItem(
                period=first.strftime("%Y-%m"),
                total_overdue_zar=still_owed,
                total_collected_zar=collected,
                total_invoiced_zar=invoiced,
                collection_rate=calc.collection_rate(collected, invoiced),
                suspensions=suspensions,
                arrangements=arrangements,
            ))
        return results
