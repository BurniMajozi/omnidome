"""Minimal connectivity facts and addressed support notifications; no camera/sensor data."""
from services.common.event_bus import publish, notify

EVENTS = {"iot.home.offline", "iot.home.recovered", "iot.support.requested"}


async def emit(session, home, event_type, key):
    if event_type not in EVENTS:
        raise ValueError("Unsupported HomeDome event")
    await publish(session, home.tenant_id, event_type, {"home_id": str(home.id)}, source="homedome",
        subject=("iot_home", home.id), idempotency_key="homedome:" + key)


async def support_notice(session, home, recipient, title):
    await notify(session, home.tenant_id, title, category="homedome", source="homedome",
        recipient_id=recipient, link="/dashboard/home-dome", subject=("iot_home", home.id))
