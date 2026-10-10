"""Identity-scoped personal context endpoints (mounted by main.py under /api/v1) + the mail-thread "forget" path.

POST /knowledge/personal/{kind}   kind = day | tasks | escalations | schedule | kpis | approvals
    READ-ONLY. The user is ALWAYS the signed caller (ctx.user_id); there is no user parameter, so another person's items
    cannot be requested. Data is read live from the real operational tables (personal.py), not from the indexed cards.
POST /knowledge/admin/mail/forget  admin: stop indexing one mail thread and erase its card (refused under legal hold).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.common.auth import AuthContext, get_auth_context
from services.tenant_memory.knowledge import personal as P
from services.tenant_memory.knowledge.access import access_meta, load_scope

logger = logging.getLogger("knowledge.personal")
router = APIRouter(prefix="/api/v1")


class PersonalRequest(BaseModel):
    limit: int = Field(20, ge=1, le=100)
    status: Optional[str] = Field(None, max_length=30)             # tasks: todo | in-progress
    overdue_only: bool = False                                     # tasks
    role: Optional[str] = Field(None, pattern=r"^(assigned|raised)$")   # escalations
    breached_only: bool = False                                    # escalations
    today_only: bool = False                                       # schedule
    include_team: bool = True                                      # kpis (managers: aggregate only)
    focus: Optional[str] = Field(None, max_length=300)             # day: also pull related knowledge cards about this


async def gather_for_caller(ctx: AuthContext, kinds) -> dict:
    """Seam for tests: the signed caller's own data only."""
    from services.common.db import session_scope
    uid = str(ctx.user_id)
    async with session_scope(ctx.tenant_id) as session:
        data = await P.gather(session, str(ctx.tenant_id), datetime.now(timezone.utc), [uid], kinds=kinds)
    return data.get(uid, {})


async def _related_knowledge(ctx: AuthContext, focus: str) -> list[dict]:
    """A few non-personal cards relevant to the user's focus (access rules apply as for any search). Fail-open."""
    try:
        from services.tenant_memory.knowledge.kdata import Filters
        from services.tenant_memory.knowledge.retrieval import KnowledgeRetriever
        from services.tenant_memory.knowledge.routes import get_runtime
        store, embedder = get_runtime()
        scope = await load_scope(ctx)
        res = await KnowledgeRetriever(store, embedder).search(focus, scope, Filters(), k=4)
        return [{"card_id": f"card:{c['source_type']}:{c['source_id']}", "title": c["title"], "module": c["module"], "as_of": c["as_of"],
                 "deep_link": c["deep_link"]} for c, h in zip(res.citations(), res.hits) if h.chunk.visibility != "private"][:3]
    except Exception as exc:  # noqa: BLE001
        logger.info("related knowledge skipped: %s", type(exc).__name__)
        return []


@router.post("/knowledge/personal/{kind}")
async def personal(kind: str, req: PersonalRequest, ctx: AuthContext = Depends(get_auth_context)):
    if kind != "day" and kind not in P.KINDS:
        raise HTTPException(404, f"unknown personal context '{kind}'; use one of day, {', '.join(P.KINDS)}")
    kinds = P.KINDS if kind == "day" else (kind,)
    try:
        data = await gather_for_caller(ctx, kinds)
    except Exception as exc:  # noqa: BLE001
        logger.warning("personal %s failed: %s", kind, exc)
        raise HTTPException(503, "personal context is temporarily unavailable")
    meta = {"owner": "caller", "source": "live operational tables", "window": data.get("window"),
            "generated_at": datetime.now(timezone.utc).isoformat()}
    if kind == "day":
        out = P.day_summary(data)
        if req.focus:
            out["related_knowledge"] = await _related_knowledge(ctx, req.focus)
        scope = await load_scope(ctx)
        out["panels"] = {"allowed": access_meta(scope)["allowed_modules"], "note": "knowledge outside these panels is not retrievable for you"}
        return {**out, "meta": meta}
    if kind == "tasks":
        body = P.shape_tasks(data.get("tasks") or [], req.limit, req.status, req.overdue_only)
    elif kind == "escalations":
        body = P.shape_escalations(data.get("escalations") or [], req.limit, req.role, req.breached_only)
    elif kind == "schedule":
        body = P.shape_schedule(data.get("schedule") or [], req.limit, req.today_only)
    elif kind == "kpis":
        body = P.shape_kpis(data.get("kpis"), req.include_team)
    else:
        body = P.shape_approvals(data.get("approvals"), req.limit)
    return {"kind": kind, **body, "meta": meta}


# ── mail forget ──────────────────────────────────────────────────────────────

class ForgetThread(BaseModel):
    mailbox_id: str = Field(..., max_length=64)
    thread_key: str = Field(..., pattern=r"^[0-9a-f]{16}$", description="the part after ':' in the mail_thread card's source_id")


@router.post("/knowledge/admin/mail/forget")
async def forget_mail_thread(req: ForgetThread, ctx: AuthContext = Depends(get_auth_context)):
    """Admin: flag a thread so it is never indexed again (headers.knowledge_forget on its agent_emails rows - the same JSON
    flag mechanism the mail UI already uses for read/starred) and erase its derived card now. Refuses a thread under legal hold."""
    from services.tenant_memory.knowledge.routes import get_runtime, require_admin
    require_admin(ctx)
    from sqlalchemy import text
    from services.common.db import session_scope
    from services.tenant_memory.knowledge.cards.builders_personal import thread_key
    sid = f"{req.mailbox_id}:{req.thread_key}"
    async with session_scope(ctx.tenant_id) as session:
        rows = (await session.execute(text(
            "SELECT id::text AS id, subject, (headers->>'legal_hold') AS hold FROM agent_emails "
            "WHERE tenant_id = CAST(:t AS uuid) AND mailbox_id = CAST(:m AS uuid)"), {"t": str(ctx.tenant_id), "m": req.mailbox_id})).mappings().all()
        mine = [r for r in rows if thread_key(r["subject"]) == req.thread_key]
        if not mine:
            raise HTTPException(404, "thread not found")
        if any(str(r["hold"]).lower() in ("true", "1", "yes") for r in mine):
            raise HTTPException(409, "thread is under legal hold; it cannot be forgotten")
        await session.execute(text(
            "UPDATE agent_emails SET headers = COALESCE(headers, '{}'::jsonb) || '{\"knowledge_forget\": true}'::jsonb "
            "WHERE tenant_id = CAST(:t AS uuid) AND id = ANY(CAST(:ids AS uuid[]))"), {"t": str(ctx.tenant_id), "ids": [r["id"] for r in mine]})
    store, _ = get_runtime()
    n = await store.tombstone_source(str(ctx.tenant_id), "mail_thread", sid)
    await store.delete_edges_by_origin(str(ctx.tenant_id), f"mail_thread:{sid}")
    logger.warning("knowledge mail forget tenant=%s thread=%s by=%s", ctx.tenant_id, sid, ctx.user_id)
    return {"forgotten": sid, "messages_flagged": len(mine), "cards_removed": n}
