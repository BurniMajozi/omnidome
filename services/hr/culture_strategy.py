"""OmniDome HR Culture, Strategy, and PPP (Policy, Process, Procedure) Engine.

Stores and synchronizes the organization's culture, strategic goals, and PPP framework
from HR/Talent into Tenant Memory (tenant_memory:8025) so that the Agent Orchestrator
and all autonomous bots ground their decisions in company policy and target metrics.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("hr.culture_strategy")

MEMORY_SERVICE_URL = os.getenv("TENANT_MEMORY_SERVICE_URL", "http://tenant_memory:8025").rstrip("/")

# ═══════════════════════════════════════════════════════════════════════════
# 1. CORE CULTURE, STRATEGY & PPP DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

OMNIDOME_CULTURE = {
    "name": "OmniDome Culture & Behavioral Code",
    "pillars": [
        {
            "name": "Ubuntu & Customer Empathy",
            "principle": "Our technology serves human connectivity. Customers experiencing connectivity issues must be treated with empathy, dignity, and prompt operational updates. Disconnections for dunning are a last resort after structured outreach.",
            "behaviors": [
                "Proactive outage communication before customer complaint",
                "Gentle reminder sequences prior to service suspension",
                "Empathetic tone in all customer and support touchpoints",
            ],
        },
        {
            "name": "Operational Excellence & Speed",
            "principle": "Fiber reliability is our core promise. We target 99.9% uptime, First Contact Resolution (FCR) > 75%, and SLA-driven dispatch times.",
            "behaviors": [
                "Automated root-cause diagnostics on ticket creation",
                "Fast-track enterprise fiber fault escalation",
                "Transparent status telemetry across all customer portals",
            ],
        },
        {
            "name": "Staff Wellness & Anti-Burnout (BCEA Compliant)",
            "principle": "Healthy agents build enduring networks. Overtime must strictly adhere to the Basic Conditions of Employment Act (max 45 normal hours/week, max 10 hours overtime). High-intensity emergency shifts require mandatory rest rebalancing.",
            "behaviors": [
                "Mandatory 36-hour consecutive rest after emergency weekend outage shifts",
                "Shift rotation for support engineers with consecutive high-sentiment calls",
                "Immediate supervisor notifications when burnout risk exceeds threshold",
            ],
        },
        {
            "name": "POPIA & Ethical Governance",
            "principle": "Zero compromise on data privacy. Identity verification must precede data disclosure. Customer PII is protected under South African POPIA regulations.",
            "behaviors": [
                "Masking sensitive personal identifiers in assistant transcripts",
                "Explicit verification before balance or billing information disclosure",
                "No unauthorized export or sharing of consumer contact profiles",
            ],
        },
    ],
}

OMNIDOME_STRATEGY = {
    "fiscal_period": "FY 2026/2027",
    "mission": "Become South Africa's most reliable and responsive open-access fiber ISP through AI-augmented operations and human-centered excellence.",
    "promised_numbers": {
        "monthly_recurring_revenue_zar": 3500000.0,  # R3.5M Target MRR
        "active_fiber_subscribers": 1200,             # 1,200 Active Subscribers
        "target_pipeline_volume_zar": 200000.0,       # R200k Active Monthly Pipeline
        "target_deal_win_rate_pct": 35.0,             # 35% Conversion Rate
        "max_churn_rate_pct": 2.0,                    # <2% Monthly Churn Ceiling
        "min_first_contact_resolution_pct": 75.0,     # >75% Support FCR
        "max_staff_attrition_risk_pct": 12.0,         # <12% High Risk Staff
    },
    "strategic_pillars": [
        "High-Velocity Fiber Sales: Aggressive expansion in newly released FNO footprint zones.",
        "Zero-Avoidable-Churn: Early algorithmic intervention on at-risk subscribers before month-end.",
        "Sustainable Operations: High agent morale, zero burnout incidents, and automated shift support.",
    ],
}

OMNIDOME_PPP = [
    {
        "code": "PPP-HR-POL-01",
        "category": "Policy",
        "title": "Workforce Wellness, Overtime Limits & Rest Mandates",
        "description": "Governs maximum allowable shift hours, emergency overtime caps, and mandatory rest periods under BCEA. Prevents field technician and support agent burnout.",
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

# ═══════════════════════════════════════════════════════════════════════════
# 2. SYNCHRONIZATION INTO TENANT MEMORY
# ═══════════════════════════════════════════════════════════════════════════

async def sync_culture_and_strategy_to_memory(tenant_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Sync Culture, Strategic Targets, and PPP entries into Tenant Memory."""
    valid_user_id = str(user_id) if user_id and len(str(user_id)) == 36 else os.getenv("DEFAULT_USER_ID", "16bb4086-288b-429b-9854-059647881b50")
    headers = {
        "X-Tenant-Id": str(tenant_id),
        "X-User-Id": valid_user_id,
        "X-Roles": "platform_admin",
        "Content-Type": "application/json",
    }

    results = {"summaries_created": 0, "entries_created": 0, "errors": []}

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Upsert Culture Summary
        culture_summary_text = (
            "OmniDome Core Culture: Ubuntu & Customer Empathy (compassionate service, gentle dunning), "
            "Operational Excellence (99.9% uptime, >75% FCR, transparent updates), "
            "Staff Wellness (BCEA compliance, max 45h normal/wk, mandatory 36h rest after emergency outages), "
            "and POPIA/Ethical Governance (strict data privacy, non-disclosure of PII)."
        )
        try:
            resp = await client.put(
                f"{MEMORY_SERVICE_URL}/api/v1/summaries/hr_culture",
                headers=headers,
                json={
                    "scope_key": "hr_culture",
                    "module": "hr",
                    "title": "OmniDome Core Culture & Behavioral Values",
                    "summary": culture_summary_text,
                    "metadata": {"category": "culture", "pillars": [p["name"] for p in OMNIDOME_CULTURE["pillars"]]},
                },
            )
            if resp.status_code in (200, 201):
                results["summaries_created"] += 1
            else:
                results["errors"].append(f"Culture summary: HTTP {resp.status_code}")
        except Exception as e:
            results["errors"].append(f"Culture summary failed: {e}")

        # 2. Upsert Strategic Goals Summary
        promised = OMNIDOME_STRATEGY["promised_numbers"]
        strategy_summary_text = (
            f"Strategic Targets ({OMNIDOME_STRATEGY['fiscal_period']}): "
            f"Target Monthly Revenue: R{promised['monthly_recurring_revenue_zar']:,.0f} ZAR; "
            f"Target Active Subscribers: {promised['active_fiber_subscribers']} accounts; "
            f"Active Pipeline Target: R{promised['target_pipeline_volume_zar']:,.0f} ZAR with {promised['target_deal_win_rate_pct']}% win rate; "
            f"Churn Ceiling: <{promised['max_churn_rate_pct']}%; "
            f"Support FCR: >{promised['min_first_contact_resolution_pct']}%; "
            f"Staff Attrition Risk Ceiling: <{promised['max_staff_attrition_risk_pct']}%."
        )
        try:
            resp = await client.put(
                f"{MEMORY_SERVICE_URL}/api/v1/summaries/strategic_goals_2026",
                headers=headers,
                json={
                    "scope_key": "strategic_goals_2026",
                    "module": "hr",
                    "title": "OmniDome Corporate Strategy & Promised Targets",
                    "summary": strategy_summary_text,
                    "metadata": {"category": "strategy", "targets": promised},
                },
            )
            if resp.status_code in (200, 201):
                results["summaries_created"] += 1
            else:
                results["errors"].append(f"Strategy summary: HTTP {resp.status_code}")
        except Exception as e:
            results["errors"].append(f"Strategy summary failed: {e}")

        # 3. Upsert PPP Framework Summary
        ppp_summary_text = (
            "HR & Operational PPP Framework: "
            "PPP-HR-POL-01 (Wellness & Overtime: max 12h shift, mandatory 36h rest post-outage, shift rebalance); "
            "PPP-SALES-PROC-02 (Sales Qualification: FNO feasibility + RICA verification required before Closed Won); "
            "PPP-RET-PROC-03 (Retention Authority: Tier 1 max 10%, Tier 2 max 20%, Tier 3 Executive up to 35% on high LTV); "
            "PPP-PERF-GOV-04 (Performance Accountability: deterministic evaluation vs immutable deals, customers, invoices)."
        )
        try:
            resp = await client.put(
                f"{MEMORY_SERVICE_URL}/api/v1/summaries/hr_ppp_framework",
                headers=headers,
                json={
                    "scope_key": "hr_ppp_framework",
                    "module": "hr",
                    "title": "OmniDome Operational Policies, Processes & Procedures (PPP)",
                    "summary": ppp_summary_text,
                    "metadata": {"category": "ppp", "count": len(OMNIDOME_PPP)},
                },
            )
            if resp.status_code in (200, 201):
                results["summaries_created"] += 1
            else:
                results["errors"].append(f"PPP summary: HTTP {resp.status_code}")
        except Exception as e:
            results["errors"].append(f"PPP summary failed: {e}")

        # 4. Write Individual Memory Entries for Granular Recall
        for ppp in OMNIDOME_PPP:
            try:
                resp = await client.post(
                    f"{MEMORY_SERVICE_URL}/api/v1/memories",
                    headers=headers,
                    json={
                        "source_type": "hr_policy_registry",
                        "source_id": ppp["code"],
                        "module": "hr",
                        "scope_key": "hr_ppp_framework",
                        "title": f"[{ppp['code']}] {ppp['title']}",
                        "content": f"{ppp['description']}\nRules:\n" + "\n".join(f"- {r}" for r in ppp["rules"]),
                        "summary": f"{ppp['title']}: {ppp['description'][:150]}",
                        "importance": "high",
                        "tags": ["ppp", "policy", "process", "procedure", ppp["category"].lower(), "hr"],
                        "metadata": {"code": ppp["code"], "category": ppp["category"]},
                    },
                )
                if resp.status_code in (200, 201):
                    results["entries_created"] += 1
                else:
                    results["errors"].append(f"Entry {ppp['code']}: HTTP {resp.status_code}")
            except Exception as e:
                results["errors"].append(f"Entry {ppp['code']} failed: {e}")

    logger.info("Synced HR Culture, Strategy, and PPP to Tenant Memory for %s: %s", tenant_id, results)
    return results
