"""Tool registry — pre-registers tools for ALL existing OmniDome services.

Each Tool wraps a REST API endpoint on one of the OmniDome microservices.
The agent's LLM sees tools as callable functions with JSON schemas.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from config import settings

logger = logging.getLogger("tools.registry")


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

@dataclass
class Tool:
    """A callable tool that agents can invoke by hitting a service REST API."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema for the tool's input
    endpoint: str  # Full URL or path pattern, e.g. "/customers/{customer_id}"
    method: str = "GET"             # HTTP method
    service_url: str = ""          # Base URL of the target service
    timeout: int = 30              # HTTP timeout in seconds
    required_params: List[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        base = self.service_url.rstrip("/")
        return f"{base}{self.endpoint}"

    def to_schema(self) -> Dict[str, Any]:
        """Return the tool definition as an OpenAI/Ollama-compatible schema."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


# ---------------------------------------------------------------------------
# Built-in tool templates
# ---------------------------------------------------------------------------

def _pydantic_to_json_schema(
    properties: Dict[str, Dict[str, Any]],
    required: List[str] | None = None,
) -> Dict[str, Any]:
    """Helper to build a JSON Schema object from property definitions."""
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


# ---------------------------------------------------------------------------
# All registered tools
# ---------------------------------------------------------------------------

ALL_TOOLS: List[Tool] = [
    # ── CRM ────────────────────────────────────────────────────────────────
    Tool(
        name="crm.get_customer",
        description="Get a customer by ID. Returns full customer profile including contact info, status, and account number.",
        parameters=_pydantic_to_json_schema(
            {
                "customer_id": {
                    "type": "string",
                    "description": "UUID of the customer",
                },
            },
            required=["customer_id"],
        ),
        endpoint="/customers/{customer_id}",
        method="GET",
        service_url=settings.crm_service_url,
        required_params=["customer_id"],
    ),
    Tool(
        name="crm.list_customers",
        description="List customers for the current tenant. Supports filtering by status and search query.",
        parameters=_pydantic_to_json_schema(
            {
                "status": {
                    "type": "string",
                    "description": "Filter by status: active, suspended, churned",
                    "enum": ["active", "suspended", "churned"],
                },
                "search": {
                    "type": "string",
                    "description": "Search by name, email, phone, or account number",
                },
                "page": {
                    "type": "integer",
                    "description": "Page number (default 1)",
                    "default": 1,
                },
                "page_size": {
                    "type": "integer",
                    "description": "Results per page (default 20)",
                    "default": 20,
                },
            },
        ),
        endpoint="/customers",
        method="GET",
        service_url=settings.crm_service_url,
    ),

    # ── Billing ────────────────────────────────────────────────────────────
    Tool(
        name="billing.get_balance",
        description="Get the current account balance for a customer.",
        parameters=_pydantic_to_json_schema(
            {
                "customer_id": {
                    "type": "string",
                    "description": "UUID of the customer",
                },
            },
            required=["customer_id"],
        ),
        endpoint="/billing/balance/{customer_id}",
        method="GET",
        service_url=settings.billing_service_url,
        required_params=["customer_id"],
    ),
    Tool(
        name="billing.get_invoice",
        description="Get a specific invoice by ID for a customer.",
        parameters=_pydantic_to_json_schema(
            {
                "customer_id": {
                    "type": "string",
                    "description": "UUID of the customer",
                },
                "invoice_id": {
                    "type": "string",
                    "description": "UUID of the invoice",
                },
            },
            required=["customer_id", "invoice_id"],
        ),
        endpoint="/billing/invoices/{invoice_id}",
        method="GET",
        service_url=settings.billing_service_url,
        required_params=["invoice_id"],
    ),

    # ── Network ────────────────────────────────────────────────────────────
    Tool(
        name="network.check_coverage",
        description="Check if fibre broadband service is available at a given address/area.",
        parameters=_pydantic_to_json_schema(
            {
                "address": {
                    "type": "string",
                    "description": "Street address or area name to check coverage for",
                },
                "provider": {
                    "type": "string",
                    "description": "FNO provider to check (e.g., vumatel, openserve, metrofibre). Leave empty to check all.",
                },
            },
            required=["address"],
        ),
        endpoint="/network/coverage",
        method="GET",
        service_url=settings.network_service_url,
    ),
    Tool(
        name="network.get_service_status",
        description="Get the current service status for a customer's connection (active, degraded, down).",
        parameters=_pydantic_to_json_schema(
            {
                "customer_id": {
                    "type": "string",
                    "description": "UUID of the customer",
                },
            },
            required=["customer_id"],
        ),
        endpoint="/services",
        method="GET",
        service_url=settings.network_service_url,
    ),

    # ── Support ────────────────────────────────────────────────────────────
    Tool(
        name="support.create_ticket",
        description="Create a new support ticket for a customer.",
        parameters=_pydantic_to_json_schema(
            {
                "customer_id": {
                    "type": "string",
                    "description": "UUID of the customer",
                },
                "subject": {
                    "type": "string",
                    "description": "Brief summary of the issue",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the issue",
                },
                "priority": {
                    "type": "string",
                    "description": "Ticket priority",
                    "enum": ["low", "medium", "high", "urgent"],
                    "default": "medium",
                },
            },
            required=["customer_id", "subject", "description"],
        ),
        endpoint="/tickets",
        method="POST",
        service_url=settings.support_service_url,
    ),

    # ── Retention ──────────────────────────────────────────────────────────
    Tool(
        name="retention.get_predictions",
        description="Get churn risk predictions and scores for customers.",
        parameters=_pydantic_to_json_schema(
            {
                "tenant_id": {
                    "type": "string",
                    "description": "UUID of the tenant (optional, uses auth context if omitted)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of predictions to return (default 20)",
                    "default": 20,
                },
            },
        ),
        endpoint="/retention/predictions",
        method="GET",
        service_url=settings.retention_service_url,
    ),
    Tool(
        name="retention.get_cases",
        description="Get active retention cases — customers at risk with ongoing retention efforts.",
        parameters=_pydantic_to_json_schema(
            {
                "status": {
                    "type": "string",
                    "description": "Filter by case status: open, in_progress, resolved, escalated",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 20)",
                    "default": 20,
                },
            },
        ),
        endpoint="/retention/cases",
        method="GET",
        service_url=settings.retention_service_url,
    ),

    # ── Analytics ──────────────────────────────────────────────────────────
    Tool(
        name="analytics.get_executive_summary",
        description="Get a natural-language executive summary of key metrics: MRR, churn, ARPU, subscriber growth, support load.",
        parameters=_pydantic_to_json_schema(
            {
                "period": {
                    "type": "string",
                    "description": "Time period for the summary",
                    "enum": ["daily", "weekly", "monthly"],
                    "default": "monthly",
                },
            },
        ),
        endpoint="/analytics/executive-summary",
        method="GET",
        service_url=settings.analytics_service_url,
    ),

    # ── Sales ──────────────────────────────────────────────────────────────
    Tool(
        name="sales.get_pipeline",
        description="Get the current sales pipeline — all open deals grouped by stage.",
        parameters=_pydantic_to_json_schema(
            {
                "stage": {
                    "type": "string",
                    "description": "Filter by pipeline stage: prospecting, qualification, proposal, negotiation, closed_won, closed_lost",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 50)",
                    "default": 50,
                },
            },
        ),
        endpoint="/sales/pipeline",
        method="GET",
        service_url=settings.sales_service_url,
    ),

    # ── Finance ────────────────────────────────────────────────────────────
    Tool(
        name="finance.get_financial_summary",
        description="Get a financial summary including revenue, expenses, cash flow, and profitability metrics.",
        parameters=_pydantic_to_json_schema(
            {
                "period": {
                    "type": "string",
                    "description": "Reporting period",
                    "enum": ["monthly", "quarterly", "annual"],
                    "default": "monthly",
                },
            },
        ),
        endpoint="/finance/summary",
        method="GET",
        service_url=settings.finance_service_url,
    ),

    # ── Call Center ────────────────────────────────────────────────────────
    Tool(
        name="call_center.get_intelligence",
        description="Get call center intelligence: call volume, avg sentiment, top issues, and agent performance.",
        parameters=_pydantic_to_json_schema(
            {
                "period": {
                    "type": "string",
                    "description": "Time period",
                    "enum": ["today", "weekly", "monthly"],
                    "default": "today",
                },
            },
        ),
        endpoint="/call-center/intelligence",
        method="GET",
        service_url=settings.call_center_service_url,
    ),
    # ── Customer 360 (CRM aggregation) ─────────────────────────────────────
    Tool(
        name="crm.get_customer_360_details",
        description="Get full customer details: identity, properties, billing accounts, subscriptions, payment methods, handover history. Returns Tab 1 of the Customer 360 view.",
        parameters=_pydantic_to_json_schema(
            {
                "customer_id": {
                    "type": "string",
                    "description": "UUID of the customer",
                },
            },
            required=["customer_id"],
        ),
        endpoint="/customers/{customer_id}/360/details",
        method="GET",
        service_url=settings.crm_service_url,
        required_params=["customer_id"],
        timeout=15,
    ),
    Tool(
        name="crm.get_customer_360_cx",
        description="Get customer experience data: orders, deliveries, technician visits, support tickets, activity timeline, NPS score. Returns Tab 2 (CX) of the Customer 360 view.",
        parameters=_pydantic_to_json_schema(
            {
                "customer_id": {
                    "type": "string",
                    "description": "UUID of the customer",
                },
            },
            required=["customer_id"],
        ),
        endpoint="/customers/{customer_id}/360/cx",
        method="GET",
        service_url=settings.crm_service_url,
        required_params=["customer_id"],
        timeout=15,
    ),
    Tool(
        name="crm.get_customer_360_crm",
        description="Get CRM/sales data: leads, deals, quotes, commissions, segments, tags, notes, lifecycle stage. Returns Tab 3 (CRM) of the Customer 360 view.",
        parameters=_pydantic_to_json_schema(
            {
                "customer_id": {
                    "type": "string",
                    "description": "UUID of the customer",
                },
            },
            required=["customer_id"],
        ),
        endpoint="/customers/{customer_id}/360/crm",
        method="GET",
        service_url=settings.crm_service_url,
        required_params=["customer_id"],
        timeout=15,
    ),
    Tool(
        name="crm.get_customer_360_cvm",
        description="Get customer value management data: MRR, ARR, LTV, churn risk, health score, invoices, payments, usage, customer tier. Returns Tab 4 (CVM) of the Customer 360 view.",
        parameters=_pydantic_to_json_schema(
            {
                "customer_id": {
                    "type": "string",
                    "description": "UUID of the customer",
                },
            },
            required=["customer_id"],
        ),
        endpoint="/customers/{customer_id}/360/cvm",
        method="GET",
        service_url=settings.crm_service_url,
        required_params=["customer_id"],
        timeout=15,
    ),
    # ── Billing Accounts ───────────────────────────────────────────────────
    Tool(
        name="billing.list_billing_accounts",
        description="List billing accounts for a customer or company. Billing accounts are top-level billing entities that group subscriptions and invoices.",
        parameters=_pydantic_to_json_schema(
            {
                "customer_id": {
                    "type": "string",
                    "description": "UUID of the customer (optional if company_id is provided)",
                },
                "company_id": {
                    "type": "string",
                    "description": "UUID of the company (optional if customer_id is provided)",
                },
            },
        ),
        endpoint="/billing-accounts",
        method="GET",
        service_url=settings.billing_service_url,
        timeout=10,
    ),
    Tool(
        name="billing.get_billing_account",
        description="Get a specific billing account by ID with full details including balance, payment terms, and dunning stage.",
        parameters=_pydantic_to_json_schema(
            {
                "account_id": {
                    "type": "string",
                    "description": "UUID of the billing account",
                },
            },
            required=["account_id"],
        ),
        endpoint="/billing-accounts/{account_id}",
        method="GET",
        service_url=settings.billing_service_url,
        required_params=["account_id"],
        timeout=10,
    ),
    # ── Subscription Transfers ─────────────────────────────────────────────
    Tool(
        name="billing.list_transfers",
        description="List subscription transfers for a customer. Transfers track tenant-to-tenant handovers at a property.",
        parameters=_pydantic_to_json_schema(
            {
                "customer_id": {
                    "type": "string",
                    "description": "UUID of the customer (as from or to)",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by transfer status: pending, in_progress, approved, completed, cancelled, disputed",
                },
            },
        ),
        endpoint="/transfers",
        method="GET",
        service_url=settings.billing_service_url,
        timeout=10,
    ),
    # ── FNO Intelligence (Firecrawl-powered web intelligence) ──────────────
    Tool(
        name="fno_intelligence.web_intel_product_research",
        description="Research an FNO's (fibre network operator's) products, packages, speeds and prices via live web search. Returns an LLM-summarised product lineup. Use when a user asks about what packages/products an FNO offers.",
        parameters=_pydantic_to_json_schema(
            {
                "fno_name": {"type": "string", "description": "FNO name, e.g. 'Vuma Fibre', 'Vumatel', 'Openserve', 'Frogfoot'"},
                "product_query": {"type": "string", "description": "Optional custom search query override"},
            },
            required=["fno_name"],
        ),
        endpoint="/api/fno/web-intel/product-research",
        method="POST",
        service_url=settings.fno_intelligence_service_url,
        timeout=60,
        required_params=["fno_name"],
    ),
    Tool(
        name="fno_intelligence.web_intel_fno_site_message",
        description="Scrape the latest message or announcement banner from an FNO's portal/website. Use to fetch current FNO notices, outage comms, or portal messages.",
        parameters=_pydantic_to_json_schema(
            {
                "portal_url": {"type": "string", "description": "Full URL of the FNO portal or announcement page to scrape"},
            },
            required=["portal_url"],
        ),
        endpoint="/api/fno/web-intel/fno-site-message",
        method="POST",
        service_url=settings.fno_intelligence_service_url,
        timeout=60,
        required_params=["portal_url"],
    ),
    Tool(
        name="fno_intelligence.web_intel_new_site_releases",
        description="Discover newly-released fibre coverage areas / build sites for an FNO via web search. Use when checking where an FNO has just launched or is launching coverage.",
        parameters=_pydantic_to_json_schema(
            {
                "fno_name": {"type": "string", "description": "FNO name"},
                "city": {"type": "string", "description": "Optional city filter"},
            },
            required=["fno_name"],
        ),
        endpoint="/api/fno/web-intel/new-site-releases",
        method="POST",
        service_url=settings.fno_intelligence_service_url,
        timeout=60,
        required_params=["fno_name"],
    ),
    Tool(
        name="fno_intelligence.web_intel_cancellation_processing",
        description="Extract an FNO's cancellation / termination procedure and required steps from its website. Use when a customer wants to cancel or when processing a cancellation request.",
        parameters=_pydantic_to_json_schema(
            {
                "fno_name": {"type": "string", "description": "FNO name"},
                "portal_url": {"type": "string", "description": "Optional explicit cancellation-page URL"},
            },
            required=["fno_name"],
        ),
        endpoint="/api/fno/web-intel/cancellation-processing",
        method="POST",
        service_url=settings.fno_intelligence_service_url,
        timeout=60,
        required_params=["fno_name"],
    ),
    Tool(
        name="fno_intelligence.web_intel_address_lookup",
        description="Resolve a street address to fibre coverage / available FNOs via web search. Use to check which fibre networks service a given address.",
        parameters=_pydantic_to_json_schema(
            {
                "address": {"type": "string", "description": "Street address to look up"},
                "fno_name": {"type": "string", "description": "Optional FNO to scope the lookup to"},
            },
            required=["address"],
        ),
        endpoint="/api/fno/web-intel/address-lookup",
        method="POST",
        service_url=settings.fno_intelligence_service_url,
        timeout=60,
        required_params=["address"],
    ),
    Tool(
        name="fno_intelligence.web_intel_competitor_analysis",
        description="Compare an FNO against named competitors (pricing, speeds, coverage, reliability) using web data and LLM analysis. Use for competitive intelligence questions.",
        parameters=_pydantic_to_json_schema(
            {
                "fno_name": {"type": "string", "description": "FNO to analyse"},
                "competitors": {"type": "array", "items": {"type": "string"}, "description": "Competitor FNO names to compare against"},
            },
            required=["fno_name"],
        ),
        endpoint="/api/fno/web-intel/competitor-analysis",
        method="POST",
        service_url=settings.fno_intelligence_service_url,
        timeout=60,
        required_params=["fno_name"],
    ),
]


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

# Fast lookup: tool_name -> Tool
_TOOL_INDEX: Dict[str, Tool] = {t.name: t for t in ALL_TOOLS}


def get_tool(name: str) -> Optional[Tool]:
    """Look up a tool by name."""
    return _TOOL_INDEX.get(name)


def list_tools() -> List[Dict[str, Any]]:
    """Return all registered tools as JSON schemas (for /api/tools endpoint)."""
    return [t.to_schema() for t in ALL_TOOLS]


def get_tools_for_agent(agent_type: str) -> List[Tool]:
    """Return the subset of tools available to a given agent_type.

    Uses the agent_tool_map from config.settings. Supports exact tool names
    and prefix wildcards (e.g., 'crm.*' matches all crm tools).
    """
    import fnmatch
    tool_names = settings.agent_tool_map.get(agent_type, [])
    result = []
    for t in ALL_TOOLS:
        for pattern in tool_names:
            if fnmatch.fnmatch(t.name, pattern):
                result.append(t)
                break
    return result


# Alias for backward compatibility with agents.py
filter_for_agent = get_tools_for_agent


def to_openai_format(tools: list) -> list:
    """Convert a list of Tool objects to OpenAI/Ollama tool format."""
    return [t.to_schema() for t in tools]


async def execute_tool(tool_name: str, params: Dict[str, Any], tenant_id: str = "", user_id: str = "") -> Dict[str, Any]:
    """Execute a tool by name with given parameters.

    Makes an HTTP call to the underlying OmniDome microservice.
    Returns the parsed JSON response or an error dict.
    """
    tool = get_tool(tool_name)
    if not tool:
        return {"error": f"Unknown tool: {tool_name}"}

    # Build URL — replace path params
    url = tool.url
    for key, value in params.items():
        placeholder = "{" + key + "}"
        if placeholder in url:
            url = url.replace(placeholder, str(value))

    # Separate path params from query params
    query_params = {
        k: v for k, v in params.items()
        if "{" + k + "}" not in tool.endpoint
    }

    headers = {
        "X-Tenant-Id": tenant_id,
        "X-User-Id": user_id,
        "Content-Type": "application/json",
    }

    logger.info("Tool call: %s params=%s", tool_name, params)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(tool.timeout, connect=5.0)) as client:
            if tool.method.upper() == "GET":
                resp = await client.get(url, params=query_params, headers=headers)
            elif tool.method.upper() == "POST":
                resp = await client.post(url, json=query_params, headers=headers)
            elif tool.method.upper() == "PATCH":
                resp = await client.patch(url, json=query_params, headers=headers)
            elif tool.method.upper() == "DELETE":
                resp = await client.delete(url, params=query_params, headers=headers)
            else:
                return {"error": f"Unsupported HTTP method: {tool.method}"}

            if resp.status_code >= 400:
                logger.warning("Tool %s returned %d: %s", tool_name, resp.status_code, resp.text[:200])
                return {
                    "error": f"Service returned {resp.status_code}",
                    "detail": resp.text[:500],
                }

            try:
                return resp.json()
            except Exception:
                return {"result": resp.text}

    except httpx.TimeoutException:
        logger.error("Tool %s timed out after %ds", tool_name, tool.timeout)
        return {"error": f"Tool {tool_name} timed out"}
    except Exception as exc:
        logger.error("Tool %s error: %s", tool_name, exc)
        return {"error": str(exc)}
