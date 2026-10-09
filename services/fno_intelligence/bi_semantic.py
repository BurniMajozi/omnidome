"""BI Studio semantic layer: a governed dataset registry and a query compiler.

There is NO free SQL anywhere. A query is a JSON spec (dataset, measures, dimensions, filters, time)
whose every field id is validated against the registry below. SQL text is assembled only from
registry-authored fragments; every user-supplied value (filter values, dates, tenant) travels as a bound
parameter. Cross-service tables are read inside begin_nested() and ALWAYS constrained by tenant_id.

Dialects: PostgreSQL in production, SQLite in unit tests. Registry fragments that differ are callables
taking the dialect name.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time as _time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Literal, Optional, Union

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import logging

logger = logging.getLogger("fno_intelligence.bi")

GRAINS = ("day", "week", "month", "quarter", "year")
MAX_LIMIT = 1000
DEFAULT_LIMIT = 500
MAX_MEASURES = 12
MAX_DIMENSIONS = 4
MAX_FILTERS = 20
MAX_IN_VALUES = 100
STATEMENT_TIMEOUT_MS = 8000
TIMEZONE = "Africa/Johannesburg"

Dialect = str  # "postgresql" | "sqlite"
Frag = Union[str, Callable[[Dialect], str]]


class BiQueryError(HTTPException):
    """Spec failed validation against the registry (HTTP 422)."""

    def __init__(self, message: str):
        super().__init__(422, message)


def _f(x: Optional[Frag], d: Dialect) -> str:
    return x(d) if callable(x) else (x or "")


# ── dialect helpers (registry fragments) ──────────────────────────────────

def today(d: Dialect) -> str:
    return "CURRENT_DATE" if d == "postgresql" else "date('now')"


def days_since(col: str) -> Callable[[Dialect], str]:
    return lambda d: f"(CURRENT_DATE - {col})" if d == "postgresql" else f"(julianday('now') - julianday({col}))"


def hours_between(a: str, b: str) -> Callable[[Dialect], str]:
    return lambda d: (f"(EXTRACT(EPOCH FROM ({b} - {a})) / 3600.0)" if d == "postgresql"
                      else f"((julianday({b}) - julianday({a})) * 24.0)")


# ── registry types ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Dimension:
    id: str
    label: str
    type: str                       # time | category | number
    expr: Frag                      # SQL expression (already cast to text for categories)
    kind: str = "ts"                # time dims: 'ts' (timestamp) | 'date'
    grains: tuple = GRAINS          # time dims only
    cardinality: str = "medium"     # category hint for chart suggestions: low (<=8) | medium | high
    sort: Optional[Frag] = None     # optional ordering expression (e.g. aging buckets)
    description: str = ""


@dataclass(frozen=True)
class Measure:
    id: str
    label: str
    agg: str                        # sum | count | avg | min | max | distinct | ratio
    sql: Callable[[Dialect], str]   # full aggregate expression
    format: str = "number"          # currency_zar | number | percent | duration
    unit: Optional[str] = None      # duration unit ('hours')
    description: str = ""
    additive: bool = False          # safe to stack / pie (sum or count)


@dataclass(frozen=True)
class Dataset:
    id: str
    label: str
    description: str
    category: str
    source_tables: tuple
    from_sql: str
    tenant_expr: str
    dimensions: tuple
    measures: tuple
    base_where: Optional[Frag] = None
    default_time: Optional[str] = None
    notes: str = ""

    def dim(self, i: str) -> Optional[Dimension]:
        return next((x for x in self.dimensions if x.id == i), None)

    def measure(self, i: str) -> Optional[Measure]:
        return next((x for x in self.measures if x.id == i), None)


def agg_measure(id_: str, label: str, agg: str, expr: Frag = "1", *, when: Optional[Frag] = None,
                format: str = "number", unit: Optional[str] = None, description: str = "") -> Measure:
    def sql(d: Dialect) -> str:
        e, w = _f(expr, d), _f(when, d)
        inner = f"CASE WHEN {w} THEN {e} END" if w else e
        if agg == "count":
            return f"COUNT(CASE WHEN {w} THEN 1 END)" if w else "COUNT(*)"
        if agg == "distinct":
            return f"COUNT(DISTINCT {inner})"
        if agg == "sum":
            return f"COALESCE(SUM({inner}), 0)"
        return f"{agg.upper()}({inner})"
    return Measure(id_, label, agg, sql, format, unit, description, additive=agg in ("sum", "count"))


def ratio_measure(id_: str, label: str, num: Measure, den: Measure, *, format: str = "percent",
                  description: str = "") -> Measure:
    def sql(d: Dialect) -> str:
        return f"CAST(({num.sql(d)}) AS DOUBLE PRECISION) / NULLIF(({den.sql(d)}), 0)"
    return Measure(id_, label, "ratio", sql, format, None, description)


def tdim(id_: str, label: str, col: str, kind: str = "ts", description: str = "") -> Dimension:
    return Dimension(id_, label, "time", col, kind=kind, description=description)


def cdim(id_: str, label: str, expr: Frag, cardinality: str = "medium", sort: Optional[Frag] = None,
         description: str = "") -> Dimension:
    return Dimension(id_, label, "category", expr, cardinality=cardinality, sort=sort, description=description)


# ── datasets ──────────────────────────────────────────────────────────────

def _build() -> dict[str, Dataset]:
    ds: list[Dataset] = []

    # billing: invoices ------------------------------------------------------
    open_status = "i.status IN ('sent','partially_paid','overdue')"
    inv_count = agg_measure("invoice_count", "Invoices", "count")
    invoiced = agg_measure("invoiced", "Invoiced (incl. VAT)", "sum", "i.total_zar", format="currency_zar")
    collected = agg_measure("collected", "Collected", "sum", "i.amount_paid_zar", format="currency_zar",
                            description="Sum of amount paid recorded on the invoices")
    billed_customers = agg_measure("customers_billed", "Customers billed", "distinct", "i.customer_id")
    ds.append(Dataset(
        id="billing_invoices", label="Billing: invoices", category="Billing",
        description="Issued invoices (drafts and voided invoices excluded). Credit notes are included at their stored value.",
        source_tables=("invoices", "subscriptions"),
        from_sql="invoices i LEFT JOIN subscriptions s ON s.id = i.subscription_id",
        tenant_expr="i.tenant_id", base_where="i.status NOT IN ('draft','voided')", default_time="created_at",
        dimensions=(
            tdim("created_at", "Invoice date", "i.created_at"),
            tdim("due_date", "Due date", "i.due_date", "date"),
            tdim("period_start", "Billing period start", "i.billing_period_start", "date"),
            cdim("status", "Invoice status", "CAST(i.status AS TEXT)", "low"),
            cdim("aging_bucket", "Aging bucket", lambda d: (
                f"CASE WHEN NOT ({open_status}) THEN 'Settled' WHEN i.due_date >= {today(d)} THEN 'Current' "
                f"WHEN {_f(days_since('i.due_date'), d)} <= 30 THEN '1-30 days' "
                f"WHEN {_f(days_since('i.due_date'), d)} <= 60 THEN '31-60 days' "
                f"WHEN {_f(days_since('i.due_date'), d)} <= 90 THEN '61-90 days' ELSE '90+ days' END"), "low",
                sort=lambda d: (
                    f"CASE WHEN NOT ({open_status}) THEN 6 WHEN i.due_date >= {today(d)} THEN 1 "
                    f"WHEN {_f(days_since('i.due_date'), d)} <= 30 THEN 2 WHEN {_f(days_since('i.due_date'), d)} <= 60 THEN 3 "
                    f"WHEN {_f(days_since('i.due_date'), d)} <= 90 THEN 4 ELSE 5 END"),
                description="Days past due for open invoices, as of today"),
            cdim("plan", "Plan", "COALESCE(s.plan, 'Unassigned')", "medium"),
            cdim("segment", "Segment", "COALESCE(s.segment, 'Unassigned')", "low"),
        ),
        measures=(
            inv_count, invoiced,
            agg_measure("invoiced_ex_vat", "Invoiced (excl. VAT)", "sum", "i.subtotal_zar", format="currency_zar"),
            agg_measure("vat", "VAT", "sum", "i.vat_zar", format="currency_zar"),
            collected,
            agg_measure("outstanding", "Outstanding", "sum", "(i.total_zar - i.amount_paid_zar)", when=open_status,
                        format="currency_zar", description="Unpaid balance on sent / partially paid / overdue invoices"),
            agg_measure("overdue_amount", "Overdue amount", "sum", "(i.total_zar - i.amount_paid_zar)",
                        when=lambda d: f"{open_status} AND i.due_date < {today(d)}", format="currency_zar"),
            ratio_measure("collection_rate", "Collection rate", collected, invoiced,
                          description="Collected / invoiced"),
            billed_customers,
            ratio_measure("arpu", "ARPU (invoiced per billed customer)", invoiced, billed_customers, format="currency_zar",
                          description="Invoiced amount divided by distinct customers billed in the selected slice"),
            agg_measure("avg_invoice", "Average invoice", "avg", "i.total_zar", format="currency_zar"),
        )))

    # billing: payments ------------------------------------------------------
    ds.append(Dataset(
        id="billing_payments", label="Billing: payments", category="Billing",
        description="Payment attempts and receipts against invoices.",
        source_tables=("payments",), from_sql="payments p", tenant_expr="p.tenant_id", default_time="created_at",
        dimensions=(
            tdim("created_at", "Payment date", "p.created_at"),
            cdim("method", "Method", "CAST(p.method AS TEXT)", "low"),
            cdim("status", "Status", "CAST(p.status AS TEXT)", "low"),
        ),
        measures=(
            agg_measure("payment_count", "Payments", "count"),
            agg_measure("payments_received", "Payments received", "sum", "p.amount_zar", when="p.status = 'completed'",
                        format="currency_zar"),
            agg_measure("completed_count", "Completed payments", "count", when="p.status = 'completed'"),
            agg_measure("failed_count", "Failed payments", "count", when="p.status = 'failed'"),
            agg_measure("refunded_amount", "Refunded", "sum", "p.amount_zar", when="p.status = 'refunded'",
                        format="currency_zar"),
            agg_measure("avg_payment", "Average payment", "avg", "p.amount_zar", when="p.status = 'completed'",
                        format="currency_zar"),
            agg_measure("customers_paying", "Customers paying", "distinct", "p.customer_id", when="p.status = 'completed'"),
        )))

    # billing: subscriptions / MRR ------------------------------------------
    mrr_expr = ("(s.base_price_zar * s.quantity / CASE CAST(s.billing_interval AS TEXT) WHEN 'monthly' THEN 1 "
                "WHEN 'quarterly' THEN 3 WHEN 'semi_annual' THEN 6 WHEN 'annual' THEN 12 ELSE 1 END)")
    sub_count = agg_measure("subscription_count", "Subscriptions", "count")
    mrr = agg_measure("mrr", "MRR", "sum", mrr_expr, when="s.status = 'active'", format="currency_zar",
                      description="Monthly recurring revenue of ACTIVE subscriptions as of today (annual/quarterly plans normalised "
                                  "to a month). A current snapshot, not historical: grouping by date groups by when subscriptions started.")
    active_customers = agg_measure("active_customers", "Active customers", "distinct", "s.customer_id", when="s.status = 'active'")
    ds.append(Dataset(
        id="billing_subscriptions", label="Billing: subscriptions and MRR", category="Billing",
        description="Subscriptions with normalised monthly recurring revenue.",
        source_tables=("subscriptions",), from_sql="subscriptions s", tenant_expr="s.tenant_id", default_time="created_at",
        dimensions=(
            tdim("created_at", "Start date", "s.created_at"),
            tdim("cancelled_at", "Cancelled date", "s.cancelled_at"),
            cdim("status", "Status", "CAST(s.status AS TEXT)", "low"),
            cdim("plan", "Plan", "s.plan", "medium"),
            cdim("segment", "Segment", "COALESCE(s.segment, 'Unassigned')", "low"),
            cdim("billing_interval", "Billing interval", "CAST(s.billing_interval AS TEXT)", "low"),
        ),
        measures=(
            sub_count,
            agg_measure("active_subscriptions", "Active subscriptions", "count", when="s.status = 'active'"),
            mrr,
            active_customers,
            ratio_measure("arpu", "ARPU (MRR per active customer)", mrr, active_customers, format="currency_zar"),
            agg_measure("trial_subscriptions", "Trials", "count", when="s.status = 'trial'"),
            agg_measure("cancelled_subscriptions", "Cancelled", "count", when="s.status = 'cancelled'"),
            ratio_measure("cancelled_share", "Cancelled share of subscriptions",
                          agg_measure("_c", "", "count", when="s.status = 'cancelled'"), sub_count),
        )))

    # crm: customers ----------------------------------------------------------
    cust_count = agg_measure("customer_count", "Customers", "count")
    rica = agg_measure("rica_verified", "RICA verified", "count", when="c.rica_verified")
    ds.append(Dataset(
        id="crm_customers", label="CRM: customers", category="CRM",
        description="Customer records. For plan/segment views use the subscriptions dataset (customers carry no segment).",
        source_tables=("customers",), from_sql="customers c", tenant_expr="c.tenant_id", default_time="created_at",
        dimensions=(
            tdim("created_at", "Created", "c.created_at"),
            cdim("status", "Status", "CAST(c.status AS TEXT)", "low"),
            cdim("province", "Province", "COALESCE(CAST(c.province AS TEXT), 'Unknown')", "medium"),
            cdim("rica_status", "RICA status", "CASE WHEN c.rica_verified THEN 'Verified' ELSE 'Not verified' END", "low"),
            cdim("customer_type", "Customer type",
                 "CASE WHEN c.company_id IS NULL THEN 'Individual' ELSE 'Company member' END", "low"),
        ),
        measures=(
            cust_count,
            agg_measure("active_customers", "Active customers", "count", when="c.status = 'active'"),
            agg_measure("churned_customers", "Churned customers", "count", when="c.status = 'churned'"),
            rica, ratio_measure("rica_rate", "RICA verified rate", rica, cust_count),
        )))

    # sales: leads (table shared with crm; only the common columns are used) --
    lead_count = agg_measure("lead_count", "Leads", "count")
    conv = agg_measure("converted_leads", "Converted leads", "count",
                       when="(l.converted_at IS NOT NULL OR UPPER(l.status) IN ('CONVERTED','WON'))")
    ds.append(Dataset(
        id="sales_leads", label="Sales: leads", category="Sales",
        description="Leads and their conversion. Uses only the columns shared by the CRM and Sales lead tables.",
        source_tables=("leads",), from_sql="leads l", tenant_expr="l.tenant_id", default_time="created_at",
        dimensions=(
            tdim("created_at", "Created", "l.created_at"),
            tdim("converted_at", "Converted", "l.converted_at"),
            cdim("status", "Status", "UPPER(l.status)", "low"),
            cdim("source", "Source", "COALESCE(l.source, 'Unknown')", "medium"),
        ),
        measures=(
            lead_count, conv,
            agg_measure("won_leads", "Won leads", "count", when="UPPER(l.status) = 'WON'"),
            agg_measure("lost_leads", "Lost leads", "count", when="UPPER(l.status) = 'LOST'"),
            ratio_measure("conversion_rate", "Lead conversion rate", conv, lead_count),
        )))

    # sales: pipeline ---------------------------------------------------------
    deal_count = agg_measure("deal_count", "Deals", "count")
    won = agg_measure("won_deals", "Won deals", "count", when="UPPER(d.status) = 'WON'")
    closed = agg_measure("closed_deals", "Closed deals", "count", when="UPPER(d.status) IN ('WON','LOST')")
    ds.append(Dataset(
        id="sales_pipeline", label="Sales: pipeline and deals", category="Sales",
        description="Deals by board stage with value and win rate.",
        source_tables=("deals", "deal_stages"), from_sql="deals d LEFT JOIN deal_stages ds ON ds.id = d.stage_id",
        tenant_expr="d.tenant_id", default_time="created_at",
        dimensions=(
            tdim("created_at", "Created", "d.created_at"),
            tdim("closed_at", "Closed", "d.closed_at"),
            tdim("close_date", "Expected close date", "d.close_date", "date"),
            cdim("stage", "Stage", "COALESCE(ds.name, 'No stage')", "low", sort="COALESCE(ds.sort_order, 999)"),
            cdim("status", "Status", "UPPER(d.status)", "low"),
        ),
        measures=(
            deal_count,
            agg_measure("pipeline_value", "Total deal value", "sum", "COALESCE(d.value_zar, 0)", format="currency_zar"),
            agg_measure("open_deals", "Open deals", "count", when="UPPER(d.status) = 'OPEN'"),
            agg_measure("open_value", "Open pipeline value", "sum", "COALESCE(d.value_zar, 0)", when="UPPER(d.status) = 'OPEN'",
                        format="currency_zar"),
            won,
            agg_measure("won_value", "Won value", "sum", "COALESCE(d.value_zar, 0)", when="UPPER(d.status) = 'WON'",
                        format="currency_zar"),
            agg_measure("lost_deals", "Lost deals", "count", when="UPPER(d.status) = 'LOST'"),
            closed,
            ratio_measure("win_rate", "Win rate (won / closed)", won, closed),
            agg_measure("avg_deal_value", "Average deal value", "avg", "COALESCE(d.value_zar, 0)", format="currency_zar"),
        )))

    # support: tickets --------------------------------------------------------
    t_count = agg_measure("ticket_count", "Tickets", "count")
    fcr = agg_measure("fcr_tickets", "First-contact resolved", "count", when="t.is_fcr")
    ds.append(Dataset(
        id="support_tickets", label="Support: tickets", category="Support",
        description="Support ticket volume and resolution time.",
        source_tables=("tickets",), from_sql="tickets t", tenant_expr="t.tenant_id", default_time="created_at",
        dimensions=(
            tdim("created_at", "Opened", "t.created_at"),
            tdim("resolved_at", "Resolved", "t.resolved_at"),
            cdim("priority", "Priority", "COALESCE(UPPER(t.priority), 'NORMAL')", "low"),
            cdim("category", "Category", "COALESCE(t.category, 'Uncategorised')", "medium"),
            cdim("status", "Status", "UPPER(t.status)", "low"),
        ),
        measures=(
            t_count,
            agg_measure("open_tickets", "Open tickets", "count", when="(t.resolved_at IS NULL AND UPPER(t.status) <> 'CLOSED')"),
            agg_measure("resolved_tickets", "Resolved tickets", "count", when="t.resolved_at IS NOT NULL"),
            agg_measure("avg_resolution_hours", "Average resolution time", "avg", hours_between("t.created_at", "t.resolved_at"),
                        when="t.resolved_at IS NOT NULL", format="duration", unit="hours"),
            fcr, ratio_measure("fcr_rate", "First-contact resolution rate", fcr, t_count),
        )))

    # network ----------------------------------------------------------------
    ds.append(Dataset(
        id="network_services", label="Network: services", category="Network",
        description="Provisioned fibre services by status, technology, FNO provider and speed.",
        source_tables=("network_services",), from_sql="network_services n", tenant_expr="n.tenant_id", default_time="created_at",
        dimensions=(
            tdim("created_at", "Created", "n.created_at"),
            tdim("activated_at", "Activated", "n.activated_at"),
            cdim("status", "Status", "CAST(n.status AS TEXT)", "low"),
            cdim("technology", "Technology", "CAST(n.technology AS TEXT)", "low"),
            cdim("fno_provider", "FNO provider", "CAST(n.fno_provider AS TEXT)", "medium"),
            cdim("province", "Province", "n.province", "medium"),
            cdim("speed_profile", "Speed profile", "COALESCE(n.speed_profile_name, 'Unnamed')", "medium"),
        ),
        measures=(
            agg_measure("service_count", "Services", "count"),
            agg_measure("active_services", "Active services", "count", when="n.status = 'active'"),
            agg_measure("avg_download_mbps", "Average download speed (Mbps)", "avg", "n.download_speed_mbps"),
            agg_measure("avg_upload_mbps", "Average upload speed (Mbps)", "avg", "n.upload_speed_mbps"),
        )))
    ds.append(Dataset(
        id="network_sla_breaches", label="Network: SLA breaches", category="Network",
        description="SLA breaches by severity and metric.",
        source_tables=("network_sla_breaches",), from_sql="network_sla_breaches b", tenant_expr="b.tenant_id",
        default_time="started_at",
        dimensions=(
            tdim("started_at", "Started", "b.started_at"),
            cdim("severity", "Severity", "CAST(b.severity AS TEXT)", "low"),
            cdim("metric_type", "Metric", "CAST(b.metric_type AS TEXT)", "medium"),
        ),
        measures=(
            agg_measure("breach_count", "Breaches", "count"),
            agg_measure("open_breaches", "Open breaches", "count", when="b.resolved_at IS NULL"),
            agg_measure("avg_duration_hours", "Average breach duration", "avg", "(b.duration_seconds / 3600.0)",
                        when="b.duration_seconds IS NOT NULL", format="duration", unit="hours"),
        )))

    # marketing ---------------------------------------------------------------
    delivered = agg_measure("delivered", "Delivered", "sum", "m.total_delivered")
    opened = agg_measure("opened", "Opened", "sum", "m.total_opened")
    clicked = agg_measure("clicked", "Clicked", "sum", "m.total_clicked")
    ds.append(Dataset(
        id="marketing_campaigns", label="Marketing: campaigns", category="Marketing",
        description="Campaign delivery and response totals.",
        source_tables=("marketing_campaigns",), from_sql="marketing_campaigns m", tenant_expr="m.tenant_id", default_time="created_at",
        dimensions=(
            tdim("created_at", "Created", "m.created_at"),
            tdim("start_date", "Start date", "m.start_date"),
            cdim("channel", "Channel", "m.channel", "low"),
            cdim("status", "Status", "m.status", "low"),
            cdim("campaign", "Campaign", "m.name", "high"),
        ),
        measures=(
            agg_measure("campaign_count", "Campaigns", "count"),
            agg_measure("budget_zar", "Budget", "sum", "m.budget_zar", format="currency_zar"),
            agg_measure("sent", "Sent", "sum", "m.total_sent"), delivered, opened, clicked,
            agg_measure("conversions", "Conversions", "sum", "m.total_conversions"),
            ratio_measure("open_rate", "Open rate (of delivered)", opened, delivered),
            ratio_measure("click_rate", "Click rate (of delivered)", clicked, delivered),
        )))
    eng_daily = agg_measure("engagement", "Engagements (likes+comments+shares+saves)", "sum",
                            "(g.likes + g.comments + g.shares + g.saves)")
    imp_daily = agg_measure("impressions", "Impressions", "sum", "g.impressions")
    ds.append(Dataset(
        id="social_daily", label="Marketing: social daily metrics", category="Marketing",
        description="Daily social performance from the analytics sync worker (published-post attribution, all platforms combined).",
        source_tables=("marketing_daily_metrics",), from_sql="marketing_daily_metrics g", tenant_expr="g.tenant_id",
        base_where="g.attribution = 'publish' AND g.platform = 'all'", default_time="metric_date",
        dimensions=(tdim("metric_date", "Date", "g.metric_date", "date"),),
        measures=(
            agg_measure("posts", "Posts", "sum", "g.post_count"), imp_daily,
            agg_measure("reach", "Reach", "sum", "g.reach"), agg_measure("likes", "Likes", "sum", "g.likes"),
            agg_measure("comments", "Comments", "sum", "g.comments"), agg_measure("shares", "Shares", "sum", "g.shares"),
            agg_measure("saves", "Saves", "sum", "g.saves"), agg_measure("clicks", "Clicks", "sum", "g.clicks"),
            agg_measure("views", "Views", "sum", "g.views"), eng_daily,
            ratio_measure("engagement_rate", "Engagement rate (per impression)", eng_daily, imp_daily),
        )))
    eng_post = agg_measure("engagement", "Engagements (likes+comments+shares+saves)", "sum",
                           "(a.likes + a.comments + a.shares + a.saves)")
    imp_post = agg_measure("impressions", "Impressions", "sum", "a.impressions")
    ds.append(Dataset(
        id="social_posts", label="Marketing: social posts", category="Marketing",
        description="Per-post, per-platform analytics from the analytics sync worker.",
        source_tables=("marketing_post_analytics",), from_sql="marketing_post_analytics a", tenant_expr="a.tenant_id",
        default_time="published_at",
        dimensions=(
            tdim("published_at", "Published", "a.published_at"),
            cdim("platform", "Platform", "a.platform", "low"),
        ),
        measures=(
            agg_measure("post_count", "Posts", "count"), imp_post,
            agg_measure("reach", "Reach", "sum", "a.reach"), agg_measure("likes", "Likes", "sum", "a.likes"),
            agg_measure("comments", "Comments", "sum", "a.comments"), agg_measure("shares", "Shares", "sum", "a.shares"),
            agg_measure("saves", "Saves", "sum", "a.saves"), agg_measure("clicks", "Clicks", "sum", "a.clicks"),
            agg_measure("views", "Views", "sum", "a.views"), eng_post,
            ratio_measure("engagement_rate", "Engagement rate (per impression)", eng_post, imp_post),
        )))

    # BI Studio's own research products -----------------------------------------
    ds.append(Dataset(
        id="competitor_changes", label="Competitors: detected changes", category="Competitive intelligence",
        description="Price / plan / promotion changes detected by competitor scans.",
        source_tables=("analytics_competitor_changes", "analytics_competitors"),
        from_sql="analytics_competitor_changes ch JOIN analytics_competitors co ON co.id = ch.competitor_id AND co.tenant_id = ch.tenant_id",
        tenant_expr="ch.tenant_id", default_time="detected_at",
        dimensions=(
            tdim("detected_at", "Detected", "ch.detected_at"),
            cdim("competitor", "Competitor", "co.name", "medium"),
            cdim("change_type", "Change type", "ch.change_type", "low"),
            cdim("verified", "Verified", "CASE WHEN ch.verified THEN 'Verified' ELSE 'Unverified' END", "low"),
        ),
        measures=(
            agg_measure("change_count", "Changes", "count"),
            agg_measure("verified_changes", "Verified changes", "count", when="ch.verified"),
            agg_measure("avg_pct_change", "Average % change", "avg", "ch.pct_change", when="ch.pct_change IS NOT NULL"),
            agg_measure("avg_abs_change", "Average absolute change", "avg", "ch.abs_change", when="ch.abs_change IS NOT NULL"),
            agg_measure("competitors_changed", "Competitors with changes", "distinct", "ch.competitor_id"),
        )))
    ds.append(Dataset(
        id="competitor_scans", label="Competitors: scans", category="Competitive intelligence",
        description="Competitor scan snapshots taken over time.",
        source_tables=("analytics_competitor_snapshots", "analytics_competitors"),
        from_sql="analytics_competitor_snapshots sn JOIN analytics_competitors co ON co.id = sn.competitor_id AND co.tenant_id = sn.tenant_id",
        tenant_expr="sn.tenant_id", default_time="scanned_at",
        dimensions=(tdim("scanned_at", "Scanned", "sn.scanned_at"), cdim("competitor", "Competitor", "co.name", "medium")),
        measures=(agg_measure("scan_count", "Scans", "count"),
                  agg_measure("competitors_scanned", "Competitors scanned", "distinct", "sn.competitor_id"))))
    pos = agg_measure("positive_items", "Positive items", "count", when="it.sentiment = 'positive'")
    neg = agg_measure("negative_items", "Negative items", "count", when="it.sentiment = 'negative'")
    items = agg_measure("item_count", "Items analysed", "count")
    ds.append(Dataset(
        id="campaign_sentiment", label="Campaign analysis: sentiment", category="Competitive intelligence",
        description="Items collected by campaign / brand reaction analyses, with sentiment.",
        source_tables=("analytics_campaign_items", "analytics_campaign_analyses"),
        from_sql="analytics_campaign_items it JOIN analytics_campaign_analyses an ON an.id = it.analysis_id AND an.tenant_id = it.tenant_id",
        tenant_expr="it.tenant_id", default_time="fetched_at",
        dimensions=(
            tdim("fetched_at", "Collected", "it.fetched_at"),
            tdim("item_date", "Item date", "it.item_date"),
            cdim("analysis", "Analysis", "an.name", "medium"),
            cdim("sentiment", "Sentiment", "it.sentiment", "low"),
            cdim("source_type", "Source type", "it.source_type", "low"),
            cdim("domain", "Source domain", "it.domain", "high"),
        ),
        measures=(
            items, pos, neg,
            agg_measure("neutral_items", "Neutral items", "count", when="it.sentiment = 'neutral'"),
            agg_measure("avg_sentiment", "Average sentiment score (-1 to 1)", "avg", "it.sentiment_score"),
            agg_measure("avg_rating", "Average rating", "avg", "it.rating", when="it.rating IS NOT NULL"),
            ratio_measure("positive_share", "Positive share", pos, items),
            ratio_measure("negative_share", "Negative share", neg, items),
        )))
    return {d.id: d for d in ds}


DATASETS: dict[str, Dataset] = _build()

SKIPPED_DATASETS = [
    {"id": "network_usage", "reason": "No per-subscriber usage volume table exists. network_performance_metrics holds mixed-unit probe "
                                      "samples (latency, signal, CPU) that cannot be summed safely, so it is not exposed."},
    {"id": "marketing_followers", "reason": "marketing_follower_stats stores cumulative follower counts per day; a SUM across a grain would be "
                                              "wrong and a governed 'last value per bucket' measure is not implemented yet."},
    {"id": "finance_gl", "reason": "General-ledger tables were not verified for this release."},
    {"id": "competitor_plan_prices", "reason": "Competitor plan prices are stored inside JSON columns of snapshots; only the structured "
                                                "change records (competitor_changes) are exposed."},
]


# ── query spec ────────────────────────────────────────────────────────────

_ID = re.compile(r"^[a-z][a-z0-9_]{0,48}$")
OPS = {"eq", "neq", "in", "not_in", "gt", "gte", "lt", "lte", "between", "contains", "is_null", "not_null"}
OPS_BY_TYPE = {
    "category": {"eq", "neq", "in", "not_in", "contains", "is_null", "not_null"},
    "number": {"eq", "neq", "gt", "gte", "lt", "lte", "between", "in", "is_null", "not_null"},
    "time": {"eq", "gt", "gte", "lt", "lte", "between", "is_null", "not_null"},
}


class FilterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(..., max_length=50)
    op: str = Field(..., max_length=12)
    value: Any = None


class TimeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    dimension: Optional[str] = Field(None, max_length=50)
    grain: Optional[Literal["day", "week", "month", "quarter", "year"]] = None
    from_: Optional[date] = Field(None, alias="from")
    to: Optional[date] = None


class OrderSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(..., max_length=50)
    dir: Literal["asc", "desc"] = "asc"


class QuerySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset: str = Field(..., max_length=50)
    measures: list[str] = Field(default_factory=list, max_length=MAX_MEASURES)
    dimensions: list[str] = Field(default_factory=list, max_length=MAX_DIMENSIONS)
    filters: list[FilterSpec] = Field(default_factory=list, max_length=MAX_FILTERS)
    time: Optional[TimeSpec] = None
    order_by: list[OrderSpec] = Field(default_factory=list, max_length=4)
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)

    @field_validator("measures", "dimensions")
    @classmethod
    def _ids(cls, v):
        for i in v:
            if not isinstance(i, str) or not _ID.match(i):
                raise ValueError(f"invalid field id {i!r}")
        return v


def canonical_key(spec: QuerySpec) -> str:
    return hashlib.sha256(json.dumps(spec.model_dump(by_alias=True, mode="json"), sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()[:24]


# ── compiler ──────────────────────────────────────────────────────────────

def bucket_sql(d: Dialect, expr: str, grain: str) -> str:
    if d == "postgresql":
        return f"to_char(date_trunc('{grain}', {expr}), 'YYYY-MM-DD')"
    if grain == "day":
        return f"strftime('%Y-%m-%d', {expr})"
    if grain == "month":
        return f"strftime('%Y-%m-01', {expr})"
    if grain == "year":
        return f"strftime('%Y-01-01', {expr})"
    if grain == "week":
        return f"date({expr}, 'weekday 0', '-6 days')"
    return (f"(strftime('%Y-', {expr}) || CASE (CAST(strftime('%m', {expr}) AS INTEGER) - 1) / 3 "
            f"WHEN 0 THEN '01' WHEN 1 THEN '04' WHEN 2 THEN '07' ELSE '10' END || '-01')")


@dataclass
class Column:
    id: str
    label: str
    kind: str                 # dimension | time | measure
    type: str                 # category | number | time
    format: Optional[str] = None
    unit: Optional[str] = None
    grain: Optional[str] = None
    agg: Optional[str] = None
    additive: bool = False

    def public(self) -> dict:
        out = {"id": self.id, "label": self.label, "kind": self.kind, "type": self.type}
        for k in ("format", "unit", "grain", "agg"):
            if getattr(self, k):
                out[k] = getattr(self, k)
        if self.kind == "measure":
            out["additive"] = self.additive
        return out


@dataclass
class Compiled:
    sql: str
    totals_sql: Optional[str]
    params: dict
    columns: list
    limit: int
    dialect: str
    time_info: Optional[dict] = None


def _coerce_time(v: Any, field_id: str) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and re.match(r"^\d{4}-\d{2}-\d{2}", v):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            pass
    raise BiQueryError(f"filter on {field_id!r}: expected an ISO date (YYYY-MM-DD)")


def _coerce_number(v: Any, field_id: str, d: Dialect):
    if isinstance(v, bool) or v is None:
        raise BiQueryError(f"filter on {field_id!r}: expected a number")
    try:
        n = Decimal(str(v).strip())
    except Exception:
        raise BiQueryError(f"filter on {field_id!r}: expected a number")
    if not n.is_finite() or abs(n) > Decimal("1e15"):
        raise BiQueryError(f"filter on {field_id!r}: number out of range")
    return float(n) if d == "sqlite" else n


def _coerce_text(v: Any, field_id: str) -> str:
    if isinstance(v, bool) or not isinstance(v, (str, int, float)):
        raise BiQueryError(f"filter on {field_id!r}: expected text")
    s = str(v)
    if len(s) > 200 or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", s):
        raise BiQueryError(f"filter on {field_id!r}: value too long or contains control characters")
    return s


def _time_param(day: date, dim: Dimension, d: Dialect) -> tuple[str, Any]:
    """(sql placeholder wrapper, bound value) for a day boundary on a time dimension."""
    if d == "sqlite":
        return ":{n}", day.isoformat() if dim.kind == "date" else f"{day.isoformat()} 00:00:00"
    if dim.kind == "date":
        return "CAST(:{n} AS DATE)", day
    return "CAST(:{n} AS TIMESTAMP)", datetime(day.year, day.month, day.day)


def _tenant_value(tenant_id: uuid.UUID, d: Dialect):
    return tenant_id.hex if d == "sqlite" else tenant_id


def compile_query(spec: QuerySpec, dialect: str, tenant_id: uuid.UUID) -> Compiled:
    ds = DATASETS.get(spec.dataset)
    if ds is None:
        raise BiQueryError(f"Unknown dataset {spec.dataset!r}")
    d = dialect
    params: dict[str, Any] = {"tenant": _tenant_value(tenant_id, d)}
    n_param = 0

    def add(value) -> str:
        nonlocal n_param
        name = f"p{n_param}"
        n_param += 1
        params[name] = value
        return name

    pairs: list[tuple[Column, str, Optional[str]]] = []   # (column, sql, sort expr) in output order
    where = [f"{ds.tenant_expr} = :tenant"]
    if ds.base_where:
        where.append(f"({_f(ds.base_where, d)})")

    # dimensions
    seen: set[str] = set()
    for dim_id in spec.dimensions:
        dim = ds.dim(dim_id)
        if dim is None:
            raise BiQueryError(f"Unknown dimension {dim_id!r} for dataset {ds.id!r}")
        if dim.type == "time":
            raise BiQueryError(f"{dim_id!r} is a time dimension: pass it as time.dimension with a grain, not in dimensions")
        if dim_id in seen:
            raise BiQueryError(f"Duplicate dimension {dim_id!r}")
        seen.add(dim_id)
        pairs.append((Column(dim.id, dim.label, "dimension", dim.type), _f(dim.expr, d),
                      _f(dim.sort, d) if dim.sort else None))

    # time
    time_info = None
    t = spec.time
    if t is not None:
        tdim_id = t.dimension or ds.default_time
        tdm = ds.dim(tdim_id) if tdim_id else None
        if tdm is None or tdm.type != "time":
            raise BiQueryError(f"Unknown time dimension {t.dimension!r} for dataset {ds.id!r}")
        if t.grain is not None and t.grain not in tdm.grains:
            raise BiQueryError(f"Grain {t.grain!r} is not available for {tdm.id!r}")
        if t.from_ and t.to and t.from_ > t.to:
            raise BiQueryError("time.from must be on or before time.to")
        texpr = _f(tdm.expr, d)
        if t.grain:
            if tdm.id in seen:
                raise BiQueryError(f"Duplicate dimension {tdm.id!r}")
            seen.add(tdm.id)
            where.append(f"{texpr} IS NOT NULL")
            pairs.insert(0, (Column(tdm.id, tdm.label, "time", "time", grain=t.grain), bucket_sql(d, texpr, t.grain), None))
        if t.from_:
            ph, val = _time_param(t.from_, tdm, d)
            where.append(f"{texpr} >= " + ph.format(n=add(val)))
        if t.to:
            ph, val = _time_param(t.to + timedelta(days=1), tdm, d)
            where.append(f"{texpr} < " + ph.format(n=add(val)))
        time_info = {"dimension": tdm.id, "grain": t.grain, "from": t.from_.isoformat() if t.from_ else None,
                     "to": t.to.isoformat() if t.to else None}

    # measures
    meas_sql: list[tuple[Measure, str]] = []
    seen_m: set[str] = set()
    for m_id in spec.measures:
        m = ds.measure(m_id)
        if m is None or m.id.startswith("_"):
            raise BiQueryError(f"Unknown measure {m_id!r} for dataset {ds.id!r}")
        if m_id in seen_m:
            raise BiQueryError(f"Duplicate measure {m_id!r}")
        seen_m.add(m_id)
        meas_sql.append((m, m.sql(d)))
    if not spec.measures and not spec.dimensions and not (t and t.grain):
        raise BiQueryError("Select at least one measure or dimension")

    select: list[str] = []
    group: list[str] = []
    alias_for: dict[str, str] = {}
    sort_by_id: dict[str, str] = {}
    columns: list[Column] = []
    for col, sql, sort in pairs:
        alias = f"c{len(select)}"
        select.append(f"{sql} AS {alias}")
        alias_for[col.id] = alias
        group.append(sql)
        columns.append(col)
        if sort:
            sort_by_id[col.id] = sort
            group.append(sort)
    for m, sql in meas_sql:
        alias = f"c{len(select)}"
        select.append(f"{sql} AS {alias}")
        alias_for[m.id] = alias
        columns.append(Column(m.id, m.label, "measure", "number", m.format, m.unit, None, m.agg, m.additive))

    # filters
    for f in spec.filters:
        dim = ds.dim(f.field)
        if dim is None:
            raise BiQueryError(f"Unknown filter field {f.field!r} for dataset {ds.id!r}")
        if f.op not in OPS:
            raise BiQueryError(f"Unknown filter operator {f.op!r}")
        if f.op not in OPS_BY_TYPE[dim.type]:
            raise BiQueryError(f"Operator {f.op!r} is not allowed on {dim.type} field {f.field!r}")
        e = _f(dim.expr, d)
        if f.op == "is_null":
            where.append(f"{e} IS NULL"); continue
        if f.op == "not_null":
            where.append(f"{e} IS NOT NULL"); continue
        if dim.type == "time":
            if f.op == "between":
                if not isinstance(f.value, (list, tuple)) or len(f.value) != 2:
                    raise BiQueryError(f"between on {f.field!r} needs [from, to]")
                lo, hi = _coerce_time(f.value[0], f.field), _coerce_time(f.value[1], f.field)
                ph1, v1 = _time_param(lo, dim, d)
                ph2, v2 = _time_param(hi + timedelta(days=1), dim, d)
                where.append(f"({e} >= {ph1.format(n=add(v1))} AND {e} < {ph2.format(n=add(v2))})")
                continue
            day = _coerce_time(f.value, f.field)
            lo_day, hi_day = day, day + timedelta(days=1)
            op, bound = {"gte": (">=", lo_day), "gt": (">=", hi_day), "lt": ("<", lo_day), "lte": ("<", hi_day)}.get(f.op, (None, None))
            if f.op == "eq":
                ph1, v1 = _time_param(lo_day, dim, d); ph2, v2 = _time_param(hi_day, dim, d)
                where.append(f"({e} >= {ph1.format(n=add(v1))} AND {e} < {ph2.format(n=add(v2))})")
            else:
                ph, v = _time_param(bound, dim, d)
                where.append(f"{e} {op} " + ph.format(n=add(v)))
            continue
        if f.op in ("in", "not_in"):
            vals = f.value
            if not isinstance(vals, (list, tuple)) or not vals or len(vals) > MAX_IN_VALUES:
                raise BiQueryError(f"{f.op} on {f.field!r} needs a non-empty list of at most {MAX_IN_VALUES} values")
            names = [":" + add(_coerce_number(v, f.field, d) if dim.type == "number" else _coerce_text(v, f.field)) for v in vals]
            where.append(f"{e} {'NOT ' if f.op == 'not_in' else ''}IN ({', '.join(names)})")
            continue
        if f.op == "between":
            if not isinstance(f.value, (list, tuple)) or len(f.value) != 2:
                raise BiQueryError(f"between on {f.field!r} needs [low, high]")
            a, b = (_coerce_number(v, f.field, d) for v in f.value)
            where.append(f"{e} BETWEEN :{add(a)} AND :{add(b)}")
            continue
        if f.op == "contains":
            s = _coerce_text(f.value, f.field).lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append(f"LOWER({e}) LIKE :{add('%' + s + '%')} ESCAPE '\\'")
            continue
        val = _coerce_number(f.value, f.field, d) if dim.type == "number" else _coerce_text(f.value, f.field)
        sym = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[f.op]
        where.append(f"{e} {sym} :{add(val)}")

    # ordering
    order_sql: list[str] = []
    if spec.order_by:
        for o in spec.order_by:
            if o.field not in alias_for:
                raise BiQueryError(f"order_by field {o.field!r} must be one of the selected columns")
            key = sort_by_id.get(o.field) or alias_for[o.field]
            order_sql.append(f"{key} {o.dir.upper()} NULLS LAST")
    else:
        time_cols = [c for c in columns if c.kind == "time"]
        if time_cols:
            order_sql.append(f"{alias_for[time_cols[0].id]} ASC")
        else:
            dims = [c for c in columns if c.kind == "dimension"]
            first_m = next((c for c in columns if c.kind == "measure"), None)
            if first_m is not None and dims:
                order_sql.append(f"{alias_for[first_m.id]} DESC NULLS LAST")
            for c in dims:
                order_sql.append(sort_by_id.get(c.id) or alias_for[c.id])

    from_where = f"FROM {ds.from_sql} WHERE " + " AND ".join(where)
    sql = f"SELECT {', '.join(select)} {from_where}"
    if group:
        sql += " GROUP BY " + ", ".join(group)
    if order_sql:
        sql += " ORDER BY " + ", ".join(order_sql)
    sql += f" LIMIT {int(spec.limit) + 1}"
    totals_sql = None
    if meas_sql:
        totals_sql = "SELECT " + ", ".join(f"{s} AS t{i}" for i, (_, s) in enumerate(meas_sql)) + " " + from_where
    return Compiled(sql, totals_sql, params, columns, spec.limit, d, time_info)


# ── execution ─────────────────────────────────────────────────────────────

_RATE: dict[uuid.UUID, deque] = {}


def rate_limit_per_minute() -> int:
    try:
        return max(1, int(os.getenv("BI_QUERY_RATE_PER_MIN", "120")))
    except ValueError:
        return 120


def check_rate(tenant_id: uuid.UUID, cost: int = 1) -> None:
    """Per-tenant sliding window (process local). 429 when exceeded."""
    now_ = _time.monotonic()
    q = _RATE.setdefault(tenant_id, deque())
    while q and now_ - q[0] > 60:
        q.popleft()
    if len(q) + cost > rate_limit_per_minute():
        raise HTTPException(429, f"BI query rate limit reached ({rate_limit_per_minute()} per minute per tenant). Try again shortly.")
    for _ in range(cost):
        q.append(now_)


def reset_rate_limits() -> None:
    _RATE.clear()


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float):
        return None if (math.isnan(v) or math.isinf(v)) else round(v, 6)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    return v


async def run_query(db: AsyncSession, tenant_id: uuid.UUID, spec: QuerySpec, *, enforce_rate: bool = True) -> dict:
    dialect = db.bind.dialect.name if db.bind is not None else "postgresql"
    cq = compile_query(spec, dialect, tenant_id)
    if enforce_rate:
        check_rate(tenant_id)
    try:
        async with db.begin_nested():
            if dialect == "postgresql":
                await db.execute(text("SELECT set_config('statement_timeout', :ms, true), set_config('timezone', :tz, true)"),
                                 {"ms": str(STATEMENT_TIMEOUT_MS), "tz": TIMEZONE})
            res = await db.execute(text(cq.sql), cq.params)
            raw = res.fetchall()
            totals_row = None
            if cq.totals_sql:
                totals_row = (await db.execute(text(cq.totals_sql), cq.params)).first()
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("BI query on %s failed: %s", spec.dataset, str(exc)[:300])
        raise HTTPException(503, f"Dataset {spec.dataset!r} could not be read (its source table is unavailable or the query timed out).")
    truncated = len(raw) > cq.limit
    rows = [[_jsonable(v) for v in r] for r in raw[: cq.limit]]
    measure_cols = [c for c in cq.columns if c.kind == "measure"]
    totals = None
    if totals_row is not None:
        totals = {c.id: _jsonable(totals_row[i]) for i, c in enumerate(measure_cols)}
    return {
        "columns": [c.public() for c in cq.columns],
        "rows": rows,
        "totals": totals,
        "meta": {"dataset": spec.dataset, "generated_at": datetime.now(timezone.utc).isoformat(),
                 "row_count": len(rows), "truncated": truncated, "timezone": TIMEZONE, "time": cq.time_info,
                 "query_key": canonical_key(spec)},
    }


def validate_spec_only(spec: QuerySpec) -> None:
    """Registry validation without a database (used by deck/outline validation)."""
    compile_query(spec, "sqlite", uuid.UUID(int=0))


# ── catalog ───────────────────────────────────────────────────────────────

def catalog() -> dict:
    out = []
    for ds in DATASETS.values():
        out.append({
            "id": ds.id, "label": ds.label, "description": ds.description, "category": ds.category,
            "source_tables": list(ds.source_tables), "default_time_dimension": ds.default_time, "notes": ds.notes,
            "dimensions": [{"id": x.id, "label": x.label, "type": x.type, "description": x.description,
                            **({"grains": list(x.grains)} if x.type == "time" else {"cardinality": x.cardinality}),
                            "filter_ops": sorted(OPS_BY_TYPE[x.type])} for x in ds.dimensions],
            "measures": [{"id": m.id, "label": m.label, "agg": m.agg, "format": m.format, "unit": m.unit,
                          "description": m.description, "additive": m.additive}
                         for m in ds.measures if not m.id.startswith("_")],
        })
    return {"datasets": out, "skipped": SKIPPED_DATASETS, "grains": list(GRAINS), "filter_ops": sorted(OPS),
            "limits": {"max_rows": MAX_LIMIT, "default_rows": DEFAULT_LIMIT, "max_measures": MAX_MEASURES,
                       "max_dimensions": MAX_DIMENSIONS, "max_filters": MAX_FILTERS, "queries_per_minute": rate_limit_per_minute(),
                       "statement_timeout_ms": STATEMENT_TIMEOUT_MS}}


# ── chart suggestions (deterministic) ─────────────────────────────────────

class SuggestSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset: str
    measures: list[str] = Field(default_factory=list, max_length=MAX_MEASURES)
    dimensions: list[str] = Field(default_factory=list, max_length=MAX_DIMENSIONS)
    time: Optional[TimeSpec] = None
    row_count: Optional[int] = Field(None, ge=0, le=100000, description="optional: actual rows, sharpens cardinality rules")


def suggest_charts(s: SuggestSpec) -> dict:
    ds = DATASETS.get(s.dataset)
    if ds is None:
        raise BiQueryError(f"Unknown dataset {s.dataset!r}")
    ms = []
    for i in s.measures:
        m = ds.measure(i)
        if m is None or m.id.startswith("_"):
            raise BiQueryError(f"Unknown measure {i!r}")
        ms.append(m)
    cats = []
    for i in s.dimensions:
        dm = ds.dim(i)
        if dm is None or dm.type == "time":
            raise BiQueryError(f"Unknown category dimension {i!r}")
        cats.append(dm)
    has_time = bool(s.time and s.time.grain)
    if s.time and s.time.dimension and ds.dim(s.time.dimension) is None:
        raise BiQueryError(f"Unknown time dimension {s.time.dimension!r}")
    if not ms and not cats and not has_time:
        raise BiQueryError("Select at least one field")

    card = "low"
    if cats:
        order = {"low": 0, "medium": 1, "high": 2}
        card = max((c.cardinality for c in cats), key=lambda k: order[k])
        if s.row_count is not None and len(cats) == 1:
            card = "low" if s.row_count <= 8 else "medium" if s.row_count <= 25 else "high"
    additive = bool(ms) and all(m.additive for m in ms)
    mixed_formats = len({m.format for m in ms}) > 1
    tdim_id = (s.time.dimension or ds.default_time) if has_time else None
    out: list[dict] = []

    def add(type_, score, reason, x=None, y=None, series=None):
        out.append({"type": type_, "score": score, "reason": reason,
                    "series_mapping": {"x": x, "y": y or [m.id for m in ms], "series": series}})

    n = len(ms)
    if not ms:
        out.append({"type": "table", "score": 100, "reason": "No measure selected: list the distinct values", "series_mapping": {}})
    elif has_time and not cats:
        if mixed_formats and n == 2:
            add("combo", 95, "Two measures with different units over time: columns plus a line on a second axis", tdim_id)
        add("line", 90, "A trend over time reads best as a line", tdim_id)
        add("column", 80 if additive else 60, "Periods compared side by side", tdim_id)
        if additive:
            add("area", 70, "Cumulative volume over time", tdim_id)
    elif has_time and len(cats) == 1:
        if card == "low" and additive and n == 1:
            add("stacked_column", 92, "Composition by category over time", tdim_id, series=cats[0].id)
        add("line", 88 if n == 1 else 70, "One line per category over time", tdim_id, series=cats[0].id if n == 1 else None)
        if n == 1:
            add("area", 60, "Layered categories over time", tdim_id, series=cats[0].id)
    elif cats and not has_time and len(cats) == 1:
        c = cats[0]
        if n == 1:
            if card == "low" and additive:
                add("donut", 85 if (s.row_count or 0) <= 6 else 70, "Few categories forming a whole", c.id)
                add("pie", 55, "Few categories forming a whole", c.id)
            add("bar", 95 if card != "low" else 82, "Ranked comparison across categories", c.id)
            add("column", 80 if card == "low" else 60, "Category comparison", c.id)
            if additive:
                add("waterfall", 40, "Contribution of each category to the total", c.id)
        elif n == 2 and mixed_formats:
            add("combo", 92, "Two measures with different units per category", c.id)
            add("scatter", 50, "Relationship between the two measures", c.id)
        else:
            add("column", 90, "Several measures compared per category", c.id)
            add("bar", 80, "Several measures compared per category", c.id)
            if n == 2:
                add("scatter", 55, "Relationship between the two measures", c.id)
    elif len(cats) >= 2 and not has_time:
        if n == 1 and additive:
            add("stacked_column", 90, "Composition of the second category within the first", cats[0].id, series=cats[1].id)
        add("column", 75, "Clustered comparison", cats[0].id, series=cats[1].id if n == 1 else None)
        add("bar", 65, "Ranked comparison", cats[0].id, series=cats[1].id if n == 1 else None)
    elif has_time and len(cats) >= 2:
        add("line", 80, "One line per category combination", tdim_id, series=cats[0].id)
        add("stacked_column", 70 if additive and n == 1 else 40, "Composition over time", tdim_id, series=cats[0].id)
    else:  # measures only
        out.append({"type": "kpi", "score": 100, "reason": "Measures with no breakdown are best shown as KPI tiles",
                    "series_mapping": {"values": [m.id for m in ms]}})
    if ms:
        out.append({"type": "table", "score": 20, "reason": "Exact values", "series_mapping": {}})
    out.sort(key=lambda r: (-r["score"], r["type"]))
    return {"dataset": ds.id, "suggestions": out, "recommended": out[0]["type"]}
