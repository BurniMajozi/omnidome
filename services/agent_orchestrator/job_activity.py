"""Persist public step summaries, never hidden reasoning or tool arguments."""
import asyncio
import logging
from sqlalchemy import select
from services.common.db import session_scope
from services.agent_orchestrator.models import AgentJobActivity
logger = logging.getLogger(__name__)

async def capture_activity(job_id, tenant, tracker):
    items, status = {}, "Starting"
    while True:
        try:
            event = await asyncio.wait_for(tracker.queue.get(), timeout=10)
        except TimeoutError:
            tracker.heartbeat()
            continue
        if event is None:
            return
        if event["name"] == "omnidome.step":
            value = event["value"]
            items[value["id"]] = {k: value.get(k) for k in (
                "id", "kind", "title", "status", "started_at", "ended_at", "duration_ms", "result_summary")}
            items = dict(list(items.items())[-60:])
        elif event["name"] == "omnidome.status":
            status = event["value"].get("text", status)[:300]
        else:
            continue
        try:
            async with session_scope() as session:
                row = (await session.execute(select(AgentJobActivity).where(
                    AgentJobActivity.job_id == job_id, AgentJobActivity.tenant_id == tenant))).scalar_one_or_none()
                if row is None:
                    row = AgentJobActivity(job_id=job_id, tenant_id=tenant)
                    session.add(row)
                row.items, row.status_text = dict(items), status
        except Exception:
            logger.warning("Public activity could not be persisted for job %s", job_id)
