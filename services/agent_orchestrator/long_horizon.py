"""Long-Horizon Agent runner (Cookbook: 'Build a Long-Horizon Agent').

Features:
1. Hard Ceilings: max_cost_usd, max_steps, max_tokens.
2. Resumable State: Checkpointed state to survive crashes, deploys, and human approval gates.
3. Adversarial Self-Review Loop: Research -> Adversarial review (with Jev or LLM) -> [DONE] sentinel.
4. Notifications on Completion: Webhooks & EventBus events upon completion.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx

from services.agent_orchestrator.agents import Agent
from services.agent_orchestrator.config import settings
from services.agent_orchestrator import usage
from services.common.db import session_scope
from services.agent_orchestrator.models import AgentConversation, AgentMessage
from sqlalchemy import select

logger = logging.getLogger("agent_orchestrator.long_horizon")

# Default cost estimation per token (blended standard rate: $2/1M in, $8/1M out)
DEFAULT_INPUT_TOKEN_COST_USD = 0.000002
DEFAULT_OUTPUT_TOKEN_COST_USD = 0.000008

DONE_SENTINEL = "[DONE]"

DEFAULT_ADVERSARIAL_REVIEW_PROMPT = (
    "Review your last response adversarially:\n"
    "- Are there gaps, ambiguities, or unverified claims in relation to the primary objective?\n"
    "- If the work is complete and every claim is verified, reply with only [DONE].\n"
    "- Otherwise, list the specific missing items, gaps, or questions and continue investigating."
)


@dataclass
class LongHorizonJobResult:
    job_id: str
    conversation_id: str
    status: str  # "completed" | "stopped_by_ceiling" | "max_iterations" | "awaiting_hitl" | "failed"
    final_output: str
    iterations: int
    total_steps: int
    total_tokens: int
    estimated_cost_usd: float
    actual_cost_usd: Optional[float] = None
    stopped_by: Optional[str] = None
    iteration_history: List[Dict[str, Any]] = field(default_factory=list)
    checkpoint: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "conversation_id": self.conversation_id,
            "status": self.status,
            "final_output": self.final_output,
            "iterations": self.iterations,
            "total_steps": self.total_steps,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
            "actual_cost_usd": round(self.actual_cost_usd, 4) if self.actual_cost_usd is not None else None,
            "cost_source": "provider" if self.actual_cost_usd is not None else "estimated",
            "stopped_by": self.stopped_by,
            "iteration_history": self.iteration_history,
            "model_calls": self.checkpoint.get("model_calls", []),
            "jev_usage": {"tokens": self.checkpoint.get("jev_tokens", 0),
                          "reported_cost_usd": self.checkpoint.get("jev_cost_usd") if self.checkpoint.get("jev_cost_complete", True) else None,
                          "cost_reported": self.checkpoint.get("jev_cost_complete", True)},
        }


def estimate_token_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens * DEFAULT_INPUT_TOKEN_COST_USD) + (completion_tokens * DEFAULT_OUTPUT_TOKEN_COST_USD)


def check_ceilings(
    step_count: int,
    cost_usd: float,
    tokens_used: int,
    max_steps: Optional[int] = None,
    max_cost_usd: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Optional[str]:
    """Returns ceiling name if a hard limit is breached, else None."""
    if max_cost_usd is not None and cost_usd >= max_cost_usd:
        return f"max_cost_usd ({cost_usd:.4f} >= {max_cost_usd:.4f})"
    if max_steps is not None and step_count >= max_steps:
        return f"max_steps ({step_count} >= {max_steps})"
    if max_tokens is not None and tokens_used >= max_tokens:
        return f"max_tokens ({tokens_used} >= {max_tokens})"
    return None


async def evaluate_adversarial_jev(
    objective: str,
    draft_output: str,
    iteration: int,
) -> tuple[bool, Optional[str], dict]:
    """Use Jev System One to adversarially evaluate whether a long-horizon task is complete.
    Returns (is_complete, critique_or_none, reported_usage)."""
    if not settings.jev_gate_enabled:
        return False, None, {}

    from services.agent_orchestrator.jev_gate import _get_credentials, DEFAULT_TIMEOUT_S
    provider, api_key, endpoint = _get_credentials()
    if not api_key:
        return False, None, {}

    state_payload = {
        "primary_objective": objective[:2000],
        "draft_output": draft_output[:3000],
        "iteration": iteration,
    }

    questions = {
        "is_task_complete": {
            "type": "noul",
            "instructions": (
                "The draft_output completely and fully satisfies every component of primary_objective "
                "with no missing sections, uninvestigated questions, or remaining action items."
            ),
        },
        "has_unresolved_gaps": {
            "type": "noul",
            "instructions": (
                "The draft_output contains notable omissions, explicitly mentions unverified claims, "
                "or asks for further research on unresolved questions."
            ),
        },
    }

    try:
        model_name = "typesafe/jev-1.13" if provider == "openrouter" else getattr(settings, "typesafe_model", "jev-latest")
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_S) as client:
            resp = await client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "OmniDome-Agent-Orchestrator/1.0",
                },
                json={
                    "state": state_payload,
                    "model": model_name,
                    "questions": questions,
                },
            )

        if resp.status_code == 200:
            body = resp.json()
            answers = body.get("answers", {})
            raw_usage = body.get("usage") or {}
            jev_usage = {
                "provider": provider, "model": body.get("model") or model_name,
                "total_tokens": raw_usage.get("total_tokens") or raw_usage.get("tokens") or 0,
                "cost_usd": raw_usage.get("cost"),
            }
            complete_prob = float(answers.get("is_task_complete", {}).get("noul", 0.5))
            gaps_prob = float(answers.get("has_unresolved_gaps", {}).get("noul", 0.5))

            logger.info("Jev Adversarial Review (iter %d): complete=%.2f, gaps=%.2f", iteration, complete_prob, gaps_prob)

            if complete_prob >= 0.85 and gaps_prob <= 0.15:
                return True, None, jev_usage

            critique = f"Jev identified unresolved gaps (complete_prob={complete_prob:.2f}, gaps_prob={gaps_prob:.2f})."
            return False, critique, jev_usage
    except Exception as exc:
        logger.warning("Jev adversarial review failed (%r). Falling back to sentinel.", exc)

    return False, None, {}


async def dispatch_completion_notification(
    webhook_url: Optional[str],
    job_result: LongHorizonJobResult,
    tenant_id: Optional[str] = None,
) -> None:
    """Send webhook and emit EventBus event upon long-horizon job completion."""
    payload = job_result.to_dict()

    # 1. EventBus event
    try:
        from services.common.db import session_scope
        from services.agent_orchestrator.events import publish
        if tenant_id:
            async with session_scope() as session:
                await publish(
                    session,
                    tenant_id=uuid.UUID(str(tenant_id)),
                    event_type="agents.job.completed",
                    payload=payload,
                    source="long_horizon_runner",
                    idempotency_key=f"job:{job_result.job_id}",
                )
    except Exception as exc:
        logger.warning("EventBus notification failed for job %s: %s", job_result.job_id, exc)

    # 2. Webhook POST
    if webhook_url:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(webhook_url, json=payload)
                logger.info("Completion webhook delivered to %s for job %s", webhook_url, job_result.job_id)
        except Exception as exc:
            logger.error("Failed to post completion webhook to %s: %s", webhook_url, exc)


async def run_long_horizon_agent(
    prompt: str,
    agent_type: str = "assistant",
    tenant_id: Optional[str | uuid.UUID] = None,
    conversation_id: Optional[uuid.UUID] = None,
    max_cost_usd: float = 5.00,
    max_iterations: int = 10,
    max_steps_per_iteration: int = 25,
    max_tokens: int = 20000,
    webhook_url: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    resume_from_checkpoint: Optional[Dict[str, Any]] = None,
    checkpoint_callback: Optional[Callable[[Dict[str, Any], Optional[Dict[str, Any]]], Awaitable[None]]] = None,
) -> LongHorizonJobResult:
    """Execute a self-ask, multi-hour resilient long-horizon agent run with strict cost/step ceilings."""
    job_id = str((resume_from_checkpoint or {}).get("job_id") or f"lh_{uuid.uuid4().hex[:12]}")
    conv_id = conversation_id or uuid.uuid4()
    t_id = str(tenant_id) if tenant_id else "00000000-0000-0000-0000-000000000001"

    # Initialize or restore checkpoint
    checkpoint = resume_from_checkpoint or {
        "job_id": job_id,
        "conversation_id": str(conv_id),
        "iterations_completed": 0,
        "total_steps": 0,
        "total_tokens": 0,
        "accumulated_cost_usd": 0.0,
        "history": [],
    }
    if conversation_id is None and checkpoint.get("conversation_id"):
        conv_id = uuid.UUID(str(checkpoint["conversation_id"]))

    total_steps = checkpoint.get("total_steps", 0)
    total_tokens = checkpoint.get("total_tokens", 0)
    accumulated_cost = checkpoint.get("accumulated_cost_usd", 0.0)
    estimated_cost = float(checkpoint.get("estimated_cost_usd", 0.0))
    provider_cost = float(checkpoint.get("provider_cost_usd", 0.0))
    provider_cost_complete = bool(checkpoint.get("provider_cost_complete", True))
    jev_cost = float(checkpoint.get("jev_cost_usd", 0.0))
    jev_cost_complete = bool(checkpoint.get("jev_cost_complete", True))
    jev_tokens = int(checkpoint.get("jev_tokens", 0))
    model_calls = list(checkpoint.get("model_calls", []))
    history = list(checkpoint.get("history", []))
    iteration_history: List[Dict[str, Any]] = []

    current_input = prompt
    final_output = ""
    status = "completed"
    stopped_by = None

    agent = Agent(
        agent_type=agent_type,
        tenant_id=uuid.UUID(t_id),
        context=context or {},
    )
    if checkpoint.get("run_guidance"):
        agent.context["run_guidance"] = checkpoint["run_guidance"]

    logger.info("Starting Long-Horizon job %s for agent '%s' (max_cost=$%.2f, max_iter=%d)", job_id, agent_type, max_cost_usd, max_iterations)

    for i in range(checkpoint.get("iterations_completed", 0), max_iterations):
        # 1. Pre-turn Ceiling Check
        ceiling_breach = check_ceilings(
            step_count=total_steps,
            cost_usd=accumulated_cost,
            tokens_used=total_tokens,
            max_cost_usd=max_cost_usd,
            max_steps=max_steps_per_iteration * max_iterations,
            max_tokens=max_tokens,
        )
        if ceiling_breach:
            logger.warning("Job %s halted by ceiling before iteration %d: %s", job_id, i + 1, ceiling_breach)
            status = "stopped_by_ceiling"
            stopped_by = ceiling_breach
            break

        # 2. Run agent iteration
        try:
            turn_result = await agent.run(
                user_message=current_input,
                history=history,
                max_tool_calls=max_steps_per_iteration,
            )
        except Exception as exc:
            logger.exception("Iteration %d of job %s failed: %s", i + 1, job_id, exc)
            status = "failed"
            stopped_by = f"exception: {exc}"
            break

        turn_content = turn_result.get("content", "")
        final_output = turn_content
        tool_calls = turn_result.get("tool_calls", [])
        turn_status = turn_result.get("status")

        # Track steps & usage
        turn_steps = len(tool_calls)
        total_steps += turn_steps

        # Estimate cost from tokens
        p_tok, c_tok, tot_tok = usage.tokens_from(turn_result)
        total_tokens += tot_tok
        turn_cost = estimate_token_cost(p_tok, c_tok)
        model_calls.extend(turn_result.get("model_calls") or [])
        estimated_cost += turn_cost
        reported_cost = (turn_result.get("usage") or {}).get("cost")
        try:
            reported_cost = float(reported_cost) if reported_cost is not None else None
        except (TypeError, ValueError):
            reported_cost = None
        if reported_cost is None:
            provider_cost_complete = False
        else:
            provider_cost += reported_cost
        accumulated_cost += reported_cost if reported_cost is not None else turn_cost
        turn_jev_calls = turn_result.get("jev_calls") or []
        for call in turn_jev_calls:
            tokens = int(call.get("total_tokens") or 0)
            jev_tokens += tokens
            total_tokens += tokens
            charge = call.get("cost_usd")
            if charge is None:
                jev_cost_complete = False
                provider_cost_complete = False
            else:
                jev_cost += float(charge)
                accumulated_cost += float(charge)

        iteration_record = {
            "iteration": i + 1,
            "steps": turn_steps,
            "tokens": tot_tok,
            "cost_usd": turn_cost,
            "provider_cost_usd": reported_cost,
            "content_preview": turn_content[:180],
            "status": turn_status,
            "verification": turn_result.get("verification"),
            "jev_decisions": [
                {"tool": call.get("name"), "decision": (call.get("result") or {}).get("jev_gate")}
                for call in tool_calls if isinstance(call.get("result"), dict) and (call.get("result") or {}).get("jev_gate")
            ],
            "model_calls": turn_result.get("model_calls") or [],
            "jev_calls": turn_jev_calls,
            "context_used": turn_result.get("context_used") or {},
        }
        iteration_history.append(iteration_record)

        checkpoint.update({
            "iterations_completed": i + 1,
            "total_steps": total_steps,
            "total_tokens": total_tokens,
            "accumulated_cost_usd": accumulated_cost,
            "estimated_cost_usd": estimated_cost,
            "provider_cost_usd": provider_cost,
            "provider_cost_complete": provider_cost_complete,
            "jev_tokens": jev_tokens,
            "jev_cost_usd": jev_cost,
            "jev_cost_complete": jev_cost_complete,
            "model_calls": model_calls[-100:],
            "context_used": turn_result.get("context_used") or {},
            "last_output": turn_content,
            "history": [*history, {"role": "user", "content": current_input}, {"role": "assistant", "content": turn_content}],
            "next_input": prompt,
        })
        if checkpoint_callback:
            await checkpoint_callback(dict(checkpoint), dict(iteration_record))

        if turn_result.get("unavailable"):
            status = "failed"
            stopped_by = "model_unavailable"
            break

        # 3. Check for Human-In-The-Loop pause
        if turn_status == "awaiting_hitl":
            logger.info("Job %s paused at iteration %d for human approval", job_id, i + 1)
            status = "awaiting_hitl"
            stopped_by = "awaiting_hitl"
            break

        # 4. Check for [DONE] sentinel
        if DONE_SENTINEL in turn_content:
            logger.info("Job %s received [DONE] sentinel on iteration %d", job_id, i + 1)
            final_output = turn_content.replace(DONE_SENTINEL, "").strip()
            status = "completed"
            stopped_by = "done_sentinel"
            break

        # 5. Adversarial Self-Review check (via Jev)
        is_complete, critique, jev_usage = await evaluate_adversarial_jev(prompt, turn_content, i + 1)
        if jev_usage:
            review_tokens = int(jev_usage.get("total_tokens") or 0)
            jev_tokens += review_tokens
            total_tokens += review_tokens
            jev_reported_cost = jev_usage.get("cost_usd")
            if jev_reported_cost is None:
                jev_cost_complete = False
                provider_cost_complete = False
            else:
                jev_cost += float(jev_reported_cost)
                accumulated_cost += float(jev_reported_cost)
            iteration_record["jev_review"] = jev_usage
            checkpoint.update({"jev_tokens": jev_tokens, "total_tokens": total_tokens,
                               "jev_cost_usd": jev_cost,
                               "jev_cost_complete": jev_cost_complete,
                               "last_jev_review": jev_usage,
                               "provider_cost_complete": provider_cost_complete,
                               "accumulated_cost_usd": accumulated_cost})
            if checkpoint_callback:
                await checkpoint_callback(dict(checkpoint), None)
        if is_complete:
            logger.info("Job %s confirmed complete by Jev adversarial gate on iteration %d", job_id, i + 1)
            status = "completed"
            stopped_by = "jev_complete"
            break

        # A text-only turn did not gather new evidence. Asking the same model
        # to review itself again only repeats its context and burns tokens.
        if not turn_steps:
            status = "awaiting_review"
            stopped_by = "no_evidence_progress"
            break

        # 6. Post-turn Ceiling Check
        ceiling_breach = check_ceilings(
            step_count=total_steps,
            cost_usd=accumulated_cost,
            tokens_used=total_tokens,
            max_cost_usd=max_cost_usd,
            max_steps=max_steps_per_iteration * max_iterations,
            max_tokens=max_tokens,
        )
        if ceiling_breach:
            logger.warning("Job %s halted by ceiling after iteration %d: %s", job_id, i + 1, ceiling_breach)
            status = "stopped_by_ceiling"
            stopped_by = ceiling_breach
            break

        # 7. Update checkpoint and history for next iteration
        history.append({"role": "user", "content": current_input})
        history.append({"role": "assistant", "content": turn_content})

        checkpoint.update({
            "iterations_completed": i + 1,
            "total_steps": total_steps,
            "total_tokens": total_tokens,
            "accumulated_cost_usd": accumulated_cost,
            "history": history,
            "last_output": turn_content,
            "next_input": current_input,
        })

        # Next prompt: adversarial review prompt enriched with critique if available
        if critique:
            agent.context["run_guidance"] = (
                "Continue the original operator request. Gather missing evidence with your authorized "
                f"read-only tools before answering. Verification finding: {critique[:500]}"
            )
        else:
            agent.context["run_guidance"] = (
                "Continue the original operator request and verify missing evidence with authorized tools."
            )
        current_input = prompt
        checkpoint["next_input"] = prompt
        checkpoint["run_guidance"] = agent.context["run_guidance"]
        if checkpoint_callback:
            # The first save protects against replaying tools after a crash;
            # this save keeps Jev's critique for the next turn without adding
            # a second iteration to the operator timeline.
            await checkpoint_callback(dict(checkpoint), None)

    if status == "completed" and not stopped_by:
        status = "max_iterations"
        stopped_by = "max_iterations"

    result = LongHorizonJobResult(
        job_id=job_id,
        conversation_id=str(conv_id),
        status=status,
        final_output=final_output,
        iterations=len(iteration_history),
        total_steps=total_steps,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost,
        actual_cost_usd=provider_cost + jev_cost if provider_cost_complete and iteration_history else None,
        stopped_by=stopped_by,
        iteration_history=iteration_history,
        checkpoint=checkpoint,
    )

    # Dispatch notifications
    await dispatch_completion_notification(webhook_url, result, tenant_id=t_id)
    return result
