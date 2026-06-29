"""Dashboard aggregation & rule-based insight endpoints for the CRM module UI.

Reads CustomerLifecycle / RetentionPrediction directly via cross-service DB
reads, same convention as customer_360.py — all services share one Postgres.
No LLM calls: every "insight" here is a deterministic rule over real rows.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text

from services.common.auth import AuthContext, get_auth_context
from services.crm.database import get_session
from services.crm.models import ActivityEvent, Customer, Lead
from services.lifecycle.models import CustomerLifecycle
from services.retention.batch_churn import RetentionPrediction

logger = logging.getLogger("crm.dashboard")

router = APIRouter(tags=["Dashboard"])


def _last_n_months(n: int, now: datetime) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year, month = now.year, now.month
    for _ in range(n):
        months.append((year, month))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    months.reverse()
    return months


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) if month == 12 else datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


def _relative_time(dt: Optional[datetime], now: datetime) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    seconds = delta.total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} minutes ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)} hours ago"
    days = int(seconds // 86400)
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    return dt.strftime("%Y-%m-%d")


def _pct_change(current: float, previous: float) -> Optional[str]:
    if previous == 0:
        return None
    change = (current - previous) / previous * 100
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.1f}%"


@router.get("/customers/dashboard-summary")
async def dashboard_summary(ctx: AuthContext = Depends(get_auth_context)):
    now = datetime.now(timezone.utc)

    async with get_session() as session:
        total_customers = (
            await session.execute(select(func.count(Customer.id)).where(Customer.tenant_id == ctx.tenant_id))
        ).scalar_one()

        status_counts_rows = (
            await session.execute(
                select(Customer.status, func.count(Customer.id))
                .where(Customer.tenant_id == ctx.tenant_id)
                .group_by(Customer.status)
            )
        ).all()
        status_counts = {row[0]: row[1] for row in status_counts_rows}

        # 6-month customer growth (cumulative active count as of month end) & churn (churned that month)
        customer_growth = []
        for year, month in _last_n_months(6, now):
            start, end = _month_bounds(year, month)
            active_as_of_end = (
                await session.execute(
                    select(func.count(Customer.id)).where(
                        Customer.tenant_id == ctx.tenant_id,
                        Customer.created_at < end,
                        Customer.status != "churned",
                    )
                )
            ).scalar_one()
            churned_this_month = (
                await session.execute(
                    select(func.count(Customer.id)).where(
                        Customer.tenant_id == ctx.tenant_id,
                        Customer.status == "churned",
                        Customer.updated_at >= start,
                        Customer.updated_at < end,
                    )
                )
            ).scalar_one()
            customer_growth.append(
                {"month": start.strftime("%b"), "customers": active_as_of_end, "churn": churned_this_month}
            )

        # 4-week lead generation & conversion
        lead_funnel = []
        for i in range(3, -1, -1):
            week_end = now - timedelta(days=7 * i)
            week_start = week_end - timedelta(days=7)
            leads_created = (
                await session.execute(
                    select(func.count(Lead.id)).where(
                        Lead.tenant_id == ctx.tenant_id,
                        Lead.created_at >= week_start,
                        Lead.created_at < week_end,
                    )
                )
            ).scalar_one()
            leads_converted = (
                await session.execute(
                    select(func.count(Lead.id)).where(
                        Lead.tenant_id == ctx.tenant_id,
                        Lead.status == "converted",
                        Lead.updated_at >= week_start,
                        Lead.updated_at < week_end,
                    )
                )
            ).scalar_one()
            lead_funnel.append({"week": f"W{4 - i}", "leads": leads_created, "converted": leads_converted})

        total_leads = (
            await session.execute(select(func.count(Lead.id)).where(Lead.tenant_id == ctx.tenant_id))
        ).scalar_one()
        lead_status_rows = (
            await session.execute(
                select(Lead.status, func.count(Lead.id))
                .where(Lead.tenant_id == ctx.tenant_id)
                .group_by(Lead.status)
            )
        ).all()
        lead_status_counts = {row[0]: row[1] for row in lead_status_rows}
        active_leads = sum(lead_status_counts.get(s, 0) for s in ("new", "contacted", "qualified"))
        converted_leads = lead_status_counts.get("converted", 0)
        conversion_rate = round((converted_leads / total_leads * 100), 1) if total_leads else 0.0

        mrr_row = (
            await session.execute(
                select(func.avg(CustomerLifecycle.monthly_recurring_revenue), func.count(CustomerLifecycle.id))
                .select_from(CustomerLifecycle)
                .join(Customer, Customer.id == CustomerLifecycle.customer_id)
                .where(Customer.tenant_id == ctx.tenant_id, CustomerLifecycle.monthly_recurring_revenue > 0)
            )
        ).one()
        avg_mrr = float(mrr_row[0] or 0)
        customers_with_mrr = mrr_row[1] or 0

    customers_change = (
        _pct_change(customer_growth[-1]["customers"], customer_growth[-2]["customers"])
        if len(customer_growth) >= 2
        else None
    )
    leads_change = (
        _pct_change(lead_funnel[-1]["leads"], lead_funnel[-2]["leads"]) if len(lead_funnel) >= 2 else None
    )

    flashcard_kpis = [
        {
            "id": "1",
            "title": "Total Customers",
            "value": str(total_customers),
            "change": customers_change or "",
            "changeType": "positive" if (customers_change or "").startswith("+") else "neutral",
            "iconKey": "customers",
            "backTitle": "Customer Breakdown",
            "backDetails": [
                {"label": "Active", "value": str(status_counts.get("active", 0))},
                {"label": "Suspended", "value": str(status_counts.get("suspended", 0))},
                {"label": "Churned", "value": str(status_counts.get("churned", 0))},
            ],
            "backInsight": f"{status_counts.get('active', 0)} of {total_customers} customers are active.",
        },
        {
            "id": "2",
            "title": "Active Leads",
            "value": str(active_leads),
            "change": leads_change or "",
            "changeType": "positive" if (leads_change or "").startswith("+") else "neutral",
            "iconKey": "leads",
            "backTitle": "Lead Pipeline",
            "backDetails": [
                {"label": "New", "value": str(lead_status_counts.get("new", 0))},
                {"label": "Contacted", "value": str(lead_status_counts.get("contacted", 0))},
                {"label": "Qualified", "value": str(lead_status_counts.get("qualified", 0))},
            ],
            "backInsight": f"{lead_status_counts.get('qualified', 0)} leads are qualified and ready to convert.",
        },
        {
            "id": "3",
            "title": "Conversion Rate",
            "value": f"{conversion_rate}%",
            "change": "",
            "changeType": "neutral",
            "iconKey": "conversion",
            "backTitle": "Conversion Detail",
            "backDetails": [
                {"label": "Converted", "value": str(converted_leads)},
                {"label": "Lost", "value": str(lead_status_counts.get("lost", 0))},
                {"label": "Total Leads", "value": str(total_leads)},
            ],
            "backInsight": f"{converted_leads} of {total_leads} leads have converted to customers.",
        },
        {
            "id": "4",
            "title": "Avg. Revenue per Customer",
            "value": f"R {avg_mrr:,.0f}",
            "change": "",
            "changeType": "neutral",
            "iconKey": "revenue",
            "backTitle": "Revenue Detail",
            "backDetails": [
                {"label": "Customers with billing data", "value": str(customers_with_mrr)},
            ],
            "backInsight": "Average monthly recurring revenue across customers with an active subscription.",
        },
    ]

    return {
        "totalCustomers": total_customers,
        "activeLeads": active_leads,
        "conversionRate": conversion_rate,
        "avgRevenuePerCustomer": avg_mrr,
        "customerData": customer_growth,
        "leadData": lead_funnel,
        "flashcardKPIs": flashcard_kpis,
    }


@router.get("/customers/activities")
async def list_activities(ctx: AuthContext = Depends(get_auth_context), limit: int = 10):
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        rows = (
            await session.execute(
                select(ActivityEvent, Customer.first_name, Customer.last_name)
                .join(Customer, Customer.id == ActivityEvent.customer_id)
                .where(ActivityEvent.tenant_id == ctx.tenant_id)
                .order_by(ActivityEvent.created_at.desc())
                .limit(limit)
            )
        ).all()

    type_map = {"signup": "create", "status_change": "update", "churn_risk": "assign"}
    activities = []
    for event, first_name, last_name in rows:
        activities.append(
            {
                "id": str(event.id),
                "user": f"{first_name} {last_name}",
                "action": event.event_type.replace("_", " "),
                "target": event.summary,
                "time": _relative_time(event.created_at, now),
                "type": type_map.get(event.event_type, "update"),
            }
        )
    return activities


@router.get("/tasks")
async def list_crm_tasks(ctx: AuthContext = Depends(get_auth_context), limit: int = 10):
    """Reads the shared `tasks` table (owned by master_schema.sql, not CRM)."""
    async with get_session() as session:
        rows = (
            await session.execute(
                text(
                    """
                    select t.id, t.subject, t.priority, t.status, t.due_date,
                           coalesce(u.full_name, 'Unassigned') as assignee
                    from tasks t
                    left join users u on u.id = t.user_id
                    where t.tenant_id = :tenant_id
                    order by t.due_date asc nulls last
                    limit :limit
                    """
                ),
                {"tenant_id": str(ctx.tenant_id), "limit": limit},
            )
        ).mappings().all()

    return [
        {
            "id": str(row["id"]),
            "title": row["subject"],
            "priority": (row["priority"] or "normal").lower(),
            "status": (row["status"] or "todo").lower().replace(" ", "-"),
            "dueDate": row["due_date"].isoformat() if row["due_date"] else "",
            "assignee": row["assignee"],
        }
        for row in rows
    ]


@router.get("/customers/insights")
async def customer_insights(ctx: AuthContext = Depends(get_auth_context)):
    """Rule-based recommendations & issues computed from real churn predictions and stalled leads."""
    now = datetime.now(timezone.utc)
    stalled_cutoff = now - timedelta(days=14)

    async with get_session() as session:
        risk_rows = (
            await session.execute(
                select(RetentionPrediction, Customer.first_name, Customer.last_name)
                .join(Customer, Customer.id == RetentionPrediction.customer_id)
                .where(
                    RetentionPrediction.tenant_id == ctx.tenant_id,
                    RetentionPrediction.risk_level.in_(["HIGH", "CRITICAL"]),
                )
                .order_by(RetentionPrediction.risk_score.desc())
                .limit(5)
            )
        ).all()

        stalled_rows = (
            await session.execute(
                select(Lead)
                .where(
                    Lead.tenant_id == ctx.tenant_id,
                    Lead.status.in_(["new", "contacted", "qualified"]),
                    Lead.updated_at < stalled_cutoff,
                )
                .order_by(Lead.updated_at.asc())
                .limit(5)
            )
        ).scalars().all()

    ai_recommendations = []
    issues = []
    for idx, (prediction, first_name, last_name) in enumerate(risk_rows, start=1):
        name = f"{first_name} {last_name}"
        ai_recommendations.append(
            {
                "id": f"churn-{idx}",
                "title": f"Reach out to {name} before they churn",
                "description": f"{name} has a {prediction.risk_level.lower()} churn risk "
                f"({prediction.risk_score:.0f}/100), primarily due to {prediction.primary_reason or 'unknown factors'}.",
                "impact": "high" if prediction.risk_level == "CRITICAL" else "medium",
                "category": "Retention",
            }
        )
        issues.append(
            {
                "id": f"churn-issue-{idx}",
                "title": f"{name} flagged as {prediction.risk_level.lower()} churn risk",
                "severity": "high" if prediction.risk_level == "CRITICAL" else "medium",
                "status": "open",
                "assignee": "Account Owner",
                "time": _relative_time(prediction.created_at, now),
            }
        )

    for idx, lead in enumerate(stalled_rows, start=1):
        days_stalled = (now - lead.updated_at.replace(tzinfo=timezone.utc)).days
        ai_recommendations.append(
            {
                "id": f"stalled-{idx}",
                "title": f"Follow up with {lead.first_name} {lead.last_name}",
                "description": f"This lead has been in '{lead.status}' status for {days_stalled} days without movement.",
                "impact": "medium",
                "category": "Sales",
            }
        )
        issues.append(
            {
                "id": f"stalled-issue-{idx}",
                "title": f"Lead {lead.first_name} {lead.last_name} stalled in '{lead.status}'",
                "severity": "low",
                "status": "open",
                "assignee": "Sales",
                "time": _relative_time(lead.updated_at, now),
            }
        )

    return {"aiRecommendations": ai_recommendations, "issues": issues}
