"""Deterministic Goal Setting & Performance Tracking Engine.

Connects the Agent Orchestrator to immutable database tables (sales deals,
active customers, subscriptions, billing invoices) to deterministically track
actual business performance against promised strategic targets.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from services.common.db import session_scope

logger = logging.getLogger("orchestrator.goals")

# ═══════════════════════════════════════════════════════════════════════════
# PROMISED STRATEGIC TARGETS (Determined from Corporate Strategy & HR)
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_STRATEGIC_TARGETS = {
    "fiscal_period": "FY 2026/2027",
    "targets": {
        "monthly_recurring_revenue_zar": 3500000.0,  # R3.5M Target
        "active_subscribers_count": 1200,            # 1,200 Active Subscribers
        "active_pipeline_zar": 200000.0,              # R200k Open Pipeline
        "closed_won_deals_zar": 1500000.0,            # R1.5M Closed Won YTD
        "target_win_rate_pct": 35.0,                  # 35% Conversion
        "max_churn_rate_pct": 2.0,                   # Max 2% Churn
        "max_staff_attrition_risk_pct": 12.0,        # Max 12% Burnout/Attrition
    },
    "culture_pillars": [
        "Ubuntu & Customer Empathy (compassionate service, fair dunning)",
        "Operational Excellence & Speed (99.9% uptime, >75% FCR)",
        "Staff Wellness & Anti-Burnout (BCEA max 45h, mandatory rest days)",
        "POPIA & Ethical Governance (strict consumer privacy)",
    ],
}

DEFAULT_PPP_FRAMEWORK = [
    {
        "code": "PPP-HR-POL-01",
        "category": "Policy",
        "title": "Workforce Wellness, Overtime Limits & Rest Mandates",
        "description": "Governs maximum allowable shift hours, emergency overtime caps, and mandatory rest periods under BCEA.",
        "rules": [
            "No employee may work more than 12 consecutive hours in any 24-hour cycle.",
            "Support staff logging >10 overtime hours in a week must be granted a compulsory wellness rest day.",
            "AI Orchestrator is authorized to recommend shift rebalancing when burnout alerts trigger.",
        ],
    },
    {
        "code": "PPP-SALES-PROC-02",
        "category": "Procedure",
        "title": "Fiber Sales Qualification & Deal Pipeline Stages",
        "description": "Standardized procedure for moving sales leads through the 6 pipeline stages: Prospecting -> Qualified -> Proposal -> Negotiation -> Closed Won -> Closed Lost.",
        "rules": [
            "Feasibility check with relevant FNO (Vumatel, Openserve, Frogfoot, MetroFibre) must precede Proposal stage.",
            "RICA identity document verification is required before advancing to Closed Won.",
            "Deals exceeding R10,000/mo require executive AI margin validation before closing.",
        ],
    },
    {
        "code": "PPP-RET-PROC-03",
        "category": "Procedure",
        "title": "Customer Retention Authority & Tiered Discount Matrix",
        "description": "Establishes deterministic guidelines for customer retention offers based on Customer Lifetime Value (LTV).",
        "rules": [
            "Tier 1 (DomeBot / Frontline): Authorized up to 10% discount for 3 months on accounts in good standing.",
            "Tier 2 (ChurnGuard / Supervisor): Authorized up to 20% discount or free speed bump for 6 months on LTV > R8,000.",
            "Tier 3 (Executive AI): Authorized for bespoke contract restructuring or equipment subsidy for high-value enterprise accounts.",
        ],
    },
    {
        "code": "PPP-PERF-GOV-04",
        "category": "Process",
        "title": "Deterministic Performance Goal Tracking Framework",
        "description": "Governs how performance is deterministically scored against immutable database tables (sales deals, active subscribers, billing collections) without subjective bias.",
        "rules": [
            "Performance targets are compared directly against immutable database records (deals, customers, invoices).",
            "Variance >= 90% of target = ON_TRACK; 75%-89% = AT_RISK; <75% = BEHIND; >110% = EXCEEDED.",
            "Corrective recommendations must balance revenue velocity with staff operational capacity.",
        ],
    },
]


def evaluate_variance(actual: float, target: float, higher_is_better: bool = True) -> Dict[str, Any]:
    """Calculate attainment, variance, and deterministic health status."""
    if target == 0:
        attainment = 100.0
        status = "ON_TRACK"
    else:
        attainment = round((actual / target) * 100, 1)

    diff = actual - target

    if higher_is_better:
        if attainment >= 105.0:
            status = "EXCEEDED"
        elif attainment >= 90.0:
            status = "ON_TRACK"
        elif attainment >= 70.0:
            status = "AT_RISK"
        else:
            status = "CRITICAL"
    else:
        # Lower is better (e.g. churn, attrition)
        if actual <= target:
            status = "ON_TRACK"
        elif actual <= target * 1.25:
            status = "AT_RISK"
        else:
            status = "CRITICAL"

    return {
        "actual": actual,
        "target": target,
        "variance": round(diff, 2),
        "attainment_pct": attainment,
        "status": status,
    }


async def get_strategic_goals_and_culture(tenant_id: Optional[Any] = None) -> Dict[str, Any]:
    """Return corporate strategy, culture pillars, and PPP framework."""
    return {
        "success": True,
        "fiscal_period": DEFAULT_STRATEGIC_TARGETS["fiscal_period"],
        "targets": DEFAULT_STRATEGIC_TARGETS["targets"],
        "culture_pillars": DEFAULT_STRATEGIC_TARGETS["culture_pillars"],
        "ppp_framework": DEFAULT_PPP_FRAMEWORK,
    }


async def track_deterministic_performance(
    tenant_id: Optional[Any] = None,
    target_overrides: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Query immutable tables and calculate real vs promised performance."""
    targets = dict(DEFAULT_STRATEGIC_TARGETS["targets"])
    if target_overrides:
        targets.update(target_overrides)

    actuals = {
        "closed_won_zar": 0.0,
        "closed_won_count": 0,
        "active_pipeline_zar": 0.0,
        "active_pipeline_count": 0,
        "win_rate_pct": 0.0,
        "active_subscribers": 0,
        "active_mrr_zar": 0.0,
        "collected_revenue_zar": 0.0,
    }

    try:
        async with session_scope() as session:
            # 1. Closed Won Deals (from immutable deals table)
            res_won = await session.execute(
                text("SELECT count(*), coalesce(sum(coalesce(value_zar, amount, 0)), 0) FROM deals WHERE upper(status::text) IN ('WON', 'CLOSED_WON')")
            )
            won_row = res_won.fetchone()
            if won_row:
                actuals["closed_won_count"] = int(won_row[0] or 0)
                actuals["closed_won_zar"] = float(won_row[1] or 0.0)

            # 2. Active Open Pipeline (from immutable deals table)
            res_pipe = await session.execute(
                text("SELECT count(*), coalesce(sum(coalesce(value_zar, amount, 0)), 0) FROM deals WHERE upper(status::text) NOT IN ('WON', 'CLOSED_WON', 'LOST', 'CLOSED_LOST')")
            )
            pipe_row = res_pipe.fetchone()
            if pipe_row:
                actuals["active_pipeline_count"] = int(pipe_row[0] or 0)
                actuals["active_pipeline_zar"] = float(pipe_row[1] or 0.0)

            # Win Rate
            res_lost = await session.execute(
                text("SELECT count(*) FROM deals WHERE upper(status::text) IN ('LOST', 'CLOSED_LOST')")
            )
            lost_count = int(res_lost.scalar() or 0)
            total_resolved = actuals["closed_won_count"] + lost_count
            if total_resolved > 0:
                actuals["win_rate_pct"] = round((actuals["closed_won_count"] / total_resolved) * 100, 1)

            # 3. Active Subscribers (from customers table)
            res_cust = await session.execute(
                text("SELECT count(*) FROM customers WHERE upper(status::text) = 'ACTIVE'")
            )
            actuals["active_subscribers"] = int(res_cust.scalar() or 0)

            # 4. Live MRR (from subscriptions table joined with billing_plans)
            try:
                res_sub = await session.execute(
                    text("""
                        SELECT coalesce(sum(p.price), 0)
                        FROM subscriptions s
                        JOIN billing_plans p ON s.plan_id = p.id
                        WHERE upper(s.status::text) = 'ACTIVE'
                    """)
                )
                actuals["active_mrr_zar"] = float(res_sub.scalar() or 0.0)
            except Exception:
                actuals["active_mrr_zar"] = 0.0

            # 5. Invoices Paid (from invoices table)
            try:
                res_inv = await session.execute(
                    text("SELECT coalesce(sum(total_amount), 0) FROM invoices WHERE upper(status::text) IN ('PAID', 'SETTLED')")
                )
                actuals["collected_revenue_zar"] = float(res_inv.scalar() or 0.0)
            except Exception:
                actuals["collected_revenue_zar"] = 0.0

    except Exception as exc:
        logger.warning("Error querying immutable performance tables: %s", exc)

    # Calculate Scorecard against Promised Numbers
    pipeline_target = targets.get("active_pipeline_zar", targets.get("target_pipeline_volume_zar", 200000.0))
    scorecard = {
        "monthly_recurring_revenue": evaluate_variance(
            actuals["active_mrr_zar"], targets["monthly_recurring_revenue_zar"]
        ),
        "active_subscribers": evaluate_variance(
            actuals["active_subscribers"], targets["active_subscribers_count"]
        ),
        "sales_pipeline": evaluate_variance(
            actuals["active_pipeline_zar"], pipeline_target
        ),
        "closed_won_deals": evaluate_variance(
            actuals["closed_won_zar"], targets["closed_won_deals_zar"]
        ),
        "win_rate": evaluate_variance(
            actuals["win_rate_pct"], targets["target_win_rate_pct"]
        ),
    }

    # Deterministic Strategic Synthesis
    critical_gaps = [k for k, v in scorecard.items() if v["status"] in ("CRITICAL", "AT_RISK")]

    summary = (
        f"Deterministic Performance Summary ({DEFAULT_STRATEGIC_TARGETS['fiscal_period']}):\n"
        f"- MRR: R{actuals['active_mrr_zar']:,.2f} vs Target R{targets['monthly_recurring_revenue_zar']:,.2f} ({scorecard['monthly_recurring_revenue']['attainment_pct']}% - {scorecard['monthly_recurring_revenue']['status']})\n"
        f"- Active Subscribers: {actuals['active_subscribers']} vs Target {targets['active_subscribers_count']} ({scorecard['active_subscribers']['attainment_pct']}% - {scorecard['active_subscribers']['status']})\n"
        f"- Active Pipeline: R{actuals['active_pipeline_zar']:,.2f} across {actuals['active_pipeline_count']} deals ({scorecard['sales_pipeline']['status']})\n"
        f"- Closed Won Revenue: R{actuals['closed_won_zar']:,.2f} across {actuals['closed_won_count']} closed deals\n"
        f"- Conversion Win Rate: {actuals['win_rate_pct']}% vs Target {targets['target_win_rate_pct']}%\n"
    )

    recommendations = []
    if "monthly_recurring_revenue" in critical_gaps or "active_subscribers" in critical_gaps:
        recommendations.append("Prioritize high-conversion enterprise fiber proposals in the sales pipeline to accelerate MRR.")
    if "sales_pipeline" in critical_gaps:
        recommendations.append("Deploy Firecrawl FNO coverage scans to generate qualified leads in newly released footprint zones.")
    if not critical_gaps:
        recommendations.append("All primary commercial goals are on track. Focus on support First Contact Resolution and technician dispatch efficiency.")

    return {
        "success": True,
        "fiscal_period": DEFAULT_STRATEGIC_TARGETS["fiscal_period"],
        "actuals": actuals,
        "scorecard": scorecard,
        "summary": summary,
        "recommendations": recommendations,
        "culture_alignment": DEFAULT_STRATEGIC_TARGETS["culture_pillars"],
        "ppp_framework": DEFAULT_PPP_FRAMEWORK,
    }
