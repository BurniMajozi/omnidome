"""
Communication Service — Main FastAPI Application
Implements the chat/messages/tasks/approvals hub for OmniDome.
Port: 8020 | Module: communication
"""

import logging
import os
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production

logger = logging.getLogger("communication")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(
    title="OmniDome Communication Service",
    description="Real-time communication hub — channels, messages, tasks, approvals, escalations",
    version="1.0.0",
)

guard = EntitlementGuard(
    module_id="communication",
    public_paths={"/health", "/docs", "/openapi.json", "/api/v1/public"},
)

configure_production(app)


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        from services.communication.database import init_tables
        await init_tables()
        logger.info("Communication tables ensured")


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


@app.get("/health")
async def health_check():
    return {
        "service": "communication",
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "module": "communication",
        "version": "1.0.0",
    }


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

from services.communication.routes.channels import router as channels_router
from services.communication.routes.messages import router as messages_router
from services.communication.routes.tasks import router as tasks_router
from services.communication.routes.approvals import router as approvals_router
from services.communication.routes.escalations import router as escalations_router
from services.communication.routes.events import router as events_router
from services.communication.routes.sessions import router as sessions_router
from services.communication.routes.module_data import router as module_data_router
from services.communication.routes.channel_preferences import router as channel_preferences_router
from services.communication.routes.messages_state import router as messages_state_router

app.include_router(channels_router, prefix="/api/v1")
app.include_router(messages_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(approvals_router, prefix="/api/v1")
app.include_router(escalations_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(sessions_router, prefix="/api/v1")
app.include_router(module_data_router, prefix="/api/v1")
app.include_router(channel_preferences_router, prefix="/api/v1")
app.include_router(messages_state_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8020)
