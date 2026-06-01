"""RICA Service — Main FastAPI Application. Port: 8004 | Module: rica

Smile ID identity verification for South African RICA compliance.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from services.common.entitlements import EntitlementGuard

app = FastAPI(
    title="OmniDome RICA Service",
    description="Smile ID identity verification for SA RICA compliance",
    version="1.0.0",
)

guard = EntitlementGuard(
    module_id="rica",
    public_paths={"/health", "/docs", "/openapi.json", "/api/v1/rica/verifications/webhook"},
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
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        from rica.database import init_tables
        init_tables()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


@app.get("/health")
async def health_check():
    return {"service": "rica", "status": "healthy", "timestamp": datetime.utcnow().isoformat()}


from rica.routes.verifications import router as verifications_router
app.include_router(verifications_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
