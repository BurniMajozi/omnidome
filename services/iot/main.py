"""OmniDome IoT Service — Home Assistant integration for smart device management.

Manages IoT device registry, rooms/zones, automations, events,
scenes, alerts, and Home Assistant REST/WebSocket integration.
Port: 8006
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

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
    await init_tables()
    logger.info("IoT service started — tables initialized")
    yield
    logger.info("IoT service shutting down")


app.router.lifespan_context = lifespan

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(integrations_router, prefix="/api/iot/integrations", tags=["iot-integrations"])
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
