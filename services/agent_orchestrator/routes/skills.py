"""Skills management proxy (docs/skills.md): the web panel talks to the orchestrator, which forwards to tenant memory with a
signed identity. Create/list/transfer/deactivate stay in routes/memory.py; everything else lives here.

Also serves the LIVE tool registry for the skill editor's tool picker (what an agent can really call).
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger(__name__)
router = APIRouter()

MEMORY_URL = os.getenv("TENANT_MEMORY_SERVICE_URL", "http://tenant_memory:8025").rstrip("/")


def forward_roles(ctx: AuthContext) -> List[str]:
    roles = set(ctx.roles)
    if ctx.is_platform_admin:
        roles.add("platform_admin")
    if "agents.manage" in {p.lower() for p in ctx.permissions}:
        roles.add("tenant_admin")          # permission-based admins are admins to the memory service too
    return sorted(roles)


def signed_headers(method: str, path: str, ctx: AuthContext) -> Dict[str, str]:
    from services.agent_orchestrator.tools import signed_service_headers
    return signed_service_headers(method, f"{MEMORY_URL}{path}", str(ctx.tenant_id), str(ctx.user_id or ctx.tenant_id),
                                  forward_roles(ctx))


async def forward(method: str, path: str, ctx: AuthContext, *, params: Optional[dict] = None, body: Optional[Any] = None,
                  timeout: float = 8.0) -> Any:
    """Call tenant memory; relay its status and message (so a 403/404/409/422 reaches the panel intact)."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, f"{MEMORY_URL}{path}", params=params, json=body,
                                        headers=signed_headers(method, path, ctx))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Skills service error: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Skill service unavailable") from exc
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text[:300])
        except Exception:  # noqa: BLE001
            detail = resp.text[:300]
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return resp.json()


def live_tools() -> List[dict]:
    """Every registered tool with its policy: the picker shows exactly what exists."""
    from services.agent_orchestrator.tools import policy_for, tool_registry
    out = []
    for t in sorted(tool_registry.list_tools(), key=lambda t: t.name):
        p = policy_for(t.name)
        out.append({"name": t.name, "description": (t.description or "")[:200], "mutates": p.mutates,
                    "requires_approval": p.requires_approval, "soft": False})
    return out


@router.get("/skills/meta")
async def skills_meta(ctx: AuthContext = Depends(get_auth_context)):
    meta = await forward("GET", "/api/v1/skills/meta", ctx)
    try:
        live = live_tools()
        known = {t["name"] for t in live}
        meta["tools"] = live + [t for t in meta.get("tools", []) if t.get("soft") and t["name"] not in known]
        meta["tools_source"] = "registry"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Live tool registry unavailable for skills: %s", exc)
        meta["tools_source"] = "snapshot"
    return meta


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    return await forward("GET", f"/api/v1/skills/{skill_id}", ctx)


@router.get("/skills/{skill_id}/versions")
async def skill_versions(skill_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    return await forward("GET", f"/api/v1/skills/{skill_id}/versions", ctx)


@router.get("/skills/{skill_id}/export")
async def export_skill(skill_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    return await forward("GET", f"/api/v1/skills/{skill_id}/export", ctx)


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: uuid.UUID, request: Request, ctx: AuthContext = Depends(get_auth_context)):
    return await forward("PUT", f"/api/v1/skills/{skill_id}", ctx, body=await request.json())


@router.post("/skills/import/preview")
async def import_preview(request: Request, ctx: AuthContext = Depends(get_auth_context)):
    return await forward("POST", "/api/v1/skills/import/preview", ctx, body=await request.json())


@router.post("/skills/import", status_code=201)
async def import_skill(request: Request, ctx: AuthContext = Depends(get_auth_context)):
    return await forward("POST", "/api/v1/skills/import", ctx, body=await request.json())


@router.post("/skills/{skill_id}/activate")
async def activate_skill(skill_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    return await forward("POST", f"/api/v1/skills/{skill_id}/activate", ctx)


@router.post("/skills/{skill_id}/deprecate")
async def deprecate_skill(skill_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    return await forward("POST", f"/api/v1/skills/{skill_id}/deprecate", ctx)


@router.post("/skills/{skill_id}/fork", status_code=201)
async def fork_skill(skill_id: uuid.UUID, request: Request, ctx: AuthContext = Depends(get_auth_context)):
    return await forward("POST", f"/api/v1/skills/{skill_id}/fork", ctx, body=await request.json())


@router.post("/skills/{skill_id}/share")
async def share_skill(skill_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    return await forward("POST", f"/api/v1/skills/{skill_id}/share", ctx)


@router.post("/skills/{skill_id}/feedback")
async def skill_feedback(skill_id: uuid.UUID, request: Request, ctx: AuthContext = Depends(get_auth_context)):
    return await forward("POST", f"/api/v1/skills/{skill_id}/feedback", ctx, body=await request.json())
