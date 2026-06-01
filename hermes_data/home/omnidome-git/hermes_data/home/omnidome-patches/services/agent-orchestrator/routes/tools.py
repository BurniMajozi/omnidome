"""Tool management routes."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from services.common.auth import AuthContext, get_auth_context
from agent_orchestrator.tools import tool_registry
from agent_orchestrator.schemas import ToolInfo, ToolInvokeRequest, ToolInvokeResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=list[ToolInfo])
async def list_tools(
    ctx: AuthContext = Depends(get_auth_context),
    agent_type: Optional[str] = None,
):
    """List available tools, optionally filtered by agent type."""
    if agent_type:
        tools = tool_registry.filter_for_agent(agent_type)
    else:
        tools = tool_registry.list_tools()

    return [
        ToolInfo(
            name=t.name,
            description=t.description,

            service=t.service,
            method=t.method,
            endpoint=t.endpoint,
        )
        for t in tools
    ]


@router.post("/invoke", response_model=ToolInvokeResponse)
async def invoke_tool(
    body: ToolInvokeRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Directly invoke a single tool (for testing/debugging)."""
    tool = tool_registry.get(body.tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool not found: {body.tool_name}")

    result = await tool.execute(
        tool_input=body.tool_input,
        tenant_id=str(body.tenant_id) if body.tenant_id else str(ctx.tenant_id),
        user_id=str(body.user_id) if body.user_id else str(ctx.user_id),
    )

    return ToolInvokeResponse(
        tool_name=body.tool_name,
        result=result.get("data") if result.get("success") else result.get("error"),
        success=result.get("success", False),
        error=result.get("error"),
    )
