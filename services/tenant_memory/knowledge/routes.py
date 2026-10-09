"""HTTP surface of the knowledge layer (mounted by tenant_memory.main under /api/v1).

Internal functions for in-process callers (the orchestrator calls these over HTTP via the existing
TENANT_MEMORY_SERVICE_URL): `POST /api/v1/knowledge/context` is `knowledge.context`, and
`GET /api/v1/recall?mode=hybrid` is `memory.recall` with knowledge hits.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_session
from services.tenant_memory.knowledge import consolidation, tiers
from services.tenant_memory.knowledge.cards.sources import SOURCES
from services.tenant_memory.knowledge.config import get_settings, knowledge_enabled
from services.tenant_memory.knowledge.embeddings import Embedder, OllamaEmbedder
from services.tenant_memory.knowledge.kdata import ADMIN_ROLES, AccessScope, Filters
from services.tenant_memory.knowledge.metrics import MetricFactIn, upsert_metric_fact
from services.tenant_memory.knowledge.retrieval import KnowledgeRetriever, pack_context
from services.tenant_memory.knowledge.store import KnowledgeStore

logger = logging.getLogger("knowledge.routes")
router = APIRouter(prefix="/api/v1")

_runtime: dict[str, Any] = {}


def set_runtime(store: Optional[KnowledgeStore], embedder: Optional[Embedder]) -> None:
    """Tests (and the worker) inject fakes here."""
    _runtime["store"], _runtime["embedder"] = store, embedder


def get_runtime() -> tuple[KnowledgeStore, Embedder]:
    if "store" not in _runtime:
        if not knowledge_enabled():
            raise HTTPException(503, "Knowledge layer is not configured (KNOWLEDGE_DB_URL unset)")
        from services.tenant_memory.knowledge.store_pg import PgVectorStore
        _runtime["store"], _runtime["embedder"] = PgVectorStore(), OllamaEmbedder()
    if _runtime["store"] is None:
        raise HTTPException(503, "Knowledge layer is not configured")
    return _runtime["store"], _runtime["embedder"]


def require_admin(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    roles = {r.lower() for r in ctx.roles}
    if not (ctx.is_platform_admin or roles & ADMIN_ROLES or "agents.manage" in {p.lower() for p in ctx.permissions}):
        raise HTTPException(403, "Admin role required")
    return ctx


def require_metric_writer(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    if not (ctx.is_platform_admin or "metrics.write" in {p.lower() for p in ctx.permissions}):
        raise HTTPException(403, "metrics.write permission required (deterministic writers only)")
    return ctx


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000)
    k: int = Field(8, ge=1, le=30)
    modules: Optional[list[str]] = None
    source_types: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    min_importance: Optional[float] = Field(None, ge=0, le=1)
    include_expired: bool = False
    graph: bool = False
    graph_depth: int = Field(1, ge=1, le=4)


class ContextRequest(SearchRequest):
    budget_tokens: int = Field(1500, ge=200, le=12000)
    k: int = Field(12, ge=1, le=30)


def _filters(r: SearchRequest) -> Filters:
    return Filters(r.modules, r.source_types, r.tags, r.since, r.until, r.min_importance, r.include_expired)


async def _search(r: SearchRequest, ctx: AuthContext):
    store, embedder = get_runtime()
    retr = KnowledgeRetriever(store, embedder)
    return await retr.search(r.query, AccessScope.from_ctx(ctx), _filters(r), k=r.k, graph=r.graph,
                             graph_depth=min(r.graph_depth, get_settings().max_graph_depth))


@router.get("/knowledge/health")
async def knowledge_health(ctx: AuthContext = Depends(get_auth_context)):
    if not knowledge_enabled() and "store" not in _runtime:
        return {"enabled": False}
    store, embedder = get_runtime()
    return {"enabled": True, "store_ok": await store.ping(), "embedding": await embedder.health()}


@router.post("/knowledge/search")
async def knowledge_search(req: SearchRequest, ctx: AuthContext = Depends(get_auth_context)):
    res = await _search(req, ctx)
    cits = res.citations()
    return {"degraded": res.degraded,
            "results": [{**c, "markdown": h.chunk.markdown} for c, h in zip(cits, res.hits)]}


@router.post("/knowledge/context")
async def knowledge_context(req: ContextRequest, ctx: AuthContext = Depends(get_auth_context)):
    res = await _search(req, ctx)
    return pack_context(res, req.budget_tokens)


@router.get("/knowledge/graph")
async def knowledge_graph(source_type: str, source_id: str, depth: int = Query(2, ge=1, le=4),
                          relation: Optional[list[str]] = Query(None), limit: int = Query(50, ge=1, le=200),
                          ctx: AuthContext = Depends(get_auth_context)):
    store, _ = get_runtime()
    nodes = await store.traverse(str(ctx.tenant_id), [(source_type, source_id)], min(depth, get_settings().max_graph_depth), relation, limit)
    access = AccessScope.from_ctx(ctx)
    chunks = await store.chunks_for_sources(str(ctx.tenant_id), [(n["node_type"], n["node_id"]) for n in nodes], Filters(), access)
    titles = {(c.source_type, c.source_id): c.title for c in chunks}
    # Nodes the caller may not read are listed without a title (structure only), never with content.
    return {"root": {"source_type": source_type, "source_id": source_id},
            "nodes": [{**n, "title": titles.get((n["node_type"], n["node_id"])), "readable": (n["node_type"], n["node_id"]) in titles} for n in nodes]}


# ── admin: indexing ────────────────────────────────────────────────────────

class ReindexRequest(BaseModel):
    modules: Optional[list[str]] = None
    sources: Optional[list[str]] = None
    full: bool = False
    force: bool = Field(False, description="re-write metadata (visibility/importance) even when text is unchanged")


@router.post("/knowledge/admin/reindex", status_code=202)
async def reindex(req: ReindexRequest, ctx: AuthContext = Depends(require_admin)):
    unknown = [s for s in (req.sources or []) if s not in SOURCES]
    if unknown:
        raise HTTPException(400, f"unknown sources: {unknown}; known: {sorted(SOURCES)}")
    store, _ = get_runtime()
    jid = await store.enqueue_job(str(ctx.tenant_id), "reindex", req.model_dump(), str(ctx.user_id))
    return {"job_id": jid, "status": "queued"}


@router.get("/knowledge/admin/coverage")
async def coverage(ctx: AuthContext = Depends(require_admin)):
    store, embedder = get_runtime()
    cov = await store.coverage(str(ctx.tenant_id))
    covered = {s["source_type"] for s in cov["sources"]}
    cov["not_yet_indexed"] = sorted(t for name, src in SOURCES.items() for t in src.source_types if t not in covered)
    cov["embedding"] = await embedder.health()
    return cov


class ConsolidateRequest(BaseModel):
    dry_run: bool = True


@router.post("/knowledge/admin/consolidate", status_code=202)
async def consolidate(req: ConsolidateRequest, ctx: AuthContext = Depends(require_admin)):
    store, _ = get_runtime()
    jid = await store.enqueue_job(str(ctx.tenant_id), "consolidate", req.model_dump(), str(ctx.user_id))
    return {"job_id": jid, "status": "queued"}


class EraseRequest(BaseModel):
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    module: Optional[str] = None
    entire_tenant: bool = False
    confirm: str = Field("", description='must equal "ERASE" - this is a hard delete')


@router.post("/knowledge/admin/erase")
async def erase(req: EraseRequest, ctx: AuthContext = Depends(require_admin)):
    """POPIA erasure / offboarding. Hard-deletes derived chunks, edges and bookkeeping from knowledge_db."""
    if req.confirm != "ERASE":
        raise HTTPException(400, 'confirm must be "ERASE"')
    if not (req.entire_tenant or req.source_type or req.source_id or req.module):
        raise HTTPException(400, "give a scope (source_type/source_id/module) or entire_tenant=true")
    if req.source_id and not req.source_type:
        raise HTTPException(400, "source_id needs source_type")
    store, _ = get_runtime()
    out = await consolidation.erase_tenant_knowledge(store, str(ctx.tenant_id), source_type=req.source_type,
                                                     source_id=req.source_id, module=req.module)
    logger.warning("knowledge erase tenant=%s scope=%s by=%s result=%s", ctx.tenant_id, req.model_dump(exclude={"confirm"}), ctx.user_id, out)
    return {"erased": out, "note": "operational source rows are unchanged; delete them in their own service to prevent re-indexing"}


# ── short-term (working) memory ────────────────────────────────────────────

class WorkingCreate(BaseModel):
    session_key: str = Field(..., max_length=160)
    content: str = Field(..., min_length=1, max_length=8000)
    kind: str = Field("note", pattern=r"^(turn|state|context_ref|note)$")
    module: Optional[str] = Field(None, max_length=80)
    title: Optional[str] = Field(None, max_length=240)
    importance: str = Field("normal", pattern=r"^(low|normal|high|critical)$")
    pinned: bool = False
    ttl_minutes: Optional[int] = Field(None, ge=1, le=10080)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _jsonable(row: dict) -> dict:
    return {k: (str(v) if k.endswith("id") or k == "id" else v) for k, v in row.items()}


@router.post("/memory/working", status_code=201)
async def working_add(req: WorkingCreate, ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_async_session)):
    row = await tiers.add_working(session, str(ctx.tenant_id), req.session_key, req.content, kind=req.kind, module=req.module,
                                  title=req.title, importance=req.importance, pinned=req.pinned, metadata=req.metadata,
                                  user_id=str(ctx.user_id) if ctx.user_id else None, ttl_minutes=req.ttl_minutes)
    return _jsonable(row)


@router.get("/memory/working/{session_key}")
async def working_get(session_key: str, limit: int = Query(50, ge=1, le=200), ctx: AuthContext = Depends(get_auth_context),
                      session: AsyncSession = Depends(get_async_session)):
    return {"items": [_jsonable(r) for r in await tiers.get_session_items(session, str(ctx.tenant_id), session_key, limit)]}


@router.delete("/memory/working/{session_key}")
async def working_clear(session_key: str, ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_async_session)):
    return {"deleted": await tiers.clear_session(session, str(ctx.tenant_id), session_key)}


@router.post("/memory/working/{item_id}/pin")
async def working_pin(item_id: str, pinned: bool = True, ctx: AuthContext = Depends(get_auth_context),
                      session: AsyncSession = Depends(get_async_session)):
    if not await tiers.pin_item(session, str(ctx.tenant_id), item_id, pinned):
        raise HTTPException(404, "Working-memory item not found")
    return {"id": item_id, "pinned": pinned}


# ── metric facts ───────────────────────────────────────────────────────────

@router.post("/metrics/facts", status_code=201)
async def metric_fact_write(fact: MetricFactIn, ctx: AuthContext = Depends(require_metric_writer),
                            session: AsyncSession = Depends(get_async_session)):
    return await upsert_metric_fact(session, str(ctx.tenant_id), fact)
