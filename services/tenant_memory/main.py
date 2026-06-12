from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from sqlalchemy import String, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_session, session_scope
from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
from services.tenant_memory.database import init_tables
from services.tenant_memory.schemas import (
    MemoryEntryCreate,
    MemoryEntryRead,
    MemoryEntryUpdate,
    MemoryListResponse,
    MemoryRecallResponse,
    MemorySummaryRead,
    MemorySummaryUpsert,
)

logger = logging.getLogger("tenant_memory")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(
    title="OmniDome Tenant Memory Service",
    version="1.0.0",
    description="Tenant-scoped operational memory, summaries, and agent recall.",
)

guard = EntitlementGuard(module_id="memory")
configure_production(app)


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        async with session_scope() as session:
            await init_tables(session)
        logger.info("Tenant memory tables ensured")


@app.middleware("http")
async def entitlement_middleware(request: Request, call_next):
    return await guard.middleware(request, call_next)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "tenant_memory", "module": "memory"}


def _jsonable_row(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["tags"] = item.get("tags") or []
    item["metadata"] = item.get("metadata") or {}
    item["source_entry_ids"] = item.get("source_entry_ids") or []
    return item


def _entry_from_row(row: Any) -> MemoryEntryRead:
    return MemoryEntryRead.model_validate(_jsonable_row(row))


def _summary_from_row(row: Any) -> MemorySummaryRead:
    return MemorySummaryRead.model_validate(_jsonable_row(row))


@app.post("/api/v1/memories", response_model=MemoryEntryRead, status_code=status.HTTP_201_CREATED)
async def create_memory(
    payload: MemoryEntryCreate,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    entry_id = uuid.uuid4()
    result = await session.execute(
        text(
            """
            insert into tenant_memory_entries (
                id, tenant_id, source_type, source_id, module, scope_key, title,
                content, summary, visibility, importance, tags, metadata, created_by, occurred_at
            )
            values (
                :id, :tenant_id, :source_type, :source_id, :module, :scope_key, :title,
                :content, :summary, :visibility, :importance, :tags, :metadata, :created_by, :occurred_at
            )
            returning *
            """
        ).bindparams(
            bindparam("tags", type_=ARRAY(String())),
            bindparam("metadata", type_=JSONB),
        ),
        {
            "id": str(entry_id),
            "tenant_id": str(ctx.tenant_id),
            "source_type": payload.source_type,
            "source_id": payload.source_id,
            "module": payload.module,
            "scope_key": payload.scope_key,
            "title": payload.title,
            "content": payload.content,
            "summary": payload.summary,
            "visibility": payload.visibility,
            "importance": payload.importance,
            "tags": payload.tags,
            "metadata": payload.metadata,
            "created_by": str(ctx.user_id),
            "occurred_at": payload.occurred_at or datetime.now(timezone.utc),
        },
    )
    return _entry_from_row(result.mappings().one())


@app.get("/api/v1/memories", response_model=MemoryListResponse)
async def list_memories(
    module: Optional[str] = Query(None),
    scope_key: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    q: Optional[str] = Query(None, min_length=2),
    include_archived: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    clauses = ["tenant_id = :tenant_id"]
    params: dict[str, Any] = {"tenant_id": str(ctx.tenant_id), "limit": limit}
    if not include_archived:
        clauses.append("archived_at is null")
    if module:
        clauses.append("module = :module")
        params["module"] = module
    if scope_key:
        clauses.append("scope_key = :scope_key")
        params["scope_key"] = scope_key
    if source_type:
        clauses.append("source_type = :source_type")
        params["source_type"] = source_type
    if tag:
        clauses.append(":tag = any(tags)")
        params["tag"] = tag
    if q:
        clauses.append(
            "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content, '')) "
            "@@ plainto_tsquery('english', :query)"
        )
        params["query"] = q

    result = await session.execute(
        text(
            f"""
            select *
            from tenant_memory_entries
            where {' and '.join(clauses)}
            order by occurred_at desc, created_at desc
            limit :limit
            """
        ),
        params,
    )
    return MemoryListResponse(items=[_entry_from_row(row) for row in result.mappings().all()], limit=limit)


@app.get("/api/v1/memories/{memory_id}", response_model=MemoryEntryRead)
async def get_memory(
    memory_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        text("select * from tenant_memory_entries where id = :id and tenant_id = :tenant_id"),
        {"id": str(memory_id), "tenant_id": str(ctx.tenant_id)},
    )
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return _entry_from_row(row)


@app.patch("/api/v1/memories/{memory_id}", response_model=MemoryEntryRead)
async def update_memory(
    memory_id: uuid.UUID,
    payload: MemoryEntryUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No updates provided")

    archived = updates.pop("archived", None)
    if archived is not None:
        updates["archived_at"] = datetime.now(timezone.utc) if archived else None

    allowed = {"title", "content", "summary", "visibility", "importance", "tags", "metadata", "archived_at"}
    set_parts = [f"{key} = :{key}" for key in updates if key in allowed]
    if not set_parts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid updates provided")

    updates["id"] = str(memory_id)
    updates["tenant_id"] = str(ctx.tenant_id)
    stmt = text(
            f"""
            update tenant_memory_entries
            set {', '.join(set_parts)}, updated_at = now()
            where id = :id and tenant_id = :tenant_id
            returning *
            """
    )
    if "tags" in updates:
        stmt = stmt.bindparams(bindparam("tags", type_=ARRAY(String())))
    if "metadata" in updates:
        stmt = stmt.bindparams(bindparam("metadata", type_=JSONB))
    result = await session.execute(stmt, updates)
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return _entry_from_row(row)


@app.put("/api/v1/summaries/{scope_key}", response_model=MemorySummaryRead)
async def upsert_summary(
    scope_key: str,
    payload: MemorySummaryUpsert,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    if payload.scope_key != scope_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_key mismatch")

    result = await session.execute(
        text(
            """
            insert into tenant_memory_summaries (
                tenant_id, scope_key, module, title, summary, source_entry_ids, metadata, updated_by
            )
            values (
                :tenant_id, :scope_key, :module, :title, :summary, :source_entry_ids, :metadata, :updated_by
            )
            on conflict (tenant_id, scope_key)
            do update set
                module = excluded.module,
                title = excluded.title,
                summary = excluded.summary,
                source_entry_ids = excluded.source_entry_ids,
                metadata = excluded.metadata,
                updated_by = excluded.updated_by,
                updated_at = now()
            returning *
            """
        ).bindparams(
            bindparam("source_entry_ids", type_=ARRAY(PG_UUID(as_uuid=True))),
            bindparam("metadata", type_=JSONB),
        ),
        {
            "tenant_id": str(ctx.tenant_id),
            "scope_key": payload.scope_key,
            "module": payload.module,
            "title": payload.title,
            "summary": payload.summary,
            "source_entry_ids": payload.source_entry_ids,
            "metadata": payload.metadata,
            "updated_by": str(ctx.user_id),
        },
    )
    return _summary_from_row(result.mappings().one())


@app.get("/api/v1/summaries", response_model=list[MemorySummaryRead])
async def list_summaries(
    module: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    clauses = ["tenant_id = :tenant_id"]
    params: dict[str, Any] = {"tenant_id": str(ctx.tenant_id), "limit": limit}
    if module:
        clauses.append("module = :module")
        params["module"] = module
    result = await session.execute(
        text(
            f"""
            select *
            from tenant_memory_summaries
            where {' and '.join(clauses)}
            order by updated_at desc
            limit :limit
            """
        ),
        params,
    )
    return [_summary_from_row(row) for row in result.mappings().all()]


@app.get("/api/v1/recall", response_model=MemoryRecallResponse)
async def recall(
    module: Optional[str] = Query(None),
    scope_key: Optional[str] = Query(None),
    q: Optional[str] = Query(None, min_length=2),
    limit: int = Query(10, ge=1, le=50),
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    summary_clauses = ["tenant_id = :tenant_id"]
    entry_clauses = ["tenant_id = :tenant_id", "archived_at is null"]
    params: dict[str, Any] = {"tenant_id": str(ctx.tenant_id), "limit": limit}
    if module:
        summary_clauses.append("module = :module")
        entry_clauses.append("module = :module")
        params["module"] = module
    if scope_key:
        summary_clauses.append("scope_key = :scope_key")
        entry_clauses.append("scope_key = :scope_key")
        params["scope_key"] = scope_key
    if q:
        entry_clauses.append(
            "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content, '')) "
            "@@ plainto_tsquery('english', :query)"
        )
        params["query"] = q

    summaries_result = await session.execute(
        text(
            f"""
            select *
            from tenant_memory_summaries
            where {' and '.join(summary_clauses)}
            order by updated_at desc
            limit :limit
            """
        ),
        params,
    )
    entries_result = await session.execute(
        text(
            f"""
            select *
            from tenant_memory_entries
            where {' and '.join(entry_clauses)}
            order by occurred_at desc, created_at desc
            limit :limit
            """
        ),
        params,
    )
    return MemoryRecallResponse(
        summaries=[_summary_from_row(row) for row in summaries_result.mappings().all()],
        entries=[_entry_from_row(row) for row in entries_result.mappings().all()],
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8025)
