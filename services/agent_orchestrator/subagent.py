"""OpenRouter Subagent Server Tool Delegation.

Implements the OpenRouter cookbook:
'Delegate Routine Work to Cheaper Models' (https://openrouter.ai/docs/cookbook/building-agents/subagent-server-tool)

Enables orchestrator models to plan and integrate while delegating routine subtasks
(summarization, extraction, reformatting, drafting, or external lookup) to a cheaper
worker model (e.g. `~anthropic/claude-haiku-latest`) via the `openrouter:subagent`
server tool.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from services.agent_orchestrator.config import settings
from services.common import openrouter

logger = logging.getLogger(__name__)

# Default prompt instructed by OpenRouter Subagent Cookbook
DELEGATION_SYSTEM_PROMPT = (
    "You are a senior orchestrator. Break complex tasks into focused subtasks. "
    "Delegate routine work (summarization, extraction, reformatting, drafting) "
    "to the subagent. Include all context the worker needs in task_description — "
    "it cannot see this conversation. Keep planning and integration for yourself."
)

DEFAULT_WORKER_INSTRUCTIONS = (
    "You are a fast, concise subagent worker. Complete routine subtasks "
    "(summarization, extraction, reformatting, drafting, or data lookups) "
    "exactly as described in task_description. Output structured, factual results directly."
)


def get_worker_model() -> str:
    """Resolve configured worker model alias (e.g. ~anthropic/claude-haiku-latest)."""
    return (
        os.getenv("OPENROUTER_SUBAGENT_WORKER_MODEL")
        or getattr(settings, "subagent_worker_model", "~anthropic/claude-haiku-latest")
    )


def is_delegation_enabled_for_agent(agent_type: str) -> bool:
    """Check if server-tool subagent delegation is active for this agent type."""
    if not getattr(settings, "subagent_delegation_enabled", True):
        return False
    enabled_agents = getattr(settings, "subagent_enabled_agents", [
        "auto", "orchestrator", "executive", "analytics", "assistant"
    ])
    return agent_type in enabled_agents


def build_subagent_tool(
    worker_model: Optional[str] = None,
    instructions: Optional[str] = None,
    max_completion_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    reasoning_effort: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    include_web_search: bool = False,
) -> Dict[str, Any]:
    """Construct an `openrouter:subagent` server-tool entry per OpenRouter specification."""
    chosen_model = worker_model or get_worker_model()
    max_tokens = max_completion_tokens or getattr(settings, "subagent_max_tokens", 1024)
    temp = temperature if temperature is not None else getattr(settings, "subagent_temperature", 0.2)
    effort = reasoning_effort or getattr(settings, "subagent_reasoning_effort", "low")

    nested_tools: List[Dict[str, Any]] = list(tools or [])
    if include_web_search and not any(t.get("type") == "openrouter:web_search" for t in nested_tools):
        nested_tools.append({"type": "openrouter:web_search"})

    params: Dict[str, Any] = {
        "model": chosen_model,
        "instructions": instructions or DEFAULT_WORKER_INSTRUCTIONS,
        "max_completion_tokens": max_tokens,
        "temperature": temp,
        "reasoning": {"effort": effort},
    }
    if nested_tools:
        params["tools"] = nested_tools

    return {
        "type": "openrouter:subagent",
        "parameters": params,
    }


def extract_worker_model_from_tools(tools: Optional[List[Dict[str, Any]]]) -> str:
    """Extract worker model name from tools list, or return default."""
    if tools:
        for t in tools:
            if isinstance(t, dict) and t.get("type") == "openrouter:subagent":
                return t.get("parameters", {}).get("model", get_worker_model())
    return get_worker_model()


def build_delegation_request(
    task: str,
    orchestrator_model: str,
    worker_model: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    include_web_search: bool = False,
    stream: bool = False,
) -> Dict[str, Any]:
    """Build a complete OpenRouter Chat Completion request with subagent delegation."""
    subagent_tool = build_subagent_tool(
        worker_model=worker_model,
        include_web_search=include_web_search,
    )
    all_tools = [subagent_tool]
    if tools:
        all_tools.extend(tools)

    return {
        "model": orchestrator_model,
        "messages": [
            {
                "role": "system",
                "content": DELEGATION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": task,
            },
        ],
        "tools": all_tools,
        "tool_choice": "auto",
        "stream": stream,
    }


def log_delegation_telemetry(
    orchestrator_model: str,
    worker_model: str,
    did_enable_delegation: bool,
    finish_reason: Optional[str],
    usage: Optional[Dict[str, Any]] = None,
    route: str = "delegated_analysis",
) -> Dict[str, Any]:
    """Log telemetry according to the OpenRouter Subagent Cookbook specifications.

    MUST LOG:
    - orchestrator_model
    - worker_model
    - did_enable_delegation
    - finish_reason
    - token counts (prompt, completion, total) and usage.cost if present
    - route / feature name

    MUST NOT LOG:
    - prompts or task descriptions
    - worker outcomes
    - cookies or API keys
    - user content
    """
    usage_dict = usage or {}
    prompt_tokens = usage_dict.get("prompt_tokens") or usage_dict.get("input_tokens") or 0
    completion_tokens = usage_dict.get("completion_tokens") or usage_dict.get("output_tokens") or 0
    total_tokens = usage_dict.get("total_tokens") or (prompt_tokens + completion_tokens)
    cost = usage_dict.get("cost")

    entry: Dict[str, Any] = {
        "orchestrator_model": orchestrator_model,
        "worker_model": worker_model,
        "did_enable_delegation": did_enable_delegation,
        "finish_reason": finish_reason,
        "usage_prompt_tokens": int(prompt_tokens),
        "usage_completion_tokens": int(completion_tokens),
        "usage_total_tokens": int(total_tokens),
        "usage_cost": float(cost) if cost is not None else None,
        "route": route,
    }

    cost_str = f"${entry['usage_cost']:.6f}" if entry["usage_cost"] is not None else "None"
    logger.info(
        "OpenRouter Delegation Telemetry: [route=%s] orchestrator=%s worker=%s enabled=%s finish=%s tokens=%d cost=%s",
        entry["route"],
        entry["orchestrator_model"],
        entry["worker_model"],
        entry["did_enable_delegation"],
        entry["finish_reason"],
        entry["usage_total_tokens"],
        cost_str,
    )
    return entry


async def send_delegation_request(
    task: str,
    orchestrator_model: Optional[str] = None,
    worker_model: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    include_web_search: bool = False,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """Execute a delegated chat completion request directly via OpenRouter."""
    orch_model = orchestrator_model or os.getenv("OPENROUTER_MODEL") or openrouter.DEFAULT_MODEL
    w_model = worker_model or get_worker_model()

    request_body = build_delegation_request(
        task=task,
        orchestrator_model=orch_model,
        worker_model=w_model,
        tools=tools,
        include_web_search=include_web_search,
        stream=False,
    )

    api_key = openrouter.api_key()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not configured for delegated task execution.")

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{openrouter.base_url()}/chat/completions",
            json=request_body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://omnidome.local",
                "X-Title": "OmniDome Agent Orchestrator",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    choice = data.get("choices", [{}])[0]
    log_delegation_telemetry(
        orchestrator_model=orch_model,
        worker_model=w_model,
        did_enable_delegation=True,
        finish_reason=choice.get("finish_reason"),
        usage=data.get("usage"),
        route="send_delegation_request",
    )
    return data
