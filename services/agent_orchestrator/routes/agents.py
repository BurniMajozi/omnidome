"""Agent invocation routes — with conversation persistence."""

import json
import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope as get_session
from services.agent_orchestrator.agents import Agent
from services.agent_orchestrator.tools import tool_registry
from services.agent_orchestrator.config import settings
from services.agent_orchestrator.hermes_client import hermes_client
from services.agent_orchestrator.protocols import AGUIEvent
from services.agent_orchestrator.schemas import AgentInvokeRequest, AgentInvokeResponse, AgentInfo
from services.agent_orchestrator.conversation.models import (
    AgentConversation,
    AgentMessage,
    AgentAction,
)
from services.agent_orchestrator.guardrails.gate import run_gate
from services.agent_orchestrator.audit_actions import GUARDRAILS_INPUT, GUARDRAILS_OUTPUT

logger = logging.getLogger(__name__)

router = APIRouter()


def _hermes_system_note(agent_type: str, tenant_id, context: dict) -> str:
    """Short domain/tenant context note for Hermes — it has its own persona
    (SOUL.md) and reaches business tools itself via MCP (ask_<agent_type>_agent),
    so this intentionally doesn't replicate the qwen/llama personas in llm.py."""
    return (
        f"This conversation is happening inside OmniDome's '{agent_type}' context "
        f"for tenant {tenant_id}. Use your ask_{agent_type}_agent tool (or other "
        f"ask_*_agent tools) for anything requiring real CRM/billing/network/etc. data. "
        f"Extra context: {json.dumps(context)}"
    )


# ---------------------------------------------------------------------------
# Helper: persist messages to a conversation
# ---------------------------------------------------------------------------

async def _persist_messages(
    session,
    conversation_id: uuid.UUID,
    agent_type: str,
    user_message: str,
    assistant_content: str,
    tool_calls: list,
    gate_verdicts: list | None = None,
):
    """Persist user message, tool calls, and assistant response to the conversation."""
    # User message
    user_msg = AgentMessage(
        conversation_id=conversation_id,
        role="user",
        content=user_message,
    )
    session.add(user_msg)

    # Tool call messages (if any)
    for tc in tool_calls:
        tool_msg = AgentMessage(
            conversation_id=conversation_id,
            role="tool",
            content=str(tc.get("result", "")),
            tool_calls=[{
                "name": tc.get("name", ""),
                "arguments": tc.get("arguments", {}),
            }],
            tool_results=[tc.get("result", {})],
        )
        session.add(tool_msg)

        # Also persist to AgentAction for audit trail
        action = AgentAction(
            conversation_id=conversation_id,
            agent_type=agent_type,
            tool_name=tc.get("name", ""),
            tool_input=tc.get("arguments", {}),
            tool_output=tc.get("result", {}),
            success=tc.get("result", {}).get("success", True) if isinstance(tc.get("result"), dict) else True,
        )
        session.add(action)

    # Assistant response
    assistant_msg = AgentMessage(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
    )
    session.add(assistant_msg)

    # Guardrail gate verdicts (if any) — audit trail of PII hits on either side.
    # TODO(Task 4+): forward PII hits to compliance breach register.
    for verdict in gate_verdicts or []:
        side = verdict.get("side", "")
        hits = verdict.get("hits", [])
        action = verdict.get("action", "")
        tool_name = GUARDRAILS_INPUT if side == "input" else GUARDRAILS_OUTPUT
        session.add(AgentAction(
            conversation_id=conversation_id,
            agent_type=agent_type,
            tool_name=tool_name,
            tool_input={"hits": hits},
            tool_output={"action": action},
            success=(action != "block"),
        ))

    # Update conversation timestamp
    conv_result = await session.execute(
        select(AgentConversation).where(AgentConversation.id == conversation_id)
    )
    conv = conv_result.scalar_one_or_none()
    if conv:
        conv.updated_at = __import__("datetime").datetime.now(
            tz=__import__("datetime").timezone.utc
        )


# ---------------------------------------------------------------------------
# GET /api/agents — List agents
# ---------------------------------------------------------------------------

@router.get("", response_model=list[AgentInfo])
async def list_agents():
    """List all available agents and their tool sets."""
    legacy_llm = {
        "customer_facing": "qwen2.5:7b",
        "retention": "llama3.1:70b",
        "provisioning": "qwen2.5:7b",
        "executive": "llama3.1:70b",
        "support": "qwen2.5:7b",
    }
    hermes_llm = "hermes-agent (gemma3:4b via Ollama)"

    def _llm(agent_type: str) -> str:
        return hermes_llm if settings.chat_backend == "hermes" else legacy_llm[agent_type]

    agents = [
        AgentInfo(
            agent_type="customer_facing",
            description="DomeBot — assists customers with balances, invoices, coverage, tickets",
            llm=_llm("customer_facing"),
            tools=Agent("customer_facing").available_tool_names,
        ),
        AgentInfo(
            agent_type="retention",
            description="ChurnGuard — autonomous churn prediction and retention campaigns",
            llm=_llm("retention"),
            tools=Agent("retention").available_tool_names,
        ),
        AgentInfo(
            agent_type="provisioning",
            description="ProvisionBot — automates new customer provisioning workflow",
            llm=_llm("provisioning"),
            tools=Agent("provisioning").available_tool_names,
        ),
        AgentInfo(
            agent_type="executive",
            description="InsightBot — executive briefings and analytics",
            llm=_llm("executive"),
            tools=Agent("executive").available_tool_names,
        ),
        AgentInfo(
            agent_type="support",
            description="SupportBot — ticket management and diagnostics",
            llm=_llm("support"),
            tools=Agent("support").available_tool_names,
        ),
    ]
    return agents


# ---------------------------------------------------------------------------
# GET /api/agents/actions — Audit-trail query (Task 4 / D2)
# ---------------------------------------------------------------------------

def _parse_since(since: Optional[str]):
    """Parse an ISO-8601 datetime string; None in → None out, bad → ValueError."""
    if since is None:
        return None
    try:
        return __import__("datetime").datetime.fromisoformat(since)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid ISO datetime for 'since': {since!r}") from exc


@router.get("/actions")
async def list_actions(
    agent_type: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=500),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Newest-first audit trail of AgentAction rows for this tenant.

    AgentAction has no tenant_id column, so tenant scoping goes through the
    conversation join (same ctx.tenant_id pattern as invoke_agent).
    """
    try:
        since_dt = _parse_since(since)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    async with get_session() as session:
        stmt = (
            select(AgentAction)
            .join(
                AgentConversation,
                AgentAction.conversation_id == AgentConversation.id,
            )
            .where(AgentConversation.tenant_id == ctx.tenant_id)
            .order_by(AgentAction.created_at.desc())
            .limit(limit)
        )
        if agent_type:
            stmt = stmt.where(AgentAction.agent_type == agent_type)
        if since_dt is not None:
            stmt = stmt.where(AgentAction.created_at >= since_dt)
        result = await session.execute(stmt)
        actions = result.scalars().all()

    return {
        "items": [
            {
                "id": str(a.id),
                "conversation_id": str(a.conversation_id),
                "agent_type": a.agent_type,
                "tool_name": a.tool_name,
                "tool_input": a.tool_input,
                "tool_output": a.tool_output,
                "success": a.success,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in actions
        ]
    }


# ---------------------------------------------------------------------------
# POST /api/agents/invoke — Synchronous agent invocation with persistence
# ---------------------------------------------------------------------------

@router.post("/invoke", response_model=AgentInvokeResponse)
async def invoke_agent(
    body: AgentInvokeRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Synchronous agent invocation. Waits for full response.

    If conversation_id is provided, the agent loads history from that conversation
    and appends new messages to it. If not provided, a new conversation is created.
    """
    conversation_id = body.conversation_id
    skip_db = __import__("os").getenv("VOICE_DEV_SKIP_DB", "").lower() in {"1", "true", "yes", "on"}

    # Guardrails pre-gate on the inbound user message (before any DB/agent work
    # so a blocked input leaves no stray conversation or LLM call behind).
    policy = settings.guardrails_policy
    gate_in = run_gate(body.message, policy)
    if gate_in["action"] == "block":
        raise HTTPException(
            status_code=422,
            detail={"error": gate_in.get("error", "Input blocked by guardrails"),
                    "hits": gate_in["hits"]},
        )
    safe_message = gate_in["text"]

    history = None
    if skip_db:
        if not conversation_id:
            conversation_id = uuid.uuid4()
    else:
        async with get_session() as session:
            # Load history if continuing a conversation
            if conversation_id:
                # Verify conversation exists and belongs to tenant
                conv_result = await session.execute(
                    select(AgentConversation).where(
                        AgentConversation.id == conversation_id,
                        AgentConversation.tenant_id == ctx.tenant_id,
                    )
                )
                conv = conv_result.scalar_one_or_none()
                if not conv:
                    raise HTTPException(status_code=404, detail="Conversation not found")

                # Load message history
                msg_result = await session.execute(
                    select(AgentMessage)
                    .where(AgentMessage.conversation_id == conversation_id)
                    .order_by(AgentMessage.created_at.asc())
                )
                messages = msg_result.scalars().all()
                history = [
                    {"role": m.role, "content": m.content or ""}
                    for m in messages
                    if m.role in ("user", "assistant")
                ]

            # Create new conversation if not continuing
            if not conversation_id:
                conv = AgentConversation(
                    tenant_id=ctx.tenant_id,
                    agent_type=body.agent_type,
                    channel="api",
                    context=body.context,
                )
                session.add(conv)
                await session.flush()
                conversation_id = conv.id

    # Run the agent (outside the DB session to avoid long-held locks)
    tenant_id = body.tenant_id or ctx.tenant_id
    agent = Agent(
        agent_type=body.agent_type,
        tenant_id=tenant_id,
        context=body.context,
    )

    if settings.chat_backend == "hermes":
        messages = agent._build_messages(safe_message, history)
        messages.insert(0, {"role": "system", "content": _hermes_system_note(body.agent_type, tenant_id, body.context)})
        content = await hermes_client.chat(messages)
        result = {"content": content, "tool_calls": [], "conversation_id": conversation_id}
    else:
        result = await agent.run(
            user_message=safe_message,
            history=history,
            conversation_id=conversation_id,
        )

    # Guardrails post-gate on the assistant output.
    gate_out = run_gate(result["content"], policy)
    if gate_out["action"] == "mask":
        final_content = gate_out["text"]
    elif gate_out["action"] == "block":
        final_content = "[Response withheld by guardrails]"
    else:
        final_content = result["content"]
    gate_verdicts = [
        {"side": "input", "hits": gate_in["hits"], "action": gate_in["action"]},
        {"side": "output", "hits": gate_out["hits"], "action": gate_out["action"]},
    ]

    # Persist messages
    if not skip_db:
        async with get_session() as session:
            await _persist_messages(
                session=session,
                conversation_id=conversation_id,
                agent_type=body.agent_type,
                user_message=safe_message,
                assistant_content=final_content,
                tool_calls=result.get("tool_calls", []),
                gate_verdicts=gate_verdicts,
            )
            await session.flush()

    return AgentInvokeResponse(
        conversation_id=conversation_id,
        message=final_content,
        tool_calls=result.get("tool_calls", []),
        agent_type=body.agent_type,
    )


# ---------------------------------------------------------------------------
# POST /api/agents/invoke/stream — Streaming agent invocation
# ---------------------------------------------------------------------------

@router.post("/invoke/stream")
async def invoke_agent_stream(
    body: AgentInvokeRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Streaming agent invocation — returns an SSE stream of AGUIEvent JSON
    (matching packages/agent-chat's invokeAgentStreaming parser)."""
    tenant_id = body.tenant_id or ctx.tenant_id
    conversation_id = body.conversation_id

    skip_db = __import__("os").getenv("VOICE_DEV_SKIP_DB", "").lower() in {"1", "true", "yes", "on"}

    async def _ensure_conversation() -> uuid.UUID:
        if conversation_id:
            return conversation_id
        if skip_db:
            return uuid.uuid4()
        async with get_session() as session:
            conv = AgentConversation(
                tenant_id=tenant_id,
                agent_type=body.agent_type,
                channel="api",
                context=body.context,
            )
            session.add(conv)
            await session.flush()
            return conv.id

    async def event_stream():
        run_id = uuid.uuid4()

        def emit(event: AGUIEvent) -> str:
            return f"data: {event.model_dump_json()}\n\n"

        # Guardrails pre-gate on the inbound user message. On block, emit
        # RUN_ERROR without creating a conversation or calling the LLM.
        policy = settings.guardrails_policy
        gate_in = run_gate(body.message, policy)
        if gate_in["action"] == "block":
            conv_id = conversation_id or uuid.uuid4()
            yield emit(AGUIEvent(
                type="RUN_ERROR", run_id=run_id, tenant_id=tenant_id,
                conversation_id=conv_id,
                data={"error": gate_in.get("error", "Input blocked by guardrails"),
                      "hits": gate_in["hits"]},
            ))
            return
        safe_message = gate_in["text"]

        conv_id = await _ensure_conversation()

        yield emit(AGUIEvent(
            type="RUN_STARTED",
            run_id=run_id,
            tenant_id=tenant_id,
            conversation_id=conv_id,
            data={"agent_type": body.agent_type},
        ))

        agent = Agent(agent_type=body.agent_type, tenant_id=tenant_id, context=body.context)
        history = body.context.get("history", [])
        full_content = ""

        try:
            if settings.chat_backend == "hermes":
                messages = agent._build_messages(safe_message, history)
                messages.insert(0, {"role": "system", "content": _hermes_system_note(body.agent_type, tenant_id, body.context)})
                async for delta in hermes_client.chat_stream(messages):
                    full_content += delta
                    yield emit(AGUIEvent(
                        type="TEXT_MESSAGE_CONTENT", run_id=run_id, tenant_id=tenant_id,
                        conversation_id=conv_id, data={"delta": delta},
                    ))
            else:
                from services.agent_orchestrator.llm import llm_client

                tools_for_llm = tool_registry.to_openai_format(agent.tools)
                messages = agent._build_messages(safe_message, history)
                async for token in llm_client.chat_stream(
                    agent_type=body.agent_type, messages=messages, tools=tools_for_llm,
                ):
                    full_content += token
                    yield emit(AGUIEvent(
                        type="TEXT_MESSAGE_CONTENT", run_id=run_id, tenant_id=tenant_id,
                        conversation_id=conv_id, data={"delta": token},
                    ))
        except Exception as exc:
            logger.error("Agent stream failed (backend=%s): %s", settings.chat_backend, exc)
            yield emit(AGUIEvent(
                type="RUN_ERROR", run_id=run_id, tenant_id=tenant_id,
                conversation_id=conv_id, data={"error": str(exc)},
            ))
            return

        # Guardrails post-gate on the accumulated assistant output.
        gate_out = run_gate(full_content, policy)
        if gate_out["action"] == "mask":
            full_content = gate_out["text"]
        elif gate_out["action"] == "block":
            full_content = "[Response withheld by guardrails]"
        gate_verdicts = [
            {"side": "input", "hits": gate_in["hits"], "action": gate_in["action"]},
            {"side": "output", "hits": gate_out["hits"], "action": gate_out["action"]},
        ]

        if not skip_db:
            async with get_session() as session:
                await _persist_messages(
                    session=session,
                    conversation_id=conv_id,
                    agent_type=body.agent_type,
                    user_message=safe_message,
                    assistant_content=full_content,
                    tool_calls=[],
                    gate_verdicts=gate_verdicts,
                )
                await session.flush()

        yield emit(AGUIEvent(type="RUN_FINISHED", run_id=run_id, tenant_id=tenant_id, conversation_id=conv_id))

    return StreamingResponse(event_stream(), media_type="text/event-stream")
