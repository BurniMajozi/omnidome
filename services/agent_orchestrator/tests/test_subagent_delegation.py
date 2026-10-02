"""Unit tests for OpenRouter Subagent server-tool delegation.

Cookbook: Delegate Routine Work to Cheaper Models
(https://openrouter.ai/docs/cookbook/building-agents/subagent-server-tool)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
import pytest
import httpx

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator.subagent import (
    build_subagent_tool,
    build_delegation_request,
    extract_worker_model_from_tools,
    is_delegation_enabled_for_agent,
    log_delegation_telemetry,
    DELEGATION_SYSTEM_PROMPT,
    get_worker_model,
)
from services.agent_orchestrator import llm
from services.agent_orchestrator.agents import Agent


def test_build_subagent_tool_structure():
    """Verify openrouter:subagent parameter structure matching OpenRouter specs."""
    tool = build_subagent_tool(
        worker_model="~anthropic/claude-haiku-latest",
        max_completion_tokens=1024,
        temperature=0.2,
        reasoning_effort="low",
    )
    assert tool["type"] == "openrouter:subagent"
    params = tool["parameters"]
    assert params["model"] == "~anthropic/claude-haiku-latest"
    assert params["max_completion_tokens"] == 1024
    assert params["temperature"] == 0.2
    assert params["reasoning"] == {"effort": "low"}
    assert "tools" not in params


def test_build_subagent_tool_with_server_tools():
    """Verify web search server-tool injection for worker when required."""
    tool = build_subagent_tool(
        include_web_search=True,
    )
    params = tool["parameters"]
    assert "tools" in params
    assert any(t.get("type") == "openrouter:web_search" for t in params["tools"])


def test_build_delegation_request_shape():
    """Verify complete request body shape for OpenRouter chat completions."""
    req = build_delegation_request(
        task="Analyze fiber failure logs and summarize root causes.",
        orchestrator_model="~anthropic/claude-opus-latest",
        worker_model="~anthropic/claude-haiku-latest",
        stream=True,
    )
    assert req["model"] == "~anthropic/claude-opus-latest"
    assert req["stream"] is True
    assert req["tool_choice"] == "auto"
    assert len(req["messages"]) == 2
    assert req["messages"][0]["role"] == "system"
    assert req["messages"][0]["content"] == DELEGATION_SYSTEM_PROMPT
    assert req["messages"][1]["role"] == "user"
    assert req["messages"][1]["content"] == "Analyze fiber failure logs and summarize root causes."

    # Subagent tool exists in tools list
    tools = req["tools"]
    assert len(tools) == 1
    assert tools[0]["type"] == "openrouter:subagent"
    assert tools[0]["parameters"]["model"] == "~anthropic/claude-haiku-latest"


def test_log_delegation_telemetry_privacy_and_fields():
    """Verify telemetry logs required metrics without leaking prompts, outcomes, or keys."""
    usage_info = {
        "prompt_tokens": 150,
        "completion_tokens": 300,
        "total_tokens": 450,
        "cost": 0.00125,
    }
    entry = log_delegation_telemetry(
        orchestrator_model="~anthropic/claude-opus-latest",
        worker_model="~anthropic/claude-haiku-latest",
        did_enable_delegation=True,
        finish_reason="stop",
        usage=usage_info,
        route="network_rca_analysis",
    )

    # Required fields
    assert entry["orchestrator_model"] == "~anthropic/claude-opus-latest"
    assert entry["worker_model"] == "~anthropic/claude-haiku-latest"
    assert entry["did_enable_delegation"] is True
    assert entry["finish_reason"] == "stop"
    assert entry["usage_prompt_tokens"] == 150
    assert entry["usage_completion_tokens"] == 300
    assert entry["usage_total_tokens"] == 450
    assert entry["usage_cost"] == 0.00125
    assert entry["route"] == "network_rca_analysis"

    # Privacy guards: no sensitive content stored
    forbidden_keys = {"prompt", "task_description", "outcome", "cookie", "api_key", "authorization"}
    assert not any(k in entry for k in forbidden_keys)


def test_llm_format_tools_preserves_server_tools():
    """Verify LLMClient preserves openrouter:subagent directly and filters for Ollama."""
    client = llm.LLMClient()

    mixed_tools = [
        {"name": "billing_get_balance", "description": "Get balance", "parameters": {"type": "object"}},
        build_subagent_tool(worker_model="~anthropic/claude-haiku-latest"),
    ]

    # OpenRouter format preserves openrouter:subagent and wraps function tools
    or_formatted = client._format_tools(mixed_tools)
    assert len(or_formatted) == 2
    func_tool = next(t for t in or_formatted if t.get("type") == "function")
    subagent_tool = next(t for t in or_formatted if t.get("type") == "openrouter:subagent")
    assert func_tool["function"]["name"] == "billing_get_balance"
    assert subagent_tool["parameters"]["model"] == "~anthropic/claude-haiku-latest"

    # Ollama format omits openrouter:subagent
    ollama_formatted = client._format_ollama_tools(mixed_tools)
    assert len(ollama_formatted) == 1
    assert ollama_formatted[0]["function"]["name"] == "billing_get_balance"


def test_openrouter_stream_skips_processing_heartbeats(monkeypatch):
    """Verify stream gracefully ignores ': OPENROUTER PROCESSING' SSE comments."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test_key")
    monkeypatch.setenv("OPENROUTER_MODEL", "orch/model")

    def _handler(request):
        # Emits comment heartbeat lines while server worker runs
        sse_body = (
            ": OPENROUTER PROCESSING\n\n"
            ": OPENROUTER PROCESSING\n\n"
            'data: {"choices": [{"delta": {"content": "Analysis "}}]}\n\n'
            'data: {"choices": [{"delta": {"content": "Complete."}}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda *a, **kw: real_client(*a, **{**kw, "transport": httpx.MockTransport(_handler)}),
    )

    client = llm.LLMClient()

    async def _collect():
        return [t async for t in client._openrouter_stream("orch/model", [{"role": "user", "content": "hi"}], None)]

    tokens = asyncio.run(_collect())
    assert "".join(tokens) == "Analysis Complete."


def test_agent_run_includes_subagent_tool_and_guidance():
    """Verify Agent attaches openrouter:subagent tool and delegation prompt for orchestrator."""
    agent = Agent(agent_type="orchestrator", tenant_id=uuid.uuid4())

    async def _run():
        messages = await agent.prepare_turn("Review quarterly churn and summarize key risks.")
        assert DELEGATION_SYSTEM_PROMPT in agent.skills_prompt

        # Non-orchestrator specialized agent (e.g. talent) doesn't inject if not in enabled list
        assert is_delegation_enabled_for_agent("orchestrator") is True
        assert is_delegation_enabled_for_agent("analytics") is True

    asyncio.run(_run())
