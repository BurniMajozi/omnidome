"""Weekly refresh of the Home Assistant reference library for the integrations in our catalogue."""
import asyncio
import logging
import os

from sqlalchemy import text

from services.iot import ha_reference
from services.iot.database import get_session
from services.iot.integration_catalog import INTEGRATIONS

logger = logging.getLogger("iot.ha_reference")
LOCK_KEY = 0x10_7_0_07  # one replica refreshes at a time


async def refresh_once() -> dict | None:
    async with get_session() as session:
        got = (await session.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": LOCK_KEY})).scalar()
        if not got:
            return None
        return await ha_reference.refresh(session, [item[0] for item in INTEGRATIONS])


async def refresh_loop() -> None:
    interval = float(os.getenv("HA_REFERENCE_REFRESH_HOURS", "168")) * 3600
    await asyncio.sleep(120)  # let the service finish starting first
    while True:
        try:
            async with get_session() as session:
                await ha_reference.ensure_table(session)
                last = (await session.execute(text("SELECT max(fetched_at) FROM ha_reference_docs WHERE kind = 'integration'"))).scalar()
                due = last is None or (await session.execute(text("SELECT now() - :t > make_interval(secs => :s)"), {"t": last, "s": interval})).scalar()
            if due:
                stats = await refresh_once()
                logger.info("HA reference refresh: %s", stats)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a failed refresh retries on the next tick
            logger.exception("HA reference refresh failed")
        await asyncio.sleep(6 * 3600)
