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
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(..., min_length=1)
    source_agent_type: str = Field(..., min_length=1, max_length=80)
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


class StrategyEntryRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=240)
    content: str = Field(..., min_length=10, max_length=8000)
    agent_type: Optional[str] = Field(default=None, max_length=80)


def require_skill_admin(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    roles = {role.lower() for role in ctx.roles}
    permissions = {permission.lower() for permission in ctx.permissions}
    if not (ctx.is_platform_admin or roles & {"admin", "org_admin", "tenant_admin", "owner"}
            or "agents.manage" in permissions):
        raise HTTPException(status_code=403, detail="Agent admin role required")
    return ctx


def skill_forward_headers(ctx: AuthContext) -> Dict[str, str]:
    roles = set(ctx.roles)
    if ctx.is_platform_admin:
        roles.add("platform_admin")
    return {
        "X-Tenant-Id": str(ctx.tenant_id),
        "X-User-Id": str(ctx.user_id or ctx.tenant_id),
        "X-Roles": ",".join(sorted(roles)),
        "X-Permissions": ",".join(ctx.permissions),
    }


@router.post("/strategy", status_code=status.HTTP_201_CREATED)
async def create_strategy_entry(
    payload: StrategyEntryRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Publish an operator-authored strategy note for tenant agent briefings."""
    roles = {role.lower() for role in ctx.roles}
    permissions = {permission.lower() for permission in ctx.permissions}
    if not (ctx.is_platform_admin or roles & {"admin", "org_admin", "tenant_admin", "owner"}
            or "agents.manage" in permissions):
        raise HTTPException(status_code=403, detail="Agent admin role required")
    headers = {"X-Tenant-Id": str(ctx.tenant_id), "X-User-Id": str(ctx.user_id or ctx.tenant_id)}
    body = {
        "source_type": "operator_strategy",
        "module": "strategy",
        "scope_key": f"agent:{payload.agent_type}" if payload.agent_type else "tenant:strategy",
        "title": payload.title.strip(),
        "content": payload.content.strip(),
        "summary": payload.content.strip()[:1000],
        "visibility": "tenant",
        "importance": "high",
        "tags": ["strategy", "operator_approved"],
        "metadata": {"approved_by": str(ctx.user_id or ctx.tenant_id)},
    }
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(f"{MEMORY_URL}/api/v1/memories", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        logger.error("Strategy memory write failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Memory service unavailable") from exc


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
    session: AsyncSession = Depends(get_async_session),
):
    """Return the last housekeeping execution report and retention settings."""
    last = await get_last_run(session, str(ctx.tenant_id))
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
        raise HTTPException(status_code=503, detail="Memory service unavailable") from exc


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
        raise HTTPException(status_code=503, detail="Memory service unavailable") from exc


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
        logger.warning("List skills error: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Skill service unavailable") from exc


@router.post("/skills", status_code=status.HTTP_201_CREATED)
async def create_skill(
    payload: SkillCreateRequest,
    ctx: AuthContext = Depends(require_skill_admin),
):
    """Register a new OKF skill for this tenant."""
    headers = skill_forward_headers(ctx)
    body = {
        "skill_name": payload.name,
        "description": payload.description,
        "source_agent_type": payload.source_agent_type,
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
    ctx: AuthContext = Depends(require_skill_admin),
):
    """Deactivate an OKF skill so agents stop loading it."""
    headers = skill_forward_headers(ctx)
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
    ctx: AuthContext = Depends(require_skill_admin),
):
    """Transfer or assign an OKF skill to another agent type."""
    headers = skill_forward_headers(ctx)
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
