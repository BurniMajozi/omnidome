"""OmniDome Billing Service — Invoicing, Payments, Collections, Auto-Suspension.

Port: 8003
"""

import logging
import os

from fastapi import FastAPI
from starlette.requests import Request

from services.common.entitlements import EntitlementGuard
from services.billing.database import init_tables
from services.billing.routes.invoices import router as invoices_router
from services.billing.routes.payments import router as payments_router
from services.billing.routes.paystack import router as paystack_router
from services.billing.routes.collections import router as collections_router
from services.billing.routes.reports import router as reports_router

logger = logging.getLogger("billing")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

# ---------------------------------------------------------------------------
# App & guard setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="OmniDome Billing Service",
    version="1.0.0",
    description="Invoicing, payments (Paystack), collections & dunning for SA ISPs — all in ZAR",
)

# Paystack webhook is public (no auth required)
guard = EntitlementGuard(
    module_id="billing",
    public_paths={"/payments/paystack/webhook"},
)


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        init_tables()
        logger.info("Billing tables ensured")


@app.middleware("http")
async def entitlement_middleware(request: Request, call_next):
    return await guard.middleware(request, call_next)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "billing"}


# ---------------------------------------------------------------------------
# Include routers
# ---------------------------------------------------------------------------

app.include_router(invoices_router)
app.include_router(payments_router)
app.include_router(paystack_router)
app.include_router(collections_router)
app.include_router(reports_router)


# ---------------------------------------------------------------------------
# Dunning cron endpoint (call from external scheduler)
# ---------------------------------------------------------------------------

@app.post("/dunning/process", tags=["Dunning"])
async def run_dunning():
    """Process all pending dunning actions.  Call this from a cron/scheduler."""
    from services.billing.routes.collections import process_pending_dunning
    count = process_pending_dunning()
    return {"processed": count}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
