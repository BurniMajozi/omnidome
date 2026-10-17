"""Minimal connectivity facts and addressed support notifications; no camera/sensor data."""
from services.common.event_bus import publish, notify

EVENTS = {"iot.home.offline", "iot.home.recovered", "iot.support.requested", "iot.gateway.activated", "iot.integration.connected",
          "iot.gateway.failed", "iot.integration.failed"}


async def emit(session, home, event_type, key):
    if event_type not in EVENTS:
        raise ValueError("Unsupported HomeDome event")
    await publish(session, home.tenant_id, event_type, {"home_id": str(home.id)}, source="homedome",
        subject=("iot_home", home.id), idempotency_key="homedome:" + key)


async def support_notice(session, home, recipient, title):
    await notify(session, home.tenant_id, title, category="homedome", source="homedome",
        recipient_id=recipient, link="/dashboard/home-dome", subject=("iot_home", home.id))


async def report_failure(tenant_id, home_id, event_type, reason, *, integration=None):
    """Publish a gateway/integration failure (turned into a deduplicated support ticket) from a code path that
    has no open session. Never raises: reporting must not change the customer's error response."""
    import logging
    from services.iot.database import get_session
    from services.common.redaction import redact_text
    if event_type not in EVENTS:
        raise ValueError("Unsupported HomeDome event")
    try:
        async with get_session() as session:
            payload = {"home_id": str(home_id), "reason": redact_text(reason, 200)}
            if integration:
                payload["integration"] = str(integration)[:60]
            await publish(session, tenant_id, event_type, payload, source="homedome", subject=("iot_home", home_id))
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("iot.home_events").warning("could not publish %s: %s", event_type, type(exc).__name__)
