"""Operator-facing agent roster, work queue and budget endpoints."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import defer

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.agent_orchestrator.control_plane import (
    TENANT_DAILY_BUDGET_USD, daily_spend, job_dict, job_summary, monthly_spend, registered_dict, tenant_budget_limit,
    tenant_cap_reason,
)
from services.agent_orchestrator.models import AgentApproval, AgentJob, AgentTenantBudget, RegisteredAgent
from services.agent_orchestrator import memory_capture
from services.agent_orchestrator.routes.agents import _may_manage_agents

router = APIRouter(tags=["agent-work"])

RUNNABLE_BUILTINS = frozenset({"assistant", "executive", "retention", "provisioning", "support",
                              "analytics", "call_center", "products", "talent", "customer_facing"})


def require_operator(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    if not _may_manage_agents(ctx):
        raise HTTPException(status_code=403, detail="Agent manager role required")
    return ctx


class CreateJob(BaseModel):
    agent_type: str = Field(min_length=1, max_length=80)
    objective: str = Field(min_length=10, max_length=4000)
    goal_label: str | None = Field(default=None, max_length=200)
    max_cost_usd: float = Field(default=5, gt=0, le=100)
    max_iterations: int = Field(default=10, ge=1, le=25)
    max_steps: int = Field(default=10, ge=1, le=10)


class ReviseJob(BaseModel):
    objective: str = Field(min_length=10, max_length=4000)


class RetryJob(ReviseJob):
    max_cost_usd: float = Field(default=2, gt=0, le=100)


class BudgetUpdate(BaseModel):
    monthly_budget_usd: float = Field(ge=0, le=10000)


class TenantBudgetUpdate(BaseModel):
    monthly_budget_usd: float | None = Field(default=None, ge=0, le=100000)


@router.get("/budgets/tenant")
async def get_tenant_budget(ctx: AuthContext = Depends(require_operator)):
    async with session_scope(ctx.tenant_id) as session:
        row = (await session.execute(select(AgentTenantBudget).where(
            AgentTenantBudget.tenant_id == ctx.tenant_id,
        ))).scalar_one_or_none()
        return {"monthly_budget_usd": tenant_budget_limit(row),
                "daily_budget_usd": float(TENANT_DAILY_BUDGET_USD),
                "month_spend_usd": await monthly_spend(session, ctx.tenant_id),
                "day_spend_usd": await daily_spend(session, ctx.tenant_id)}


@router.put("/budgets/tenant")
async def set_tenant_budget(body: TenantBudgetUpdate, ctx: AuthContext = Depends(require_operator)):
    # The cap protects the platform spend, so the tenant it limits cannot change it.
    if not ctx.is_platform_admin:
        raise HTTPException(status_code=403, detail="Tenant budgets are set by the platform")
    async with session_scope(ctx.tenant_id) as session:
        row = (await session.execute(select(AgentTenantBudget).where(
            AgentTenantBudget.tenant_id == ctx.tenant_id,
        ).with_for_update())).scalar_one_or_none()
        if row is None:
            row = AgentTenantBudget(tenant_id=ctx.tenant_id)
            session.add(row)
        row.monthly_budget_usd = Decimal(str(body.monthly_budget_usd)) if body.monthly_budget_usd is not None else None
        await session.flush()
        return {"monthly_budget_usd": float(row.monthly_budget_usd) if row.monthly_budget_usd is not None else None,
                "month_spend_usd": await monthly_spend(session, ctx.tenant_id)}


@router.get("/registered")
async def list_registered(ctx: AuthContext = Depends(require_operator)):
    async with session_scope(ctx.tenant_id) as session:
        rows = (await session.execute(select(RegisteredAgent).where(
            RegisteredAgent.tenant_id == ctx.tenant_id,
        ).order_by(RegisteredAgent.name))).scalars().all()
        result = []
        for row in rows:
            item = registered_dict(row)
            item["month_spend_usd"] = await monthly_spend(session, ctx.tenant_id, row.agent_type)
            result.append(item)
        return result


@router.put("/registered/{employee_id}/budget")
async def set_agent_budget(employee_id: uuid.UUID, body: BudgetUpdate,
                           ctx: AuthContext = Depends(require_operator)):
    async with session_scope(ctx.tenant_id) as session:
        row = (await session.execute(select(RegisteredAgent).where(
            RegisteredAgent.tenant_id == ctx.tenant_id,
            RegisteredAgent.employee_id == employee_id,
        ).with_for_update())).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Registered agent not found")
        row.monthly_budget_usd = Decimal(str(body.monthly_budget_usd))
        await session.flush()
        result = registered_dict(row)
        result["month_spend_usd"] = await monthly_spend(session, ctx.tenant_id, row.agent_type)
        return result


@router.get("/registered/{employee_id}/readiness")
async def agent_readiness(employee_id: uuid.UUID, ctx: AuthContext = Depends(require_operator)):
    """Read-only preflight: disclose missing context before an expensive run."""
    from services.agent_orchestrator.agents import Agent
    from services.agent_orchestrator import memory_context, skills_runtime
    from services.agent_orchestrator.kpi_context import approved_kpi_briefing

    async with session_scope(ctx.tenant_id) as session:
        row = (await session.execute(select(RegisteredAgent).where(
            RegisteredAgent.tenant_id == ctx.tenant_id,
            RegisteredAgent.employee_id == employee_id,
        ))).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Registered agent not found")
        agent_type, scope, model, role = row.agent_type, row.scope, row.llm_model, row.role

    diagnostics: dict = {}
    await memory_context.recall_block(str(ctx.tenant_id), agent_type, scope or role,
                                      actor_id=str(ctx.user_id), diagnostics=diagnostics)
    skills = await skills_runtime.skills_for(str(ctx.tenant_id), agent_type, actor_id=str(ctx.user_id))
    _, kpi_status = await approved_kpi_briefing(ctx.tenant_id, employee_id, str(ctx.user_id))
    tools = [tool.name for tool in Agent("assistant").tools if not tool.mutates]
    return {"agent_type": agent_type, "memory_status": diagnostics.get("status", "unknown"),
            "memory_entries": diagnostics.get("entries", 0),
            "skills": [skill.get("skill_name") for skill in skills],
            "kpi_status": kpi_status, "scope_configured": bool(scope and scope.strip()),
            "requested_model": model, "read_only_tools": tools,
            "guardrails": ["draft_only", "read_only_tools", "human_approval_for_actions", "monthly_budget"]}


@router.post("/jobs", status_code=201)
async def create_job(body: CreateJob, ctx: AuthContext = Depends(require_operator)):
    async with session_scope(ctx.tenant_id) as session:
        tenant_budget = (await session.execute(select(AgentTenantBudget).where(
            AgentTenantBudget.tenant_id == ctx.tenant_id,
        ))).scalar_one_or_none()
        reason = await tenant_cap_reason(session, ctx.tenant_id)
        if reason:
            raise HTTPException(status_code=409, detail=reason)
        employee_id = None
        if body.agent_type not in RUNNABLE_BUILTINS:
            row = (await session.execute(select(RegisteredAgent).where(
                RegisteredAgent.tenant_id == ctx.tenant_id,
                RegisteredAgent.agent_type == body.agent_type,
                RegisteredAgent.status == "registered",
            ))).scalar_one_or_none()
            if row is None:
                raise HTTPException(status_code=404, detail="Agent is not registered for this tenant")
            spent = await monthly_spend(session, ctx.tenant_id, row.agent_type)
            if spent >= float(row.monthly_budget_usd):
                raise HTTPException(status_code=409, detail="Monthly agent budget reached")
            employee_id = row.employee_id
        job = AgentJob(
            tenant_id=ctx.tenant_id, agent_type=body.agent_type, employee_id=employee_id,
            objective=body.objective.strip(), goal_label=body.goal_label,
            max_cost_usd=Decimal(str(body.max_cost_usd)), max_iterations=body.max_iterations,
            max_steps=body.max_steps, status="queued",
            checkpoint={"actor_id": str(ctx.user_id)},
        )
        session.add(job)
        await session.flush()
        return job_dict(job)


@router.get("/jobs")
async def list_jobs(ctx: AuthContext = Depends(require_operator)):
    async with session_scope(ctx.tenant_id) as session:
        # Summaries only: the heavy columns (checkpoint, result, history) are not even read.
        rows = (await session.execute(
            select(AgentJob, AgentJob.checkpoint["parent_job_id"].astext)
            .options(defer(AgentJob.checkpoint), defer(AgentJob.result), defer(AgentJob.iteration_history))
            .where(AgentJob.tenant_id == ctx.tenant_id)
            .order_by(AgentJob.created_at.desc(), AgentJob.id.desc()).limit(100))).all()
        return [job_summary(row, parent) for row, parent in rows]


@router.get("/jobs/{job_id}")
async def get_job(job_id: uuid.UUID, ctx: AuthContext = Depends(require_operator)):
    async with session_scope(ctx.tenant_id) as session:
        row = (await session.execute(select(AgentJob).where(
            AgentJob.id == job_id, AgentJob.tenant_id == ctx.tenant_id,
        ))).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job_dict(row)


@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: uuid.UUID, ctx: AuthContext = Depends(require_operator)):
    async with session_scope(ctx.tenant_id) as session:
        row = (await session.execute(select(AgentJob).where(
            AgentJob.id == job_id, AgentJob.tenant_id == ctx.tenant_id,
        ).with_for_update())).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if row.status == "queued":
            row.status = "paused"
        elif row.status == "running":
            row.status = "pause_requested"
        else:
            raise HTTPException(status_code=409, detail="Only queued or running jobs can be paused")
        return job_dict(row)


@router.patch("/jobs/{job_id}")
async def revise_queued_job(job_id: uuid.UUID, body: ReviseJob,
                            ctx: AuthContext = Depends(require_operator)):
    """Edit an objective only before the worker has made a model call."""
    async with session_scope(ctx.tenant_id) as session:
        row = (await session.execute(select(AgentJob).where(
            AgentJob.id == job_id, AgentJob.tenant_id == ctx.tenant_id,
        ).with_for_update())).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if row.status not in {"queued", "paused"} or row.total_tokens or row.iteration_history:
            raise HTTPException(status_code=409, detail="A started run cannot be edited; retry it as new work")
        row.objective = body.objective.strip()
        return job_dict(row)


@router.post("/jobs/{job_id}/retry", status_code=201)
async def retry_job(job_id: uuid.UUID, body: RetryJob,
                    ctx: AuthContext = Depends(require_operator)):
    """Create a bounded new run. Never replay a tool call from the old checkpoint."""
    async with session_scope(ctx.tenant_id) as session:
        prior = (await session.execute(select(AgentJob).where(
            AgentJob.id == job_id, AgentJob.tenant_id == ctx.tenant_id,
        ).with_for_update())).scalar_one_or_none()
        if prior is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if prior.status not in {"awaiting_review", "max_iterations", "failed", "stopped_by_ceiling", "completed", "dead_letter"}:
            raise HTTPException(status_code=409, detail="This run is still active; pause or finish it first")
        if prior.employee_id:
            registered = (await session.execute(select(RegisteredAgent).where(
                RegisteredAgent.tenant_id == ctx.tenant_id,
                RegisteredAgent.employee_id == prior.employee_id,
                RegisteredAgent.status == "registered",
            ))).scalar_one_or_none()
            if registered is None:
                raise HTTPException(status_code=409, detail="Agent is no longer registered")
            if await monthly_spend(session, ctx.tenant_id, prior.agent_type) >= float(registered.monthly_budget_usd):
                raise HTTPException(status_code=409, detail="Monthly agent budget reached")
        reason = await tenant_cap_reason(session, ctx.tenant_id)
        if reason:
            raise HTTPException(status_code=409, detail=reason)
        new_job = AgentJob(
            tenant_id=ctx.tenant_id, agent_type=prior.agent_type, employee_id=prior.employee_id,
            objective=body.objective.strip(), goal_label=prior.goal_label,
            max_cost_usd=Decimal(str(body.max_cost_usd)), max_iterations=min(prior.max_iterations, 3),
            max_steps=min(prior.max_steps, 5), status="queued",
            checkpoint={"parent_job_id": str(prior.id), "actor_id": str(ctx.user_id)},
        )
        session.add(new_job)
        await session.flush()
        return job_dict(new_job)


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: uuid.UUID, ctx: AuthContext = Depends(require_operator)):
    async with session_scope(ctx.tenant_id) as session:
        row = (await session.execute(select(AgentJob).where(
            AgentJob.id == job_id, AgentJob.tenant_id == ctx.tenant_id,
        ).with_for_update())).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if row.status not in {"paused", "interrupted", "failed", "awaiting_hitl"}:
            raise HTTPException(status_code=409, detail="Job cannot be resumed from this state")
        if row.status == "awaiting_hitl":
            pending = (await session.execute(select(AgentApproval.id).where(
                AgentApproval.tenant_id == ctx.tenant_id,
                AgentApproval.run_id == job_id,
                AgentApproval.status == "pending",
            ).limit(1))).first()
            if pending:
                raise HTTPException(status_code=409, detail="Decide the pending approval before resuming")
        row.status, row.error, row.finished_at = "queued", None, None
        row.lease_owner, row.lease_expires_at = None, None
        return job_dict(row)


@router.post("/jobs/{job_id}/accept")
async def accept_job_output(job_id: uuid.UUID, ctx: AuthContext = Depends(require_operator)):
    """A human verifies the output before the task is marked complete."""
    async with session_scope(ctx.tenant_id) as session:
        row = (await session.execute(select(AgentJob).where(
            AgentJob.id == job_id, AgentJob.tenant_id == ctx.tenant_id,
        ).with_for_update())).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if row.status not in {"awaiting_review", "max_iterations"}:
            raise HTTPException(status_code=409, detail="This job has no output awaiting review")
        row.status = "completed"
        row.reviewed_by = ctx.user_id
        row.reviewed_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        output = (row.result or {}).get("final_output") or (row.checkpoint or {}).get("last_output") or ""
        if output.strip():
            await memory_capture.request_in(session, ctx.tenant_id, {
                "source_type": "agent_job", "source_id": str(row.id),
                "module": row.agent_type, "title": f"Reviewed agent work: {row.goal_label or row.objective[:80]}",
                "content": output[:1500], "summary": output[:400], "importance": "normal",
                "tags": ["agent_job", row.agent_type, "human_reviewed"],
                "metadata": {"job_id": str(row.id), "reviewed_by": str(ctx.user_id)},
            }, key=f"accepted-job:{row.id}")
        return job_dict(row)
