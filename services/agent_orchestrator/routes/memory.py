"""Memory management & OKF skills routes (SPEC-orchestrator-memory-hardening.md, M1-M5).

Provides endpoints for:
- Memory housekeeping (dry-run, execution, status)
- Memory search & recall per module/scope
- Memory entry archiving
- OKF skills management (list, register, deactivate, transfer)
- Conversation compaction stats
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
import httpx
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from services.agent_orchestrator.conversation.models import AgentConversation
from services.agent_orchestrator.memory_housekeeping import (
    LOW_IMPORTANCE_DAYS,
    ROLLUP_DAYS,
    get_last_run,
    run_tenant_housekeeping,
)
from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter()

MEMORY_URL = os.getenv("TENANT_MEMORY_SERVICE_URL", "http://tenant_memory:8025").rstrip("/")


class SkillCreateRequest(BaseModel):
    name: str
    description: str
    target_agent_types: List[str] = Field(default_factory=list)
    guidance_prompt: str
    tools_required: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SkillTransferRequest(BaseModel):
    target_agent_type: str


class MemoryEntryUpdateRequest(BaseModel):
    archived: Optional[bool] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    importance: Optional[str] = None


# ── Housekeeping (M5) ────────────────────────────────────────────────────────

@router.post("/housekeeping/dry-run")
async def housekeeping_dry_run(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    """Preview what memory housekeeping would archive, merge, and roll up without modifying records."""
    return await run_tenant_housekeeping(session, ctx.tenant_id, dry_run=True)


@router.post("/housekeeping/run")
async def housekeeping_run(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    """Execute memory housekeeping: merge exact duplicates, archive stale low-importance items,
    and roll entries older than 30 days into summaries."""
    return await run_tenant_housekeeping(session, ctx.tenant_id, dry_run=False)


@router.get("/housekeeping/status")
async def housekeeping_status(
    ctx: AuthContext = Depends(get_auth_context),
):
    """Return the last housekeeping execution report and retention settings."""
    last = get_last_run(str(ctx.tenant_id))
    return {
        "tenant_id": str(ctx.tenant_id),
        "config": {
            "rollup_days": ROLLUP_DAYS,
            "low_importance_retention_days": LOW_IMPORTANCE_DAYS,
        },
        "last_run": last,
    }


# ── Memory Recall & Search (M1, M3) ──────────────────────────────────────────

@router.get("/recall")
async def memory_recall(
    q: Optional[str] = Query(None, min_length=2),
    module: Optional[str] = Query(None),
    scope_key: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Search tenant memories and summaries using ranked full-text search."""
    headers = {"X-Tenant-Id": str(ctx.tenant_id), "X-User-Id": str(ctx.user_id or ctx.tenant_id)}
    params = {"limit": limit, "match": "any"}
    if q:
        params["q"] = q
    if module:
        params["module"] = module
    if scope_key:
        params["scope_key"] = scope_key

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{MEMORY_URL}/api/v1/recall", headers=headers, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("Memory recall proxy error: %s", exc)
        return {"summaries": [], "entries": []}


@router.get("/entries")
async def list_entries(
    module: Optional[str] = Query(None),
    scope_key: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    include_archived: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    ctx: AuthContext = Depends(get_auth_context),
):
    """List operational memory entries for the tenant."""
    headers = {"X-Tenant-Id": str(ctx.tenant_id), "X-User-Id": str(ctx.user_id or ctx.tenant_id)}
    params = {"include_archived": include_archived, "limit": limit}
    if module:
        params["module"] = module
    if scope_key:
        params["scope_key"] = scope_key
    if source_type:
        params["source_type"] = source_type

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{MEMORY_URL}/api/v1/memories", headers=headers, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("List entries proxy error: %s", exc)
        return {"items": [], "limit": limit}


@router.patch("/entries/{entry_id}")
async def update_entry(
    entry_id: uuid.UUID,
    payload: MemoryEntryUpdateRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Archive or update a memory entry."""
    headers = {"X-Tenant-Id": str(ctx.tenant_id), "X-User-Id": str(ctx.user_id or ctx.tenant_id)}
    body = payload.model_dump(exclude_unset=True)

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.patch(f"{MEMORY_URL}/api/v1/memories/{entry_id}", headers=headers, json=body)
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Memory entry not found")
            resp.raise_for_status()
            return resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Update entry error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Memory service error: {exc}")


# ── OKF Skills (M2) ─────────────────────────────────────────────────────────

@router.get("/skills")
async def list_skills(
    agent_type: Optional[str] = Query(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    """List active OKF skills for this tenant, optionally filtered by agent type."""
    headers = {"X-Tenant-Id": str(ctx.tenant_id), "X-User-Id": str(ctx.user_id or ctx.tenant_id)}
    params = {}
    if agent_type:
        params["target_agent_type"] = agent_type

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{MEMORY_URL}/api/v1/skills", headers=headers, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("List skills error: %s", exc)
        return {"items": []}


@router.post("/skills", status_code=status.HTTP_201_CREATED)
async def create_skill(
    payload: SkillCreateRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Register a new OKF skill for this tenant."""
    headers = {"X-Tenant-Id": str(ctx.tenant_id), "X-User-Id": str(ctx.user_id or ctx.tenant_id)}
    body = {
        "skill_name": payload.name,
        "description": payload.description,
        "target_agent_types": payload.target_agent_types,
        "guidance_prompt": payload.guidance_prompt,
        "tools_required": payload.tools_required,
        "metadata": payload.metadata,
    }

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(f"{MEMORY_URL}/api/v1/skills", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.error("Create skill error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Memory service error: {exc}")


@router.post("/skills/{skill_id}/deactivate")
async def deactivate_skill(
    skill_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Deactivate an OKF skill so agents stop loading it."""
    headers = {"X-Tenant-Id": str(ctx.tenant_id), "X-User-Id": str(ctx.user_id or ctx.tenant_id)}
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(f"{MEMORY_URL}/api/v1/skills/{skill_id}/deactivate", headers=headers)
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Skill not found")
            resp.raise_for_status()
            return resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Deactivate skill error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Memory service error: {exc}")


@router.post("/skills/{skill_id}/transfer")
async def transfer_skill(
    skill_id: uuid.UUID,
    payload: SkillTransferRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Transfer or assign an OKF skill to another agent type."""
    headers = {"X-Tenant-Id": str(ctx.tenant_id), "X-User-Id": str(ctx.user_id or ctx.tenant_id)}
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(
                f"{MEMORY_URL}/api/v1/skills/{skill_id}/transfer",
                headers=headers,
                json={"target_agent_type": payload.target_agent_type},
            )
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Skill not found")
            resp.raise_for_status()
            return resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Transfer skill error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Memory service error: {exc}")


# ── Compaction Stats (M4) ───────────────────────────────────────────────────

@router.get("/compaction/stats")
async def compaction_stats(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    """Count of conversations that underwent context compaction and summary metrics."""
    result = await session.execute(
        select(AgentConversation).where(
            AgentConversation.tenant_id == ctx.tenant_id,
            text("context ? 'summary'"),
        )
    )
    compacted_convs = result.scalars().all()
    total_times = sum(
        int(((c.context or {}).get("compaction") or {}).get("times") or 1)
        for c in compacted_convs
    )

    return {
        "tenant_id": str(ctx.tenant_id),
        "compacted_conversations_count": len(compacted_convs),
        "total_compaction_runs": total_times,
    }
