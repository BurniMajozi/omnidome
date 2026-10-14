"""Optional per-process poller. PostgreSQL row locks avoid concurrent home syncs."""
import asyncio
import logging

from sqlalchemy import select
from services.iot.database import get_session
from services.iot.households import sync_home
from services.iot.models import IoTHome

log = logging.getLogger("iot.homedome")


async def poll_homes():
    while True:
        try:
            async with get_session() as session:
                ids = list((await session.scalars(select(IoTHome.id).where(
                    IoTHome.ha_token_encrypted.is_not(None), IoTHome.ha_url.is_not(None)))).all())
            for identity in ids:
                async with get_session() as session:
                    home = await session.scalar(select(IoTHome).where(IoTHome.id == identity).with_for_update(skip_locked=True))
                    if home and home.ha_token_encrypted and home.ha_url:
                        await asyncio.wait_for(sync_home(session, home), timeout=45)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("HomeDome polling interrupted: %s", type(exc).__name__)
        await asyncio.sleep(60)
