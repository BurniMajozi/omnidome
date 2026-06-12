"""Configuration for the Agent Orchestrator service.

Port: 8021
Module ID: agents
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Service
    service_name: str = "agent-orchestrator"
    service_port: int = 8021
    module_id: str = "agents"
    log_level: str = "INFO"

    # LLM
    ollama_base_url: str = "http://ollama:11434"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Model routing — maps agent_type -> (primary_model, fallback_model)
    # Keys match the canonical agent_type values used by frontend and routes:
    #   customer_facing, retention, provisioning, executive, support
    model_routes: dict = {
        "customer_facing": ("qwen2.5:7b", "openrouter/qwen/qwen-2.5-7b-instruct"),
        "retention":      ("llama3.1:70b", "openrouter/meta-llama/llama-3.1-70b-instruct"),
        "provisioning":   ("qwen2.5:7b", "openrouter/qwen/qwen-2.5-7b-instruct"),
        "executive":      ("llama3.1:70b", "openrouter/meta-llama/llama-3.1-70b-instruct"),
        "support":        ("qwen2.5:7b", "openrouter/qwen/qwen-2.5-7b-instruct"),
    }

    # Tool settings
    tool_timeout: int = 30
    max_tool_calls_per_agent: int = 10

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/omnidome"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Service URLs (for tool wrappers)
    crm_service_url: str = "http://crm:8001"
    billing_service_url: str = "http://billing:8003"
    network_service_url: str = "http://network:8005"
    support_service_url: str = "http://support:8008"
    retention_service_url: str = "http://retention:8012"
    analytics_service_url: str = "http://analytics:8011"
    sales_service_url: str = "http://sales:8002"
    finance_service_url: str = "http://finance:8015"
    call_center_service_url: str = "http://call_center:8007"
    tenant_memory_service_url: str = "http://tenant_memory:8025"
    public_agent_url: str = "http://agent-orchestrator:8021"
    ucp_auto_approve_limit_zar: float = 500.0
    agent_orchestrator_enable_telegram: bool = False

    # Agent-to-tool mapping — controls which tools each agent type can use.
    # Keys are agent type names, matching model_routes and frontend AGENT_CATALOG.
    # Values are lists of tool name patterns.
    # Supports exact names and prefix wildcards (e.g., "crm.*" matches all crm tools).
    agent_tool_map: dict = {
        "customer_facing": [
            "crm.get_customer", "crm.list_customers",
            "crm.get_customer_360_details", "crm.get_customer_360_cx",
            "crm.get_customer_360_cvm",
            "billing.get_balance", "billing.get_invoice",
            "billing.list_billing_accounts",
            "network.check_coverage", "network.get_service_status",
            "support.create_ticket",
            "sales.get_pipeline",
        ],
        "retention": [
            "crm.get_customer", "crm.list_customers",
            "crm.get_customer_360_cvm", "crm.get_customer_360_crm",
            "retention.get_predictions", "retention.get_cases",
            "billing.get_balance", "billing.get_invoice",
            "billing.list_billing_accounts", "billing.list_transfers",
            "sales.get_pipeline",
        ],
        "provisioning": [
            "crm.get_customer", "crm.list_customers",
            "crm.get_customer_360_details",
            "network.check_coverage", "network.get_service_status",
            "sales.get_pipeline",
            "support.create_ticket",
            "billing.list_billing_accounts",
        ],
        "executive": [
            "analytics.get_executive_summary",
            "retention.get_predictions", "retention.get_cases",
            "billing.get_balance", "billing.get_invoice",
            "billing.list_billing_accounts", "billing.list_transfers",
            "network.get_service_status",
            "call_center.get_intelligence",
            "sales.get_pipeline",
            "finance.get_financial_summary",
            "crm.get_customer_360_cvm", "crm.get_customer_360_crm",
        ],
        "support": [
            "crm.get_customer", "crm.list_customers",
            "crm.get_customer_360_details", "crm.get_customer_360_cx",
            "support.create_ticket",
            "network.get_service_status",
            "call_center.get_intelligence",
        ],
    }

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
