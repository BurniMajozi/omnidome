"""Base agent class — the core reasoning loop for OmniDome agents."""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from agent_orchestrator.llm import llm_client
from agent_orchestrator.tools import tool_registry

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 10


class Agent:
    """Stateless agent reasoning loop.
    
    Subclass this to create specific agent types, or use directly
    with agent_type parameter.
    """

    def __init__(
        self,
        agent_type: str,
        tenant_id: Optional[uuid.UUID] = None,
        channel: str = "api",
        external_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.agent_type = agent_type
        self.tenant_id = tenant_id
        self.channel = channel
        self.external_id = external_id
        self.context = context or {}
        self.tools = tool_registry.filter_for_agent(agent_type)
        self.available_tool_names = [t.name for t in self.tools]

    def _build_messages(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        """Build message list from user input + conversation history."""
        messages = []
        if history:
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant"):
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})
        return messages

    async def run(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        conversation_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Execute the agent reasoning loop.

        Returns dict with:
        - content: str (final response)
        - tool_calls: list of {name, arguments, result}
        - conversation_id: uuid (if DB persistence used)
        """
        messages = self._build_messages(user_message, history)
        tool_call_log: List[Dict[str, Any]] = []
        tool_count = 0

        while tool_count < MAX_TOOL_CALLS:
            # Call LLM with available tools
            tools_for_llm = tool_registry.to_openai_format(self.tools)

            result = await llm_client.chat(
                agent_type=self.agent_type,
                messages=messages,
                tools=tools_for_llm,
                tenant_id=str(self.tenant_id) if self.tenant_id else None,
            )

            content = result.get("content", "")
            raw_tool_calls = result.get("tool_calls", [])

            # No tool calls → final response
            if not raw_tool_calls:
                return {
                    "content": content or "I wasn't able to generate a response. Please try again.",
                    "tool_calls": tool_call_log,
                    "conversation_id": conversation_id,
                }

            # Execute each tool call
            executed_calls = []
            for tc in raw_tool_calls:
                tool_name = tc.get("name", "")
                tool_args = tc.get("arguments", {})
                if isinstance(tool_args, str):
                    import json
                    try:
                        tool_args = json.loads(tool_args)
                    except (json.JSONDecodeError, TypeError):
                        tool_args = {}

                tool = tool_registry.get(tool_name)
                if not tool:
                    tool_result = {"success": False, "error": f"Unknown tool: {tool_name}"}
                else:
                    # Inject context IDs into tool input
                    enriched_args = dict(tool_args)
                    if "customer_id" in self.context and "customer_id" not in enriched_args:
                        enriched_args["customer_id"] = self.context["customer_id"]
                    tool_result = await tool.execute(
                        tool_input=enriched_args,
                        tenant_id=str(self.tenant_id) if self.tenant_id else None,
                        user_id=str(self.context.get("user_id", "")),
                    )

                executed_calls.append({
                    "name": tool_name,
                    "arguments": tool_args,
                    "result": tool_result,
                })
                tool_call_log.append({
                    "name": tool_name,
                    "arguments": tool_args,
                    "result": tool_result,
                })
                tool_count += 1

            # Feed results back into the conversation
            messages.append({
                "role": "assistant",
                "content": content,
            })
            for call in executed_calls:
                messages.append({
                    "role": "tool",
                    "content": str(call["result"]),
                })

        # Max tool calls reached — return last assistant content
        logger.warning("Agent %s reached max tool calls (%d)", self.agent_type, MAX_TOOL_CALLS)
        return {
            "content": messages[-1].get("content", "") if messages else "I've gathered all the information I can. Is there something specific you'd like me to focus on?",
            "tool_calls": tool_call_log,
            "conversation_id": conversation_id,
        }
