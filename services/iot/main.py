"""OmniDome IoT Service — Home Assistant integration for smart device management.

Manages IoT device registry, rooms/zones, automations, events,
scenes, alerts, and Home Assistant REST/WebSocket integration.
Port: 8006
"""

import logging
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.common.db import run_with_db_retry
from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
from services.iot.database import init_tables

# Route modules
from services.iot.routes.devices import router as devices_router
from services.iot.routes.rooms import router as rooms_router
from services.iot.routes.automations import router as automations_router
from services.iot.routes.events import router as events_router
from services.iot.routes.cameras import router as cameras_router
from services.iot.routes.sensors import router as sensors_router
from services.iot.routes.scenes import router as scenes_router
from services.iot.routes.alerts import router as alerts_router
from services.iot.routes.integrations import router as integrations_router
from services.iot.routes.homes import router as homes_router
from services.iot.routes.homes import account_router
from services.iot.routes.home_features import router as home_features_router
from services.iot.routes.home_rooms import router as home_rooms_router
from services.iot.routes.home_reports import router as home_reports_router
from services.iot.routes.ha_reference import router as ha_reference_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [iot] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App + Entitlement guard
# ---------------------------------------------------------------------------

app = FastAPI(
    title="OmniDome IoT Service",
    version="1.0.0",
    description="Home Assistant IoT device management, automations & monitoring",
)

guard = EntitlementGuard(module_id="iot")

configure_production(app)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    guard.ensure_startup()
    # Retry while Postgres (or its DNS) comes up — otherwise a boot-time race with
    # the db container crashes the worker (exit 3) and it stays down. Matches the
    # rest of the stack's startup handling.
    await run_with_db_retry(init_tables, logger=logger)
    from services.common.event_bus import ensure_schema
    from services.iot.database import get_session
    async with get_session() as session:
        await ensure_schema(session)
    logger.info("IoT service started — tables initialized")
    task = None
    if os.getenv("HOME_DOME_POLL_ENABLED", "false").lower() == "true":
        from services.iot.home_worker import poll_homes
        task = asyncio.create_task(poll_homes())
    reference_task = None
    if os.getenv("HA_REFERENCE_REFRESH_ENABLED", "true").lower() == "true":
        from services.iot.ha_reference_worker import refresh_loop
        reference_task = asyncio.create_task(refresh_loop())
    try:
        yield
    finally:
        for running in (task, reference_task):
            if running:
                running.cancel()
                try:
                    await running
                except asyncio.CancelledError:
                    pass
    logger.info("IoT service shutting down")


app.router.lifespan_context = lifespan

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(integrations_router, prefix="/api/iot/integrations", tags=["iot-integrations"])
app.include_router(account_router, prefix="/api/iot/homes", tags=["customer-accounts"])
app.include_router(homes_router, prefix="/api/iot/homes", tags=["customer-homes"])
app.include_router(home_features_router, prefix="/api/iot/homes", tags=["private-home-features"])
app.include_router(home_rooms_router, prefix="/api/iot/homes", tags=["home-room-layout"])
app.include_router(home_reports_router, prefix="/api/iot/homes", tags=["home-reporting"])
app.include_router(ha_reference_router, prefix="/api/iot/reference", tags=["ha-reference"])
app.include_router(devices_router, prefix="/api/iot/devices", tags=["iot-devices"])
app.include_router(rooms_router, prefix="/api/iot/rooms", tags=["iot-rooms"])
app.include_router(cameras_router, prefix="/api/iot/cameras", tags=["iot-cameras"])
app.include_router(sensors_router, prefix="/api/iot/sensors", tags=["iot-sensors"])
app.include_router(automations_router, prefix="/api/iot/automations", tags=["iot-automations"])
app.include_router(scenes_router, prefix="/api/iot/scenes", tags=["iot-scenes"])
app.include_router(events_router, prefix="/api/iot/events", tags=["iot-events"])
app.include_router(alerts_router, prefix="/api/iot/alerts", tags=["iot-alerts"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "iot", "version": "1.0.0"}
