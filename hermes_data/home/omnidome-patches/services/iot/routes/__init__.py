"""IoT routes — exports all IoT routers."""

from iot.routes.devices import router as devices_router
from iot.routes.telemetry import router as telemetry_router

__all__ = ["devices_router", "telemetry_router"]
