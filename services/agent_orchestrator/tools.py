"""Tool registry — wraps OmniDome microservice APIs as agent tools."""

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

logger = logging.getLogger(__name__)

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
}


@dataclass
class Tool:
    name: str
    description: str
    service: str
    method: str
    endpoint: str
    parameters: Dict[str, Any]

    async def execute(
        self,
        tool_input: Dict[str, Any],
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute the tool by calling the microservice API."""
        base_url = SERVICE_URLS.get(self.service, "")
        if not base_url:
            return {"success": False, "error": f"Service {self.service} not configured"}

        url = f"{base_url}{self.endpoint}"
        request_input = dict(tool_input)
        for key, value in list(request_input.items()):
            placeholder = "{" + key + "}"
            if placeholder in url:
                url = url.replace(placeholder, str(value))
                request_input.pop(key, None)
        headers = {}
        if tenant_id:
            headers["X-Tenant-Id"] = str(tenant_id)
        if user_id:
            headers["X-User-Id"] = str(user_id)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
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
            description="Look up a customer by ID, email, phone, or account number. Returns full customer profile.",
            service="crm",
            method="GET",
            endpoint="/api/customers/search",
            parameters={"type": "object", "properties": {"customer_id": {"type": "string"}, "email": {"type": "string"}, "phone": {"type": "string"}, "account_number": {"type": "string"}}, "required": []},
        ))
        self.register(Tool(
            name="crm_get_customer_360",
            description="Get full Customer 360 view including billing, support tickets, and network services.",
            service="crm",
            method="GET",
            endpoint="/api/customers/{customer_id}",
            parameters={"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]},
        ))
        self.register(Tool(
            name="crm_create_customer",
            description="Create a new customer record.",
            service="crm",
            method="POST",
            endpoint="/api/customers",
            parameters={"type": "object", "properties": {"first_name": {"type": "string"}, "last_name": {"type": "string"}, "email": {"type": "string"}, "phone": {"type": "string"}}, "required": ["first_name", "last_name"]},
        ))

        # ── Billing Tools ────────────────────────────────────────
        self.register(Tool(
            name="billing_get_balance",
            description="Get customer's outstanding balance and latest invoice.",
            service="billing",
            method="GET",
            endpoint="/api/customers/{customer_id}/balance",
            parameters={"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]},
        ))
        self.register(Tool(
            name="billing_get_invoice",
            description="Get a specific invoice by ID.",
            service="billing",
            method="GET",
            endpoint="/api/invoices/{invoice_id}",
            parameters={"type": "object", "properties": {"invoice_id": {"type": "string"}}, "required": ["invoice_id"]},
        ))
        self.register(Tool(
            name="billing_get_payment_history",
            description="Get customer's payment history.",
            service="billing",
            method="GET",
            endpoint="/api/customers/{customer_id}/payments",
            parameters={"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]},
        ))

        # ── Network Tools ────────────────────────────────────────
        self.register(Tool(
            name="network_check_coverage",
            description="Check fibre availability at an address.",
            service="network",
            method="GET",
            endpoint="/api/coverage/check",
            parameters={"type": "object", "properties": {"address": {"type": "string"}, "latitude": {"type": "string"}, "longitude": {"type": "string"}}, "required": ["address"]},
        ))
        self.register(Tool(
            name="network_get_service_status",
            description="Get customer's network service status.",
            service="network",
            method="GET",
            endpoint="/api/services/customer/{customer_id}",
            parameters={"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]},
        ))
        self.register(Tool(
            name="network_run_diagnostics",
            description="Run remote CPE diagnostics for a customer.",
            service="network",
            method="POST",
            endpoint="/api/diagnostics/run",
            parameters={"type": "object", "properties": {"customer_id": {"type": "string"}, "service_id": {"type": "string"}}, "required": ["customer_id"]},
        ))

        # ── Support Tools ────────────────────────────────────────
        self.register(Tool(
            name="support_create_ticket",
            description="Create a support ticket for a customer.",
            service="support",
            method="POST",
            endpoint="/api/tickets",
            parameters={"type": "object", "properties": {"customer_id": {"type": "string"}, "subject": {"type": "string"}, "description": {"type": "string"}, "priority": {"type": "string"}}, "required": ["customer_id", "subject", "description"]},
        ))
        self.register(Tool(
            name="support_get_tickets",
            description="Get support tickets filtered by customer, status, or priority.",
            service="support",
            method="GET",
            endpoint="/api/tickets",
            parameters={"type": "object", "properties": {"customer_id": {"type": "string"}, "status": {"type": "string"}, "priority": {"type": "string"}}, "required": []},
        ))

        # ── Retention Tools ──────────────────────────────────────
        self.register(Tool(
            name="retention_get_predictions",
            description="Get churn predictions, optionally filtered by risk level.",
            service="retention",
            method="GET",
            endpoint="/api/predictions",
            parameters={"type": "object", "properties": {"risk_level": {"type": "string"}, "limit": {"type": "integer"}}, "required": []},
        ))
        self.register(Tool(
            name="retention_get_cases",
            description="Get active retention cases.",
            service="retention",
            method="GET",
            endpoint="/api/cases",
            parameters={"type": "object", "properties": {"status": {"type": "string"}, "risk_level": {"type": "string"}}, "required": []},
        ))

        # ── Analytics Tools ─────────────────────────────────────
        self.register(Tool(
            name="analytics_get_executive_summary",
            description="Get AI-driven executive summary with trends and recommendations.",
            service="analytics",
            method="GET",
            endpoint="/api/executive-summary",
            parameters={"type": "object", "properties": {}, "required": []},
        ))

        # ── Sales Tools ─────────────────────────────────────────
        self.register(Tool(
            name="sales_get_pipeline",
            description="Get sales pipeline summary.",
            service="sales",
            method="GET",
            endpoint="/api/pipeline",
            parameters={"type": "object", "properties": {"status": {"type": "string"}}, "required": []},
        ))

        # ── Finance Tools ───────────────────────────────────────
        self.register(Tool(
            name="finance_get_financial_summary",
            description="Get financial summary including revenue, expenses, and margins.",
            service="finance",
            method="GET",
            endpoint="/api/summary",
            parameters={"type": "object", "properties": {"period": {"type": "string"}}, "required": []},
        ))

        # ── Call Center Tools ───────────────────────────────────
        self.register(Tool(
            name="call_center_get_intelligence",
            description="Get call center health metrics and sentiment data.",
            service="call_center",
            method="GET",
            endpoint="/api/reports/intelligence",
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

    def register(self, tool: Tool):
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
        AGENT_TOOL_PERMISSIONS = {
            "customer_facing": [
                "crm_get_customer", "crm_get_customer_360", "crm_create_customer",
                "billing_get_balance", "billing_get_invoice", "billing_get_payment_history",
                "support_create_ticket", "support_get_tickets",
                "memory.recall", "memory.write_entry",
            ] + FNO_TOOLS,
            "retention": [
                "crm_get_customer", "crm_get_customer_360", "crm_create_customer",
                "billing_get_balance", "billing_get_invoice", "billing_get_payment_history",
                "support_create_ticket", "support_get_tickets",
                "memory.recall", "memory.write_entry",
            ] + FNO_TOOLS,
            "provisioning": [
                "crm_get_customer", "crm_get_customer_360",
                "billing_get_balance", "billing_get_invoice", "billing_get_payment_history",
                "support_create_ticket", "support_get_tickets",
                "memory.recall", "memory.write_entry",
            ] + FNO_TOOLS,
            "executive": [
                "crm_get_customer", "crm_get_customer_360",
                "billing_get_balance", "billing_get_invoice", "billing_get_payment_history",
                "support_create_ticket", "support_get_tickets",
                "memory.recall", "memory.write_entry",
            ] + FNO_TOOLS,
            "support": [
                "crm_get_customer", "crm_get_customer_360",
                "billing_get_balance", "billing_get_invoice", "billing_get_payment_history",
                "support_create_ticket", "support_get_tickets",
                "memory.recall", "memory.write_entry",
            ] + FNO_TOOLS,
            "billing": [
                "billing_get_balance", "billing_get_invoice", "billing_get_payment_history",
                "crm_get_customer", "crm_get_customer_360",
                "memory.recall", "memory.write_entry",
            ] + FNO_TOOLS,
            "crm": [
                "crm_get_customer", "crm_get_customer_360", "crm_create_customer",
                "support_create_ticket", "support_get_tickets",
                "memory.recall", "memory.write_entry",
            ] + FNO_TOOLS,
        }

        allowed = AGENT_TOOL_PERMISSIONS.get(agent_type, [])
        return [t for t in self._tools.values() if t.name in allowed]

    def to_openai_format(self, tools: List[Tool]) -> List[Dict]:
        """Convert tool list to OpenAI/Ollama tool-calling format."""
        result = []
        for t in tools:
            result.append({
                "name": sanitize_tool_name(t.name),
                "description": t.description,
                "parameters": t.parameters,
            })
        return result


# Singleton
tool_registry = ToolRegistry()
