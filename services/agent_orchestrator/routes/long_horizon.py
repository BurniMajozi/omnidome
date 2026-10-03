"""Compatibility paths for long-horizon work, backed by durable agent jobs."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from services.common.auth import AuthContext
from services.agent_orchestrator.routes.jobs import CreateJob, create_job, require_operator, resume_job

router = APIRouter(prefix="/long-horizon", tags=["long-horizon"])


class LongHorizonRunRequest(BaseModel):
    prompt: str = Field(min_length=10, max_length=4000)
    agent_type: str = "assistant"
    conversation_id: Optional[uuid.UUID] = None
    max_cost_usd: float = Field(default=5, gt=0, le=100)
    max_iterations: int = Field(default=10, ge=1, le=25)
    max_steps_per_iteration: int = Field(default=10, ge=1, le=10)
    webhook_url: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class LongHorizonResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: uuid.UUID


@router.post("/run", status_code=201)
async def start_long_horizon_job(body: LongHorizonRunRequest,
                                 ctx: AuthContext = Depends(require_operator)):
    """Queue work; the worker persists each checkpoint and the operator polls /jobs/{id}."""
    if body.webhook_url:
        raise HTTPException(status_code=422, detail="Arbitrary completion webhooks are disabled; poll the job endpoint")
    if body.conversation_id or body.context:
        raise HTTPException(status_code=422, detail="Conversation and custom context are not supported by durable jobs")
    return await create_job(CreateJob(
        agent_type=body.agent_type, objective=body.prompt,
        max_cost_usd=body.max_cost_usd, max_iterations=body.max_iterations,
        max_steps=body.max_steps_per_iteration,
    ), ctx)


@router.post("/resume")
async def resume_long_horizon_job(body: LongHorizonResumeRequest,
                                  ctx: AuthContext = Depends(require_operator)):
    """Only server-held, tenant-scoped checkpoints may be resumed."""
    return await resume_job(body.job_id, ctx)
