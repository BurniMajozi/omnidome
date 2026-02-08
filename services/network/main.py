"""CoreConnect Network Service — Module 8 (port 8005).

Manages fibre network services, RADIUS subscriber authentication,
FNO integrations (Vumatel, Openserve, MetroFibre, Frogfoot, Octotel),
multi-provider coverage checks, and service lifecycle operations.
"""

import logging
import os

from fastapi import FastAPI

from services.common.entitlements import EntitlementGuard
from services.network.database import init_tables

# Route modules
from services.network.routes.radius import router as radius_router
from services.network.routes.fno import router as fno_router
from services.network.routes.services import router as services_router
from services.network.routes.coverage import router as coverage_router

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


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        logger.info("Auto-creating network tables …")
        init_tables()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------

app.include_router(services_router)
app.include_router(radius_router)
app.include_router(fno_router)
app.include_router(coverage_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"service": "network", "status": "healthy"}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
