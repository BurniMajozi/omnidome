"""MCP server — exposes the 5 existing domain subagents to Hermes as tools.

Each MCP tool is a thin proxy to the same in-process Agent.run() loop that
the A2A endpoint (routes/protocols.py: POST /api/protocols/a2a/message)
already uses. This reuses the existing qwen/llama specialist agents and
their tool-chaining as-is -- Hermes (the chat brain) delegates a whole
business task to a specialist and gets back a finished answer, the same
way an external A2A caller would.

Hermes is the only intended caller (mcp_servers.omnidome in its
config.yaml), authenticated with a shared bearer token rather than the
platform's normal per-user JWT/header auth.
"""
from __future__ import annotations

import contextvars
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types

from services.agent_orchestrator.agents import Agent
from services.agent_orchestrator.config import settings
from services.agent_orchestrator.protocols import AGENT_SKILLS

logger = logging.getLogger("agent_orchestrator.mcp")

router = APIRouter()

_SSE_PATH = "/mcp/"
_MESSAGES_PATH = "/mcp/messages/"

# Per-connection context — set in the SSE handshake (where we have the raw
# request/headers), read inside call_tool (which only gets name+arguments).
_tenant_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("mcp_tenant_id", default="")
_user_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("mcp_user_id", default="hermes-agent")

server = Server("omnidome")

_DOMAIN_TOOLS = {
    f"ask_{agent_type}_agent": agent_type for agent_type in AGENT_SKILLS
}


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=tool_name,
            description=(
                f"Delegate a complete request to the OmniDome {agent_type} "
                f"specialist agent and get back a finished answer. Skills: "
                f"{', '.join(s['name'] for s in AGENT_SKILLS[agent_type])}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The request to hand to the specialist, in natural language.",
                    },
                },
                "required": ["message"],
            },
        )
        for tool_name, agent_type in _DOMAIN_TOOLS.items()
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    agent_type = _DOMAIN_TOOLS.get(name)
    if not agent_type:
        return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    message = arguments.get("message", "")
    tenant_id_raw = _tenant_id_ctx.get()
    try:
        tenant_id = uuid.UUID(tenant_id_raw) if tenant_id_raw else None
    except ValueError:
        tenant_id = None

    agent = Agent(
        agent_type=agent_type,
        tenant_id=tenant_id,
        channel="mcp",
        context={"user_id": _user_id_ctx.get()},
    )
    result = await agent.run(message)
    return [types.TextContent(type="text", text=result.get("content", ""))]


def _check_auth(request: Request) -> None:
    expected = settings.hermes_api_key
    if not expected:
        return
    auth_header = request.headers.get("authorization", "")
    if auth_header != f"Bearer {expected}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing bearer token")


sse_transport = SseServerTransport(_MESSAGES_PATH)


@router.get(_SSE_PATH)
async def handle_sse(request: Request):
    _check_auth(request)
    _tenant_id_ctx.set(request.headers.get("x-tenant-id", ""))
    _user_id_ctx.set(request.headers.get("x-user-id", "hermes-agent"))
    # Documented MCP SDK ASGI integration pattern — connect_sse needs the raw
    # ASGI send callable, which Starlette's Request only exposes as `_send`.
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())
