"""Analytics sync worker entrypoint.

A dedicated, long-running service (no HTTP port) that keeps each tenant's
analytics tables fresh:

  hot pass        every hour   (last 30 days)
  long-tail pass  every week   (up to 366 days)
  follower pass   every day
  backfill        once per tenant at first sight

Runs a single instance — schedule one replica, or add a leader lock if you
scale it out.
"""
from __future__ import annotations

import asyncio
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from services.analytics_worker import sync

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("analytics_worker")


def _ensure_tables() -> None:
    """Reuse the marketing service's DDL so the worker can run before/independently
    of the marketing API having created the tables."""
    try:
        from services.common.db import get_engine
        from services.marketing.main import _ensure_marketing_tables
        _ensure_marketing_tables(get_engine())
        logger.info("analytics tables ensured")
    except Exception as e:  # noqa: BLE001
        logger.warning("could not ensure tables (will rely on marketing service): %s", e)


async def main() -> None:
    if not sync.configured():
        logger.warning("ZERNIO_API_KEY not set — worker will idle until it is configured.")

    _ensure_tables()
    sync.maybe_seed_from_env()

    # First-time history load for any un-backfilled tenants.
    await sync.run_backfill()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(sync.run_pass, "interval", hours=1, args=[30, "last_hot_sync"], id="hot", max_instances=1)
    scheduler.add_job(sync.run_pass, "interval", weeks=1, args=[366, "last_longtail_sync"], id="longtail", max_instances=1)
    scheduler.add_job(sync.run_pass, "interval", days=1, args=[30, "last_follower_sync"], kwargs={"followers": True}, id="followers", max_instances=1)
    scheduler.start()
    logger.info("analytics worker started — hot hourly, long-tail weekly, followers daily")

    # Kick off one hot pass immediately so dashboards fill without waiting an hour.
    await sync.run_pass(30, "last_hot_sync")

    # Keep the process (and the asyncio scheduler) alive.
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("analytics worker stopped")
