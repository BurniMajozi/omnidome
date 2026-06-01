"""Agent invocation routes."""

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from services.common.auth import AuthContext, get_auth_context
from agent_orchestrator.agents import Agent
from agent_orchestrator.schemas import AgentInvokeRequest, AgentInvokeResponse, AgentInfo

logger = logging.getLogger(__name__)

router = APIRouter()


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


@router.post("/invoke", response_model=AgentInvokeResponse)
async def invoke_agent(
    body: AgentInvokeRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Synchronous agent invocation. Waits for full response."""
    agent = Agent(
        agent_type=body.agent_type,
        tenant_id=body.tenant_id or ctx.tenant_id,
        context=body.context,
    )

    result = await agent.run(
        user_message=body.message,
    )

    return AgentInvokeResponse(
        conversation_id=uuid.uuid4(),
        message=result["content"],
        tool_calls=result.get("tool_calls", []),
        agent_type=body.agent_type,
    )


@router.post("/invoke/stream")
async def invoke_agent_stream(
    body: AgentInvokeRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Streaming agent invocation — returns SSE stream."""
    from agent_orchestrator.llm import llm_client

    async def event_stream():
        agent = Agent(
            agent_type=body.agent_type,
            tenant_id=body.tenant_id or ctx.tenant_id,
            context=body.context,
        )
        tools = agent.tools
        tools_for_llm = agent.to_openai_format(tools)

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
