"""Base agent class — the core reasoning loop for OmniDome agents."""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from services.agent_orchestrator import compaction, tool_call_log, memory_capture, memory_context, skills_runtime, usage
from services.agent_orchestrator.llm import llm_client
from services.agent_orchestrator.tools import SQL_TOOL_NAMES, tool_registry
from services.agent_orchestrator.json_repair import parse_tool_arguments
from services.agent_orchestrator.tool_budget import DEFAULT_MAX_OUTPUT_CHARS, budget_tool_result
from services.agent_orchestrator.config import settings

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
        # OKF skills (spec M2), filled by load_skills() at the start of a turn.
        self.skill_names: List[str] = []
        self.skills_prompt = ""
        self._skills_loaded = False
        # Conversation compaction (spec M4): set by prepare_turn; callers that
        # own a conversation store compaction_update on it.
        self.compacted = False
        self.compaction_update: Optional[Dict[str, Any]] = None

    def _build_messages(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        memory_block: str = "",
    ) -> List[Dict[str, str]]:
        """Build message list from user input + conversation history. Recalled
        tenant memory (M1) goes just before the question, marked as reference."""
        messages = []
        if history:
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant"):
                    messages.append({"role": role, "content": content})
        # The user's task is an instruction at user priority. Retrieved memory
        # is reference data; it must not be promoted into a system instruction.
        bounded_user_message = f"<user_request>\n{user_message}\n</user_request>"
        if memory_block:
            bounded_user_message = f"{memory_block}\n\n{bounded_user_message}"
        messages.append({"role": "user", "content": bounded_user_message})
        return messages

    async def recall_memory(self, user_message: str) -> str:
        """Tenant memory for this turn (spec M1); "" when there is none or memory
        is unavailable — the agent always answers."""
        if not self.tenant_id:
            return ""
        try:
            diagnostics: dict = {}
            self.context["_memory_diagnostics"] = diagnostics
            return await memory_context.recall_block(
                str(self.tenant_id), self.context.get("memory_agent_type", self.agent_type),
                user_message, actor_id=self.context.get("user_id"), diagnostics=diagnostics)
        except Exception as exc:
            logger.warning("Memory recall failed for %s: %s", self.agent_type, exc)
            return ""

    async def load_skills(self) -> None:
        """Apply guidance only when all of a skill's required tools are assigned.

        Skills are tenant-authored instructions, never a way to grant tools.
        """
        if self._skills_loaded or not self.tenant_id:
            return
        self._skills_loaded = True
        try:
            skills = await skills_runtime.skills_for(str(self.tenant_id),
                                                     self.context.get("skill_agent_type", self.agent_type),
                                                     actor_id=self.context.get("user_id"))
        except Exception as exc:
            logger.warning("OKF skills failed for %s: %s", self.agent_type, exc)
            return
        allowed = {tool.name for tool in self.tools
                   if not (self.context.get("draft_only") and tool.mutates)}
        usable = [skill for skill in skills
                  if all(name in allowed for name in (skill.get("tools_required") or []))]
        self.skill_names = [skill.get("skill_name", "") for skill in usable]
        self.skills_prompt = skills_runtime.skills_prompt(usable)

    async def prepare_turn(
        self,
        user_message: str,
        history: Optional[List[Dict[str, Any]]] = None,
        compaction_state: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """Messages for this turn: skills applied (M2), long history compacted
        (M4, compaction_state = what the conversation stored last time), tenant
        memory recalled (M1). Used by Agent.run and every chat path."""
        await self.load_skills()
        if history:
            tenant = str(self.tenant_id) if self.tenant_id else None
            history, self.compaction_update, self.compacted = await compaction.compact(
                history, compaction_state,
                compaction.summariser_for(llm_client, self.agent_type, tenant, self.channel),
                threshold_tokens=compaction.THRESHOLD_TOKENS, keep_tokens=compaction.KEEP_RECENT_TOKENS)

        # OpenRouter Subagent Cookbook: Inject delegation guidance for orchestrators
        from services.agent_orchestrator.subagent import is_delegation_enabled_for_agent, DELEGATION_SYSTEM_PROMPT, build_subagent_tool
        if is_delegation_enabled_for_agent(self.agent_type):
            if not self.skills_prompt:
                self.skills_prompt = DELEGATION_SYSTEM_PROMPT
            elif DELEGATION_SYSTEM_PROMPT not in self.skills_prompt:
                self.skills_prompt = f"{self.skills_prompt}\n\n{DELEGATION_SYSTEM_PROMPT}"

        memory_block = await self.recall_memory(user_message)
        self.context["_memory_recalled"] = bool(memory_block)
        return self._build_messages(user_message, history, memory_block)

    async def run(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        conversation_id: Optional[uuid.UUID] = None,
        compaction_state: Optional[Dict[str, Any]] = None,
        max_tool_calls: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Execute the agent reasoning loop.

        Returns dict with:
        - content: str (final response)
        - tool_calls: list of {name, arguments, result}
        - conversation_id: uuid (if DB persistence used)
        - stopped_by: None, or which loop guard ended the turn (spec A2):
          "step_limit" | "empty" | "truncated"
        """
        messages = await self.prepare_turn(user_message, history, compaction_state)
        self.context["_current_user_message"] = user_message
        if self.context.get("draft_only"):
            # HR-registered agents start with read-only capabilities. The gate is
            # also enforced in _execute_call, including hallucinated tool names.
            self.tools = [tool for tool in self.tools if not tool.mutates]
            self.available_tool_names = [tool.name for tool in self.tools]
        tool_call_log: List[Dict[str, Any]] = []
        tool_count = 0
        empty_retries = 0
        truncated_rounds = 0
        call_counts: Dict[str, int] = {}
        tools_for_llm = tool_registry.to_openai_format(self.tools)

        # OpenRouter Subagent Cookbook: Append openrouter:subagent server tool
        from services.agent_orchestrator.subagent import is_delegation_enabled_for_agent, build_subagent_tool
        if is_delegation_enabled_for_agent(self.agent_type) and not self.context.get("draft_only"):
            needs_web = any(kw in user_message.lower() for kw in ("search", "competitor", "market", "research", "news", "fno"))
            tools_for_llm.append(build_subagent_tool(include_web_search=needs_web))
        tenant = str(self.tenant_id) if self.tenant_id else None
        started = time.perf_counter()
        turn = {"rounds": 0, "tokens": 0, "prompt_tokens": 0, "completion_tokens": 0,
                "actual_cost_usd": 0.0, "provider_cost_complete": True, "model_calls": []}
        tool_limit = min(MAX_TOOL_CALLS, max_tool_calls) if max_tool_calls is not None else MAX_TOOL_CALLS

        def done(
            content: str,
            stopped_by: Optional[str] = None,
            unavailable: bool = False,
            verification: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            # Usage tracing (spec A7): one agent_turns row per turn.
            usage.record_agent_turn(
                tenant_id=tenant, agent_type=self.agent_type, channel=self.channel, rounds=turn["rounds"],
                tool_calls=len(tool_call_log), total_tokens=turn["tokens"],
                duration_ms=int((time.perf_counter() - started) * 1000), stopped_by=stopped_by,
                unavailable=unavailable,
            )
            has_pending = any(
                isinstance(tc.get("result"), dict) and tc["result"].get("requires_approval")
                for tc in tool_call_log
            )
            hitl_status = "awaiting_hitl" if has_pending else "completed"
            jev_calls = [tc["result"]["jev_gate"]["usage"] for tc in tool_call_log
                         if isinstance(tc.get("result"), dict)
                         and isinstance(tc["result"].get("jev_gate"), dict)
                         and tc["result"]["jev_gate"].get("usage")]
            if verification and verification.get("usage"):
                jev_calls.append(verification["usage"])
            return {
                "content": content,
                "tool_calls": tool_call_log,
                "conversation_id": conversation_id,
                "unavailable": unavailable,
                "stopped_by": stopped_by,
                "status": hitl_status,
                "verification": verification,
                "model_calls": turn["model_calls"],
                "jev_calls": jev_calls,
                "context_used": {"memory_recalled": bool(self.context.get("_memory_recalled")),
                                 "memory_status": self.context.get("_memory_diagnostics", {}).get("status", "unknown"),
                                 "skills": list(self.skill_names), "tools_available": list(self.available_tool_names),
                                 "architecture_hints": list(self.context.get("architecture_hints") or []),
                                 "requested_model": self.context.get("requested_model"),
                                 "kpi_status": self.context.get("kpi_status", "not_linked")},
                "usage": {
                    "prompt_tokens": turn["prompt_tokens"],
                    "completion_tokens": turn["completion_tokens"],
                    "total_tokens": turn["tokens"],
                    "cost": turn["actual_cost_usd"] if turn["rounds"] and turn["provider_cost_complete"] else None,
                },
            }

        async def verify_and_done(
            content_str: str,
            stopped_by: Optional[str] = None,
            unavailable: bool = False,
        ) -> Dict[str, Any]:
            verif_data = None
            is_mock_llm = hasattr(llm_client, "replies")
            if not is_mock_llm and not unavailable and content_str.strip() and settings.jev_gate_enabled:
                from services.agent_orchestrator.jev_gate import verify_agent_response
                v = await verify_agent_response(
                    customer_message=user_message,
                    draft_response=content_str,
                    tool_records=tool_call_log,
                    agent_type=self.agent_type,
                )
                verif_data = v.to_dict()
            return done(content_str, stopped_by=stopped_by, unavailable=unavailable, verification=verif_data)

        while tool_count < tool_limit:
            result = await llm_client.chat(
                agent_type=self.agent_type,
                messages=messages,
                tools=tools_for_llm,
                tenant_id=tenant,
                channel=self.channel,
                requested_model=self.context.get("requested_model"),
                system_extra="\n".join(filter(None, [self.skills_prompt, self.context.get("roster_mandate", ""),
                                                    self.context.get("run_guidance", ""),
                                                    self.context.get("architecture_briefing", ""),
                                                    self.context.get("kpi_briefing", "")])),
            )
            turn["rounds"] += 1
            p_tokens, c_tokens, total_tokens = usage.tokens_from(result)
            turn["tokens"] += total_tokens
            turn["prompt_tokens"] += p_tokens
            turn["completion_tokens"] += c_tokens
            provider_cost = (result.get("usage") or {}).get("cost")
            turn["model_calls"].append({
                "model": result.get("model") or "unreported",
                "provider": result.get("provider") or ("OpenRouter" if result.get("model") else "unreported"),
                "prompt_tokens": p_tokens, "completion_tokens": c_tokens,
                "cost_usd": provider_cost,
            })
            if provider_cost is not None:
                try:
                    turn["actual_cost_usd"] += float(provider_cost)
                except (TypeError, ValueError):
                    turn["provider_cost_complete"] = False
            else:
                turn["provider_cost_complete"] = False
            content = result.get("content") or ""
            raw_tool_calls = result.get("tool_calls", [])

            # No tool calls → final response (retry an empty one, spec A2).
            if not raw_tool_calls:
                if result.get("unavailable"):
                    return done(content, unavailable=True)
                cleaned = clean_response(content)
                if cleaned.strip():
                    return await verify_and_done(cleaned)
                empty_retries += 1
                if empty_retries > MAX_EMPTY_RETRIES:
                    return done(EMPTY_ANSWER_FALLBACK, stopped_by="empty")
                logger.warning("Agent %s returned an empty answer; retry %d", self.agent_type, empty_retries)
                continue

            executed_calls = []
            for batch in plan_batches(raw_tool_calls, self._is_read_call):
                outcomes = await asyncio.gather(*(self._execute_call(tc, call_counts, tenant, conversation_id=conversation_id) for tc in batch))
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

        logger.warning("Agent %s reached the step limit (%d)", self.agent_type, tool_limit)
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
                system_extra=self.skills_prompt,
            )
        except Exception as exc:  # noqa: BLE001 - the turn must still end with text
            logger.error("Final answer call failed: %s", exc)
            result = {}
        content = clean_response(result.get("content") or "")
        if not content.strip():
            content = STEP_LIMIT_FALLBACK
        return done(content, stopped_by=stopped_by, unavailable=bool(result.get("unavailable")))

    async def _execute_call(
        self,
        tc: Dict[str, Any],
        call_counts: Dict[str, int],
        tenant: Optional[str],
        conversation_id: Optional[uuid.UUID] = None,
    ):
        """Run one tool call with the A1/A2 guards. Returns (name, args, result)."""
        tool_name = tc.get("name", "")
        # The per-agent allow-list (config.agent_tool_map) is always enforced, so a
        # hallucinated or injected tool name cannot run outside the agent's toolset.
        if tool_name not in self.available_tool_names:
            msg = ("This registered agent is limited to read-only tools."
                   if self.context.get("draft_only") else f"Tool {tool_name} is not permitted for this agent.")
            return tool_name, {}, {"success": False, "refused": True, "error": msg}
        # Spec A1: repaired arguments only. A call whose arguments could not be
        # repaired or were cut off is refused (never run with {}); the error goes
        # back to the model so it re-issues the call.
        tool_args, parse_error = parse_tool_arguments(tc.get("arguments", {}))
        args_error = tc.get("arguments_error") or parse_error
        # `_`-prefixed keys are reserved for gate metadata (_jev_gate, _tool_call_id);
        # the model cannot inject them.
        tool_args = {k: v for k, v in (tool_args or {}).items() if not str(k).startswith("_")}
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

        if tool_name in ("openrouter:subagent", "openrouter_subagent"):
            return tool_name, tool_args, {"success": True, "status": "ok", "outcome": "Server-side delegation completed."}

        tool = tool_registry.get(tool_name)
        if not tool:
            return tool_name, tool_args, {"success": False, "error": f"Unknown tool: {tool_name}"}

        # Inject context IDs into tool input
        enriched_args = dict(tool_args)
        if "customer_id" in self.context and "customer_id" not in enriched_args:
            enriched_args["customer_id"] = self.context["customer_id"]

        # Jev System One Dynamic Tool Gate (HITL Recipe & Jev Gating)
        from services.agent_orchestrator.jev_gate import evaluate_tool_call
        verdict = await evaluate_tool_call(
            agent_type=self.agent_type,
            tool_name=tool_name,
            arguments=enriched_args,
            tool=tool,
            tenant_id=tenant,
            channel=self.channel,
            customer_message=self.context.get("_current_user_message"),
        )

        if verdict.action == "block":
            logger.warning("Tool call %s blocked by Jev safety gate: %s", tool_name, verdict.reason)
            return tool_name, tool_args, {
                "success": False,
                "refused": True,
                "error": f"Tool execution blocked by safety policy: {verdict.reason}",
                "jev_gate": verdict.to_dict(),
            }

        if verdict.action == "require_approval":
            from services.agent_orchestrator.approvals import (
                request_approval_standalone,
                mark_conversation_awaiting_hitl,
            )
            conv_id = conversation_id or self.context.get("conversation_id")
            run_id = self.context.get("run_id")
            user_id = str(self.context.get("user_id", ""))
            call_id = tc.get("id", "") or f"call_{uuid.uuid4().hex[:8]}"
            appr = await request_approval_standalone(
                tenant_id=tenant,
                agent_type=self.agent_type,
                tool_name=tool_name,
                arguments=enriched_args,
                conversation_id=conv_id,
                run_id=run_id,
                requested_by=user_id or self.agent_type,
                tool_call_id=call_id,
                jev_gate=verdict.to_dict(),
            )
            if conv_id and tenant:
                try:
                    await mark_conversation_awaiting_hitl(conv_id, tenant)
                except Exception as exc:
                    logger.warning("Failed to mark conversation %s as awaiting_hitl: %s", conv_id, exc)

            return tool_name, tool_args, {
                "success": True,
                "requires_approval": True,
                "status": "awaiting_hitl",
                "approval_id": appr["id"],
                "reference": appr["reference"],
                "message": appr["message"],
                "tool_call_id": call_id,
                "jev_gate": verdict.to_dict(),
            }

        timeout = getattr(tool, "timeout_s", None) or DEFAULT_TOOL_TIMEOUT_S
        # Crash-replay guard: inside a job, a state-changing call is logged by
        # (job, iteration, tool, args hash) so a resumed run never repeats it.
        log_job = None
        if getattr(tool, "mutates", False) and self.context.get("run_id"):
            try:
                log_job = uuid.UUID(str(self.context["run_id"]))
            except ValueError:
                log_job = None
        step = str(self.context.get("iteration", 0))
        if log_job:
            try:
                claim = await tool_call_log.claim(log_job, step, tool_name, enriched_args, tenant)
            except Exception as exc:  # noqa: BLE001 - cannot prove it is safe, so do not run it
                logger.error("Tool-call log unavailable for %s: %s", tool_name, exc)
                return tool_name, tool_args, {"success": False, "refused": True,
                                              "error": "Could not record this action, so it was not run."}
            if claim["state"] == "replay":
                logger.info("Replay of %s in job %s served from the call log", tool_name, log_job)
                return tool_name, tool_args, {**(claim["result"] or {}), "replayed": True}
            if claim["state"] == "unknown":
                return tool_name, tool_args, {
                    "success": False, "refused": True,
                    "error": f"An earlier attempt at this {tool_name} call did not record an outcome, so it "
                             "may already have happened. It was not repeated; ask a person to check.",
                }
        try:
            result = await asyncio.wait_for(
                tool.execute(tool_input=enriched_args, tenant_id=tenant,
                             user_id=str(self.context.get("user_id", "")),
                             **({"roles": self.context["roles"]} if self.context.get("roles") else {}),
                             **({"agent_type": self.agent_type} if tool_name in SQL_TOOL_NAMES else {})),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Tool %s timed out after %ss", tool_name, timeout)
            result = {"success": False, "error": f"{tool_name} timed out after {timeout}s; try again later "
                                                 "or answer without it."}
        if log_job:
            try:
                await tool_call_log.finish(log_job, step, tool_name, enriched_args, result)
            except Exception as exc:  # noqa: BLE001
                logger.error("Could not record outcome of %s in job %s: %s", tool_name, log_job, exc)
        # Spec M3: whatever changed data is remembered, without relying on the model.
        if getattr(tool, "mutates", False):
            await memory_capture.request(
                tenant, memory_capture.tool_entry(self.agent_type, self.channel, tool_name, tool_args, result))
        if isinstance(result, dict) and (getattr(tool, "mutates", False) or verdict.evaluated_by_jev):
            result = {**result, "jev_gate": verdict.to_dict()}
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

    async def resume_with_approved_result(
        self,
        history: List[Dict[str, Any]],
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_result: Dict[str, Any],
        tool_call_id: Optional[str] = None,
        conversation_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Resume an in-flight conversation turn after human approval or HITL result injection.
        Follows the OpenRouter HITL cookbook resume pattern."""
        await self.load_skills()
        call_id = tool_call_id or f"call_{uuid.uuid4().hex[:8]}"

        messages: List[Dict[str, Any]] = []
        if history:
            for m in history:
                role = m.get("role", "user")
                content = m.get("content")
                if role in ("user", "assistant", "system", "tool"):
                    item: Dict[str, Any] = {"role": role, "content": content}
                    if m.get("tool_call_id"):
                        item["tool_call_id"] = m["tool_call_id"]
                    if m.get("tool_calls"):
                        item["tool_calls"] = m["tool_calls"]
                    messages.append(item)

        # Append the tool call and tool result round
        self._append_tool_round(messages, [{
            "id": call_id,
            "name": tool_name,
            "arguments": tool_args,
            "result": tool_result,
        }])

        tenant = str(self.tenant_id) if self.tenant_id else None
        tools_for_llm = tool_registry.to_openai_format(self.tools)

        try:
            result = await llm_client.chat(
                agent_type=self.agent_type,
                messages=messages,
                tools=tools_for_llm,
                tenant_id=tenant,
                channel=self.channel,
                system_extra=self.skills_prompt,
            )
            content = clean_response(result.get("content") or "")
        except Exception as exc:
            logger.error("Resume turn failed for %s: %s", self.agent_type, exc)
            content = f"The action for {tool_name} was approved and executed successfully."

        return {
            "content": content,
            "tool_call_id": call_id,
            "conversation_id": conversation_id,
        }
