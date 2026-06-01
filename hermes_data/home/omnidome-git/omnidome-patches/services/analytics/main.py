"""Analytics Service — Main FastAPI Application. Port: 8011 | Module: analytics"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from services.common.entitlements import EntitlementGuard

app = FastAPI(title="OmniDome Analytics Service", description="AI-powered executive insights and cross-service analytics", version="1.0.0")
guard = EntitlementGuard(module_id="analytics", public_paths={"/health", "/docs", "/openapi.json"})
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def startup():
    guard.ensure_startup()
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        from analytics.database import init_tables
        init_tables()

@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)

@app.get("/health")
async def health_check():
    return {"service": "analytics", "status": "healthy", "timestamp": datetime.utcnow().isoformat()}

from analytics.routes.insights import router as insights_router
app.include_router(insights_router, prefix="/api/v1/analytics")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8011)
