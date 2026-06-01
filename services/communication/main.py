"""
Communication Service — Main FastAPI Application
Implements the chat/messages/tasks/approvals hub for OmniDome.
Port: 8020 | Module: communication
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from services.common.entitlements import EntitlementGuard

app = FastAPI(
    title="OmniDome Communication Service",
    description="Real-time communication hub — channels, messages, tasks, approvals, escalations",
    version="1.0.0",
)

guard = EntitlementGuard(
    module_id="communication",
    public_paths={"/health", "/docs", "/openapi.json", "/api/v1/public"},
)

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
    # Import and create tables on startup if AUTO_CREATE_TABLES is set
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        from communication.database import init_tables
        init_tables()


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

from communication.routes.channels import router as channels_router
from communication.routes.messages import router as messages_router
from communication.routes.tasks import router as tasks_router
from communication.routes.approvals import router as approvals_router
from communication.routes.escalations import router as escalations_router
from communication.routes.events import router as events_router
from communication.routes.module_data import router as module_data_router

app.include_router(channels_router, prefix="/api/v1")
app.include_router(messages_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(approvals_router, prefix="/api/v1")
app.include_router(escalations_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(module_data_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8020)
