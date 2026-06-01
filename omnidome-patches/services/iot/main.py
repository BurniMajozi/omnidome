"""IoT Service — Main FastAPI Application. Port: 8006 | Module: iot"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from services.common.entitlements import EntitlementGuard

app = FastAPI(
    title="OmniDome IoT Service",
    description="Device telemetry and CPE health monitoring",
    version="1.0.0",
)

guard = EntitlementGuard(
    module_id="iot",
    public_paths={"/health", "/docs", "/openapi.json"},
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
        from iot.database import init_tables
        init_tables()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


@app.get("/health")
async def health_check():
    return {"service": "iot", "status": "healthy", "timestamp": datetime.utcnow().isoformat()}


from iot.routes.devices import router as devices_router
from iot.routes.telemetry import router as telemetry_router

app.include_router(devices_router)
app.include_router(telemetry_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
