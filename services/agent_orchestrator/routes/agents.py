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
        messages = agent._build_messages(body.message, history)
        messages.insert(0, {"role": "system", "content": _hermes_system_note(body.agent_type, tenant_id, body.context)})
        content = await hermes_client.chat(messages)
        result = {"content": content, "tool_calls": [], "conversation_id": conversation_id}
    else:
        result = await agent.run(
            user_message=body.message,
            history=history,
            conversation_id=conversation_id,
        )

    # Persist messages
    if not skip_db:
        async with get_session() as session:
            await _persist_messages(
                session=session,
                conversation_id=conversation_id,
                agent_type=body.agent_type,
                user_message=body.message,
                assistant_content=result["content"],
                tool_calls=result.get("tool_calls", []),
            )
            await session.flush()

    return AgentInvokeResponse(
        conversation_id=conversation_id,
        message=result["content"],
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
        conv_id = await _ensure_conversation()

        def emit(event: AGUIEvent) -> str:
            return f"data: {event.model_dump_json()}\n\n"

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
                messages = agent._build_messages(body.message, history)
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
                messages = agent._build_messages(body.message, history)
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

        if not skip_db:
            async with get_session() as session:
                await _persist_messages(
                    session=session,
                    conversation_id=conv_id,
                    agent_type=body.agent_type,
                    user_message=body.message,
                    assistant_content=full_content,
                    tool_calls=[],
                )
                await session.flush()

        yield emit(AGUIEvent(type="RUN_FINISHED", run_id=run_id, tenant_id=tenant_id, conversation_id=conv_id))

    return StreamingResponse(event_stream(), media_type="text/event-stream")
