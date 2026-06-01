"""HR Service — Main FastAPI Application. Port: 8009 | Module: hr"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from services.common.entitlements import EntitlementGuard

app = FastAPI(
    title="OmniDome HR Service",
    description="Employee management, departments, leave requests, performance reviews",
    version="1.0.0",
)

guard = EntitlementGuard(
    module_id="hr",
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
        from hr.database import init_tables
        init_tables()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


@app.get("/health")
async def health_check():
    return {"service": "hr", "status": "healthy", "timestamp": datetime.utcnow().isoformat()}


from hr.routes.employees import router as employees_router
from hr.routes.departments import router as departments_router
from hr.routes.leave import router as leave_router
from hr.routes.performance import router as performance_router

app.include_router(employees_router)
app.include_router(departments_router)
app.include_router(leave_router)
app.include_router(performance_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8009)
