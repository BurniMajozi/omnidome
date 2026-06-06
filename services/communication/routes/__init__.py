"""Communication service routes."""

from services.communication.routes.channels import router as channels_router
from services.communication.routes.messages import router as messages_router
from services.communication.routes.tasks import router as tasks_router
from services.communication.routes.approvals import router as approvals_router
from services.communication.routes.escalations import router as escalations_router
from services.communication.routes.events import router as events_router
from services.communication.routes.module_data import router as module_data_router

__all__ = [
    "channels_router",
    "messages_router",
    "tasks_router",
    "approvals_router",
    "escalations_router",
    "events_router",
    "module_data_router",
]
