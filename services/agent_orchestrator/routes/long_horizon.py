"""Long-Horizon Agent API routes (Cookbook: 'Build a Long-Horizon Agent').

Endpoints:
- POST /api/agents/long-horizon/run: Starts a self-ask, multi-iteration long-horizon job.
- POST /api/agents/long-horizon/resume: Resumes a paused/checkpointed long-horizon job.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.common.auth import AuthContext, get_auth_context
from services.agent_orchestrator.long_horizon import run_long_horizon_agent, LongHorizonJobResult

logger = logging.getLogger("agent_orchestrator.routes.long_horizon")

router = APIRouter(prefix="/long-horizon", tags=["long-horizon"])


class LongHorizonRunRequest(BaseModel):
    prompt: str = Field(..., description="The high-level, multi-hour objective or research task.")
    agent_type: str = Field("assistant", description="Specialist agent type or orchestrator.")
    conversation_id: Optional[uuid.UUID] = Field(None, description="Optional existing conversation ID.")
    max_cost_usd: float = Field(5.00, description="Hard cost ceiling in USD. Loop halts as soon as cost reaches this.")
    max_iterations: int = Field(10, description="Max self-ask review cycles.")
    max_steps_per_iteration: int = Field(25, description="Max tool steps allowed per cycle.")
    webhook_url: Optional[str] = Field(None, description="Optional webhook URL to notify upon completion.")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom contextual metadata.")


class LongHorizonResumeRequest(BaseModel):
    checkpoint: Dict[str, Any] = Field(..., description="Saved checkpoint dict to resume from.")
    webhook_url: Optional[str] = Field(None, description="Optional webhook URL to notify upon completion.")
    max_cost_usd: Optional[float] = Field(None, description="Updated max cost ceiling.")
    max_iterations: Optional[int] = Field(None, description="Updated max iterations limit.")


@router.post("/run")
async def start_long_horizon_job(
    body: LongHorizonRunRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Start an autonomous long-horizon agent run with cost ceilings, adversarial review, and resumability."""
    try:
        result: LongHorizonJobResult = await run_long_horizon_agent(
            prompt=body.prompt,
            agent_type=body.agent_type,
            tenant_id=ctx.tenant_id,
            conversation_id=body.conversation_id,
            max_cost_usd=body.max_cost_usd,
            max_iterations=body.max_iterations,
            max_steps_per_iteration=body.max_steps_per_iteration,
            webhook_url=body.webhook_url,
            context=body.context,
        )
        return result.to_dict()
    except Exception as exc:
        logger.exception("Long-horizon run failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/resume")
async def resume_long_horizon_job(
    body: LongHorizonResumeRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Resume a paused or checkpointed long-horizon run using its saved state."""
    checkpoint = body.checkpoint
    original_prompt = checkpoint.get("last_output") or "Continue previously checkpointed task."
    conv_id = checkpoint.get("conversation_id")
    conv_uuid = uuid.UUID(conv_id) if conv_id else None

    max_cost = body.max_cost_usd if body.max_cost_usd is not None else 5.00
    max_iter = body.max_iterations if body.max_iterations is not None else 10

    try:
        result = await run_long_horizon_agent(
            prompt=original_prompt,
            tenant_id=ctx.tenant_id,
            conversation_id=conv_uuid,
            max_cost_usd=max_cost,
            max_iterations=max_iter,
            webhook_url=body.webhook_url,
            resume_from_checkpoint=checkpoint,
        )
        return result.to_dict()
    except Exception as exc:
        logger.exception("Long-horizon resumption failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
