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
    public_paths={"/health", "/docs", "/openapi.json", "/.well-known/agent-card.json", "/.well-known/ucp"},
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
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        from services.agent_orchestrator.conversation.models import Base as ConvBase
        from services.common.db import get_engine
        engine = get_engine()
        ConvBase.metadata.create_all(bind=engine)
        logger.info("Agent orchestrator conversation tables ensured")


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

app.include_router(agents_router, prefix="/api/agents")
app.include_router(conversations_router, prefix="/api/conversations")
app.include_router(protocols_router)
app.include_router(tools_router, prefix="/api/tools")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8021)
