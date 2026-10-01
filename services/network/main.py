"""CoreConnect Network Service — Module 8 (port 8005).

Manages fibre network services, RADIUS subscriber authentication,
FNO integrations (Vumatel, Openserve, MetroFibre, Frogfoot, Octotel),
multi-provider coverage checks, and service lifecycle operations.
"""

import logging
import os
import random
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
from services.common.auth import AuthContext, get_auth_context
from services.common.db import run_with_db_retry
from services.network.access import enforce_route_tier
from services.network.database import init_tables, get_session
from services.network.models import NetworkService, RadiusAccount
from services.network.secrets_migration import run_secrets_migration

# Route modules
from services.network.routes.radius import router as radius_router
from services.network.routes.fno import router as fno_router
from services.network.routes.services import router as services_router
from services.network.routes.coverage import router as coverage_router
from services.network.routes.performance import router as performance_router
from services.network.routes.notifications import router as notifications_router
from services.network.routes.devices import router as devices_router
from services.network.routes.topology import router as topology_router
from services.network.routes.phase4 import router as phase4_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [network] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App + Entitlement guard
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CoreConnect Network Service",
    version="1.0.0",
    description="Fibre network management, RADIUS, FNO automation & coverage",
)

guard = EntitlementGuard(module_id="network")

configure_production(app)


@app.on_event("startup")
async def startup() -> None:
    # NOTE: this service keeps in-process state and must run with a SINGLE worker (--workers 1).
    guard.ensure_startup()

    async def _init() -> None:
        if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
            logger.info("Auto-creating network tables …")
            await run_in_threadpool(init_tables)
        # idempotent locked ALTERs (+ encrypt legacy plaintext secrets when SECRETS_ENCRYPTION_KEY is set)
        await run_in_threadpool(run_secrets_migration)

    await run_with_db_retry(_init, logger=logger)


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------

app.include_router(services_router, dependencies=[Depends(enforce_route_tier)])
app.include_router(radius_router, dependencies=[Depends(enforce_route_tier)])
app.include_router(fno_router, dependencies=[Depends(enforce_route_tier)])
app.include_router(coverage_router, dependencies=[Depends(enforce_route_tier)])
app.include_router(performance_router, dependencies=[Depends(enforce_route_tier)])
app.include_router(notifications_router, dependencies=[Depends(enforce_route_tier)])
app.include_router(devices_router, dependencies=[Depends(enforce_route_tier)])
app.include_router(topology_router, dependencies=[Depends(enforce_route_tier)])
app.include_router(phase4_router, dependencies=[Depends(enforce_route_tier)])


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"service": "network", "status": "healthy"}


# ── Speed Test (for mobile technician app) ────────────────────────────

@app.post("/speed-test")
async def run_speed_test(
    auth: AuthContext = Depends(get_auth_context),
):
    """Run a speed test from the gateway. SIMULATED: no iperf3 backend is wired, values are random and
    flagged as such so no client mistakes them for a measurement."""
    return {
        "simulated": True,
        "download_mbps": round(random.uniform(20, 100), 1),
        "upload_mbps": round(random.uniform(10, 50), 1),
        "latency_ms": round(random.uniform(5, 30), 1),
        "jitter_ms": round(random.uniform(1, 10), 1),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── RADIUS Account Lookup (for mobile technician app) ─────────────────

@app.get("/radius-accounts")
async def lookup_radius_account(
    contact_id: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
):
    """Real lookup: the customer's RADIUS accounts (secrets are never returned)."""
    if not contact_id:
        return []
    try:
        import uuid as _uuid
        customer = _uuid.UUID(contact_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="contact_id must be a UUID")

    def _query():
        with get_session() as session:
            rows = session.execute(
                select(RadiusAccount).join(NetworkService, NetworkService.id == RadiusAccount.service_id).where(
                    RadiusAccount.tenant_id == auth.tenant_id, NetworkService.customer_id == customer)
            ).scalars().all()
            return [{"username": r.username, "status": r.status, "profile_name": r.profile_name,
                     "has_password": r.has_password} for r in rows]

    return await run_in_threadpool(_query)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005, workers=1)
