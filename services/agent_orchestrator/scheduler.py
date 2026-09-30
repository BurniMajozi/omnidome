"""Cron scheduler for workflows.

Runs in the orchestrator process. Because the service runs multiple uvicorn
workers, each tick grabs a Postgres transaction-level advisory lock — only the
worker that wins the lock processes due workflows that tick, so scheduled runs
fire exactly once. Due workflows are *claimed* (next_run_at advanced) inside the
lock, then executed after the lock releases so LLM work doesn't hold it.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, text

from services.common.db import session_scope
from services.agent_orchestrator.models import Workflow
from services.agent_orchestrator.workflow_engine import run_workflow

logger = logging.getLogger(__name__)

LOCK_KEY = 918273645  # arbitrary constant shared by all workers
HOUSEKEEPING_LOCK_KEY = 918273646
TICK_SECONDS = 60
SYSTEM_USER = "00000000-0000-0000-0000-000000000000"
_last_housekeeping_date = None


def _next_run(cron_expr: str, base: datetime) -> datetime:
    from croniter import croniter

    return croniter(cron_expr, base).get_next(datetime)


async def _tick_housekeeping(now: datetime) -> None:
    """Nightly memory housekeeping (spec M5): roll old memories into summaries,
    archive duplicates and low-importance entries."""
    global _last_housekeeping_date
    if _last_housekeeping_date == now.date() or now.hour < 2:
        return
    async with session_scope() as s:
        got = (await s.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": HOUSEKEEPING_LOCK_KEY})).scalar()
        if not got:
            return
        from services.agent_orchestrator import memory_housekeeping
        # The scheduler can tick before startup's background schema step has
        # run; the tables are idempotent, and the lock serialises the DDL.
        await memory_housekeeping.ensure_schema(s)
        # The night is claimed in Postgres, so another worker (or this one after
        # a restart) that gets the lock later tonight finds it taken.
        if not await memory_housekeeping.claim_nightly(s, now.date()):
            _last_housekeeping_date = now.date()
            return
        _last_housekeeping_date = now.date()
        logger.info("Starting nightly memory housekeeping")
        try:
            res = await s.execute(text("SELECT DISTINCT tenant_id FROM tenant_memory_entries WHERE archived_at IS NULL"))
            tenants = res.scalars().all()
            for t_id in tenants:
                await memory_housekeeping.run_tenant_housekeeping(s, t_id, dry_run=False, now=now, trigger="nightly")
            await memory_housekeeping.finish_nightly(s, now.date())
            logger.info("Nightly memory housekeeping completed for %d tenants", len(tenants))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Nightly memory housekeeping failed: %s", exc)


async def _tick() -> None:
    now = datetime.now(timezone.utc)
    claimed: list[tuple] = []
    async with session_scope() as s:
        got = (await s.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": LOCK_KEY})).scalar()
        if not got:
            return  # another worker owns the scheduler this tick
        due = (
            await s.execute(
                select(Workflow).where(
                    Workflow.schedule_enabled.is_(True),
                    Workflow.next_run_at.is_not(None),
                    Workflow.next_run_at <= now,
                )
            )
        ).scalars().all()
        for wf in due:
            claimed.append((wf.id, str(wf.tenant_id)))
            wf.last_run_at = now
            try:
                wf.next_run_at = _next_run(wf.schedule_cron, now)
            except Exception:
                logger.warning("workflow %s has an invalid cron %r; disabling", wf.id, wf.schedule_cron)
                wf.schedule_enabled = False
        await s.flush()  # commit the claim + release the xact advisory lock on exit

    # Execute claimed workflows outside the lock (next_run_at already advanced).
    for wf_id, tenant_id in claimed:
        try:
            await run_workflow(
                workflow_id=wf_id, tenant_id=tenant_id, user_id=SYSTEM_USER,
                input_data={"trigger": "schedule"}, trigger="schedule",
            )
            logger.info("scheduled workflow %s fired", wf_id)
        except Exception:
            logger.exception("scheduled workflow %s failed", wf_id)


async def scheduler_loop() -> None:
    logger.info("workflow scheduler loop started (tick=%ss)", TICK_SECONDS)
    while True:
        now = datetime.now(timezone.utc)
        try:
            await _tick()
        except Exception:
            logger.exception("scheduler tick error")
        try:
            await _tick_housekeeping(now)
        except Exception:
            logger.exception("housekeeping tick error")
        await asyncio.sleep(TICK_SECONDS)
