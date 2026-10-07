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
LEASE = timedelta(minutes=int(os.getenv("AGENT_JOB_LEASE_MINUTES", "15")))
# A claim past this many attempts goes to the dead-letter state instead of running again.
MAX_JOB_ATTEMPTS = int(os.getenv("AGENT_JOB_MAX_ATTEMPTS", "3"))
DEFAULT_TENANT_MONTHLY_BUDGET_USD = Decimal(os.getenv("AGENT_TENANT_MONTHLY_BUDGET_USD", "100"))
# Platform-set daily cap for every tenant (env only: no tenant or request input can change it).
TENANT_DAILY_BUDGET_USD = Decimal(os.getenv("AGENT_TENANT_DAILY_BUDGET_USD", "10"))
# Metered LLM usage (llm_calls tokens) is priced at this conservative flat rate, so spend
# that never became a job (chat, nested consultations, workflows) still counts.
USD_PER_1K_TOKENS = float(os.getenv("AGENT_USD_PER_1K_TOKENS", "0.01"))


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
        "model_calls": (row.checkpoint or {}).get("model_calls", []),
        "jev_usage": {"tokens": (row.checkpoint or {}).get("jev_tokens", 0),
                      "reported_cost_usd": (row.checkpoint or {}).get("jev_cost_usd") if (row.checkpoint or {}).get("jev_cost_complete", True) else None,
                      "cost_reported": (row.checkpoint or {}).get("jev_cost_complete", True)},
        "context_used": (row.checkpoint or {}).get("context_used", {}),
        "parent_job_id": (row.checkpoint or {}).get("parent_job_id"),
        "result": row.result, "error": row.error,
        "reviewed_by": str(row.reviewed_by) if row.reviewed_by else None,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def job_summary(row: AgentJob, parent_job_id: str | None = None) -> dict:
    """List view: no result, iteration history or checkpoint payloads."""
    return {
        "id": str(row.id), "agent_type": row.agent_type,
        "employee_id": str(row.employee_id) if row.employee_id else None,
        "objective": (row.objective or "")[:200], "status": row.status,
        "goal_label": row.goal_label,
        "max_cost_usd": float(row.max_cost_usd),
        "estimated_cost_usd": float(row.estimated_cost_usd),
        "actual_cost_usd": float(row.actual_cost_usd) if row.actual_cost_usd is not None else None,
        "cost_source": row.cost_source, "total_steps": row.total_steps, "total_tokens": row.total_tokens,
        "parent_job_id": parent_job_id,
        "error": row.error,
        "reviewed_by": str(row.reviewed_by) if row.reviewed_by else None,
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


def _month_start() -> datetime:
    return datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _day_start() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


async def _metered_spend(session, tenant_id: uuid.UUID, since: datetime, agent_type: str | None = None) -> float:
    """Priced token usage from every recorded model call, job or not."""
    sql = "SELECT COALESCE(SUM(total_tokens), 0) FROM llm_calls WHERE tenant_id = :t AND created_at >= :since"
    params: dict = {"t": tenant_id, "since": since}
    if agent_type:
        sql += " AND agent_type = :a"
        params["a"] = agent_type
    try:
        async with session.begin_nested():
            tokens = (await session.execute(text(sql), params)).scalar_one()
    except Exception as exc:  # noqa: BLE001 - tracing table may not exist yet
        logger.warning("metered spend unavailable: %s", exc)
        return 0.0
    return float(tokens or 0) / 1000.0 * USD_PER_1K_TOKENS


async def spend_since(session, tenant_id: uuid.UUID, since: datetime, agent_type: str | None = None) -> float:
    """Spend is the larger of job accounting and metered usage, so neither a job
    that under-reports nor usage outside any job can slip under a cap."""
    query = select(func.coalesce(func.sum(
        func.coalesce(AgentJob.actual_cost_usd, AgentJob.estimated_cost_usd)
    ), 0)).where(
        AgentJob.tenant_id == tenant_id,
        AgentJob.created_at >= since,
    )
    if agent_type:
        query = query.where(AgentJob.agent_type == agent_type)
    jobs = float((await session.execute(query)).scalar_one() or 0)
    return max(jobs, await _metered_spend(session, tenant_id, since, agent_type))


async def monthly_spend(session, tenant_id: uuid.UUID, agent_type: str | None = None) -> float:
    return await spend_since(session, tenant_id, _month_start(), agent_type)


async def daily_spend(session, tenant_id: uuid.UUID) -> float:
    return await spend_since(session, tenant_id, _day_start())


async def tenant_cap_reason(session, tenant_id: uuid.UUID) -> str | None:
    """Why this tenant may not start more agent work right now (None = within caps)."""
    row = (await session.execute(select(AgentTenantBudget).where(
        AgentTenantBudget.tenant_id == tenant_id,
    ))).scalar_one_or_none()
    limit = tenant_budget_limit(row)
    if limit is not None and await monthly_spend(session, tenant_id) >= limit:
        return "Tenant monthly agent budget reached"
    if float(TENANT_DAILY_BUDGET_USD) > 0 and await daily_spend(session, tenant_id) >= float(TENANT_DAILY_BUDGET_USD):
        return "Tenant daily agent budget reached"
    return None


async def enforce_tenant_caps(tenant_id: uuid.UUID) -> None:
    """Gate for interactive (non-job) agent calls. 429 when a cap is hit; a database
    failure is logged and lets the call through rather than taking chat down."""
    from fastapi import HTTPException

    try:
        async with session_scope(tenant_id) as session:
            reason = await tenant_cap_reason(session, tenant_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tenant cap check skipped: %s", exc)
        return
    if reason:
        raise HTTPException(status_code=429, detail=reason)


async def recover_expired_jobs() -> None:
    """A crashed turn may have made side effects: require deliberate resume. A job
    that keeps getting stuck is dead-lettered once it has used its attempts."""
    async with session_scope() as session:
        rows = (await session.execute(select(AgentJob).where(
            AgentJob.status.in_(["running", "pause_requested"]),
            AgentJob.lease_expires_at < datetime.now(timezone.utc),
        ).with_for_update(skip_locked=True))).scalars().all()
        for row in rows:
            attempts = int((row.checkpoint or {}).get("attempts", 0))
            if attempts >= MAX_JOB_ATTEMPTS:
                row.status = "dead_letter"
                row.error = f"Stopped after {attempts} attempts without finishing; needs an operator."
                row.finished_at = datetime.now(timezone.utc)
            else:
                row.status = "interrupted"
                row.error = "Worker stopped before the run finished. Review the checkpoint before resuming."
            row.lease_owner, row.lease_expires_at = None, None


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
            attempts = int((row.checkpoint or {}).get("attempts", 0)) + 1
            if attempts > MAX_JOB_ATTEMPTS:
                row.status = "dead_letter"
                row.error = f"Dead-lettered: {MAX_JOB_ATTEMPTS} attempts used. Retry it as new work."
                row.finished_at = datetime.now(timezone.utc)
                await session.flush()
                continue
            row.checkpoint = {**(row.checkpoint or {}), "attempts": attempts}  # new dict so JSONB change is saved
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
    from services.agent_orchestrator.architecture_context import component_hints, briefing
    from services.agent_orchestrator.kpi_context import approved_kpi_briefing

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
        if float(TENANT_DAILY_BUDGET_USD) > 0:
            daily_remaining = float(TENANT_DAILY_BUDGET_USD) - await daily_spend(session, tenant_id)
            if daily_remaining <= 0:
                job.status, job.error = "stopped_by_ceiling", "Tenant daily agent budget reached"
                return
            max_cost = min(max_cost, float(checkpoint.get("accumulated_cost_usd", 0)) + daily_remaining)
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
                "requested_model": registered.llm_model,
                "roster_mandate": f"You are {registered.name}, {registered.role}. Assigned scope: {registered.scope or 'Draft and analyse only'}. Do not take external actions.",
            }
            runtime_type = "assistant"
        else:
            # Unattended built-in agent runs only read and draft; a person reviews the output.
            context = {"draft_only": True}
            runtime_type = agent_type
        context["run_id"] = str(job_id)
        hints = component_hints(objective)
        context["architecture_hints"] = hints
        context["architecture_briefing"] = briefing(hints)
        if checkpoint.get("actor_id"):
            context["user_id"] = checkpoint["actor_id"]
        if registered:
            context["skill_agent_type"] = registered.agent_type
            context["memory_agent_type"] = registered.agent_type

    if employee_id:
        kpi_briefing, kpi_status = await approved_kpi_briefing(tenant_id, employee_id,
                                                               context.get("user_id"))
        context["kpi_briefing"] = kpi_briefing
        context["kpi_status"] = kpi_status

    attempts = int(checkpoint.get("attempts", 0))

    async def save_checkpoint(state: dict, iteration: dict | None) -> None:
        state = {**state, "attempts": attempts}
        pause_requested = False
        async with session_scope() as session:
            row = (await session.execute(select(AgentJob).where(
                AgentJob.id == job_id, AgentJob.tenant_id == tenant_id,
            ).with_for_update())).scalar_one()
            row.checkpoint = state
            row.estimated_cost_usd = Decimal(str(state.get("estimated_cost_usd", 0)))
            if state.get("provider_cost_complete"):
                row.actual_cost_usd = Decimal(str(float(state.get("provider_cost_usd", 0)) + float(state.get("jev_cost_usd", 0))))
                row.cost_source = "provider"
            else:
                row.actual_cost_usd = None
                row.cost_source = "estimated"
            row.total_steps = int(state.get("total_steps", 0))
            row.total_tokens = int(state.get("total_tokens", 0))
            if iteration is not None:
                row.iteration_history = [*(row.iteration_history or []), iteration]
            elif state.get("last_jev_review") and row.iteration_history:
                revised = list(row.iteration_history)
                revised[-1] = {**revised[-1], "jev_review": state["last_jev_review"]}
                row.iteration_history = revised
            row.lease_expires_at = datetime.now(timezone.utc) + LEASE
            pause_requested = row.status == "pause_requested"
        if pause_requested:
            raise PauseRequested()

    async def heartbeat() -> None:
        # Keeps the lease alive through a long model call; a dead worker stops renewing it.
        while True:
            await asyncio.sleep(LEASE.total_seconds() / 3)
            try:
                async with session_scope() as session:
                    await session.execute(update(AgentJob).where(
                        AgentJob.id == job_id, AgentJob.lease_owner == WORKER_ID,
                        AgentJob.status.in_(["running", "pause_requested"]),
                    ).values(lease_expires_at=datetime.now(timezone.utc) + LEASE))
            except Exception:  # noqa: BLE001
                logger.warning("lease heartbeat failed for job %s", job_id)

    heartbeat_task = asyncio.create_task(heartbeat())
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
            row.checkpoint = {**(result.checkpoint or {}), "attempts": attempts}
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
    finally:
        heartbeat_task.cancel()


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
