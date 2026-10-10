"""Tool registry — wraps OmniDome microservice APIs as agent tools."""

import json
import os
import re
import logging


def sanitize_tool_name(name: str) -> str:
    """LLM providers (Anthropic via OpenRouter) require tool names to match
    ^[a-zA-Z0-9_-]{1,64}$ — our tool ids use dots (e.g. memory.recall), which
    get a 400. Map invalid chars to '_' deterministically so we can reverse it."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:64]
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

import httpx
from urllib.parse import unquote, urlparse

from services.common import internal_auth

logger = logging.getLogger(__name__)


def signed_service_headers(
    method: str,
    url: str,
    tenant_id: Optional[str],
    user_id: Optional[str],
    roles: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Identity headers for a service call, HMAC-signed over this exact method and
    path (services/common/internal_auth), roles included so the signature covers
    them. Unsigned (header-mode peers) only when INTERNAL_AUTH_SECRET is not set."""
    headers: Dict[str, str] = {}
    if tenant_id:
        headers["X-Tenant-Id"] = str(tenant_id)
    if user_id:
        headers["X-User-Id"] = str(user_id)
    if roles:
        headers["X-Roles"] = ",".join(sorted({str(r).strip() for r in roles if str(r).strip()}))
    if not headers:
        return headers
    try:
        secret = internal_auth.get_secret()
    except internal_auth.IdentityConfigError:
        return headers
    headers.update(internal_auth.sign_headers(headers, method, unquote(urlparse(url).path), secret))
    return headers

# Service URL resolution
SERVICE_URLS = {
    "crm": os.getenv("CRM_SERVICE_URL", "http://crm:8001"),
    "billing": os.getenv("BILLING_SERVICE_URL", "http://billing:8003"),
    "network": os.getenv("NETWORK_SERVICE_URL", "http://network:8005"),
    "retention": os.getenv("RETENTION_SERVICE_URL", "http://retention:8012"),
    "support": os.getenv("SUPPORT_SERVICE_URL", "http://support:8008"),
    "analytics": os.getenv("ANALYTICS_SERVICE_URL", "http://analytics:8011"),
    "sales": os.getenv("SALES_SERVICE_URL", "http://sales:8002"),
    "finance": os.getenv("FINANCE_SERVICE_URL", "http://finance:8015"),
    "call_center": os.getenv("CALL_CENTER_SERVICE_URL", "http://call_center:8007"),
    "communication": os.getenv("COMMUNICATION_SERVICE_URL", "http://communication:8020"),
    "memory": os.getenv("TENANT_MEMORY_SERVICE_URL", "http://tenant_memory:8025"),
    "fno_intelligence": os.getenv("FNO_INTELLIGENCE_SERVICE_URL", "http://fno-intelligence:8024"),
    "hr": os.getenv("HR_SERVICE_URL", "http://hr:8009"),
    "portal": os.getenv("PORTAL_BUILDER_SERVICE_URL", "http://portal_builder:8018"),
}


# Run in-process by knowledge_client (signed calls to tenant_memory's knowledge routes).
KNOWLEDGE_TOOL_NAMES = frozenset({
    "knowledge.search", "knowledge.context", "memory.working.get", "memory.working.put", "metrics.facts"})


# Run in-process by safe_sql; the calling agent decides which tables it may read.
SQL_TOOL_NAMES = ("analytics.query", "analytics_query")


@dataclass(frozen=True)
class ToolPolicy:
    """What a tool may do (spec A6). HTTP method is not a reliable signal: the
    web-intel tools POST but only read."""
    mutates: bool = True             # changes data; runs alone, never in parallel (A5)
    requires_approval: bool = False  # waits for a person before running (A8)
    timeout_s: int = 60
    max_output_chars: int = 8000     # cap on the result sent back to the model (A3)


_READ = ToolPolicy(mutates=False)
_WEB_READ = ToolPolicy(mutates=False, timeout_s=120, max_output_chars=12000)

# Every registered tool has an explicit entry (enforced by tests/test_tool_policy.py).
TOOL_POLICIES: Dict[str, ToolPolicy] = {
    # CRM
    "crm_get_customer": _READ,
    "crm_get_customer_360": _READ,
    "crm_create_customer": ToolPolicy(mutates=True, requires_approval=True),
    # Billing
    "billing_get_balance": _READ,
    "billing_get_invoice": _READ,
    "billing_get_payment_history": _READ,
    # Network: diagnostics can act on the line, so it runs alone.
    "network_check_coverage": _READ,
    "network_get_service_status": _READ,
    # Support
    "support_create_ticket": ToolPolicy(mutates=True, requires_approval=True),
    "support_get_tickets": _READ,
    # Retention, analytics, sales, finance, call centre
    "retention_get_predictions": _READ,
    "retention_get_cases": _READ,
    "analytics_get_executive_summary": _READ,
    "analytics_get_mrr_trends": _READ,
    "analytics_get_network_health": _READ,
    "analytics.query": ToolPolicy(mutates=False, timeout_s=10, max_output_chars=8000),
    "sales_get_pipeline": _READ,
    "sales.get_pipeline": _READ,
    "finance_get_financial_summary": _READ,
    "call_center_get_intelligence": _READ,
    "call_center_get_queues": _READ,
    "call_center_get_agent_metrics": _READ,
    # Products, talent & HR
    "products_list_plans": _READ,
    "products_list_bundles": _READ,
    "talent_list_employees": _READ,
    "talent_get_performance_summary": _READ,
    "hr.list_employees": _READ,
    "hr.get_employee": _READ,
    "hr.get_wellness_insights": _READ,
    "hr.execute_wellness_action": ToolPolicy(mutates=True, requires_approval=True),
    "hr.get_attrition_risk": _READ,
    "hr.list_leave_requests": _READ,
    # Tenant memory
    "memory.recall": _READ,
    "memory.write_entry": ToolPolicy(mutates=True),
    "memory.upsert_summary": ToolPolicy(mutates=True),
    # Knowledge layer: reads, plus a per-conversation scratchpad that expires and cannot be pinned
    # (so it is not a data change and needs no Jev review).
    "knowledge.search": ToolPolicy(mutates=False, timeout_s=10),
    "knowledge.context": ToolPolicy(mutates=False, timeout_s=10),
    "memory.working.get": ToolPolicy(mutates=False, timeout_s=10),
    "memory.working.put": ToolPolicy(mutates=False, timeout_s=10),
    "metrics.facts": ToolPolicy(mutates=False, timeout_s=10),
    # FNO web intelligence (Firecrawl): reads, but slow and large
    "fno_intelligence.web_intel_product_research": _WEB_READ,
    "fno_intelligence.web_intel_fno_site_message": _WEB_READ,
    "fno_intelligence.web_intel_new_site_releases": _WEB_READ,
    "fno_intelligence.web_intel_cancellation_processing": _WEB_READ,
    "fno_intelligence.web_intel_address_lookup": _WEB_READ,
    "fno_intelligence.web_intel_competitor_analysis": _WEB_READ,
    # Strategy & Deterministic Goals
    "strategy.track_performance": _READ,
    "strategy_track_performance": _READ,
    "strategy.get_strategic_goals": _READ,
    "strategy_get_strategic_goals": _READ,
    # A sub-agent may call mutating tools itself (each gated on its own), so the
    # consultation runs alone and gets a longer timeout.
    "orchestrator_consult_specialist": ToolPolicy(mutates=True, timeout_s=180),
    "orchestrator.consult_specialist": ToolPolicy(mutates=True, timeout_s=180),
}

# User decision 2026-09-24: creating customers or tickets, provisioning,
# customer-facing sends, refunds and posting/publishing campaigns need approval.
# Tools not in TOOL_POLICIES whose names match this are gated automatically.
_APPROVAL_NAME_RE = re.compile(
    r"refund|publish|post_campaign|send_campaign|provision|send_customer|customer_message|"
    r"send_(sms|email|whatsapp)", re.IGNORECASE)


def policy_for(name: str) -> ToolPolicy:
    """Explicit policy, or the safe default for tools not listed yet."""
    if name in TOOL_POLICIES:
        return TOOL_POLICIES[name]
    return ToolPolicy(mutates=True, requires_approval=bool(_APPROVAL_NAME_RE.search(name)))


@dataclass
class Tool:
    name: str
    description: str
    service: str
    method: str
    endpoint: str
    parameters: Dict[str, Any]
    # Filled from the tool's ToolPolicy when registered (spec A6).
    mutates: bool = True
    requires_approval: bool = False
    timeout_s: int = 60
    max_output_chars: int = 8000

    async def execute(
        self,
        tool_input: Dict[str, Any],
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        roles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute the tool by calling the microservice API or internal handler.
        agent_type selects the SQL tool's table allowlist (spec A9)."""
        if self.name in SQL_TOOL_NAMES:
            from services.agent_orchestrator.safe_sql import execute_safe_sql
            return await execute_safe_sql(
                query=tool_input.get("query") or tool_input.get("sql", ""),
                tenant_id=tenant_id,
                user_id=user_id,
                agent_type=agent_type,
                timeout_s=self.timeout_s,
                max_output_chars=self.max_output_chars,
            )

        if self.name in KNOWLEDGE_TOOL_NAMES:
            from services.agent_orchestrator import knowledge_client
            return await knowledge_client.run_tool(
                self.name, tool_input, tenant_id=tenant_id, user_id=user_id, roles=roles,
                agent_type=agent_type, timeout_s=float(self.timeout_s))

        if self.name in ("strategy.track_performance", "strategy_track_performance"):
            from services.agent_orchestrator.goals import track_deterministic_performance
            return await track_deterministic_performance(
                tenant_id=tenant_id,
                target_overrides=tool_input.get("target_overrides"),
            )

        if self.name in ("strategy.get_strategic_goals", "strategy_get_strategic_goals"):
            from services.agent_orchestrator.goals import get_strategic_goals_and_culture
            return await get_strategic_goals_and_culture(tenant_id=tenant_id)

        base_url = SERVICE_URLS.get(self.service, "")
        if not base_url:
            return {"success": False, "error": f"Service {self.service} not configured"}

        url = f"{base_url}{self.endpoint}"
        request_input = dict(tool_input)
        if self.name in {"memory.write_entry", "memory.upsert_summary"}:
            metadata = request_input.get("metadata")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    return {"success": False, "error": "Memory metadata must be a JSON object"}
                if not isinstance(metadata, dict):
                    return {"success": False, "error": "Memory metadata must be a JSON object"}
                request_input["metadata"] = metadata
        if self.name == "memory.recall" and "limit" in request_input:
            try:
                request_input["limit"] = max(1, min(50, int(request_input["limit"])))
            except (TypeError, ValueError):
                return {"success": False, "error": "Memory recall limit must be an integer"}
        for key, value in list(request_input.items()):
            placeholder = "{" + key + "}"
            if placeholder in url:
                url = url.replace(placeholder, str(value))
                request_input.pop(key, None)
        headers = signed_service_headers(self.method, url, tenant_id, user_id, roles)

        try:
            # Per-tool timeout (spec A6): the web-intel tools need well over 10 s.
            async with httpx.AsyncClient(timeout=float(self.timeout_s)) as client:
                if self.method == "GET":
                    # Map tool_input to query params
                    resp = await client.get(url, params=request_input, headers=headers)
                elif self.method == "POST":
                    resp = await client.post(url, json=request_input, headers=headers)
                elif self.method == "PUT":
                    body = dict(request_input)
                    if self.name == "memory.upsert_summary" and "scope_key" not in body:
                        body["scope_key"] = tool_input.get("scope_key")
                    resp = await client.put(url, json=body, headers=headers)
                elif self.method == "PATCH":
                    resp = await client.patch(url, json=request_input, headers=headers)
                else:
                    return {"success": False, "error": f"Unsupported method: {self.method}"}

                if 200 <= resp.status_code < 300:
                    return {"success": True, "data": resp.json()}
                else:
                    return {
                        "success": False,
                        "error": f"{self.service} returned {resp.status_code}",
                        "detail": resp.text[:500],
                    }
        except httpx.TimeoutException:
            logger.warning("Tool %s timed out", self.name)
            return {"success": False, "error": f"{self.service} timeout"}
        except Exception as e:
            logger.error("Tool %s failed: %s", self.name, e)
            return {"success": False, "error": str(e)}


class ToolRegistry:
    """Central registry of all agent tools."""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        """Register all built-in OmniDome service tools."""

        # ── CRM Tools ─────────────────────────────────────────────
        self.register(Tool(
            name="crm_get_customer",
            description="Search customers by name, email, phone or account number.",
            service="crm",
            method="GET",
            endpoint="/customers",
            parameters={"type": "object", "properties": {"search": {"type": "string", "description": "Name, email, phone or account number"}}, "required": ["search"]},
        ))
        self.register(Tool(
            name="crm_get_customer_360",
            description="Get full Customer 360 view including billing, support tickets, and network services.",
            service="crm",
            method="GET",
            endpoint="/customers/{customer_id}/360/details",
            parameters={"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]},
        ))
        self.register(Tool(
            name="crm_create_customer",
            description="Create a new customer record.",
            service="crm",
            method="POST",
            endpoint="/customers",
            parameters={"type": "object", "properties": {"first_name": {"type": "string"}, "last_name": {"type": "string"}, "email": {"type": "string"}, "phone": {"type": "string"}}, "required": ["first_name", "last_name"]},
        ))

        # ── Billing Tools ────────────────────────────────────────
        self.register(Tool(
            name="billing_get_balance",
            description="List a customer's invoices with totals and amounts paid, to work out what they owe.",
            service="billing",
            method="GET",
            endpoint="/invoices",
            parameters={"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]},
        ))
        self.register(Tool(
            name="billing_get_invoice",
            description="Get a specific invoice by ID.",
            service="billing",
            method="GET",
            endpoint="/invoices/{invoice_id}",
            parameters={"type": "object", "properties": {"invoice_id": {"type": "string"}}, "required": ["invoice_id"]},
        ))
        self.register(Tool(
            name="billing_get_payment_history",
            description="Get customer's payment history.",
            service="billing",
            method="GET",
            endpoint="/payments",
            parameters={"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]},
        ))

        # ── Network Tools ────────────────────────────────────────
        self.register(Tool(
            name="network_check_coverage",
            description="Check fibre availability at an address.",
            service="network",
            method="POST",
            endpoint="/coverage/check",
            parameters={"type": "object", "properties": {"address": {"type": "string"}, "city": {"type": "string"}, "province": {"type": "string"}, "postal_code": {"type": "string"}}, "required": ["address"]},
        ))
        self.register(Tool(
            name="network_get_service_status",
            description="Get customer's network service status.",
            service="network",
            method="GET",
            endpoint="/services",
            parameters={"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]},
        ))

        # ── Support Tools ────────────────────────────────────────
        self.register(Tool(
            name="support_create_ticket",
            description="Create a support ticket for a customer.",
            service="support",
            method="POST",
            endpoint="/tickets",
            parameters={"type": "object", "properties": {"customer_id": {"type": "string"}, "subject": {"type": "string"}, "description": {"type": "string"}, "priority": {"type": "string"}}, "required": ["customer_id", "subject", "description"]},
        ))
        self.register(Tool(
            name="support_get_tickets",
            description="Get support tickets filtered by customer, status, or priority.",
            service="support",
            method="GET",
            endpoint="/tickets",
            parameters={"type": "object", "properties": {"customer_id": {"type": "string"}, "status": {"type": "string"}, "priority": {"type": "string"}}, "required": []},
        ))

        # ── Retention Tools ──────────────────────────────────────
        self.register(Tool(
            name="retention_get_predictions",
            description="Get churn predictions, optionally filtered by risk level.",
            service="retention",
            method="GET",
            endpoint="/predictions",
            parameters={"type": "object", "properties": {"risk_level": {"type": "string"}, "limit": {"type": "integer"}}, "required": []},
        ))
        self.register(Tool(
            name="retention_get_cases",
            description="Get active retention cases.",
            service="retention",
            method="GET",
            endpoint="/cases",
            parameters={"type": "object", "properties": {"status": {"type": "string"}, "risk_level": {"type": "string"}}, "required": []},
        ))

        # ── Analytics Tools ─────────────────────────────────────
        self.register(Tool(
            name="analytics_get_executive_summary",
            description="Get AI-driven executive summary with trends and recommendations.",
            service="analytics",
            method="GET",
            endpoint="/analytics/executive-summary",
            parameters={"type": "object", "properties": {}, "required": []},
        ))

        # ── Sales Tools ─────────────────────────────────────────
        self.register(Tool(
            name="sales_get_pipeline",
            description="Get sales pipeline summary.",
            service="sales",
            method="GET",
            endpoint="/pipeline",
            parameters={"type": "object", "properties": {"status": {"type": "string"}}, "required": []},
        ))

        # ── Finance Tools ───────────────────────────────────────
        self.register(Tool(
            name="finance_get_financial_summary",
            description="Get the financial overview (revenue, expenses, margins) from the general ledger.",
            service="finance",
            method="GET",
            endpoint="/overview",
            parameters={"type": "object", "properties": {}, "required": []},
        ))

        # ── Call Center Tools ───────────────────────────────────
        self.register(Tool(
            name="call_center_get_intelligence",
            description="Get call center health metrics and sentiment data.",
            service="call_center",
            method="GET",
            endpoint="/reports/intelligence",
            parameters={"type": "object", "properties": {}, "required": []},
        ))

        # Tenant Memory Tools
        self.register(Tool(
            name="memory.recall",
            description="Recall tenant memory summaries and recent entries by module, scope, or search query.",
            service="memory",
            method="GET",
            endpoint="/api/v1/recall",
            parameters={
                "type": "object",
                "properties": {
                    "module": {"type": "string"},
                    "scope_key": {"type": "string"},
                    "q": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": [],
            },
        ))
        self.register(Tool(
            name="memory.write_entry",
            description="Write tenant memory about an agent decision, user preference, incident, or operational event.",
            service="memory",
            method="POST",
            endpoint="/api/v1/memories",
            parameters={
                "type": "object",
                "properties": {
                    "source_type": {"type": "string"},
                    "source_id": {"type": "string"},
                    "module": {"type": "string"},
                    "scope_key": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "summary": {"type": "string"},
                    "importance": {"type": "string", "enum": ["low", "normal", "high", "critical"]},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "metadata": {"type": "object"},
                },
                "required": ["source_type", "title", "content"],
            },
        ))
        self.register(Tool(
            name="memory.upsert_summary",
            description="Create or update a compact tenant memory summary for a scope key.",
            service="memory",
            method="PUT",
            endpoint="/api/v1/summaries/{scope_key}",
            parameters={
                "type": "object",
                "properties": {
                    "scope_key": {"type": "string"},
                    "module": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "source_entry_ids": {"type": "array", "items": {"type": "string"}},
                    "metadata": {"type": "object"},
                },
                "required": ["scope_key", "title", "summary"],
            },
        ))

        # Knowledge layer tools (docs/knowledge-layer.md). Executed by knowledge_client; the endpoint is the
        # route it calls (kept so tests/test_tool_routes.py proves it exists).
        self.register(Tool(
            name="knowledge.search",
            description=("Search company knowledge cards (customers, deals, campaigns, research, past decisions) "
                         "with hybrid semantic + keyword search. Returns UNTRUSTED reference text with card_ids to cite. "
                         "For context and history only: exact figures come from governed queries."),
            service="memory", method="POST", endpoint="/api/v1/knowledge/search",
            parameters={"type": "object", "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "default": 6, "description": "max cards, 1-15"},
                "modules": {"type": "array", "items": {"type": "string"}, "description": "e.g. crm, sales, marketing, analytics"},
                "source_types": {"type": "array", "items": {"type": "string"}, "description": "e.g. customer, deal, campaign, research"},
            }, "required": ["query"]},
        ))
        self.register(Tool(
            name="knowledge.context",
            description=("Get a token-budgeted pack of the most relevant knowledge cards for a question, with numbered "
                         "citations and card_ids. UNTRUSTED reference data; cite card_ids when you use it."),
            service="memory", method="POST", endpoint="/api/v1/knowledge/context",
            parameters={"type": "object", "properties": {
                "query": {"type": "string"},
                "budget_tokens": {"type": "integer", "default": 1500, "description": "200-4000"},
                "modules": {"type": "array", "items": {"type": "string"}},
            }, "required": ["query"]},
        ))
        self.register(Tool(
            name="memory.working.get",
            description="Read this conversation's short-term scratchpad (notes and recent turns). It expires.",
            service="memory", method="GET", endpoint="/api/v1/memory/working/{session_key}",
            parameters={"type": "object", "properties": {"limit": {"type": "integer", "default": 20}}, "required": []},
        ))
        self.register(Tool(
            name="memory.working.put",
            description=("Save a short note or intermediate state to this conversation's short-term scratchpad "
                         "(e.g. a customer id you resolved, a plan step). It expires; use memory.write_entry for "
                         "anything that must last."),
            service="memory", method="POST", endpoint="/api/v1/memory/working",
            parameters={"type": "object", "properties": {
                "content": {"type": "string"},
                "kind": {"type": "string", "enum": ["note", "state"]},
                "title": {"type": "string"},
            }, "required": ["content"]},
        ))
        self.register(Tool(
            name="metrics.facts",
            description=("Read-only: the latest stored deterministic metric facts for a metric key and optional period "
                         "(e.g. revenue, 2026-03). Each states its value, period, as-of date and governed source query. "
                         "You cannot write facts; re-verify through the governed query tool before reporting."),
            service="memory", method="POST", endpoint="/api/v1/knowledge/search",
            parameters={"type": "object", "properties": {
                "metric_key": {"type": "string", "description": "e.g. revenue, billing.mrr"},
                "period": {"type": "string", "description": "e.g. 2026-03"},
                "kind": {"type": "string", "enum": ["actual", "forecast", "target"]},
            }, "required": ["metric_key"]},
        ))

        self.register(Tool(
            name="fno_intelligence.web_intel_product_research",
            description="Research an FNO's (fibre network operator's) products, packages, speeds and prices via live web search. Returns an LLM-summarised product lineup. Use when a user asks what packages/products an FNO offers.",
            service="fno_intelligence",
            method="POST",
            endpoint="/api/fno/web-intel/product-research",
            parameters={"type": "object", "properties": {
                "fno_name": {"type": "string", "description": "FNO name, e.g. 'Vuma Fibre', 'Vumatel', 'Openserve', 'Frogfoot'"},
                "product_query": {"type": "string", "description": "Optional custom search query override"},
            }, "required": ["fno_name"]},
        ))
        self.register(Tool(
            name="fno_intelligence.web_intel_fno_site_message",
            description="Scrape the latest message or announcement banner from an FNO's portal/website. Use to fetch current FNO notices, outage comms, or portal messages.",
            service="fno_intelligence",
            method="POST",
            endpoint="/api/fno/web-intel/fno-site-message",
            parameters={"type": "object", "properties": {
                "portal_url": {"type": "string", "description": "Full URL of the FNO portal or announcement page to scrape"},
            }, "required": ["portal_url"]},
        ))
        self.register(Tool(
            name="fno_intelligence.web_intel_new_site_releases",
            description="Discover newly-released fibre coverage areas / build sites for an FNO via web search. Use when checking where an FNO has just launched or is launching coverage.",
            service="fno_intelligence",
            method="POST",
            endpoint="/api/fno/web-intel/new-site-releases",
            parameters={"type": "object", "properties": {
                "fno_name": {"type": "string", "description": "FNO name"},
                "city": {"type": "string", "description": "Optional city filter"},
            }, "required": ["fno_name"]},
        ))
        self.register(Tool(
            name="fno_intelligence.web_intel_cancellation_processing",
            description="Extract an FNO's cancellation / termination procedure and required steps from its website. Use when a customer wants to cancel or when processing a cancellation request.",
            service="fno_intelligence",
            method="POST",
            endpoint="/api/fno/web-intel/cancellation-processing",
            parameters={"type": "object", "properties": {
                "fno_name": {"type": "string", "description": "FNO name"},
                "portal_url": {"type": "string", "description": "Optional explicit cancellation-page URL"},
            }, "required": ["fno_name"]},
        ))
        self.register(Tool(
            name="fno_intelligence.web_intel_address_lookup",
            description="Resolve a street address to fibre coverage / available FNOs via web search. Use to check which fibre networks service a given address.",
            service="fno_intelligence",
            method="POST",
            endpoint="/api/fno/web-intel/address-lookup",
            parameters={"type": "object", "properties": {
                "address": {"type": "string", "description": "Street address to look up"},
                "fno_name": {"type": "string", "description": "Optional FNO to scope the lookup to"},
            }, "required": ["address"]},
        ))
        self.register(Tool(
            name="fno_intelligence.web_intel_competitor_analysis",
            description="Compare an FNO against named competitors (pricing, speeds, coverage, reliability) using web data and LLM analysis. Use for competitive intelligence questions.",
            service="fno_intelligence",
            method="POST",
            endpoint="/api/fno/web-intel/competitor-analysis",
            parameters={"type": "object", "properties": {
                "fno_name": {"type": "string", "description": "FNO to analyse"},
                "competitors": {"type": "array", "items": {"type": "string"}, "description": "Competitor FNO names to compare against"},
            }, "required": ["fno_name"]},
        ))

        # ── Call Center Tools (Read-Only) ───────────────────────────
        self.register(Tool(
            name="call_center_get_queues",
            description="Get real-time call center queue status, active callers waiting, and SLA health.",
            service="call_center",
            method="GET",
            endpoint="/queues/dashboard/summary",
            parameters={"type": "object", "properties": {}, "required": []},
        ))
        self.register(Tool(
            name="call_center_get_agent_metrics",
            description="Get call center agent statuses, active calls, and daily resolution stats.",
            service="call_center",
            method="GET",
            endpoint="/agents",
            parameters={"type": "object", "properties": {}, "required": []},
        ))

        # ── Product Catalog Tools (Read-Only) ───────────────────────
        self.register(Tool(
            name="products_list_plans",
            description="List active broadband and VoIP plans with pricing, speeds, and router equipment.",
            service="billing",
            method="GET",
            endpoint="/plans",
            parameters={"type": "object", "properties": {}, "required": []},
        ))
        self.register(Tool(
            name="products_list_bundles",
            description="List combined fiber & voice packages, bundle discounts, and add-on services.",
            service="billing",
            method="GET",
            endpoint="/bundles",
            parameters={"type": "object", "properties": {}, "required": []},
        ))

        # ── Talent & HR Tools ───────────────────────────────────────
        self.register(Tool(
            name="talent_list_employees",
            description="Query employee directory, departments, and active shift rosters.",
            service="hr",
            method="GET",
            endpoint="/employees",
            parameters={"type": "object", "properties": {"department": {"type": "string"}}, "required": []},
        ))
        self.register(Tool(
            name="talent_get_performance_summary",
            description="Get team performance metrics, completed reviews, and attrition risk indicators.",
            service="hr",
            method="GET",
            endpoint="/analytics/attrition-risk",
            parameters={"type": "object", "properties": {}, "required": []},
        ))
        self.register(Tool(
            name="hr.list_employees",
            description="Query employee directory, departments, and active rosters.",
            service="hr",
            method="GET",
            endpoint="/employees",
            parameters={"type": "object", "properties": {"department": {"type": "string"}}, "required": []},
        ))
        self.register(Tool(
            name="hr.get_employee",
            description="Get detailed profile, contact info, and tenure for a specific employee.",
            service="hr",
            method="GET",
            endpoint="/employees/{employee_id}",
            parameters={"type": "object", "properties": {"employee_id": {"type": "string"}}, "required": ["employee_id"]},
        ))
        self.register(Tool(
            name="hr.get_wellness_insights",
            description="Retrieve team burnout indicators, sentiment scores, and wellness survey trends.",
            service="hr",
            method="GET",
            endpoint="/cross-service/orchestrator/wellness",
            parameters={"type": "object", "properties": {"department": {"type": "string"}}, "required": []},
        ))
        self.register(Tool(
            name="hr.execute_wellness_action",
            description="Trigger a wellness check-in, workload rebalancing, or support plan for an employee.",
            service="hr",
            method="POST",
            endpoint="/cross-service/orchestrator/wellness/{alert_id}/execute",
            parameters={
                "type": "object",
                "properties": {
                    "alert_id": {"type": "string"},
                    "action_type": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["alert_id"],
            },
        ))
        self.register(Tool(
            name="hr.get_attrition_risk",
            description="Get attrition risk scores, flight-risk factors, and retention suggestions.",
            service="hr",
            method="GET",
            endpoint="/analytics/attrition-risk",
            parameters={"type": "object", "properties": {}, "required": []},
        ))
        self.register(Tool(
            name="hr.list_leave_requests",
            description="List an employee's leave requests (pending and approved), newest first.",
            service="hr",
            method="GET",
            endpoint="/employees/{emp_id}/leave",
            parameters={"type": "object", "properties": {"emp_id": {"type": "string", "description": "Employee id"}}, "required": ["emp_id"]},
        ))
        self.register(Tool(
            name="sales.get_pipeline",
            description="Get sales pipeline summary with stages, deal counts, and conversion probabilities.",
            service="sales",
            method="GET",
            endpoint="/pipeline",
            parameters={"type": "object", "properties": {"status": {"type": "string"}}, "required": []},
        ))

        # ── Analytics & Telemetry Tools (Read-Only) ─────────────────
        self.register(Tool(
            name="analytics_get_mrr_trends",
            description="Get revenue broken down by plan and FNO for a period.",
            service="analytics",
            method="GET",
            endpoint="/analytics/revenue",
            parameters={"type": "object", "properties": {"period": {"type": "string", "description": "7d, 30d or 90d"}}, "required": []},
        ))
        self.register(Tool(
            name="analytics_get_network_health",
            description="Get network utilisation and FNO performance.",
            service="analytics",
            method="GET",
            endpoint="/analytics/network",
            parameters={"type": "object", "properties": {}, "required": []},
        ))
        self.register(Tool(
            name="analytics.query",
            description=(
                "Safely query structured business data using read-only SQL (WeKnora pattern). "
                "Allowed tables and columns: "
                "leads(id, first_name, last_name, email, phone, address, source, interest_level, status, priority, coverage_area, interested_package, created_at); "
                "deals(id, name, amount, value_zar, status, close_date, contact_id, lead_id, stage_id); "
                "contacts(id, first_name, last_name, email, phone, physical_address, status); "
                "customers(id, account_number, status, balance_zar); "
                "invoices(id, invoice_number, total_zar, balance_zar, status, due_date); "
                "subscriptions(id, status, monthly_fee_zar); "
                "tickets(id, ticket_number, subject, status, priority). "
                "Rules: In leads use 'interest_level' (1-5) and 'created_at' for ranking top leads. In deals use 'name' and 'value_zar' (NOT title or deal_value). In contacts use 'first_name', 'last_name' (no company column). "
                "Returns table rows, row count and columns. The query is automatically rewritten to be strictly scoped to your tenant."
            ),
            service="orchestrator",
            method="POST",
            endpoint="/api/tools/analytics/query",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A single SELECT query in PostgreSQL syntax",
                    }
                },
                "required": ["query"],
            },
        ))

        # ── Cross-Agent Orchestration Tools ──────────────────────────
        self.register(Tool(
            name="orchestrator_consult_specialist",
            description=(
                "Consult an internal specialist agent to gather domain expertise and multi-agent findings. "
                "Available specialists: 'churnguard' (retention risks & LTV), 'supportbot' (troubleshooting & tickets), "
                "'domebot' (customer service & plans), 'provisionbot' (onboarding & fibre provisioning), "
                "'analytics' (telemetry & metrics), 'talent' (HR & call center performance)."
            ),
            service="orchestrator",
            method="POST",
            endpoint="/api/agents/internal/consult",
            parameters={
                "type": "object",
                "properties": {
                    "specialist": {
                        "type": "string",
                        "description": "Specialist agent name: churnguard, supportbot, domebot, provisionbot, analytics, talent",
                        "enum": ["churnguard", "supportbot", "domebot", "provisionbot", "analytics", "talent"],
                    },
                    "query": {
                        "type": "string",
                        "description": "The specific question or directive for the specialist",
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional context such as customer_id, ticket_id, or background details",
                    },
                },
                "required": ["specialist", "query"],
            },
        ))

        # ── Strategy & Deterministic Goals Tools ────────────────────
        self.register(Tool(
            name="strategy.track_performance",
            description=(
                "Track actual business performance deterministically against promised corporate targets. "
                "Queries immutable tables (deals, customers, subscriptions, invoices) to calculate real MRR, "
                "active subscriber count, pipeline value, closed-won totals, and win rate with variance scoring."
            ),
            service="orchestrator",
            method="POST",
            endpoint="/api/tools/strategy/track_performance",
            parameters={"type": "object", "properties": {}, "required": []},
        ))
        self.register(Tool(
            name="strategy.get_strategic_goals",
            description=(
                "Retrieve corporate strategy, promised targets (FY 2026/2027), culture pillars, and "
                "HR PPP (Policy, Process, Procedure) governance frameworks (BCEA wellness, sales stages, retention authority)."
            ),
            service="orchestrator",
            method="GET",
            endpoint="/api/tools/strategy/get_strategic_goals",
            parameters={"type": "object", "properties": {}, "required": []},
        ))

    def register(self, tool: Tool):
        policy = policy_for(tool.name)
        tool.mutates = policy.mutates
        tool.requires_approval = policy.requires_approval
        tool.timeout_s = policy.timeout_s
        tool.max_output_chars = policy.max_output_chars
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        tool = self._tools.get(name)
        if tool:
            return tool
        # The LLM may return a sanitized name (dots→underscores); reverse-map it.
        for t in self._tools.values():
            if sanitize_tool_name(t.name) == name:
                return t
        return None

    def list_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def filter_for_agent(self, agent_type: str) -> List[Tool]:
        """Return only tools an agent type is allowed to use."""

        FNO_TOOLS = [
            "fno_intelligence.web_intel_product_research",
            "fno_intelligence.web_intel_fno_site_message",
            "fno_intelligence.web_intel_new_site_releases",
            "fno_intelligence.web_intel_cancellation_processing",
            "fno_intelligence.web_intel_address_lookup",
            "fno_intelligence.web_intel_competitor_analysis",
        ]
        KNOWLEDGE_TOOLS = ["knowledge.search", "knowledge.context", "memory.working.get", "memory.working.put"]
        METRIC_TOOLS = ["metrics.facts"]
        AGENT_TOOL_PERMISSIONS = {
            "customer_facing": [
                "crm_get_customer", "crm_get_customer_360",
                "billing_get_balance", "billing_get_invoice", "billing_get_payment_history",
                "products_list_plans", "products_list_bundles",
                "network_check_coverage", "network_get_service_status",
                "support_create_ticket", "support_get_tickets",
                "memory.recall", "memory.write_entry",
            ] + FNO_TOOLS,
            "retention": [
                "crm_get_customer", "crm_get_customer_360",
                "billing_get_balance", "billing_get_invoice", "billing_get_payment_history",
                "retention_get_predictions", "retention_get_cases",
                "products_list_plans", "products_list_bundles",
                "support_create_ticket", "support_get_tickets",
                "strategy.track_performance", "strategy.get_strategic_goals",
                "memory.recall", "memory.write_entry",
            ] + FNO_TOOLS,
            "provisioning": [
                "crm_get_customer", "crm_get_customer_360",
                "network_check_coverage", "network_get_service_status",
                "billing_get_balance", "billing_get_invoice",
                "support_create_ticket", "support_get_tickets",
                "memory.recall", "memory.write_entry",
            ] + FNO_TOOLS,
            "executive": [
                "orchestrator_consult_specialist", "orchestrator.consult_specialist",
                "strategy.track_performance", "strategy.get_strategic_goals",
                "analytics_get_executive_summary", "analytics_get_mrr_trends", "analytics_get_network_health",
                "analytics.query",
                "finance_get_financial_summary", "sales_get_pipeline", "sales.get_pipeline",
                "retention_get_predictions", "retention_get_cases",
                "call_center_get_intelligence", "call_center_get_queues",
                "talent_get_performance_summary", "hr.list_employees", "hr.get_wellness_insights", "hr.get_attrition_risk",
                "memory.recall", "memory.write_entry", "memory.upsert_summary",
            ] + FNO_TOOLS,
            "support": [
                "crm_get_customer", "crm_get_customer_360",
                "support_create_ticket", "support_get_tickets",
                "network_get_service_status",
                "billing_get_balance", "billing_get_invoice",
                "memory.recall", "memory.write_entry",
            ] + FNO_TOOLS,
            "billing": [
                "billing_get_balance", "billing_get_invoice", "billing_get_payment_history",
                "crm_get_customer", "crm_get_customer_360",
                "products_list_plans", "products_list_bundles",
                "memory.recall", "memory.write_entry",
            ] + FNO_TOOLS,
            "crm": [
                "crm_get_customer", "crm_get_customer_360", "crm_create_customer",
                "support_create_ticket", "support_get_tickets",
                "memory.recall", "memory.write_entry",
            ] + FNO_TOOLS,
            "call_center": [
                "call_center_get_queues", "call_center_get_agent_metrics", "call_center_get_intelligence",
                "crm_get_customer", "crm_get_customer_360",
                "support_create_ticket", "support_get_tickets",
                "memory.recall", "memory.write_entry",
            ],
            "products": [
                "products_list_plans", "products_list_bundles",
                "network_check_coverage",
                "memory.recall", "memory.write_entry",
            ] + FNO_TOOLS,
            "talent": [
                "talent_list_employees", "talent_get_performance_summary",
                "strategy.track_performance", "strategy.get_strategic_goals",
                "hr.list_employees", "hr.get_employee", "hr.get_wellness_insights",
                "hr.execute_wellness_action", "hr.get_attrition_risk", "hr.list_leave_requests",
                "call_center_get_agent_metrics",
                "memory.recall", "memory.write_entry",
            ],
            "analytics": [
                "strategy.track_performance", "strategy.get_strategic_goals",
                "analytics_get_mrr_trends", "analytics_get_network_health", "analytics_get_executive_summary",
                "analytics.query",
                "sales_get_pipeline", "sales.get_pipeline", "finance_get_financial_summary",
                "retention_get_predictions", "call_center_get_intelligence",
                "memory.recall", "memory.write_entry",
            ],
            "assistant": [
                "orchestrator_consult_specialist", "orchestrator.consult_specialist",
                "strategy.track_performance", "strategy.get_strategic_goals",
                "crm_get_customer", "crm_get_customer_360",
                "billing_get_balance", "billing_get_invoice",
                "products_list_plans", "products_list_bundles",
                "network_check_coverage", "network_get_service_status",
                "support_get_tickets",
                "sales.get_pipeline", "hr.list_employees", "hr.get_wellness_insights",
                "memory.recall", "memory.write_entry",
            ] + FNO_TOOLS,
        }

        # Knowledge layer (docs/knowledge-layer.md). Every agent gets search/context/scratchpad (the module
        # filter for customer_facing is enforced in knowledge_client); read-only metric facts go to the
        # agents that report on numbers.
        for _agent, _tools in AGENT_TOOL_PERMISSIONS.items():
            _tools.extend(t for t in KNOWLEDGE_TOOLS if t not in _tools)
            if _agent in ("executive", "analytics", "assistant", "billing", "retention", "products"):
                _tools.extend(t for t in METRIC_TOOLS if t not in _tools)

        if agent_type in ("auto", "orchestrator", "master"):
            return list(self._tools.values())

        allowed = AGENT_TOOL_PERMISSIONS.get(agent_type, AGENT_TOOL_PERMISSIONS.get("customer_facing", []))
        return [t for t in self._tools.values() if t.name in allowed]

    def to_openai_format(self, tools: List[Tool]) -> List[Dict]:
        """Convert tool list to OpenAI/Ollama tool-calling format, deterministically sorted for prompt caching."""
        sorted_tools = sorted(tools, key=lambda t: t.name)
        result = []
        for t in sorted_tools:
            result.append({
                "name": sanitize_tool_name(t.name),
                "description": t.description,
                "parameters": t.parameters,
            })
        return result


# Singleton
tool_registry = ToolRegistry()
