"""Agent invocation routes — with conversation persistence."""

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from services.common.auth import AuthContext, get_auth_context
from services.crm.database import get_session
from services.agent_orchestrator.agents import Agent
from services.agent_orchestrator.tools import tool_registry
from services.agent_orchestrator.schemas import AgentInvokeRequest, AgentInvokeResponse, AgentInfo
from services.agent_orchestrator.conversation.models import (
    AgentConversation,
    AgentMessage,
    AgentAction,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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
    agents = [
        AgentInfo(
            agent_type="customer_facing",
            description="DomeBot — assists customers with balances, invoices, coverage, tickets",
            llm="qwen2.5:7b",
            tools=Agent("customer_facing").available_tool_names,
        ),
        AgentInfo(
            agent_type="retention",
            description="ChurnGuard — autonomous churn prediction and retention campaigns",
            llm="llama3.1:70b",
            tools=Agent("retention").available_tool_names,
        ),
        AgentInfo(
            agent_type="provisioning",
            description="ProvisionBot — automates new customer provisioning workflow",
            llm="qwen2.5:7b",
            tools=Agent("provisioning").available_tool_names,
        ),
        AgentInfo(
            agent_type="executive",
            description="InsightBot — executive briefings and analytics",
            llm="llama3.1:70b",
            tools=Agent("executive").available_tool_names,
        ),
        AgentInfo(
            agent_type="support",
            description="SupportBot — ticket management and diagnostics",
            llm="qwen2.5:7b",
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

    async with get_session() as session:
        # Load history if continuing a conversation
        history = None
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
    agent = Agent(
        agent_type=body.agent_type,
        tenant_id=body.tenant_id or ctx.tenant_id,
        context=body.context,
    )

    result = await agent.run(
        user_message=body.message,
        history=history,
        conversation_id=conversation_id,
    )

    # Persist messages
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
    """Streaming agent invocation — returns SSE stream."""
    from services.agent_orchestrator.llm import llm_client

    async def event_stream():
        agent = Agent(
            agent_type=body.agent_type,
            tenant_id=body.tenant_id or ctx.tenant_id,
            context=body.context,
        )
        tools = agent.tools
        tools_for_llm = tool_registry.to_openai_format(tools)

        history = body.context.get("history", [])
        messages = agent._build_messages(body.message, history)

        async for token in llm_client.chat_stream(
            agent_type=body.agent_type,
            messages=messages,
            tools=tools_for_llm,
        ):
            yield f"data: {token}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
