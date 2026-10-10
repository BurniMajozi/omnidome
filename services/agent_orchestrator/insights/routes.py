"""HTTP surface (mounted at /api/insights; the web proxy exposes it as /api/orchestrator/insights/...).

POST /panel                {module, scope?, refresh?}      the briefing for one panel (cache-aware)
GET  /panel?module=&scope=                                  the stored briefing, no generation
GET  /modules                                               panels this caller may open
POST /{insight_id}/feedback {verdict, rec_id?, note?}       helpful | not_helpful | dismissed | acted
Identity is the signed AuthContext; nothing in the body can name another user or tenant.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from services.agent_orchestrator.identity import is_admin
from services.agent_orchestrator.insights import config, service
from services.agent_orchestrator.insights.modules import PANELS
from services.agent_orchestrator.insights.sources import Caller, HttpSources
from services.agent_orchestrator.insights.store import StoreError
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger(__name__)
router = APIRouter()


def caller_from(ctx: AuthContext) -> Caller:
    from services.agent_orchestrator.routes.skills import forward_roles
    return Caller(tenant_id=str(ctx.tenant_id), user_id=str(ctx.user_id), roles=forward_roles(ctx),
                  modules=list(ctx.modules or []), is_admin=is_admin(ctx))


class PanelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    module: str = Field(..., min_length=2, max_length=40)
    scope: str = Field("", max_length=80)
    refresh: Union[bool, str] = False          # true = force (rate-limited); "background" = serve cache, refresh behind it


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: str = Field(..., pattern=r"^(helpful|not_helpful|dismissed|acted)$")
    rec_id: Optional[str] = Field(None, max_length=40)
    note: Optional[str] = Field(None, max_length=500)


def _guard() -> None:
    if not config.enabled():
        raise HTTPException(503, "AI insights are switched off for this deployment")


def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, service.UnknownModule):
        return HTTPException(404, {"message": str(exc), "valid": exc.valid})
    if isinstance(exc, service.AccessDenied):
        return HTTPException(403, {"message": f"You do not have access to the {exc.module} panel.", "module": exc.module,
                                   "allowed": exc.allowed})
    if isinstance(exc, service.NotFound):
        return HTTPException(404, str(exc))
    raise exc


@router.post("/panel")
async def post_panel(req: PanelRequest, ctx: AuthContext = Depends(get_auth_context)):
    _guard()
    refresh: Any = req.refresh
    if isinstance(refresh, str):
        refresh = "background" if refresh.lower() == "background" else refresh.lower() in ("true", "1", "yes")
    try:
        return await service.panel_insights(caller_from(ctx), req.module, req.scope, refresh)
    except (service.UnknownModule, service.AccessDenied) as exc:
        raise _map(exc)


@router.get("/panel")
async def get_panel(module: str = Query(..., min_length=2, max_length=40), scope: str = Query("", max_length=80),
                    ctx: AuthContext = Depends(get_auth_context)):
    _guard()
    try:
        doc = await service.cached_insights(caller_from(ctx), module, scope)
    except (service.UnknownModule, service.AccessDenied) as exc:
        raise _map(exc)
    return doc if doc is not None else {"available": False, "module": module}


@router.get("/modules")
async def get_modules(ctx: AuthContext = Depends(get_auth_context)):
    caller = caller_from(ctx)
    allowed = await service.resolve_access(HttpSources(), caller)
    return {"allowed": ["overview", *allowed], "panels": [{"module": m, "label": PANELS[m].label} for m in ["overview", *allowed]]}


@router.post("/{insight_id}/feedback", status_code=201)
async def post_feedback(insight_id: uuid.UUID, req: FeedbackRequest, ctx: AuthContext = Depends(get_auth_context)):
    _guard()
    try:
        return await service.submit_feedback(caller_from(ctx), str(insight_id), req.verdict, req.rec_id, req.note)
    except service.NotFound as exc:
        raise _map(exc)
    except StoreError:
        raise HTTPException(503, "Feedback could not be saved right now. Please try again.")
