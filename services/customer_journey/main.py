"""Customer Journey Service — unified fiber customer lifecycle management.

Orchestrates: coverage, orders, delivery, technician visits, promotions,
announcements, activity timeline, and customer 360 view.
"""

import logging
import os

from fastapi import FastAPI

from services.common.entitlements import EntitlementGuard
from services.customer_journey.database import init_tables
from services.customer_journey.routes import router as journey_router
from services.customer_journey.store_routes import router as store_router

logger = logging.getLogger("customer_journey")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(
    title="CoreConnect Customer Journey Service",
    version="0.1.0",
    description="Unified fiber customer lifecycle — coverage, orders, delivery, technician, promotions, 360",
)
guard = EntitlementGuard(module_id="customer_journey")


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "customer_journey"}


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    await init_tables()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


# Register routes
app.include_router(journey_router)
app.include_router(store_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8022)
