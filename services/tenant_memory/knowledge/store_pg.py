"""pgvector-backed KnowledgeStore (the `knowledge_db` container).

NOT exercised by the unit tests (SQLite has no pgvector); the SQL builders at the
top are pure functions so their shape is unit-tested, and tests/test_pg_integration.py
runs the whole thing against a real server when KNOWLEDGE_TEST_DB_URL is set.

Isolation: every statement filters on tenant_id explicitly AND every transaction
sets `app.tenant_id` so row-level security (forced, app connects as a non-superuser
role) rejects anything that slips through.
"""
from __future__ import annotations

import json
import logging
import uuid
import zlib
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from services.tenant_memory.knowledge.config import Settings, get_settings
from services.tenant_memory.knowledge.store import KnowledgeStore, SearchResult, vector_literal
from services.tenant_memory.knowledge.kdata import AccessScope, Chunk, Edge, Filters

logger = logging.getLogger("knowledge.store_pg")

MIGRATION_LOCK_KEY = 727_001
APP_ROLE = "knowledge_app"

_CHUNK_COLS = (
    "id, tenant_id, source_type, source_id, chunk_no, source_ref, module, title, markdown, content_hash, "
    "embedding_model, visibility, required_roles, required_permission, owner_id, as_of, valid_to, importance, "
    "tags, updated_at, deleted_at"
)


def migration_statements(s: Settings) -> list[str]:
    dim = int(s.embedding_dim)
    return [
        "CREATE EXTENSION IF NOT EXISTS vector",
        f"""CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            chunk_no INT NOT NULL DEFAULT 0,
            source_ref JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            module TEXT NOT NULL DEFAULT 'general',
            title TEXT NOT NULL,
            markdown TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            embedding vector({dim}),
            embedding_model TEXT,
            tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(title, '') || ' ' || markdown)) STORED,
            visibility TEXT NOT NULL DEFAULT 'tenant' CHECK (visibility IN ('private','team','tenant','system')),
            required_roles TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            required_permission TEXT,
            owner_id UUID,
            as_of TIMESTAMPTZ,
            valid_to TIMESTAMPTZ,
            importance REAL NOT NULL DEFAULT 0.5,
            tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at TIMESTAMPTZ,
            UNIQUE (tenant_id, source_type, source_id, chunk_no)
        )""",
        f"""CREATE INDEX IF NOT EXISTS ix_kc_embedding_hnsw ON knowledge_chunks
            USING hnsw (embedding vector_cosine_ops) WITH (m = {int(s.hnsw_m)}, ef_construction = {int(s.hnsw_ef_construction)})
            WHERE deleted_at IS NULL""",
        "CREATE INDEX IF NOT EXISTS ix_kc_tsv ON knowledge_chunks USING gin (tsv)",
        "CREATE INDEX IF NOT EXISTS ix_kc_tags ON knowledge_chunks USING gin (tags)",
        "CREATE INDEX IF NOT EXISTS ix_kc_tenant_module ON knowledge_chunks (tenant_id, module, source_type)",
        "CREATE INDEX IF NOT EXISTS ix_kc_hash ON knowledge_chunks (tenant_id, content_hash)",
        """CREATE TABLE IF NOT EXISTS knowledge_edges (
            tenant_id UUID NOT NULL,
            src_type TEXT NOT NULL, src_id TEXT NOT NULL,
            dst_type TEXT NOT NULL, dst_id TEXT NOT NULL,
            relation TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1.0,
            as_of TIMESTAMPTZ,
            origin_key TEXT NOT NULL,
            PRIMARY KEY (tenant_id, src_type, src_id, dst_type, dst_id, relation)
        )""",
        "CREATE INDEX IF NOT EXISTS ix_ke_src ON knowledge_edges (tenant_id, src_type, src_id)",
        "CREATE INDEX IF NOT EXISTS ix_ke_dst ON knowledge_edges (tenant_id, dst_type, dst_id)",
        "CREATE INDEX IF NOT EXISTS ix_ke_origin ON knowledge_edges (tenant_id, origin_key)",
        """CREATE TABLE IF NOT EXISTS knowledge_watermarks (
            tenant_id UUID NOT NULL, source TEXT NOT NULL,
            last_ts TIMESTAMPTZ, last_full_at TIMESTAMPTZ,
            meta JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, source)
        )""",
        """CREATE TABLE IF NOT EXISTS knowledge_failures (
            id BIGSERIAL PRIMARY KEY, tenant_id UUID NOT NULL, source TEXT NOT NULL,
            source_ref TEXT, error TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_kf_tenant ON knowledge_failures (tenant_id, source, created_at DESC)",
        """CREATE TABLE IF NOT EXISTS knowledge_jobs (
            id UUID PRIMARY KEY, tenant_id UUID NOT NULL, kind TEXT NOT NULL,
            params JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed')),
            requested_by TEXT, result JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(), started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ
        )""",
        "CREATE INDEX IF NOT EXISTS ix_kj_status ON knowledge_jobs (status, created_at)",
        # Row-level security on every tenant table (jobs are platform-level queue rows).
        *[stmt for t in ("knowledge_chunks", "knowledge_edges", "knowledge_watermarks", "knowledge_failures") for stmt in (
            f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY",
            f"DROP POLICY IF EXISTS tenant_isolation ON {t}",
            f"""CREATE POLICY tenant_isolation ON {t}
                USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)""",
        )],
    ]


def access_clause(access: AccessScope, alias: str = "c") -> tuple[str, dict]:
    """SQL mirror of AccessScope.allows(). Tenant filter first, always."""
    a = alias
    clauses = [f"{a}.tenant_id = CAST(:tenant_id AS uuid)", f"{a}.deleted_at IS NULL"]
    params: dict[str, Any] = {"tenant_id": access.tenant_id}
    if access.user_id:
        clauses.append(f"({a}.visibility <> 'private' OR {a}.owner_id = CAST(:user_id AS uuid))")
        params["user_id"] = access.user_id
    else:
        clauses.append(f"{a}.visibility <> 'private'")
    if not access.is_admin:
        clauses.append(f"({a}.required_permission IS NULL OR lower({a}.required_permission) = ANY(CAST(:perms AS text[])))")
        clauses.append(f"(cardinality({a}.required_roles) = 0 OR {a}.required_roles && CAST(:roles AS text[]))")
        params["perms"] = sorted(access.permissions)
        params["roles"] = sorted(access.roles)
    return " AND ".join(clauses), params


def filter_clause(flt: Filters, alias: str = "c") -> tuple[str, dict]:
    a = alias
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if flt.modules:
        clauses.append(f"{a}.module = ANY(CAST(:f_modules AS text[]))")
        params["f_modules"] = list(flt.modules)
    if flt.source_types:
        clauses.append(f"{a}.source_type = ANY(CAST(:f_types AS text[]))")
        params["f_types"] = list(flt.source_types)
    if flt.tags:
        clauses.append(f"{a}.tags && CAST(:f_tags AS text[])")
        params["f_tags"] = list(flt.tags)
    if flt.since:
        clauses.append(f"{a}.as_of >= :f_since")
        params["f_since"] = flt.since
    if flt.until:
        clauses.append(f"{a}.as_of <= :f_until")
        params["f_until"] = flt.until
    if flt.min_importance is not None:
        clauses.append(f"{a}.importance >= :f_minimp")
        params["f_minimp"] = flt.min_importance
    if not flt.include_expired:
        clauses.append(f"({a}.valid_to IS NULL OR {a}.valid_to > now())")
    return (" AND " + " AND ".join(clauses)) if clauses else "", params


def vector_search_sql(flt: Filters, access: AccessScope) -> tuple[str, dict]:
    acc, p1 = access_clause(access)
    fl, p2 = filter_clause(flt)
    sql = (f"SELECT {_CHUNK_COLS.replace('id,', 'c.id,', 1)}, 1 - (c.embedding <=> CAST(:q AS vector)) AS score "
           f"FROM knowledge_chunks c WHERE {acc}{fl} AND c.embedding IS NOT NULL "
           f"ORDER BY c.embedding <=> CAST(:q AS vector) LIMIT :limit")
    return sql, {**p1, **p2}


def text_search_sql(flt: Filters, access: AccessScope) -> tuple[str, dict]:
    acc, p1 = access_clause(access)
    fl, p2 = filter_clause(flt)
    # Questions rarely contain only words present in one card: OR the stemmed words and rank.
    tsq = "to_tsquery('english', replace(plainto_tsquery('english', :q)::text, ' & ', ' | '))"
    sql = (f"SELECT {_CHUNK_COLS.replace('id,', 'c.id,', 1)}, ts_rank_cd(c.tsv, {tsq}) AS score "
           f"FROM knowledge_chunks c WHERE {acc}{fl} AND c.tsv @@ {tsq} "
           f"ORDER BY score DESC LIMIT :limit")
    return sql, {**p1, **p2}


TRAVERSE_SQL = """
WITH RECURSIVE seeds(node_type, node_id) AS (
    SELECT * FROM unnest(CAST(:seed_types AS text[]), CAST(:seed_ids AS text[]))
), walk(node_type, node_id, depth, path, relation) AS (
    SELECT node_type, node_id, 0, ARRAY[node_type || ':' || node_id], NULL::text FROM seeds
    UNION ALL
    SELECT CASE WHEN e.src_type = w.node_type AND e.src_id = w.node_id THEN e.dst_type ELSE e.src_type END,
           CASE WHEN e.src_type = w.node_type AND e.src_id = w.node_id THEN e.dst_id ELSE e.src_id END,
           w.depth + 1,
           w.path || (CASE WHEN e.src_type = w.node_type AND e.src_id = w.node_id THEN e.dst_type || ':' || e.dst_id
                           ELSE e.src_type || ':' || e.src_id END),
           e.relation
    FROM walk w
    JOIN knowledge_edges e ON e.tenant_id = CAST(:tenant_id AS uuid)
         AND ((e.src_type = w.node_type AND e.src_id = w.node_id) OR (e.dst_type = w.node_type AND e.dst_id = w.node_id))
    WHERE w.depth < :depth
      AND (CAST(:relations AS text[]) IS NULL OR e.relation = ANY(CAST(:relations AS text[])))
      AND NOT ((CASE WHEN e.src_type = w.node_type AND e.src_id = w.node_id THEN e.dst_type || ':' || e.dst_id
                     ELSE e.src_type || ':' || e.src_id END) = ANY(w.path))
)
SELECT DISTINCT ON (node_type, node_id) node_type, node_id, depth, relation
FROM walk WHERE depth > 0
ORDER BY node_type, node_id, depth
LIMIT :limit
"""


def _row_to_chunk(r: Any) -> Chunk:
    ref = r["source_ref"]
    return Chunk(
        id=str(r["id"]), tenant_id=str(r["tenant_id"]), source_type=r["source_type"], source_id=r["source_id"],
        chunk_no=r["chunk_no"], source_ref=json.loads(ref) if isinstance(ref, str) else (ref or {}),
        module=r["module"], title=r["title"], markdown=r["markdown"], content_hash=r["content_hash"],
        embedding_model=r["embedding_model"], visibility=r["visibility"], required_roles=list(r["required_roles"] or []),
        required_permission=r["required_permission"], owner_id=str(r["owner_id"]) if r["owner_id"] else None,
        as_of=r["as_of"], valid_to=r["valid_to"], importance=float(r["importance"]), tags=list(r["tags"] or []),
        updated_at=r["updated_at"], deleted_at=r["deleted_at"],
    )


def _async_url(url: str) -> str:
    u = make_url(url)
    if u.drivername.startswith("postgresql") and "+asyncpg" not in u.drivername:
        u = u.set(drivername="postgresql+asyncpg")
    return u.render_as_string(hide_password=False)


class PgVectorStore(KnowledgeStore):
    def __init__(self, url: Optional[str] = None, settings: Optional[Settings] = None, admin_url: Optional[str] = None):
        self.s = settings or get_settings()
        url = url or self.s.knowledge_db_url
        if not url:
            raise RuntimeError("KNOWLEDGE_DB_URL is not set; the knowledge layer is disabled")
        self.engine: AsyncEngine = create_async_engine(_async_url(url), pool_size=3, max_overflow=2, pool_pre_ping=True)
        self._admin_url = admin_url
        self._lock_conns: dict[str, Any] = {}

    @asynccontextmanager
    async def _tx(self, tenant: Optional[str] = None):
        async with self.engine.begin() as conn:
            if tenant:
                await conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
            yield conn

    # ── lifecycle ──
    async def ensure_schema(self) -> None:
        """Idempotent; serialised across processes by an advisory lock. Run by the worker with the owner URL."""
        import os

        admin = self._admin_url or os.getenv("KNOWLEDGE_DB_ADMIN_URL", "") or self.s.knowledge_db_url
        engine = create_async_engine(_async_url(admin))
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": MIGRATION_LOCK_KEY})
                for stmt in migration_statements(self.s):
                    await conn.execute(text(stmt))
                dim = (await conn.execute(text(
                    "SELECT atttypmod FROM pg_attribute WHERE attrelid = 'knowledge_chunks'::regclass AND attname = 'embedding'"
                ))).scalar()
                if dim is not None and int(dim) != int(self.s.embedding_dim):
                    raise RuntimeError(
                        f"knowledge_chunks.embedding is vector({dim}) but EMBEDDING_DIM={self.s.embedding_dim}; "
                        "changing model dimension needs a rebuild (derived data: drop the table and reindex)")
                app_pw = os.getenv("KNOWLEDGE_APP_PASSWORD", "")
                if app_pw and make_url(admin).username != APP_ROLE:
                    create = (await conn.execute(text("SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', CAST(:r AS text), CAST(:p AS text))"),
                                                 {"r": APP_ROLE, "p": app_pw})).scalar()
                    alter = (await conn.execute(text("SELECT format('ALTER ROLE %I PASSWORD %L', CAST(:r AS text), CAST(:p AS text))"),
                                                {"r": APP_ROLE, "p": app_pw})).scalar()
                    exists = (await conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": APP_ROLE})).first()
                    await conn.execute(text(alter if exists else create))
                    await conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"))
                    await conn.execute(text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}"))
        finally:
            await engine.dispose()

    async def ping(self) -> bool:
        try:
            async with self.engine.connect() as c:
                await c.execute(text("SELECT 1 FROM knowledge_chunks LIMIT 1"))
            return True
        except Exception:  # noqa: BLE001
            return False

    # ── chunks ──
    async def source_state(self, tenant, source_type, source_id):
        async with self._tx(tenant) as c:
            rows = (await c.execute(text(
                "SELECT chunk_no, content_hash, embedding_model FROM knowledge_chunks WHERE tenant_id = CAST(:t AS uuid) "
                "AND source_type = :st AND source_id = :sid AND deleted_at IS NULL AND embedding IS NOT NULL"),
                {"t": tenant, "st": source_type, "sid": source_id})).mappings().all()
        return {r["chunk_no"]: (r["content_hash"], r["embedding_model"]) for r in rows}

    async def cached_embeddings(self, tenant, hashes, model):
        if not hashes:
            return {}
        async with self._tx(tenant) as c:
            rows = (await c.execute(text(
                "SELECT DISTINCT ON (content_hash) content_hash, embedding::text AS e FROM knowledge_chunks "
                "WHERE tenant_id = CAST(:t AS uuid) AND content_hash = ANY(CAST(:h AS text[])) "
                "AND embedding_model = :m AND embedding IS NOT NULL"),
                {"t": tenant, "h": hashes, "m": model})).mappings().all()
        return {r["content_hash"]: json.loads(r["e"]) for r in rows}

    async def upsert_chunks(self, tenant, chunks):
        out = {"inserted": 0, "updated": 0, "unchanged": 0}
        sql = text("""
            INSERT INTO knowledge_chunks (tenant_id, source_type, source_id, chunk_no, source_ref, module, title, markdown,
                content_hash, embedding, embedding_model, visibility, required_roles, required_permission, owner_id,
                as_of, valid_to, importance, tags)
            VALUES (CAST(:tenant_id AS uuid), :source_type, :source_id, :chunk_no, CAST(:source_ref AS jsonb), :module, :title,
                :markdown, :content_hash, CAST(:embedding AS vector), :embedding_model, :visibility,
                CAST(:required_roles AS text[]), :required_permission, CAST(:owner_id AS uuid), :as_of, :valid_to,
                :importance, CAST(:tags AS text[]))
            ON CONFLICT (tenant_id, source_type, source_id, chunk_no) DO UPDATE SET
                source_ref = EXCLUDED.source_ref, module = EXCLUDED.module, title = EXCLUDED.title,
                markdown = EXCLUDED.markdown, content_hash = EXCLUDED.content_hash, embedding = EXCLUDED.embedding,
                embedding_model = EXCLUDED.embedding_model, visibility = EXCLUDED.visibility,
                required_roles = EXCLUDED.required_roles, required_permission = EXCLUDED.required_permission,
                owner_id = EXCLUDED.owner_id, as_of = EXCLUDED.as_of, valid_to = EXCLUDED.valid_to,
                importance = EXCLUDED.importance, tags = EXCLUDED.tags, updated_at = now(), deleted_at = NULL
            WHERE knowledge_chunks.content_hash IS DISTINCT FROM EXCLUDED.content_hash
               OR knowledge_chunks.deleted_at IS NOT NULL
               OR knowledge_chunks.embedding_model IS DISTINCT FROM EXCLUDED.embedding_model
               OR knowledge_chunks.visibility IS DISTINCT FROM EXCLUDED.visibility
               OR knowledge_chunks.required_roles IS DISTINCT FROM EXCLUDED.required_roles
               OR knowledge_chunks.required_permission IS DISTINCT FROM EXCLUDED.required_permission
               OR knowledge_chunks.importance IS DISTINCT FROM EXCLUDED.importance
            RETURNING (xmax = 0) AS inserted
        """)
        async with self._tx(tenant) as c:
            for ch in chunks:
                if str(ch.tenant_id) != tenant:
                    raise ValueError("chunk tenant mismatch")
                r = (await c.execute(sql, {
                    "tenant_id": tenant, "source_type": ch.source_type, "source_id": ch.source_id, "chunk_no": ch.chunk_no,
                    "source_ref": json.dumps(ch.source_ref, default=str), "module": ch.module, "title": ch.title[:300],
                    "markdown": ch.markdown, "content_hash": ch.content_hash,
                    "embedding": vector_literal(ch.embedding) if ch.embedding else None,
                    "embedding_model": ch.embedding_model, "visibility": ch.visibility,
                    "required_roles": [x.lower() for x in ch.required_roles], "required_permission": ch.required_permission,
                    "owner_id": ch.owner_id, "as_of": ch.as_of, "valid_to": ch.valid_to, "importance": ch.importance,
                    "tags": list(ch.tags),
                })).first()
                out["unchanged" if r is None else "inserted" if r[0] else "updated"] += 1
        return out

    async def retire_chunks(self, tenant, source_type, source_id, keep_chunk_nos):
        async with self._tx(tenant) as c:
            r = await c.execute(text(
                "UPDATE knowledge_chunks SET deleted_at = now() WHERE tenant_id = CAST(:t AS uuid) AND source_type = :st "
                "AND source_id = :sid AND deleted_at IS NULL AND NOT (chunk_no = ANY(CAST(:keep AS int[])))"),
                {"t": tenant, "st": source_type, "sid": source_id, "keep": list(keep_chunk_nos)})
        return r.rowcount

    async def tombstone_source(self, tenant, source_type, source_id):
        return await self.retire_chunks(tenant, source_type, source_id, [])

    async def live_source_ids(self, tenant, source_type):
        async with self._tx(tenant) as c:
            rows = (await c.execute(text(
                "SELECT DISTINCT source_id FROM knowledge_chunks WHERE tenant_id = CAST(:t AS uuid) AND source_type = :st "
                "AND deleted_at IS NULL"), {"t": tenant, "st": source_type})).all()
        return {r[0] for r in rows}

    async def vector_search(self, tenant, vec, flt, access, limit):
        if access.tenant_id != tenant:
            raise ValueError("access scope tenant mismatch")
        sql, params = vector_search_sql(flt, access)
        async with self._tx(tenant) as c:
            await c.execute(text("SELECT set_config('hnsw.ef_search', :v, true)"), {"v": str(self.s.hnsw_ef_search)})
            await c.execute(text("SELECT set_config('hnsw.iterative_scan', 'relaxed_order', true)"))
            rows = (await c.execute(text(sql), {**params, "q": vector_literal(vec), "limit": limit})).mappings().all()
        return [(_row_to_chunk(r), float(r["score"])) for r in rows]

    async def text_search(self, tenant, query, flt, access, limit):
        if access.tenant_id != tenant:
            raise ValueError("access scope tenant mismatch")
        sql, params = text_search_sql(flt, access)
        async with self._tx(tenant) as c:
            rows = (await c.execute(text(sql), {**params, "q": query, "limit": limit})).mappings().all()
        return [(_row_to_chunk(r), float(r["score"])) for r in rows]

    async def chunks_for_sources(self, tenant, nodes, flt, access, per_source=1):
        if not nodes:
            return []
        acc, p1 = access_clause(access)
        fl, p2 = filter_clause(flt)
        sql = (f"SELECT {_CHUNK_COLS.replace('id,', 'c.id,', 1)} FROM knowledge_chunks c WHERE {acc}{fl} "
               "AND (c.source_type || ':' || c.source_id) = ANY(CAST(:keys AS text[])) AND c.chunk_no < :per ORDER BY c.source_type, c.source_id, c.chunk_no")
        async with self._tx(tenant) as c:
            rows = (await c.execute(text(sql), {**p1, **p2, "keys": [f"{a}:{b}" for a, b in nodes], "per": per_source})).mappings().all()
        return [_row_to_chunk(r) for r in rows]

    async def near_duplicates(self, tenant, source_type, threshold, limit):
        async with self._tx(tenant) as c:
            rows = (await c.execute(text("""
                SELECT a.source_id AS a_id, nb.source_id AS b_id, 1 - (a.embedding <=> nb.embedding) AS sim
                FROM knowledge_chunks a
                CROSS JOIN LATERAL (
                    SELECT b.source_id, b.embedding FROM knowledge_chunks b
                    WHERE b.tenant_id = a.tenant_id AND b.source_type = a.source_type AND b.deleted_at IS NULL
                      AND b.embedding IS NOT NULL AND b.source_id > a.source_id AND b.chunk_no = 0
                    ORDER BY b.embedding <=> a.embedding LIMIT 3) nb
                WHERE a.tenant_id = CAST(:t AS uuid) AND a.source_type = :st AND a.deleted_at IS NULL
                  AND a.embedding IS NOT NULL AND a.chunk_no = 0 AND 1 - (a.embedding <=> nb.embedding) >= :th
                ORDER BY sim DESC LIMIT :limit"""),
                {"t": tenant, "st": source_type, "th": threshold, "limit": limit})).mappings().all()
        return [(r["a_id"], r["b_id"], float(r["sim"])) for r in rows]

    # ── graph ──
    async def replace_edges(self, tenant, origin_key, edges):
        async with self._tx(tenant) as c:
            await c.execute(text("DELETE FROM knowledge_edges WHERE tenant_id = CAST(:t AS uuid) AND origin_key = :o"),
                            {"t": tenant, "o": origin_key})
            for e in edges:
                await c.execute(text(
                    "INSERT INTO knowledge_edges (tenant_id, src_type, src_id, dst_type, dst_id, relation, weight, as_of, origin_key) "
                    "VALUES (CAST(:t AS uuid), :a, :b, :c, :d, :r, :w, :asof, :o) ON CONFLICT DO NOTHING"),
                    {"t": tenant, "a": e.src_type, "b": e.src_id, "c": e.dst_type, "d": e.dst_id, "r": e.relation,
                     "w": e.weight, "asof": e.as_of, "o": origin_key})

    async def delete_edges_by_origin(self, tenant, origin_key):
        async with self._tx(tenant) as c:
            await c.execute(text("DELETE FROM knowledge_edges WHERE tenant_id = CAST(:t AS uuid) AND origin_key = :o"),
                            {"t": tenant, "o": origin_key})

    async def traverse(self, tenant, start, depth, relations, limit):
        depth = max(1, min(int(depth), self.s.max_graph_depth))
        if not start:
            return []
        async with self._tx(tenant) as c:
            rows = (await c.execute(text(TRAVERSE_SQL), {
                "tenant_id": tenant, "seed_types": [a for a, _ in start], "seed_ids": [b for _, b in start],
                "depth": depth, "relations": relations or None, "limit": limit})).mappings().all()
        seeds = {tuple(s) for s in start}
        return [dict(r) for r in rows if (r["node_type"], r["node_id"]) not in seeds]

    # ── bookkeeping ──
    async def get_watermark(self, tenant, source):
        async with self._tx(tenant) as c:
            r = (await c.execute(text("SELECT last_ts, last_full_at, meta, updated_at FROM knowledge_watermarks "
                                      "WHERE tenant_id = CAST(:t AS uuid) AND source = :s"), {"t": tenant, "s": source})).mappings().first()
        return dict(r) if r else None

    async def set_watermark(self, tenant, source, last_ts, *, full=False, meta=None):
        async with self._tx(tenant) as c:
            await c.execute(text("""
                INSERT INTO knowledge_watermarks (tenant_id, source, last_ts, last_full_at, meta)
                VALUES (CAST(:t AS uuid), :s, :ts, CASE WHEN CAST(:full AS boolean) THEN now() END, CAST(:m AS jsonb))
                ON CONFLICT (tenant_id, source) DO UPDATE SET
                    last_ts = COALESCE(EXCLUDED.last_ts, knowledge_watermarks.last_ts),
                    last_full_at = CASE WHEN CAST(:full AS boolean) THEN now() ELSE knowledge_watermarks.last_full_at END,
                    meta = knowledge_watermarks.meta || EXCLUDED.meta, updated_at = now()"""),
                {"t": tenant, "s": source, "ts": last_ts, "full": full, "m": json.dumps(meta or {})})

    async def record_failure(self, tenant, source, source_ref, error):
        async with self._tx(tenant) as c:
            await c.execute(text("INSERT INTO knowledge_failures (tenant_id, source, source_ref, error) "
                                 "VALUES (CAST(:t AS uuid), :s, :r, :e)"),
                            {"t": tenant, "s": source, "r": source_ref, "e": error[:500]})
            await c.execute(text("DELETE FROM knowledge_failures WHERE tenant_id = CAST(:t AS uuid) AND id NOT IN "
                                 "(SELECT id FROM knowledge_failures WHERE tenant_id = CAST(:t AS uuid) ORDER BY id DESC LIMIT 200)"),
                            {"t": tenant})

    async def clear_failures(self, tenant, source):
        async with self._tx(tenant) as c:
            await c.execute(text("DELETE FROM knowledge_failures WHERE tenant_id = CAST(:t AS uuid) AND source = :s"),
                            {"t": tenant, "s": source})

    async def coverage(self, tenant):
        async with self._tx(tenant) as c:
            srcs = (await c.execute(text("""
                SELECT source_type, module, count(*) FILTER (WHERE deleted_at IS NULL) AS chunks,
                       count(*) FILTER (WHERE deleted_at IS NOT NULL) AS tombstoned, max(updated_at) AS last_indexed
                FROM knowledge_chunks WHERE tenant_id = CAST(:t AS uuid) GROUP BY source_type, module ORDER BY source_type"""),
                {"t": tenant})).mappings().all()
            wms = (await c.execute(text("SELECT source, last_ts, last_full_at, meta FROM knowledge_watermarks "
                                        "WHERE tenant_id = CAST(:t AS uuid) ORDER BY source"), {"t": tenant})).mappings().all()
            fails = (await c.execute(text("SELECT source, source_ref, error, created_at FROM knowledge_failures "
                                          "WHERE tenant_id = CAST(:t AS uuid) ORDER BY id DESC LIMIT 50"), {"t": tenant})).mappings().all()
        async with self.engine.begin() as c:
            q = (await c.execute(text("SELECT status, count(*) FROM knowledge_jobs WHERE tenant_id = CAST(:t AS uuid) "
                                      "AND status IN ('queued','running') GROUP BY status"), {"t": tenant})).all()
        queue = {"queued": 0, "running": 0, **{k: v for k, v in q}}
        return {"sources": [dict(r) for r in srcs], "watermarks": [dict(r) for r in wms],
                "failures": [dict(r) for r in fails], "queue": queue}

    async def enqueue_job(self, tenant, kind, params, requested_by=None):
        jid = str(uuid.uuid4())
        async with self.engine.begin() as c:
            await c.execute(text("INSERT INTO knowledge_jobs (id, tenant_id, kind, params, requested_by) "
                                 "VALUES (CAST(:i AS uuid), CAST(:t AS uuid), :k, CAST(:p AS jsonb), :u)"),
                            {"i": jid, "t": tenant, "k": kind, "p": json.dumps(params), "u": requested_by})
        return jid

    async def claim_job(self):
        async with self.engine.begin() as c:
            r = (await c.execute(text("""
                UPDATE knowledge_jobs SET status = 'running', started_at = now() WHERE id = (
                    SELECT id FROM knowledge_jobs WHERE status = 'queued' ORDER BY created_at
                    FOR UPDATE SKIP LOCKED LIMIT 1)
                RETURNING id, tenant_id, kind, params"""))).mappings().first()
        if not r:
            return None
        return {"id": str(r["id"]), "tenant_id": str(r["tenant_id"]), "kind": r["kind"], "params": r["params"] or {}}

    async def finish_job(self, job_id, status, result):
        async with self.engine.begin() as c:
            await c.execute(text("UPDATE knowledge_jobs SET status = :s, result = CAST(:r AS jsonb), finished_at = now() "
                                 "WHERE id = CAST(:i AS uuid)"), {"s": status, "r": json.dumps(result, default=str), "i": job_id})

    async def try_lock(self, name):
        key = zlib.crc32(name.encode()) & 0x7FFFFFFF
        conn = await self.engine.connect()          # session-level lock lives on this dedicated connection
        got = (await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key})).scalar()
        if got:
            self._lock_conns[name] = conn
            return True
        await conn.close()
        return False

    async def unlock(self, name):
        conn = self._lock_conns.pop(name, None)
        if conn is not None:
            key = zlib.crc32(name.encode()) & 0x7FFFFFFF
            try:
                await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
            finally:
                await conn.close()

    # ── erasure / retention ──
    async def erase(self, tenant, *, source_type=None, source_id=None, module=None):
        where = ["tenant_id = CAST(:t AS uuid)"]
        params: dict[str, Any] = {"t": tenant}
        for col, val in (("source_type", source_type), ("source_id", source_id), ("module", module)):
            if val is not None:
                where.append(f"{col} = :{col}")
                params[col] = val
        whole = source_type is None and source_id is None and module is None
        async with self._tx(tenant) as c:
            chunks = (await c.execute(text(f"DELETE FROM knowledge_chunks WHERE {' AND '.join(where)}"), params)).rowcount
            edges = 0
            if whole:
                edges = (await c.execute(text("DELETE FROM knowledge_edges WHERE tenant_id = CAST(:t AS uuid)"), {"t": tenant})).rowcount
                await c.execute(text("DELETE FROM knowledge_watermarks WHERE tenant_id = CAST(:t AS uuid)"), {"t": tenant})
                await c.execute(text("DELETE FROM knowledge_failures WHERE tenant_id = CAST(:t AS uuid)"), {"t": tenant})
            elif source_type and source_id:
                edges = (await c.execute(text("DELETE FROM knowledge_edges WHERE tenant_id = CAST(:t AS uuid) AND origin_key = :o"),
                                         {"t": tenant, "o": f"{source_type}:{source_id}"})).rowcount
        return {"chunks": chunks, "edges": edges}

    async def purge_tombstones(self, tenant, older_than):
        async with self._tx(tenant) as c:
            r = await c.execute(text("DELETE FROM knowledge_chunks WHERE tenant_id = CAST(:t AS uuid) AND deleted_at < :o"),
                                {"t": tenant, "o": older_than})
        return r.rowcount

    async def set_importance(self, tenant, source_type, source_id, importance):
        async with self._tx(tenant) as c:
            r = await c.execute(text("UPDATE knowledge_chunks SET importance = :i, updated_at = now() WHERE tenant_id = CAST(:t AS uuid) "
                                     "AND source_type = :st AND source_id = :sid AND deleted_at IS NULL"),
                                {"i": importance, "t": tenant, "st": source_type, "sid": source_id})
        return r.rowcount
