"""Base agent class — the core reasoning loop for OmniDome agents."""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from services.agent_orchestrator import usage
from services.agent_orchestrator.llm import llm_client
from services.agent_orchestrator.tools import tool_registry
from services.agent_orchestrator.json_repair import parse_tool_arguments
from services.agent_orchestrator.tool_budget import DEFAULT_MAX_OUTPUT_CHARS, budget_tool_result

logger = logging.getLogger(__name__)

# Loop guards (spec A2; patterns from Tencent/WeKnora internal/agent, MIT).
MAX_TOOL_CALLS = int(os.getenv("AGENT_MAX_TOOL_CALLS", "10"))
MAX_EMPTY_RETRIES = 2          # empty answer with no tool calls -> ask again
MAX_TRUNCATED_ROUNDS = 2       # consecutive rounds cut off inside tool arguments
MAX_IDENTICAL_CALLS = 2        # same tool + same arguments; the 3rd is refused
DEFAULT_TOOL_TIMEOUT_S = 60

EMPTY_ANSWER_FALLBACK = "I wasn't able to generate a response. Please try again."
STEP_LIMIT_FALLBACK = (
    "I gathered information but couldn't finish composing an answer. "
    "Please ask again, or narrow the question."
)

SPECIALIST_MAP = {
    "churnguard": "retention",
    "retention": "retention",
    "supportbot": "support",
    "support": "support",
    "domebot": "customer_facing",
    "customer_facing": "customer_facing",
    "provisionbot": "provisioning",
    "provisioning": "provisioning",
    "analytics": "analytics",
    "metricbot": "analytics",
    "talent": "talent",
    "staffbot": "talent",
}


def plan_batches(calls: List[Dict[str, Any]], can_run_concurrently) -> List[List[Dict[str, Any]]]:
    """Group a round's tool calls (spec A5; WeKnora CanRunConcurrently): runs of
    consecutive read-only calls form one batch that executes concurrently; any
    other call (writes, unknown tools, consultations) is a barrier and runs alone,
    in order."""
    batches: List[List[Dict[str, Any]]] = []
    for tc in calls:
        if can_run_concurrently(tc) and batches and batches[-1] and batches[-1][-1].get("_read"):
            batches[-1].append({**tc, "_read": True})
        else:
            batches.append([{**tc, "_read": bool(can_run_concurrently(tc))}])
    return [[{k: v for k, v in tc.items() if k != "_read"} for tc in batch] for batch in batches]


def clean_response(text: str) -> str:
    """Clean repeated assistant responses if the LLM emitted premature drafts."""
    if not text or not isinstance(text, str):
        return text or ""
    parts = text.split("\n---\n")
    if len(parts) > 1:
        # Check if consecutive parts are near-duplicates (e.g. repeated briefings)
        stripped = [p.strip() for p in parts if p.strip()]
        if len(stripped) >= 2:
            # If the first line of the parts match, or one starts similarly
            first_lines = [p.splitlines()[0] for p in stripped if p.splitlines()]
            if len(first_lines) >= 2 and first_lines[0] == first_lines[1]:
                return stripped[-1]
    return text.strip()


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
        # Enclose user query in untrusted boundary delimiters
        bounded_user_message = f"<untrusted_user_input>\n{user_message}\n</untrusted_user_input>"
        messages.append({"role": "user", "content": bounded_user_message})
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
        - stopped_by: None, or which loop guard ended the turn (spec A2):
          "step_limit" | "empty" | "truncated"
        """
        messages = self._build_messages(user_message, history)
        tool_call_log: List[Dict[str, Any]] = []
        tool_count = 0
        empty_retries = 0
        truncated_rounds = 0
        call_counts: Dict[str, int] = {}
        tools_for_llm = tool_registry.to_openai_format(self.tools)
        tenant = str(self.tenant_id) if self.tenant_id else None
        started = time.perf_counter()
        turn = {"rounds": 0, "tokens": 0}

        def done(content: str, stopped_by: Optional[str] = None, unavailable: bool = False) -> Dict[str, Any]:
            # Usage tracing (spec A7): one agent_turns row per turn.
            usage.record_agent_turn(
                tenant_id=tenant, agent_type=self.agent_type, channel=self.channel, rounds=turn["rounds"],
                tool_calls=len(tool_call_log), total_tokens=turn["tokens"],
                duration_ms=int((time.perf_counter() - started) * 1000), stopped_by=stopped_by,
                unavailable=unavailable,
            )
            return {
                "content": content,
                "tool_calls": tool_call_log,
                "conversation_id": conversation_id,
                "unavailable": unavailable,
                "stopped_by": stopped_by,
            }

        while tool_count < MAX_TOOL_CALLS:
            result = await llm_client.chat(
                agent_type=self.agent_type,
                messages=messages,
                tools=tools_for_llm,
                tenant_id=tenant,
                channel=self.channel,
            )
            turn["rounds"] += 1
            turn["tokens"] += usage.tokens_from(result)[2]
            content = result.get("content") or ""
            raw_tool_calls = result.get("tool_calls", [])

            # No tool calls → final response (retry an empty one, spec A2).
            if not raw_tool_calls:
                if result.get("unavailable"):
                    return done(content, unavailable=True)
                cleaned = clean_response(content)
                if cleaned.strip():
                    return done(cleaned)
                empty_retries += 1
                if empty_retries > MAX_EMPTY_RETRIES:
                    return done(EMPTY_ANSWER_FALLBACK, stopped_by="empty")
                logger.warning("Agent %s returned an empty answer; retry %d", self.agent_type, empty_retries)
                continue

            executed_calls = []
            for batch in plan_batches(raw_tool_calls, self._is_read_call):
                outcomes = await asyncio.gather(*(self._execute_call(tc, call_counts, tenant) for tc in batch))
                for tc, (tool_name, tool_args, tool_result) in zip(batch, outcomes):
                    executed_calls.append({
                        "id": tc.get("id", ""),
                        "name": tc.get("name", tool_name),
                        "arguments": tool_args,
                        "result": tool_result,
                    })
                    tool_call_log.append({"name": tool_name, "arguments": tool_args, "result": tool_result})
                    tool_count += 1

            self._append_tool_round(messages, executed_calls)

            # Rounds cut off at the output limit inside tool arguments: the model
            # keeps writing ever longer calls and hitting the cap (spec A2).
            all_refused = all(c["result"].get("refused") for c in executed_calls)
            if result.get("finish_reason") == "length" and all_refused:
                truncated_rounds += 1
                if truncated_rounds >= MAX_TRUNCATED_ROUNDS:
                    return await self._final_answer(messages, tools_for_llm, tenant, done, "truncated")
            else:
                truncated_rounds = 0

        logger.warning("Agent %s reached the step limit (%d)", self.agent_type, MAX_TOOL_CALLS)
        return await self._final_answer(messages, tools_for_llm, tenant, done, "step_limit")

    @staticmethod
    def _is_read_call(tc: Dict[str, Any]) -> bool:
        """Known tool whose policy says it does not change anything (spec A6)."""
        tool = tool_registry.get(tc.get("name", ""))
        return bool(tool) and getattr(tool, "mutates", True) is False

    async def _final_answer(self, messages, tools_for_llm, tenant, done, stopped_by: str) -> Dict[str, Any]:
        """One last call with tools disabled: answer from what was gathered
        (WeKnora handleMaxIterations). Never returns raw tool output."""
        reason = (
            "You have reached the tool-call limit for this request"
            if stopped_by == "step_limit"
            else "Your tool calls keep being cut off at the output limit"
        )
        final_messages = messages + [{
            "role": "user",
            "content": f"{reason}. Do not call any more tools. Answer now from the information already "
                       "gathered, and say briefly what could not be checked.",
        }]
        try:
            result = await llm_client.chat(
                agent_type=self.agent_type, messages=final_messages, tools=tools_for_llm,
                tenant_id=tenant, tool_choice="none", channel=self.channel, purpose="final",
            )
        except Exception as exc:  # noqa: BLE001 - the turn must still end with text
            logger.error("Final answer call failed: %s", exc)
            result = {}
        content = clean_response(result.get("content") or "")
        if not content.strip():
            content = STEP_LIMIT_FALLBACK
        return done(content, stopped_by=stopped_by, unavailable=bool(result.get("unavailable")))

    async def _execute_call(self, tc: Dict[str, Any], call_counts: Dict[str, int], tenant: Optional[str]):
        """Run one tool call with the A1/A2 guards. Returns (name, args, result)."""
        tool_name = tc.get("name", "")
        # Spec A1: repaired arguments only. A call whose arguments could not be
        # repaired or were cut off is refused (never run with {}); the error goes
        # back to the model so it re-issues the call.
        tool_args, parse_error = parse_tool_arguments(tc.get("arguments", {}))
        args_error = tc.get("arguments_error") or parse_error
        tool_args = tool_args or {}
        if args_error:
            logger.warning("Refused %s: %s", tool_name, args_error)
            return tool_name, tool_args, {"success": False, "error": args_error, "refused": True}

        # Spec A2: the same call over and over is a stuck loop; the model already
        # has that result.
        key = f"{tool_name}:{json.dumps(tool_args, sort_keys=True, default=str)}"
        call_counts[key] = call_counts.get(key, 0) + 1
        if call_counts[key] > MAX_IDENTICAL_CALLS:
            return tool_name, tool_args, {
                "success": False, "refused": True,
                "error": "You already called this tool with the same arguments; use the earlier result "
                         "instead of calling it again.",
            }

        if tool_name in ("orchestrator_consult_specialist", "orchestrator.consult_specialist"):
            return tool_name, tool_args, await self._consult_specialist(tool_args)

        tool = tool_registry.get(tool_name)
        if not tool:
            return tool_name, tool_args, {"success": False, "error": f"Unknown tool: {tool_name}"}

        # Inject context IDs into tool input
        enriched_args = dict(tool_args)
        if "customer_id" in self.context and "customer_id" not in enriched_args:
            enriched_args["customer_id"] = self.context["customer_id"]
        timeout = getattr(tool, "timeout_s", None) or DEFAULT_TOOL_TIMEOUT_S
        try:
            result = await asyncio.wait_for(
                tool.execute(tool_input=enriched_args, tenant_id=tenant,
                             user_id=str(self.context.get("user_id", ""))),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Tool %s timed out after %ss", tool_name, timeout)
            result = {"success": False, "error": f"{tool_name} timed out after {timeout}s; try again later "
                                                 "or answer without it."}
        return tool_name, tool_args, result

    async def _consult_specialist(self, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Cross-agent consultation: run another specialist agent in-process."""
        specialist = str(tool_args.get("specialist", "support")).lower()
        query = str(tool_args.get("query", ""))
        extra_ctx = str(tool_args.get("context", ""))
        full_query = f"{query}\nContext: {extra_ctx}" if extra_ctx else query
        target_agent = SPECIALIST_MAP.get(specialist, "support")
        try:
            logger.info("Executing cross-agent consultation with specialist %s (agent=%s)", specialist, target_agent)
            sub_agent = Agent(
                agent_type=target_agent,
                tenant_id=self.tenant_id,
                channel="internal_consultation",
                context=self.context,
            )
            sub_result = await sub_agent.run(user_message=full_query)
            return {
                "success": True,
                "specialist": specialist,
                "agent_type": target_agent,
                "findings": sub_result.get("content", ""),
                "sub_tools_called": [t.get("name") for t in sub_result.get("tool_calls", [])],
            }
        except Exception as err:
            logger.error("Cross-agent consultation failed: %s", err)
            return {"success": False, "error": f"Failed to consult {specialist}: {str(err)}"}

    def _append_tool_round(self, messages: List[Dict[str, Any]], executed_calls: List[Dict[str, Any]]) -> None:
        """Feed results back in OpenAI/Anthropic tool-calling format: an assistant
        message carrying the tool_calls (with ids), then one tool message per
        result keyed by tool_call_id. Content stays None so the model does not
        echo a premature draft into the final response. Each result is capped
        to the tool's output budget (spec A3); the full result stays in the log."""
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": c["id"],
                    "type": "function",
                    "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])},
                }
                for c in executed_calls
                if c.get("id")
            ],
        })
        for c in executed_calls:
            if not c.get("id"):
                continue
            tool = tool_registry.get(c["name"])
            max_chars = getattr(tool, "max_output_chars", None) or DEFAULT_MAX_OUTPUT_CHARS
            messages.append({
                "role": "tool",
                "tool_call_id": c["id"],
                "content": budget_tool_result(c["result"], max_chars),
            })
