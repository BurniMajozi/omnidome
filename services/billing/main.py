"""OmniDome Billing Service — Invoicing, Payments, Collections, Auto-Suspension.

Port: 8003
"""

import logging
import os

from fastapi import FastAPI
from starlette.requests import Request

from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
from services.billing.database import init_tables
from services.billing.routes.invoices import router as invoices_router
from services.billing.routes.payments import router as payments_router
from services.billing.routes.paystack import router as paystack_router
from services.billing.routes.paystack_recurring import router as paystack_recurring_router
from services.billing.routes.collections import router as collections_router
from services.billing.routes.reports import router as reports_router
from services.billing.routes.subscriptions import router as subscriptions_router
from services.billing.routes.cancellations import router as cancellations_router
from services.billing.routes.radius_billing import router as radius_billing_router
from services.billing.routes.billing_accounts import router as billing_accounts_router
from services.billing.routes.subscription_transfers import router as transfers_router
from services.billing.routes.plans import router as plans_router
from services.billing.routes.seats import router as seats_router
from services.billing.routes.finance_outbox import PUBLIC_PATHS as OUTBOX_PUBLIC_PATHS, router as outbox_router
from services.billing.routes.invoice_documents import router as invoice_documents_router
from services.billing.routes.quotes import router as quotes_router
from services.billing.routes.public_invoices import router as public_invoices_router
from services.billing.routes.delivery import PUBLIC_PATHS as DELIVERY_PUBLIC_PATHS, router as delivery_router
from services.billing.routes.movements import router as movements_router
from services.billing.routes.customer_app import router as customer_app_router
from services.billing.routes.fee_policies import router as fee_policies_router

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
    public_paths={"/payments/paystack/webhook"} | OUTBOX_PUBLIC_PATHS | DELIVERY_PUBLIC_PATHS,  # the latter authorize themselves (internal key / admin)
    public_prefixes=("/public/",),  # share-token routes: per-IP rate limited, generic 404, sanitised (routes/public_invoices.py)
)

configure_production(app)


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        init_tables()
        logger.info("Billing tables ensured")
    # Seat-billing scheduler: OFF unless SEAT_BILLING_WORKER_ENABLED=true.
    from services.billing import seat_runs
    if seat_runs.worker_enabled():
        import asyncio
        app.state.seat_worker = asyncio.create_task(seat_runs.worker_loop())
    from services.billing import finance_posting
    if finance_posting.worker_enabled():  # BILLING_OUTBOX_WORKER_ENABLED, default off
        import asyncio
        app.state.outbox_worker = asyncio.create_task(finance_posting.worker_loop())


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
app.include_router(paystack_recurring_router)
app.include_router(collections_router)
app.include_router(reports_router)
app.include_router(subscriptions_router)
app.include_router(cancellations_router)
app.include_router(billing_accounts_router)
app.include_router(transfers_router)
app.include_router(plans_router)
app.include_router(seats_router)
app.include_router(outbox_router)
app.include_router(fee_policies_router)
app.include_router(invoice_documents_router)
app.include_router(quotes_router)
app.include_router(public_invoices_router)
app.include_router(delivery_router)
app.include_router(movements_router)
app.include_router(customer_app_router)


app.include_router(radius_billing_router)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
