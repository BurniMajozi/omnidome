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
    """Return the subset of tools available to a given agent_type."""
    agent_tool_map = {
        "domebot": [
            "crm.get_customer", "crm.list_customers",
            "billing.get_balance", "billing.get_invoice",
            "network.check_coverage", "network.get_service_status",
            "support.create_ticket",
            "sales.get_pipeline",
        ],
        "churnguard": [
            "crm.get_customer", "crm.list_customers",
            "retention.get_predictions", "retention.get_cases",
            "billing.get_balance", "billing.get_invoice",
            "sales.get_pipeline",
        ],
        "provisionbot": [
            "crm.get_customer", "crm.list_customers",
            "network.check_coverage", "network.get_service_status",
            "sales.get_pipeline",
            "support.create_ticket",
        ],
        "insightbot": [
            "analytics.get_executive_summary",
            "retention.get_predictions", "retention.get_cases",
            "billing.get_balance", "billing.get_invoice",
            "network.get_service_status",
            "call_center.get_intelligence",
            "sales.get_pipeline",
            "finance.get_financial_summary",
        ],
        "supportbot": [
            "crm.get_customer", "crm.list_customers",
            "support.create_ticket",
            "network.get_service_status",
            "call_center.get_intelligence",
        ],
    }
    tool_names = agent_tool_map.get(agent_type, [])
    return [t for t in ALL_TOOLS if t.name in tool_names]


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
