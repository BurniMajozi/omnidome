"""Metric catalog: named business metrics mapped to governed bi_semantic query specs.

Pure data (no FastAPI / SQLAlchemy / bi_semantic imports) so the forecaster batch image can import it
without the web stack. `tests/test_metric_catalog.py` validates every entry against the real bi_semantic registry
(dataset, measure, dimension, grain), so a drifting registry fails CI rather than silently breaking snapshots.

Two shapes:
  series    one value per complete period (month/week) -> ACTUAL facts, optionally forecastable
  snapshot  one value per dimension member "as of today" (e.g. pipeline value by stage); never forecast
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

# Minimum number of complete periods before any forecast is emitted (per grain). Monthly needs a full year so
# seasonality can at least be ruled out; weekly needs two quarters.
MIN_HISTORY = {"month": 12, "week": 26, "day": 60}
DEFAULT_HORIZON = {"month": 3, "week": 8, "day": 14}
MAX_HORIZON = {"month": 12, "week": 26, "day": 60}
SEASON_LENGTH = {"month": 12, "week": 52, "day": 7}
DEFAULT_PERIODS = {"month": 36, "week": 104, "day": 180}      # history window pulled by a snapshot


@dataclass(frozen=True)
class Metric:
    key: str                                  # metric_key written to tenant_metric_facts (^[a-z][a-z0-9_.]{0,118}$)
    label: str
    dataset: str                              # bi_semantic dataset id
    measure: str                              # bi_semantic measure id
    shape: str = "series"                     # series | snapshot
    time_dimension: Optional[str] = None      # series: the time dimension; snapshot: None
    grain: Optional[str] = None               # month | week for series
    snapshot_dimensions: tuple = ()           # snapshot: category dimensions (one fact per member)
    unit: str = "count"                       # ZAR | count | hours | percent
    filters: tuple = ()                       # extra governed filters, each {"field","op","value"}
    additive: bool = True                     # sum/count measure: a period with no rows is a real 0 (zero-filled)
    nonnegative: bool = True                  # counts/currency cannot go below 0: forecasts are clipped
    forecastable: bool = False
    min_history: Optional[int] = None         # override of MIN_HISTORY[grain]
    horizon: Optional[int] = None             # override of DEFAULT_HORIZON[grain]
    description: str = ""

    # -- derived ---------------------------------------------------------------------------------------------
    @property
    def history_needed(self) -> int:
        return self.min_history or MIN_HISTORY.get(self.grain or "", 9999)

    @property
    def default_horizon(self) -> int:
        return self.horizon or DEFAULT_HORIZON.get(self.grain or "", 3)

    @property
    def season_length(self) -> int:
        return SEASON_LENGTH.get(self.grain or "", 1)

    def query_spec(self, date_from: Optional[date] = None, date_to: Optional[date] = None) -> dict[str, Any]:
        """The governed QuerySpec (by-alias JSON, i.e. what POST /bi/query accepts) that produces this metric."""
        spec: dict[str, Any] = {"dataset": self.dataset, "measures": [self.measure]}
        if self.shape == "series":
            t: dict[str, Any] = {"dimension": self.time_dimension, "grain": self.grain}
            if date_from:
                t["from"] = date_from.isoformat()
            if date_to:
                t["to"] = date_to.isoformat()
            spec["time"] = t
            spec["limit"] = 1000
        else:
            spec["dimensions"] = list(self.snapshot_dimensions)
            spec["limit"] = 200
        if self.filters:
            spec["filters"] = [dict(f) for f in self.filters]
        return spec

    def public(self) -> dict:
        return {"key": self.key, "label": self.label, "dataset": self.dataset, "measure": self.measure, "shape": self.shape,
                "time_dimension": self.time_dimension, "grain": self.grain, "snapshot_dimensions": list(self.snapshot_dimensions),
                "unit": self.unit, "forecastable": self.forecastable,
                "min_history": self.history_needed if self.forecastable else None,
                "default_horizon": self.default_horizon if self.forecastable else None,
                "description": self.description}


def _m(key, label, dataset, measure, tdim, grain, unit="count", **kw) -> Metric:
    return Metric(key=key, label=label, dataset=dataset, measure=measure, time_dimension=tdim, grain=grain, unit=unit, **kw)


CATALOG: tuple = (
    # ── Billing / revenue (monthly) ─────────────────────────────────────────────────────────────────────────
    _m("billing.revenue_invoiced.month", "Revenue invoiced per month (incl. VAT)", "billing_invoices", "invoiced", "created_at", "month", "ZAR",
       forecastable=True, description="Sum of non-draft, non-voided invoice totals by invoice date."),
    _m("billing.revenue_collected.month", "Revenue collected per month (by invoice date)", "billing_invoices", "collected", "created_at", "month", "ZAR",
       forecastable=True, description="Amount paid against invoices raised in the month (cohort basis, grows as late payers settle)."),
    _m("billing.cash_received.month", "Cash received per month (by payment date)", "billing_payments", "payments_received", "created_at", "month", "ZAR",
       forecastable=True, description="Completed payments by payment date."),
    _m("billing.outstanding_by_aging", "Outstanding receivables by aging bucket", "billing_invoices", "outstanding", None, None, "ZAR",
       shape="snapshot", snapshot_dimensions=("aging_bucket",), description="Open invoice balance per aging bucket, as of today."),
    # ── CRM / network growth ────────────────────────────────────────────────────────────────────────────────
    _m("crm.new_customers.month", "New customers per month", "crm_customers", "customer_count", "created_at", "month",
       forecastable=True, description="Customers created in the month."),
    _m("network.services_activated.month", "Services activated per month", "network_services", "service_count", "activated_at", "month",
       forecastable=True, description="Fibre services activated in the month."),
    _m("billing.cancellations.month", "Subscription cancellations per month", "billing_subscriptions", "cancelled_subscriptions", "cancelled_at", "month",
       forecastable=True, description="Subscriptions cancelled in the month (churn proxy; billing subscriptions table)."),
    _m("billing.mrr_by_plan", "MRR by plan", "billing_subscriptions", "mrr", None, None, "ZAR",
       shape="snapshot", snapshot_dimensions=("plan",), description="Monthly recurring revenue of active subscriptions per plan, as of today."),
    # ── Sales ───────────────────────────────────────────────────────────────────────────────────────────────
    _m("sales.leads_created.month", "Leads created per month", "sales_leads", "lead_count", "created_at", "month",
       forecastable=True, description="Leads created in the month."),
    _m("sales.leads_won.month", "Leads won per month", "sales_leads", "won_leads", "converted_at", "month",
       forecastable=True, description="Leads marked WON, by conversion date."),
    _m("sales.deals_won.month", "Deals won per month", "sales_pipeline", "won_deals", "closed_at", "month",
       forecastable=True, description="Deals won, by close date."),
    _m("sales.won_value.month", "Won deal value per month", "sales_pipeline", "won_value", "closed_at", "month", "ZAR",
       forecastable=True, description="Value of deals won, by close date."),
    _m("sales.pipeline_value_by_stage", "Open pipeline value by stage", "sales_pipeline", "open_value", None, None, "ZAR",
       shape="snapshot", snapshot_dimensions=("stage",), description="Open deal value per pipeline stage, as of today."),
    # ── Support (weekly) ────────────────────────────────────────────────────────────────────────────────────
    _m("support.tickets_opened.week", "Tickets opened per week", "support_tickets", "ticket_count", "created_at", "week",
       forecastable=True, description="Support tickets opened in the week."),
    _m("support.avg_resolution_hours.week", "Average ticket resolution time per week", "support_tickets", "avg_resolution_hours", "resolved_at", "week", "hours",
       additive=False, forecastable=True, description="Mean hours from open to resolution for tickets resolved in the week."),
    # ── Network SLA ─────────────────────────────────────────────────────────────────────────────────────────
    _m("network.sla_breaches.month", "SLA breaches per month", "network_sla_breaches", "breach_count", "started_at", "month",
       forecastable=True, description="SLA breaches that started in the month."),
    # ── Marketing ───────────────────────────────────────────────────────────────────────────────────────────
    _m("marketing.campaign_sends.month", "Campaign messages sent per month", "marketing_campaigns", "sent", "start_date", "month",
       forecastable=True, description="Total sent across campaigns starting in the month."),
    _m("marketing.campaign_conversions.month", "Campaign conversions per month", "marketing_campaigns", "conversions", "start_date", "month",
       forecastable=True, description="Total conversions across campaigns starting in the month."),
)

BY_KEY: dict[str, Metric] = {m.key: m for m in CATALOG}


def get(key: str) -> Optional[Metric]:
    return BY_KEY.get(key)


def forecastable() -> list:
    return [m for m in CATALOG if m.forecastable and m.shape == "series"]


def select(keys: Optional[list] = None) -> list:
    """Resolve requested keys (None/empty = all); unknown keys raise KeyError so a typo is loud."""
    if not keys:
        return list(CATALOG)
    missing = [k for k in keys if k not in BY_KEY]
    if missing:
        raise KeyError(f"unknown metric key(s): {', '.join(missing)}")
    return [BY_KEY[k] for k in keys]


# ── period arithmetic (shared by the writer and the forecaster) ───────────────────────────────────────────────

def period_end(start: date, grain: str) -> date:
    if grain == "month":
        nxt = date(start.year + (start.month == 12), (start.month % 12) + 1, 1)
        return nxt - timedelta(days=1)
    if grain == "week":
        return start + timedelta(days=6)
    if grain == "day":
        return start
    if grain == "quarter":
        m = start.month + 3
        nxt = date(start.year + (m > 12), (m - 1) % 12 + 1, 1)
        return nxt - timedelta(days=1)
    if grain == "year":
        return date(start.year, 12, 31)
    raise ValueError(f"unsupported grain {grain!r}")


def next_period_start(start: date, grain: str) -> date:
    return period_end(start, grain) + timedelta(days=1)


def prev_period_start(start: date, grain: str) -> date:
    return period_start_for(start - timedelta(days=1), grain)


def add_periods(start: date, grain: str, n: int) -> date:
    """Move `start` (a period start) by n periods; n may be negative."""
    d = start
    for _ in range(abs(n)):
        d = next_period_start(d, grain) if n > 0 else prev_period_start(d, grain)
    return d


def period_start_for(day: date, grain: str) -> date:
    """Start of the period containing `day` (weeks start Monday, matching date_trunc)."""
    if grain == "month":
        return day.replace(day=1)
    if grain == "week":
        return day - timedelta(days=day.weekday())
    if grain == "quarter":
        return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)
    if grain == "year":
        return date(day.year, 1, 1)
    return day
