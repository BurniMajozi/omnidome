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
    model_routes: dict = {
        "domebot": ("qwen2.5:7b", "openrouter/qwen/qwen-2.5-7b-instruct"),
        "churnguard": ("llama3.1:70b", "openrouter/meta-llama/llama-3.1-70b-instruct"),
        "provisionbot": ("qwen2.5:7b", "openrouter/qwen/qwen-2.5-7b-instruct"),
        "insightbot": ("llama3.1:70b", "openrouter/meta-llama/llama-3.1-70b-instruct"),
        "supportbot": ("qwen2.5:7b", "openrouter/qwen/qwen-2.5-7b-instruct"),
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

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
