"""OmniDome CRM Service — Customer 360, Segmentation, Leads.

Port: 8001
"""

import logging
import os

from fastapi import FastAPI
from starlette.requests import Request

from services.common.entitlements import EntitlementGuard
from services.crm.database import init_tables
from services.crm.routes.customers import router as customers_router
from services.crm.routes.leads import router as leads_router
from services.crm.routes.notes_tags import router as notes_tags_router
from services.crm.routes.segments import router as segments_router

logger = logging.getLogger("crm")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

# ---------------------------------------------------------------------------
# App & guard setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="OmniDome CRM Service",
    version="1.0.0",
    description="Customer 360, segmentation, lead tracking for South African ISPs",
)

guard = EntitlementGuard(module_id="crm")


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        init_tables()
        logger.info("CRM tables ensured")


@app.middleware("http")
async def entitlement_middleware(request: Request, call_next):
    return await guard.middleware(request, call_next)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "crm"}


# ---------------------------------------------------------------------------
# Include routers
# ---------------------------------------------------------------------------

app.include_router(customers_router)
app.include_router(leads_router)
app.include_router(notes_tags_router)
app.include_router(segments_router)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
