"""Billing Reports — revenue, aging, collections."""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, func

from services.common.auth import AuthContext, get_auth_context
from services.billing.database import get_session
from services.billing.models import DunningAction, Invoice, Payment, PaymentArrangement
from services.billing.schemas import AgingBucket, CollectionsReportItem, RevenueReportItem

router = APIRouter(prefix="/reports", tags=["Reports"])


# ---------------------------------------------------------------------------
# GET /reports/revenue — Revenue by period
# ---------------------------------------------------------------------------

@router.get("/revenue", response_model=list[RevenueReportItem])
def revenue_report(
    ctx: AuthContext = Depends(get_auth_context),
    months: int = Query(6, ge=1, le=24),
):
    with get_session() as session:
        today = date.today()
        results = []

        for i in range(months):
            # Calculate month boundaries
            first_of_month = today.replace(day=1) - timedelta(days=30 * i)
            first_of_month = first_of_month.replace(day=1)
            if first_of_month.month == 12:
                next_month = first_of_month.replace(year=first_of_month.year + 1, month=1)
            else:
                next_month = first_of_month.replace(month=first_of_month.month + 1)

            period_label = first_of_month.strftime("%Y-%m")

            # Total invoiced
            invoiced = (
                session.query(func.coalesce(func.sum(Invoice.total_zar), 0))
                .filter(
                    Invoice.tenant_id == ctx.tenant_id,
                    Invoice.created_at >= first_of_month,
                    Invoice.created_at < next_month,
                    Invoice.total_zar > 0,  # exclude credit notes
                )
                .scalar()
            ) or Decimal("0.00")

            # Total paid
            paid = (
                session.query(func.coalesce(func.sum(Payment.amount_zar), 0))
                .filter(
                    Payment.tenant_id == ctx.tenant_id,
                    Payment.status == "completed",
                    Payment.created_at >= first_of_month,
                    Payment.created_at < next_month,
                )
                .scalar()
            ) or Decimal("0.00")

            results.append(RevenueReportItem(
                period=period_label,
                total_invoiced_zar=invoiced,
                total_paid_zar=paid,
                total_outstanding_zar=max(Decimal("0.00"), invoiced - paid),
            ))

        return results


# ---------------------------------------------------------------------------
# GET /reports/aging — Accounts receivable aging (30/60/90 days)
# ---------------------------------------------------------------------------

@router.get("/aging", response_model=list[AgingBucket])
def aging_report(
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        today = date.today()

        # Get all unpaid invoices
        unpaid = (
            session.query(Invoice)
            .filter(
                Invoice.tenant_id == ctx.tenant_id,
                Invoice.status.in_(["sent", "partially_paid", "overdue"]),
                Invoice.total_zar > Invoice.amount_paid_zar,
            )
            .all()
        )

        buckets = {
            "current": {"count": 0, "total": Decimal("0.00")},
            "30_days": {"count": 0, "total": Decimal("0.00")},
            "60_days": {"count": 0, "total": Decimal("0.00")},
            "90_days_plus": {"count": 0, "total": Decimal("0.00")},
        }

        for inv in unpaid:
            outstanding = inv.total_zar - inv.amount_paid_zar
            days = (today - inv.due_date).days

            if days <= 0:
                bucket = "current"
            elif days <= 30:
                bucket = "30_days"
            elif days <= 60:
                bucket = "60_days"
            else:
                bucket = "90_days_plus"

            buckets[bucket]["count"] += 1
            buckets[bucket]["total"] += outstanding

        return [
            AgingBucket(bucket=k, count=v["count"], total_zar=v["total"])
            for k, v in buckets.items()
        ]


# ---------------------------------------------------------------------------
# GET /reports/collections — Collection success rate
# ---------------------------------------------------------------------------

@router.get("/collections", response_model=list[CollectionsReportItem])
def collections_report(
    ctx: AuthContext = Depends(get_auth_context),
    months: int = Query(6, ge=1, le=24),
):
    with get_session() as session:
        today = date.today()
        results = []

        for i in range(months):
            first_of_month = today.replace(day=1) - timedelta(days=30 * i)
            first_of_month = first_of_month.replace(day=1)
            if first_of_month.month == 12:
                next_month = first_of_month.replace(year=first_of_month.year + 1, month=1)
            else:
                next_month = first_of_month.replace(month=first_of_month.month + 1)

            period_label = first_of_month.strftime("%Y-%m")

            # Total overdue at that point
            overdue = (
                session.query(func.coalesce(
                    func.sum(Invoice.total_zar - Invoice.amount_paid_zar), 0
                ))
                .filter(
                    Invoice.tenant_id == ctx.tenant_id,
                    Invoice.status.in_(["overdue", "sent", "partially_paid"]),
                    Invoice.due_date < first_of_month,
                    Invoice.due_date >= first_of_month - timedelta(days=30),
                )
                .scalar()
            ) or Decimal("0.00")

            # Collected during that month from overdue
            collected = (
                session.query(func.coalesce(func.sum(Payment.amount_zar), 0))
                .filter(
                    Payment.tenant_id == ctx.tenant_id,
                    Payment.status == "completed",
                    Payment.created_at >= first_of_month,
                    Payment.created_at < next_month,
                )
                .scalar()
            ) or Decimal("0.00")

            rate = (collected / overdue * 100) if overdue > 0 else Decimal("0.00")

            # Suspensions count
            suspensions = (
                session.query(func.count(DunningAction.id))
                .filter(
                    DunningAction.tenant_id == ctx.tenant_id,
                    DunningAction.action_type == "auto_suspend",
                    DunningAction.executed_at >= first_of_month,
                    DunningAction.executed_at < next_month,
                )
                .scalar()
            ) or 0

            # Arrangements count
            arrangements = (
                session.query(func.count(PaymentArrangement.id))
                .filter(
                    PaymentArrangement.tenant_id == ctx.tenant_id,
                    PaymentArrangement.created_at >= first_of_month,
                    PaymentArrangement.created_at < next_month,
                )
                .scalar()
            ) or 0

            results.append(CollectionsReportItem(
                period=period_label,
                total_overdue_zar=overdue,
                total_collected_zar=collected,
                collection_rate=rate.quantize(Decimal("0.01")) if isinstance(rate, Decimal) else Decimal(str(round(rate, 2))),
                suspensions=suspensions,
                arrangements=arrangements,
            ))

        return results
