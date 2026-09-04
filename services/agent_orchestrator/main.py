"""
Agent Orchestrator Service — Main FastAPI Application
AI agent runtime for OmniDome. Wraps microservice APIs as agent tools.
Port: 8021 | Module: agents
"""

import logging
import os
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production

logger = logging.getLogger("agent_orchestrator")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(
    title="OmniDome Agent Orchestrator",
    description="AI agent runtime — tool execution, conversation management, multi-agent orchestration",
    version="1.0.0",
)

guard = EntitlementGuard(
    module_id="agents",
    public_paths={
        "/health", "/docs", "/openapi.json",
        "/.well-known/agent-card.json", "/.well-known/ucp",
        "/api/protocols/a2ui/validate",
        # Hermes's MCP client — authenticated separately via bearer token
        # in routes/mcp.py, not the platform's per-tenant module licensing.
        "/mcp/", "/mcp/messages/",
    },
    # Public chat deployments (Task 7): identifier-keyed chat is reachable
    # without platform auth — tenant comes from the deployment row itself.
    # Prefix match: exact public_paths can't cover /api/chat/{identifier}.
    public_prefixes=("/api/chat",),
)

configure_production(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    skip_db = os.getenv("VOICE_DEV_SKIP_DB", "").lower() in {"1", "true", "yes", "on"}
    if skip_db:
        logger.warning("VOICE_DEV_SKIP_DB enabled; skipping agent-orchestrator table initialization")
    elif os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        import asyncio

        from services.common.db import get_engine, run_with_db_retry

        def _create_tables() -> None:
            from services.agent_orchestrator.conversation.models import Base as ConvBase
            from services.agent_orchestrator.protocol_models import (
                UCPCheckoutSessionRecord,
                AP2IntentMandateRecord,
                AP2PaymentMandateRecord,
                AP2PaymentReceiptRecord,
            )

            engine = get_engine()
            ConvBase.metadata.create_all(bind=engine)
            UCPCheckoutSessionRecord.metadata.create_all(bind=engine)
            AP2IntentMandateRecord.metadata.create_all(bind=engine)
            AP2PaymentMandateRecord.metadata.create_all(bind=engine)
            AP2PaymentReceiptRecord.metadata.create_all(bind=engine)

        await run_with_db_retry(lambda: asyncio.to_thread(_create_tables), logger=logger)
        logger.info("Agent orchestrator conversation + protocol tables ensured")


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


@app.get("/health")
async def health_check():
    return {
        "service": "agent-orchestrator",
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "module": "agents",
        "version": "1.0.0",
    }


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

from services.agent_orchestrator.routes.agents import router as agents_router
from services.agent_orchestrator.routes.conversations import router as conversations_router
from services.agent_orchestrator.routes.protocols import router as protocols_router
from services.agent_orchestrator.routes.tools import router as tools_router
from services.agent_orchestrator.routes.voice import router as voice_router
from services.agent_orchestrator.routes.mcp import router as mcp_router, sse_transport as mcp_sse_transport
from services.agent_orchestrator.routes.chat_deployments import (
    router as chat_deployments_router,
    public_router as chat_public_router,
)

app.include_router(agents_router, prefix="/api/agents")
app.include_router(conversations_router, prefix="/api/conversations")
app.include_router(protocols_router)
app.include_router(tools_router, prefix="/api/tools")
app.include_router(voice_router, prefix="/api/agents")
app.include_router(chat_deployments_router, prefix="/api/chat-deployments")
app.include_router(chat_public_router, prefix="/api/chat")
app.include_router(mcp_router)
app.mount("/mcp/messages", mcp_sse_transport.handle_post_message)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8021)
