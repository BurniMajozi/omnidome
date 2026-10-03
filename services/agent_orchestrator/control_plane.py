"""Durable agent work queue and budget accounting.

The database owns task state. Workers claim queued jobs with row locks, save a
checkpoint after every turn, and leave interrupted work for an operator to
resume. A restart never silently replays a tool call.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select, text, update

from services.common.db import session_scope
from services.agent_orchestrator.models import AgentJob, AgentTenantBudget, RegisteredAgent

logger = logging.getLogger(__name__)
WORKER_ID = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
LEASE = timedelta(hours=1)
DEFAULT_TENANT_MONTHLY_BUDGET_USD = Decimal(os.getenv("AGENT_TENANT_MONTHLY_BUDGET_USD", "100"))


def tenant_budget_limit(row: AgentTenantBudget | None) -> float | None:
    """A missing configuration has a safe cap; an explicit null opts out."""
    if row is None:
        return float(DEFAULT_TENANT_MONTHLY_BUDGET_USD)
    return float(row.monthly_budget_usd) if row.monthly_budget_usd is not None else None


def job_dict(row: AgentJob) -> dict:
    return {
        "id": str(row.id), "agent_type": row.agent_type,
        "employee_id": str(row.employee_id) if row.employee_id else None,
        "objective": row.objective, "status": row.status,
        "goal_label": row.goal_label,
        "max_cost_usd": float(row.max_cost_usd),
        "estimated_cost_usd": float(row.estimated_cost_usd),
        "actual_cost_usd": float(row.actual_cost_usd) if row.actual_cost_usd is not None else None,
        "cost_source": row.cost_source, "max_iterations": row.max_iterations,
        "max_steps": row.max_steps, "total_steps": row.total_steps,
        "total_tokens": row.total_tokens, "iteration_history": row.iteration_history or [],
        "result": row.result, "error": row.error,
        "reviewed_by": str(row.reviewed_by) if row.reviewed_by else None,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def registered_dict(row: RegisteredAgent) -> dict:
    return {
        "id": str(row.id), "employee_id": str(row.employee_id),
        "agent_type": row.agent_type, "name": row.name, "role": row.role,
        "department": row.department, "llm_model": row.llm_model,
        "scope": row.scope, "financial_limit": float(row.financial_limit) if row.financial_limit is not None else None,
        "monthly_budget_usd": float(row.monthly_budget_usd), "status": row.status,
        "last_error": row.last_error,
    }


async def monthly_spend(session, tenant_id: uuid.UUID, agent_type: str | None = None) -> float:
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    query = select(func.coalesce(func.sum(
        func.coalesce(AgentJob.actual_cost_usd, AgentJob.estimated_cost_usd)
    ), 0)).where(
        AgentJob.tenant_id == tenant_id,
        AgentJob.created_at >= start,
    )
    if agent_type:
        query = query.where(AgentJob.agent_type == agent_type)
    value = (await session.execute(query)).scalar_one()
    return float(value or 0)


async def recover_expired_jobs() -> None:
    """A crashed turn may have made side effects: require deliberate resume."""
    async with session_scope() as session:
        await session.execute(update(AgentJob).where(
            AgentJob.status.in_(["running", "pause_requested"]),
            AgentJob.lease_expires_at < datetime.now(timezone.utc),
        ).values(status="interrupted", lease_owner=None, lease_expires_at=None,
                 error="Worker stopped before the run finished. Review the checkpoint before resuming."))


async def claim_next_job() -> uuid.UUID | None:
    async with session_scope() as session:
        # Serialize claims briefly, then keep at most one running task per
        # tenant. Concurrent agents could otherwise each pass the same
        # monthly budget check before either records its spend.
        await session.execute(text("SELECT pg_advisory_xact_lock(194749)"))
        candidates = (await session.execute(select(AgentJob).where(
            AgentJob.status == "queued",
        ).order_by(AgentJob.created_at, AgentJob.id).limit(25).with_for_update(skip_locked=True))).scalars().all()
        for row in candidates:
            already_running = (await session.execute(select(AgentJob.id).where(
                AgentJob.tenant_id == row.tenant_id,
                AgentJob.status.in_(["running", "pause_requested"]),
            ).limit(1))).first()
            if already_running:
                continue
            row.status = "running"
            row.lease_owner = WORKER_ID
            row.lease_expires_at = datetime.now(timezone.utc) + LEASE
            await session.flush()
            return row.id
        return None


class PauseRequested(Exception):
    pass


async def execute_job(job_id: uuid.UUID) -> None:
    from services.agent_orchestrator.long_horizon import run_long_horizon_agent

    async with session_scope() as session:
        job = (await session.execute(select(AgentJob).where(AgentJob.id == job_id))).scalar_one()
        tenant_id, agent_type, employee_id = job.tenant_id, job.agent_type, job.employee_id
        objective, checkpoint = job.objective, dict(job.checkpoint or {})
        max_cost, max_iterations, max_steps = float(job.max_cost_usd), job.max_iterations, job.max_steps
        tenant_budget = (await session.execute(select(AgentTenantBudget).where(
            AgentTenantBudget.tenant_id == tenant_id,
        ))).scalar_one_or_none()
        tenant_limit = tenant_budget_limit(tenant_budget)
        if tenant_limit is not None:
            tenant_remaining = tenant_limit - await monthly_spend(session, tenant_id)
            if tenant_remaining <= 0:
                job.status, job.error = "stopped_by_ceiling", "Tenant monthly agent budget reached"
                return
            max_cost = min(max_cost, float(checkpoint.get("accumulated_cost_usd", 0)) + tenant_remaining)
        registered = None
        if employee_id:
            registered = (await session.execute(select(RegisteredAgent).where(
                RegisteredAgent.tenant_id == tenant_id,
                RegisteredAgent.employee_id == employee_id,
                RegisteredAgent.status == "registered",
            ))).scalar_one_or_none()
            if registered is None:
                job.status, job.error = "failed", "Assigned agent is no longer registered"
                return
            spent = await monthly_spend(session, tenant_id, agent_type)
            remaining = float(registered.monthly_budget_usd) - spent
            if remaining <= 0:
                job.status, job.error = "stopped_by_ceiling", "Monthly agent budget reached"
                return
            max_cost = min(max_cost, float(checkpoint.get("accumulated_cost_usd", 0)) + remaining)
            context = {
                "draft_only": True,
                "roster_mandate": f"You are {registered.name}, {registered.role}. Assigned scope: {registered.scope or 'Draft and analyse only'}. Do not take external actions.",
            }
            runtime_type = "assistant"
        else:
            context = {}
            runtime_type = agent_type
        context["run_id"] = str(job_id)

    async def save_checkpoint(state: dict, iteration: dict | None) -> None:
        pause_requested = False
        async with session_scope() as session:
            row = (await session.execute(select(AgentJob).where(
                AgentJob.id == job_id, AgentJob.tenant_id == tenant_id,
            ).with_for_update())).scalar_one()
            row.checkpoint = state
            row.estimated_cost_usd = Decimal(str(state.get("estimated_cost_usd", 0)))
            if state.get("provider_cost_complete"):
                row.actual_cost_usd = Decimal(str(state.get("provider_cost_usd", 0)))
                row.cost_source = "provider"
            else:
                row.actual_cost_usd = None
                row.cost_source = "estimated"
            row.total_steps = int(state.get("total_steps", 0))
            row.total_tokens = int(state.get("total_tokens", 0))
            if iteration is not None:
                row.iteration_history = [*(row.iteration_history or []), iteration]
            row.lease_expires_at = datetime.now(timezone.utc) + LEASE
            pause_requested = row.status == "pause_requested"
        if pause_requested:
            raise PauseRequested()

    try:
        result = await run_long_horizon_agent(
            prompt=objective, agent_type=runtime_type, tenant_id=tenant_id,
            max_cost_usd=max_cost, max_iterations=max_iterations,
            max_steps_per_iteration=max_steps, context=context,
            resume_from_checkpoint=checkpoint or {"job_id": str(job_id), "conversation_id": str(uuid.uuid4()),
                                                   "iterations_completed": 0, "total_steps": 0, "total_tokens": 0,
                                                   "accumulated_cost_usd": 0, "history": []},
            checkpoint_callback=save_checkpoint,
        )
        async with session_scope() as session:
            row = (await session.execute(select(AgentJob).where(AgentJob.id == job_id).with_for_update())).scalar_one()
            row.status = "awaiting_review" if result.status == "completed" else result.status
            row.result = result.to_dict()
            row.checkpoint = result.checkpoint
            row.estimated_cost_usd = Decimal(str(result.estimated_cost_usd))
            row.actual_cost_usd = Decimal(str(result.actual_cost_usd)) if result.actual_cost_usd is not None else None
            row.cost_source = "provider" if result.actual_cost_usd is not None else "estimated"
            row.total_steps, row.total_tokens = result.total_steps, result.total_tokens
            row.lease_owner, row.lease_expires_at = None, None
            row.finished_at = datetime.now(timezone.utc)
            row.error = result.stopped_by if result.status in {"failed", "stopped_by_ceiling"} else None
    except PauseRequested:
        async with session_scope() as session:
            row = (await session.execute(select(AgentJob).where(AgentJob.id == job_id))).scalar_one()
            row.status, row.lease_owner, row.lease_expires_at = "paused", None, None
    except Exception:
        logger.exception("Agent job %s failed", job_id)
        async with session_scope() as session:
            row = (await session.execute(select(AgentJob).where(AgentJob.id == job_id))).scalar_one()
            row.status, row.error = "failed", "Run failed; review its checkpoint before resuming"
            row.lease_owner, row.lease_expires_at = None, None


async def worker_loop() -> None:
    await recover_expired_jobs()
    last_recovery = time.monotonic()
    while True:
        try:
            if time.monotonic() - last_recovery >= 30:
                await recover_expired_jobs()
                last_recovery = time.monotonic()
            job_id = await claim_next_job()
            if job_id:
                await execute_job(job_id)
            else:
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Agent job worker tick failed")
            await asyncio.sleep(10)
