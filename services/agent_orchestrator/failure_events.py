"""Failed agent work -> the support ticket mechanism (services/support/ticket_rules.py maps these events).

`agents.run.failed`      an agent job or workflow run ended failed (one event per run id)
`agents.task.needs_human` an agent stopped and is waiting for a person (approvals already publish
                          `agents.approval.requested`, which the support rules map too)
"""
from __future__ import annotations

import logging

from services.common.event_bus import publish
from services.common.redaction import redact_text

logger = logging.getLogger(__name__)

RUN_FAILED = "agents.run.failed"
NEEDS_HUMAN = "agents.task.needs_human"


async def publish_run_failed(session, tenant_id, *, agent: str, run_id, error: str, kind: str = "agent_job") -> None:
    """Never raises: a bookkeeping failure must not change how the run itself is recorded."""
    try:
        async with session.begin_nested():
            await publish(session, tenant_id, RUN_FAILED,
                          {"agent": agent, "run_id": str(run_id), "error": redact_text(error, 300), "kind": kind},
                          source="orchestrator", subject=("agent_run", run_id), idempotency_key=f"run-failed:{run_id}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not publish %s for %s: %s", RUN_FAILED, run_id, type(exc).__name__)


async def publish_needs_human(session, tenant_id, *, agent: str, task_id, reason: str) -> None:
    try:
        async with session.begin_nested():
            await publish(session, tenant_id, NEEDS_HUMAN,
                          {"agent": agent, "task_id": str(task_id), "reason": redact_text(reason, 300)},
                          source="orchestrator", subject=("agent_task", task_id), idempotency_key=f"needs-human:{task_id}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not publish %s for %s: %s", NEEDS_HUMAN, task_id, type(exc).__name__)
