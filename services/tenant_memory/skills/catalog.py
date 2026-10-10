"""Snapshot of the orchestrator's real tool registry, used to validate skills.

tenant_memory cannot import the orchestrator (separate service). The snapshot is kept honest by
services/agent_orchestrator/tests/test_skills_runtime_v2.py, which fails when it drifts from tool_registry.
"""
from __future__ import annotations

# name -> (changes_data, requires_approval)
KNOWN_TOOLS: dict[str, tuple[bool, bool]] = {
    "analytics.query": (False, False), "artifacts.find": (False, False), "analytics_get_executive_summary": (False, False),
    "analytics_get_mrr_trends": (False, False), "analytics_get_network_health": (False, False),
    "billing_get_balance": (False, False), "billing_get_invoice": (False, False),
    "billing_get_payment_history": (False, False),
    "call_center_get_agent_metrics": (False, False), "call_center_get_intelligence": (False, False),
    "call_center_get_queues": (False, False),
    "crm_create_customer": (True, True), "crm_get_customer": (False, False), "crm_get_customer_360": (False, False),
    "finance_get_financial_summary": (False, False),
    "fno_intelligence.web_intel_address_lookup": (False, False),
    "fno_intelligence.web_intel_cancellation_processing": (False, False),
    "fno_intelligence.web_intel_competitor_analysis": (False, False),
    "fno_intelligence.web_intel_fno_site_message": (False, False),
    "fno_intelligence.web_intel_new_site_releases": (False, False),
    "fno_intelligence.web_intel_product_research": (False, False),
    "hr.execute_wellness_action": (True, True), "hr.get_attrition_risk": (False, False),
    "hr.get_employee": (False, False), "hr.get_wellness_insights": (False, False),
    "hr.list_employees": (False, False), "hr.list_leave_requests": (False, False),
    "knowledge.context": (False, False), "knowledge.search": (False, False),
    "memory.recall": (False, False), "memory.upsert_summary": (True, False),
    "memory.working.get": (False, False), "memory.working.put": (False, False), "memory.write_entry": (True, False),
    "metrics.facts": (False, False),
    "my.approvals": (False, False), "my.day": (False, False), "my.escalations": (False, False),
    "my.kpis": (False, False), "my.schedule": (False, False), "my.tasks": (False, False),
    "network_check_coverage": (False, False), "network_get_service_status": (False, False),
    "orchestrator_consult_specialist": (True, False),
    "products_list_bundles": (False, False), "products_list_plans": (False, False),
    "retention_get_cases": (False, False), "retention_get_predictions": (False, False),
    "sales.get_pipeline": (False, False), "sales_get_pipeline": (False, False),
    "skills.find": (False, False), "skills.get": (False, False),
    "strategy.get_strategic_goals": (False, False), "strategy.track_performance": (False, False),
    "support_create_ticket": (True, True), "support_get_tickets": (False, False),
    "talent_get_performance_summary": (False, False), "talent_list_employees": (False, False),
}

# Tools announced but not registered yet. Valid only as OPTIONAL tools (used if the agent has them). Empty today:
# artifacts.find and my.* are real now.
SOFT_TOOLS: frozenset = frozenset()

AGENT_TYPES = ("customer_facing", "retention", "provisioning", "executive", "support", "billing", "crm",
               "call_center", "products", "talent", "analytics", "assistant")

CATEGORIES = ("analytics", "sales", "finance", "support", "retention", "marketing", "operations", "onboarding",
              "productivity", "reporting", "operational")
SAFETY_CLASSES = ("read_only", "drafts_only", "can_act")
SCOPES = ("platform", "tenant", "team", "user")
STATUSES = ("draft", "active", "deprecated")


def tool_info(name: str) -> dict:
    mutates, approval = KNOWN_TOOLS.get(name, (False, False))
    return {"name": name, "mutates": mutates, "requires_approval": approval, "soft": name in SOFT_TOOLS}


def registry_listing() -> list[dict]:
    return [tool_info(n) for n in sorted(set(KNOWN_TOOLS) | SOFT_TOOLS)]
