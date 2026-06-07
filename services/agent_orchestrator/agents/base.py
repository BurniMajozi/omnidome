"""Base agent class — the core reasoning loop.

Receives a message + conversation history, calls the LLM with tools,
executes tool calls, and returns the final response.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

from config import settings
from llm.router import router
from tools.registry import Tool, execute_tool, get_tools_for_agent

logger = logging.getLogger("agents.base")


# ---------------------------------------------------------------------------
# Conversation helpers
# ---------------------------------------------------------------------------

def _system_prompt(agent_type: str) -> str:
    """Return the system prompt for each agent type."""
    prompts = {
        "domebot": (
            "You are DomeBot, a helpful customer-facing AI assistant for a South African ISP. "
            "You help customers with account questions, billing inquiries, service status, "
            "coverage checks, and creating support tickets. "
            "Be concise, friendly, and professional. Use South African English. "
            "If you need customer information, use the CRM and billing tools. "
            "Never make up information — always use tools to verify."
        ),
        "churnguard": (
            "You are ChurnGuard, an internal AI agent that evaluates customer churn risk. "
            "You analyze customer data, identify high-risk accounts, and recommend retention actions. "
            "Be analytical and data-driven. Focus on actionable insights."
        ),
        "provisionbot": (
            "You are ProvisionBot, an internal AI agent that automates service provisioning. "
            "When a sales deal is closed, you handle: coverage check, identity verification, "
            "customer creation, equipment reservation, service provisioning, subscription creation, "
            "and installation ticket generation. Be thorough and systematic."
        ),
        "insightbot": (
            "You are InsightBot, an executive intelligence AI agent. "
            "You generate natural-language briefings with key metrics: MRR, churn, ARPU, "
            "subscriber growth, support load, network health, and financial performance. "
            "Be concise and highlight trends and anomalies."
        ),
        "supportbot": (
            "You are SupportBot, a technical support AI assistant for a South African ISP. "
            "You help diagnose network issues, run service checks, and create support tickets. "
            "Be patient, thorough, and explain technical details clearly."
        ),
    }
    return prompts.get(agent_type, prompts["domebot"])


# ---------------------------------------------------------------------------
# Agent result
# ---------------------------------------------------------------------------

class AgentResult:
    """Result of an agent invocation."""

    def __init__(
        self,
        content: str,
        tool_calls: List[Dict[str, Any]] | None = None,
        tool_results: List[Dict[str, Any]] | None = None,
        conversation_id: str | None = None,
        duration_ms: float = 0,
    ):
        self.content = content
        self.tool_calls = tool_calls or []
        self.tool_results = tool_results or []
        self.conversation_id = conversation_id
        self.duration_ms = duration_ms

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "tool_calls": self.tool_calls,
            "tool_results": self.tool_results,
            "conversation_id": self.conversation_id,
            "duration_ms": self.duration_ms,
        }


# ---------------------------------------------------------------------------
# Base Agent
# ---------------------------------------------------------------------------

class BaseAgent:
    """Core agent loop: LLM call → tool execution → final response.

    Supports up to `max_tool_calls` (default 10) iterations of
    LLM → tool_execution → LLM to handle multi-step reasoning.
    """

    def __init__(
        self,
        agent_type: str,
        tenant_id: str = "default",
        user_id: str = "system",
        max_tool_calls: int | None = None,
    ):
        self.agent_type = agent_type
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.max_tool_calls = max_tool_calls or settings.max_tool_calls_per_agent
        self.conversation_id: Optional[str] = None

    def _get_tools(self) -> List[Tool]:
        """Return the tools available to this agent."""
        return get_tools_for_agent(self.agent_type)

    def _build_messages(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Build the full message list including system prompt."""
        msgs: List[Dict[str, Any]] = [
            {"role": "system", "content": _system_prompt(self.agent_type)}
        ]
        msgs.extend(messages)
        return msgs

    async def invoke(
        self,
        message: str,
        conversation_history: List[Dict[str, Any]] | None = None,
        context: Dict[str, Any] | None = None,
    ) -> AgentResult:
        """Synchronous (non-streaming) agent invocation.

        1. Build message history with system prompt.
        2. Call LLM with available tools.
        3. If LLM returns tool_calls, execute them and call LLM again.
        4. Repeat up to max_tool_calls.
        5. Return final text response.
        """
        start = time.monotonic()
        history = conversation_history or []
        all_tool_calls: List[Dict[str, Any]] = []
        all_tool_results: List[Dict[str, Any]] = []

        # Append the new user message
        current_messages = list(history)
        current_messages.append({"role": "user", "content": message})

        tools = self._get_tools()
        tool_schemas = [t.to_schema() for t in tools]

        # Map tool name -> Tool for execution
        tool_map = {t.name: t for t in tools}

        for iteration in range(self.max_tool_calls + 1):
            messages = self._build_messages(current_messages)

            response = await router.invoke(
                agent_type=self.agent_type,
                messages=messages,
                tools=tool_schemas,
                tenant_id=self.tenant_id,
            )

            # Extract the assistant message
            msg = response.get("message", {})
            content = msg.get("content", "")
            calls = msg.get("tool_calls")

            if not calls:
                # No tool calls — this is the final response
                duration = (time.monotonic() - start) * 1000
                logger.info(
                    "Agent %s responded in %.0fms (iter=%d)",
                    self.agent_type, duration, iteration,
                )
                return AgentResult(
                    content=content,
                    tool_calls=all_tool_calls,
                    tool_results=all_tool_results,
                    conversation_id=self.conversation_id,
                    duration_ms=duration,
                )

            # Execute tool calls
            logger.info(
                "Agent %s executing %d tool call(s)", self.agent_type, len(calls)
            )

            # Record assistant message with tool_calls in history
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": content,
            }
            if calls:
                assistant_msg["tool_calls"] = calls
            current_messages.append(assistant_msg)

            for call in calls:
                # Normalize call format (Ollama vs OpenRouter)
                fn = call.get("function", call)
                tool_name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {}
                else:
                    args = raw_args

                all_tool_calls.append({
                    "tool": tool_name,
                    "arguments": args,
                })

                # Execute
                result = await execute_tool(
                    tool_name=tool_name,
                    params=args,
                    tenant_id=self.tenant_id,
                    user_id=self.user_id,
                )
                all_tool_results.append({
                    "tool": tool_name,
                    "result": result,
                })

                # Append tool result message
                current_messages.append({
                    "role": "tool",
                    "name": tool_name,
                    "content": json.dumps(result),
                })

        # If we hit max_tool_calls, do one final call without tools
        messages = self._build_messages(current_messages)
        # Remove tools to force a text response
        response = await router.invoke(
            agent_type=self.agent_type,
            messages=messages,
            tools=None,
            tenant_id=self.tenant_id,
        )
        content = response.get("message", {}).get("content", "")
        duration = (time.monotonic() - start) * 1000

        logger.warning(
            "Agent %s hit max_tool_calls=%d limit", self.agent_type, self.max_tool_calls
        )

        return AgentResult(
            content=content,
            tool_calls=all_tool_calls,
            tool_results=all_tool_results,
            conversation_id=self.conversation_id,
            duration_ms=duration,
        )

    async def invoke_stream(
        self,
        message: str,
        conversation_history: List[Dict[str, Any]] | None = None,
        context: Dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming agent invocation with SSE.

        Yields tokens as they arrive. Tool calls happen between chunks
        (not streamed — tool execution is batched per iteration).
        """
        start = time.monotonic()
        history = conversation_history or []
        all_tool_calls: List[Dict[str, Any]] = []
        all_tool_results: List[Dict[str, Any]] = []

        current_messages = list(history)
        current_messages.append({"role": "user", "content": message})

        tools = self._get_tools()
        tool_schemas = [t.to_schema() for t in tools]

        for iteration in range(self.max_tool_calls + 1):
            messages = self._build_messages(current_messages)

            # Stream tokens from the LLM
            content_parts: List[str] = []
            last_meta: Dict[str, Any] = {}

            async for token in router.invoke_stream(
                agent_type=self.agent_type,
                messages=messages,
                tools=tool_schemas,
                tenant_id=self.tenant_id,
            ):
                if token.startswith("__DONE__"):
                    try:
                        last_meta = json.loads(token[8:])
                    except Exception:
                        pass
                    break
                content_parts.append(token)
                yield token

            content = "".join(content_parts)
            msg = last_meta.get("message", {})
            calls = msg.get("tool_calls")

            if not calls:
                # Final response — done
                duration = (time.monotonic() - start) * 1000
                logger.info(
                    "Agent %s streamed response in %.0fms",
                    self.agent_type, duration,
                )
                return

            # Execute tool calls (batched — not streamed)
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": content,
                "tool_calls": calls,
            }
            current_messages.append(assistant_msg)

            yield f"\n\n[Using {len(calls)} tool(s)...]\n\n"

            for call in calls:
                fn = call.get("function", call)
                tool_name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {}
                else:
                    args = raw_args

                all_tool_calls.append({"tool": tool_name, "arguments": args})

                result = await execute_tool(
                    tool_name=tool_name,
                    params=args,
                    tenant_id=self.tenant_id,
                    user_id=self.user_id,
                )
                all_tool_results.append({"tool": tool_name, "result": result})

                yield f"→ {tool_name}: {json.dumps(result)[:100]}\n"

                current_messages.append({
                    "role": "tool",
                    "name": tool_name,
                    "content": json.dumps(result),
                })

        # Hit max tool calls — force final response
        messages = self._build_messages(current_messages)
        async for token in router.invoke_stream(
            agent_type=self.agent_type,
            messages=messages,
            tools=None,
            tenant_id=self.tenant_id,
        ):
            if not token.startswith("__DONE__"):
                yield token
