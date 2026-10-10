"""pgvector/Postgres implementation of the DreamStore (same `knowledge_db`, same RLS pattern as the knowledge tables).

NOT exercised by the unit tests (SQLite has no pgvector); the DDL builder is a pure function that tests assert on, and
the SQL here is plain. Verify live per docs/dream-state.md before relying on it.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from services.tenant_memory.knowledge.kdata import Chunk
from services.tenant_memory.knowledge.dream.store import DreamStore, LOG_STATES, OPEN_STATES
from services.tenant_memory.knowledge.store_pg import (
    APP_ROLE, MIGRATION_LOCK_KEY, PgVectorStore, _CHUNK_COLS, _async_url, _row_to_chunk,
)

logger = logging.getLogger("knowledge.dream.store_pg")

DREAM_TABLES = ("dream_runs", "dream_findings", "dream_settings", "dream_jev_cache", "dream_card_state")

RUN_JSON = ("phases_requested", "phases_done", "phase_results", "state", "report", "errors", "counts")
RUN_PLAIN = ("run_date", "trigger", "dry_run", "status", "jev_calls", "jev_cost_usd", "health_score", "started_at", "finished_at", "requested_by")
FIND_JSON = ("detail", "action", "jev", "resolution")
FIND_PLAIN = ("run_id", "phase", "type", "severity", "status", "source_type", "source_id", "title", "dedupe_key", "occurrences",
              "auto_applied", "resolved_by", "resolved_at")


def migration_statements() -> list[str]:
    tenant_policy = "tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid"
    return [
        """CREATE TABLE IF NOT EXISTS dream_runs (
            id UUID PRIMARY KEY, tenant_id UUID NOT NULL, run_date DATE NOT NULL, trigger TEXT NOT NULL DEFAULT 'nightly',
            dry_run BOOLEAN NOT NULL DEFAULT false, status TEXT NOT NULL DEFAULT 'running',
            phases_requested JSONB NOT NULL DEFAULT '[]'::jsonb, phases_done JSONB NOT NULL DEFAULT '[]'::jsonb,
            phase_results JSONB NOT NULL DEFAULT '{}'::jsonb, state JSONB NOT NULL DEFAULT '{}'::jsonb,
            report JSONB NOT NULL DEFAULT '{}'::jsonb, errors JSONB NOT NULL DEFAULT '[]'::jsonb, counts JSONB NOT NULL DEFAULT '{}'::jsonb,
            jev_calls INT NOT NULL DEFAULT 0, jev_cost_usd NUMERIC(10,4) NOT NULL DEFAULT 0, health_score INT,
            requested_by TEXT, started_at TIMESTAMPTZ NOT NULL DEFAULT now(), finished_at TIMESTAMPTZ)""",
        "CREATE INDEX IF NOT EXISTS ix_dream_runs_tenant ON dream_runs (tenant_id, started_at DESC)",
        """CREATE TABLE IF NOT EXISTS dream_findings (
            id UUID PRIMARY KEY, tenant_id UUID NOT NULL, run_id UUID, phase TEXT, type TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info', status TEXT NOT NULL DEFAULT 'open', source_type TEXT, source_id TEXT,
            title TEXT NOT NULL, detail JSONB NOT NULL DEFAULT '{}'::jsonb, action JSONB, jev JSONB, resolution JSONB,
            dedupe_key TEXT, occurrences INT NOT NULL DEFAULT 1, auto_applied BOOLEAN NOT NULL DEFAULT false,
            first_seen TIMESTAMPTZ NOT NULL DEFAULT now(), last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
            resolved_by TEXT, resolved_at TIMESTAMPTZ)""",
        "CREATE INDEX IF NOT EXISTS ix_dream_findings_tenant ON dream_findings (tenant_id, status, severity, last_seen DESC)",
        "CREATE INDEX IF NOT EXISTS ix_dream_findings_key ON dream_findings (tenant_id, dedupe_key, last_seen DESC)",
        """CREATE TABLE IF NOT EXISTS dream_settings (
            tenant_id UUID PRIMARY KEY, settings JSONB NOT NULL DEFAULT '{}'::jsonb, updated_by TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
        """CREATE TABLE IF NOT EXISTS dream_jev_cache (
            tenant_id UUID NOT NULL, cache_key TEXT NOT NULL, result JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, cache_key))""",
        """CREATE TABLE IF NOT EXISTS dream_card_state (
            tenant_id UUID NOT NULL, source_type TEXT NOT NULL, source_id TEXT NOT NULL, state JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, source_type, source_id))""",
        *[stmt for t in DREAM_TABLES for stmt in (
            f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY",
            f"DROP POLICY IF EXISTS tenant_isolation ON {t}",
            f"CREATE POLICY tenant_isolation ON {t} USING ({tenant_policy}) WITH CHECK ({tenant_policy})",
        )],
        # Tables created after PgVectorStore.ensure_schema's blanket GRANT would otherwise be unreadable by the app role.
        f"""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
              GRANT SELECT, INSERT, UPDATE, DELETE ON {", ".join(DREAM_TABLES)} TO {APP_ROLE}; END IF; END $$""",
    ]


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def _ts(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    return str(v)


def _run(r: Any) -> dict:
    d = dict(r)
    for k in RUN_JSON:
        d[k] = _j(d.get(k))
    d["id"], d["tenant_id"] = str(d["id"]), str(d["tenant_id"])
    d["run_date"] = d["run_date"].isoformat() if isinstance(d["run_date"], date) else str(d["run_date"])
    d["jev_cost_usd"] = float(d.get("jev_cost_usd") or 0)
    d["started_at"], d["finished_at"] = _ts(d.get("started_at")), _ts(d.get("finished_at"))
    return d


def _finding(r: Any) -> dict:
    d = dict(r)
    for k in FIND_JSON:
        d[k] = _j(d.get(k))
    d["id"], d["tenant_id"] = str(d["id"]), str(d["tenant_id"])
    d["run_id"] = str(d["run_id"]) if d.get("run_id") else None
    for k in ("first_seen", "last_seen", "resolved_at"):
        d[k] = _ts(d.get(k))
    return d


class PgDreamStore(DreamStore):
    def __init__(self, kstore: PgVectorStore):
        self.kstore = kstore
        self.s = kstore.s

    def _tx(self, tenant: Optional[str] = None):
        return self.kstore._tx(tenant)

    async def ensure_schema(self) -> None:
        admin = self.kstore._admin_url or os.getenv("KNOWLEDGE_DB_ADMIN_URL", "") or self.s.knowledge_db_url
        engine = create_async_engine(_async_url(admin))
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": MIGRATION_LOCK_KEY})
                for stmt in migration_statements():
                    await conn.execute(text(stmt))
        finally:
            await engine.dispose()

    # ── runs ──
    async def create_run(self, tenant, run):
        rid = run.get("id") or str(uuid.uuid4())
        cols = {"id": rid, "tenant_id": tenant}
        for k in RUN_PLAIN:
            if k in run and run[k] is not None:
                cols[k] = run[k]
        for k in RUN_JSON:
            if k in run:
                cols[k] = json.dumps(run[k], default=str)
        names = list(cols)
        casts = {"id": "CAST(:id AS uuid)", "tenant_id": "CAST(:tenant_id AS uuid)", "run_date": "CAST(:run_date AS date)",
                 "started_at": "CAST(:started_at AS timestamptz)", "finished_at": "CAST(:finished_at AS timestamptz)",
                 **{k: f"CAST(:{k} AS jsonb)" for k in RUN_JSON}}
        sql = f"INSERT INTO dream_runs ({', '.join(names)}) VALUES ({', '.join(casts.get(n, ':' + n) for n in names)}) RETURNING *"
        async with self._tx(tenant) as c:
            r = (await c.execute(text(sql), cols)).mappings().one()
        return _run(r)

    async def update_run(self, tenant, run_id, patch):
        sets, params = [], {"t": tenant, "i": run_id}
        for k, v in patch.items():
            if k in RUN_JSON:
                sets.append(f"{k} = CAST(:{k} AS jsonb)")
                params[k] = json.dumps(v, default=str)
            elif k in RUN_PLAIN:
                sets.append(f"{k} = CAST(:{k} AS timestamptz)" if k in ("started_at", "finished_at") else f"{k} = :{k}")
                params[k] = v
        if not sets:
            return await self.get_run(tenant, run_id) or {}
        async with self._tx(tenant) as c:
            r = (await c.execute(text(f"UPDATE dream_runs SET {', '.join(sets)} WHERE tenant_id = CAST(:t AS uuid) "
                                      "AND id = CAST(:i AS uuid) RETURNING *"), params)).mappings().first()
        return _run(r) if r else {}

    async def get_run(self, tenant, run_id):
        async with self._tx(tenant) as c:
            r = (await c.execute(text("SELECT * FROM dream_runs WHERE tenant_id = CAST(:t AS uuid) AND id = CAST(:i AS uuid)"),
                                 {"t": tenant, "i": run_id})).mappings().first()
        return _run(r) if r else None

    async def list_runs(self, tenant, limit=30, include_dry=True):
        async with self._tx(tenant) as c:
            rows = (await c.execute(text("SELECT * FROM dream_runs WHERE tenant_id = CAST(:t AS uuid) "
                                         "AND (CAST(:dry AS boolean) OR NOT dry_run) ORDER BY started_at DESC LIMIT :n"),
                                    {"t": tenant, "dry": include_dry, "n": limit})).mappings().all()
        return [_run(r) for r in rows]

    async def find_resumable(self, tenant, run_date):
        async with self._tx(tenant) as c:
            r = (await c.execute(text("SELECT * FROM dream_runs WHERE tenant_id = CAST(:t AS uuid) AND run_date = CAST(:d AS date) "
                                      "AND NOT dry_run AND status IN ('running','interrupted') ORDER BY started_at DESC LIMIT 1"),
                                 {"t": tenant, "d": run_date})).mappings().first()
        return _run(r) if r else None

    async def nightly_done(self, tenant, run_date):
        async with self._tx(tenant) as c:
            r = (await c.execute(text("SELECT 1 FROM dream_runs WHERE tenant_id = CAST(:t AS uuid) AND run_date = CAST(:d AS date) "
                                      "AND NOT dry_run AND trigger = 'nightly' AND status IN ('completed','completed_with_errors','aborted') LIMIT 1"),
                                 {"t": tenant, "d": run_date})).first()
        return r is not None

    # ── findings ──
    async def upsert_finding(self, tenant, f):
        key = f.get("dedupe_key")
        async with self._tx(tenant) as c:
            cur = None
            if key:
                cur = (await c.execute(text("SELECT * FROM dream_findings WHERE tenant_id = CAST(:t AS uuid) AND dedupe_key = :k "
                                            "ORDER BY last_seen DESC LIMIT 1 FOR UPDATE"), {"t": tenant, "k": key})).mappings().first()
            if cur is not None:
                cur = _finding(cur)
                if cur["status"] in ("dismissed", "accepted"):
                    r = (await c.execute(text("UPDATE dream_findings SET occurrences = occurrences + 1, last_seen = now() "
                                              "WHERE id = CAST(:i AS uuid) RETURNING *"), {"i": cur["id"]})).mappings().one()
                    return _finding(r)
                if cur["status"] in LOG_STATES:
                    status = cur["status"] if (cur["status"] == "open" and f.get("status") == "proposed") else (f.get("status") or cur["status"])
                    r = (await c.execute(text("""UPDATE dream_findings SET run_id = CAST(:run AS uuid), severity = :sev, title = :title,
                        detail = CAST(:detail AS jsonb), action = CAST(:action AS jsonb), jev = CAST(:jev AS jsonb), status = :status,
                        auto_applied = :auto, occurrences = occurrences + 1, last_seen = now() WHERE id = CAST(:i AS uuid) RETURNING *"""),
                        {"run": f.get("run_id"), "sev": f.get("severity", cur["severity"]), "title": f.get("title", cur["title"])[:300],
                         "detail": json.dumps(f.get("detail", cur["detail"]), default=str),
                         "action": json.dumps(f.get("action", cur["action"]), default=str),
                         "jev": json.dumps(f.get("jev", cur["jev"]), default=str), "status": status,
                         "auto": bool(f.get("auto_applied", cur["auto_applied"])), "i": cur["id"]})).mappings().one()
                    return _finding(r)
            fid = f.get("id") or str(uuid.uuid4())
            r = (await c.execute(text("""INSERT INTO dream_findings (id, tenant_id, run_id, phase, type, severity, status, source_type, source_id,
                    title, detail, action, jev, dedupe_key, auto_applied) VALUES (CAST(:i AS uuid), CAST(:t AS uuid), CAST(:run AS uuid),
                    :phase, :type, :sev, :status, :st, :sid, :title, CAST(:detail AS jsonb), CAST(:action AS jsonb), CAST(:jev AS jsonb),
                    :key, :auto) RETURNING *"""),
                {"i": fid, "t": tenant, "run": f.get("run_id"), "phase": f.get("phase"), "type": f["type"], "sev": f.get("severity", "info"),
                 "status": f.get("status", "open"), "st": f.get("source_type"), "sid": f.get("source_id"), "title": f["title"][:300],
                 "detail": json.dumps(f.get("detail") or {}, default=str), "action": json.dumps(f.get("action"), default=str),
                 "jev": json.dumps(f.get("jev"), default=str), "key": key, "auto": bool(f.get("auto_applied"))})).mappings().one()
        return _finding(r)

    async def list_findings(self, tenant, *, status=None, severity=None, phase=None, type=None, run_id=None, limit=100):
        where, params = ["tenant_id = CAST(:t AS uuid)"], {"t": tenant, "n": limit}
        for col, val in (("status", status), ("severity", severity), ("phase", phase), ("type", type)):
            if val is not None:
                where.append(f"{col} = :{col}")
                params[col] = val
        if run_id is not None:
            where.append("run_id = CAST(:run AS uuid)")
            params["run"] = run_id
        sql = (f"SELECT * FROM dream_findings WHERE {' AND '.join(where)} ORDER BY CASE severity WHEN 'critical' THEN 4 WHEN 'high' THEN 3 "
               "WHEN 'medium' THEN 2 WHEN 'low' THEN 1 ELSE 0 END DESC, last_seen DESC LIMIT :n")
        async with self._tx(tenant) as c:
            rows = (await c.execute(text(sql), params)).mappings().all()
        return [_finding(r) for r in rows]

    async def get_finding(self, tenant, fid):
        async with self._tx(tenant) as c:
            r = (await c.execute(text("SELECT * FROM dream_findings WHERE tenant_id = CAST(:t AS uuid) AND id = CAST(:i AS uuid)"),
                                 {"t": tenant, "i": fid})).mappings().first()
        return _finding(r) if r else None

    async def update_finding(self, tenant, fid, patch):
        sets, params = [], {"t": tenant, "i": fid}
        for k, v in patch.items():
            if k in FIND_JSON:
                sets.append(f"{k} = CAST(:{k} AS jsonb)")
                params[k] = json.dumps(v, default=str)
            elif k in FIND_PLAIN:
                sets.append(f"{k} = CAST(:{k} AS timestamptz)" if k == "resolved_at" else f"{k} = :{k}")
                params[k] = v
        if not sets:
            return await self.get_finding(tenant, fid)
        async with self._tx(tenant) as c:
            r = (await c.execute(text(f"UPDATE dream_findings SET {', '.join(sets)} WHERE tenant_id = CAST(:t AS uuid) "
                                      "AND id = CAST(:i AS uuid) RETURNING *"), params)).mappings().first()
        return _finding(r) if r else None

    async def finding_counts(self, tenant):
        async with self._tx(tenant) as c:
            rows = (await c.execute(text("SELECT severity, count(*) AS n FROM dream_findings WHERE tenant_id = CAST(:t AS uuid) "
                                         "AND status IN ('open','proposed') GROUP BY severity"), {"t": tenant})).all()
        out = {k: int(v) for k, v in rows}
        return {"open": out, "total_open": sum(out.values())}

    # ── settings / cache / state ──
    async def get_settings(self, tenant):
        async with self._tx(tenant) as c:
            r = (await c.execute(text("SELECT settings FROM dream_settings WHERE tenant_id = CAST(:t AS uuid)"), {"t": tenant})).first()
        return _j(r[0]) if r else {}

    async def put_settings(self, tenant, settings, by):
        async with self._tx(tenant) as c:
            await c.execute(text("""INSERT INTO dream_settings (tenant_id, settings, updated_by) VALUES (CAST(:t AS uuid), CAST(:s AS jsonb), :by)
                ON CONFLICT (tenant_id) DO UPDATE SET settings = EXCLUDED.settings, updated_by = EXCLUDED.updated_by, updated_at = now()"""),
                {"t": tenant, "s": json.dumps(settings), "by": by})
        return settings

    async def cache_get(self, tenant, key):
        async with self._tx(tenant) as c:
            r = (await c.execute(text("SELECT result FROM dream_jev_cache WHERE tenant_id = CAST(:t AS uuid) AND cache_key = :k "
                                      "AND created_at > now() - interval '30 days'"), {"t": tenant, "k": key})).first()
        return _j(r[0]) if r else None

    async def cache_put(self, tenant, key, result):
        async with self._tx(tenant) as c:
            await c.execute(text("""INSERT INTO dream_jev_cache (tenant_id, cache_key, result) VALUES (CAST(:t AS uuid), :k, CAST(:r AS jsonb))
                ON CONFLICT (tenant_id, cache_key) DO UPDATE SET result = EXCLUDED.result, created_at = now()"""),
                {"t": tenant, "k": key, "r": json.dumps(result, default=str)})

    async def get_card_state(self, tenant, source_type, source_id):
        async with self._tx(tenant) as c:
            r = (await c.execute(text("SELECT state FROM dream_card_state WHERE tenant_id = CAST(:t AS uuid) AND source_type = :st "
                                      "AND source_id = :sid"), {"t": tenant, "st": source_type, "sid": source_id})).first()
        return _j(r[0]) if r else None

    async def put_card_state(self, tenant, source_type, source_id, state):
        async with self._tx(tenant) as c:
            await c.execute(text("""INSERT INTO dream_card_state (tenant_id, source_type, source_id, state) VALUES
                (CAST(:t AS uuid), :st, :sid, CAST(:s AS jsonb)) ON CONFLICT (tenant_id, source_type, source_id)
                DO UPDATE SET state = EXCLUDED.state, updated_at = now()"""),
                {"t": tenant, "st": source_type, "sid": source_id, "s": json.dumps(state, default=str)})

    # ── chunk-level maintenance ──
    def _chunks(self, rows, with_embedding: bool) -> list[Chunk]:
        out = []
        for r in rows:
            ch = _row_to_chunk(r)
            if with_embedding and r.get("emb"):
                ch.embedding = json.loads(r["emb"])
            out.append(ch)
        return out

    async def scan_cards(self, tenant, after, limit, *, with_embedding=False, first_chunk_only=True):
        cols = _CHUNK_COLS + (", embedding::text AS emb" if with_embedding else "")
        cond = ["tenant_id = CAST(:t AS uuid)", "deleted_at IS NULL"]
        params: dict[str, Any] = {"t": tenant, "n": limit}
        if first_chunk_only:
            cond.append("chunk_no = 0")
        if after is not None:
            cond.append("(source_type, source_id, chunk_no) > (:a, :b, :c)")
            params.update(a=after[0], b=after[1], c=int(after[2]))
        sql = f"SELECT {cols} FROM knowledge_chunks WHERE {' AND '.join(cond)} ORDER BY source_type, source_id, chunk_no LIMIT :n"
        async with self._tx(tenant) as c:
            rows = (await c.execute(text(sql), params)).mappings().all()
        return self._chunks(rows, with_embedding)

    async def get_chunks(self, tenant, source_type, source_id):
        sql = (f"SELECT {_CHUNK_COLS}, embedding::text AS emb FROM knowledge_chunks WHERE tenant_id = CAST(:t AS uuid) AND source_type = :st "
               "AND source_id = :sid AND deleted_at IS NULL ORDER BY chunk_no")
        async with self._tx(tenant) as c:
            rows = (await c.execute(text(sql), {"t": tenant, "st": source_type, "sid": source_id})).mappings().all()
        return self._chunks(rows, True)

    async def top_cards(self, tenant, n):
        sql = (f"SELECT {_CHUNK_COLS} FROM knowledge_chunks WHERE tenant_id = CAST(:t AS uuid) AND deleted_at IS NULL AND chunk_no = 0 "
               "AND visibility <> 'private' ORDER BY importance DESC, source_type, source_id LIMIT :n")
        async with self._tx(tenant) as c:
            rows = (await c.execute(text(sql), {"t": tenant, "n": n})).mappings().all()
        return self._chunks(rows, False)

    async def count_cards(self, tenant):
        async with self._tx(tenant) as c:
            tot = (await c.execute(text("""SELECT count(*) FILTER (WHERE deleted_at IS NULL) AS live_chunks,
                count(DISTINCT (source_type, source_id)) FILTER (WHERE deleted_at IS NULL) AS live_sources,
                count(*) FILTER (WHERE deleted_at IS NOT NULL) AS tombstoned,
                count(*) FILTER (WHERE deleted_at IS NULL AND chunk_no = 0 AND 'dream:stale' = ANY(tags)) AS stale_tagged
                FROM knowledge_chunks WHERE tenant_id = CAST(:t AS uuid)"""), {"t": tenant})).mappings().one()
            models = (await c.execute(text("SELECT coalesce(embedding_model,'none') AS m, count(*) FROM knowledge_chunks "
                                           "WHERE tenant_id = CAST(:t AS uuid) AND deleted_at IS NULL GROUP BY 1"), {"t": tenant})).all()
            types = (await c.execute(text("SELECT source_type, count(*) FROM knowledge_chunks WHERE tenant_id = CAST(:t AS uuid) "
                                          "AND deleted_at IS NULL AND chunk_no = 0 GROUP BY 1"), {"t": tenant})).all()
        return {**{k: int(v) for k, v in tot.items()}, "models": {m: int(n) for m, n in models}, "source_types": {t: int(n) for t, n in types}}

    async def find_stale(self, tenant, source_type, cutoff, tag, limit):
        async with self._tx(tenant) as c:
            rows = (await c.execute(text("SELECT source_type, source_id, as_of FROM knowledge_chunks WHERE tenant_id = CAST(:t AS uuid) "
                                         "AND source_type = :st AND chunk_no = 0 AND deleted_at IS NULL AND as_of IS NOT NULL AND as_of < :cut "
                                         "AND NOT (CAST(:tag AS text) = ANY(tags)) ORDER BY as_of, source_id LIMIT :n"),
                                    {"t": tenant, "st": source_type, "cut": cutoff, "tag": tag, "n": limit})).all()
        return [(r[0], r[1], r[2]) for r in rows]

    async def tagged(self, tenant, tag, limit):
        async with self._tx(tenant) as c:
            rows = (await c.execute(text("SELECT source_type, source_id, as_of FROM knowledge_chunks WHERE tenant_id = CAST(:t AS uuid) "
                                         "AND chunk_no = 0 AND deleted_at IS NULL AND CAST(:tag AS text) = ANY(tags) ORDER BY source_type, source_id LIMIT :n"),
                                    {"t": tenant, "tag": tag, "n": limit})).all()
        return [(r[0], r[1], r[2]) for r in rows]

    async def tag_source(self, tenant, source_type, source_id, add, remove):
        n = 0
        async with self._tx(tenant) as c:
            for tag in remove:
                n += (await c.execute(text("UPDATE knowledge_chunks SET tags = array_remove(tags, CAST(:tag AS text)) WHERE tenant_id = CAST(:t AS uuid) "
                                           "AND source_type = :st AND source_id = :sid AND deleted_at IS NULL AND CAST(:tag AS text) = ANY(tags)"),
                                      {"t": tenant, "st": source_type, "sid": source_id, "tag": tag})).rowcount
            for tag in add:
                n += (await c.execute(text("UPDATE knowledge_chunks SET tags = array_append(tags, CAST(:tag AS text)) WHERE tenant_id = CAST(:t AS uuid) "
                                           "AND source_type = :st AND source_id = :sid AND deleted_at IS NULL AND NOT (CAST(:tag AS text) = ANY(tags))"),
                                      {"t": tenant, "st": source_type, "sid": source_id, "tag": tag})).rowcount
        return n

    async def set_embedding(self, tenant, source_type, source_id, chunk_no, embedding, model, content_hash):
        from services.tenant_memory.knowledge.store import vector_literal
        async with self._tx(tenant) as c:
            r = await c.execute(text("UPDATE knowledge_chunks SET embedding = CAST(:e AS vector), embedding_model = :m, content_hash = :h, "
                                     "updated_at = now() WHERE tenant_id = CAST(:t AS uuid) AND source_type = :st AND source_id = :sid "
                                     "AND chunk_no = :cn AND deleted_at IS NULL"),
                                {"e": vector_literal(embedding), "m": model, "h": content_hash, "t": tenant, "st": source_type,
                                 "sid": source_id, "cn": chunk_no})
        return r.rowcount > 0

    async def edge_origins(self, tenant):
        async with self._tx(tenant) as c:
            rows = (await c.execute(text("SELECT DISTINCT origin_key FROM knowledge_edges WHERE tenant_id = CAST(:t AS uuid)"), {"t": tenant})).all()
        return {r[0] for r in rows}

    async def dangling_edges(self, tenant, types, limit):
        async with self._tx(tenant) as c:
            rows = (await c.execute(text("""SELECT e.origin_key, e.dst_type, e.dst_id FROM knowledge_edges e
                WHERE e.tenant_id = CAST(:t AS uuid) AND e.dst_type = ANY(CAST(:types AS text[])) AND NOT EXISTS (
                    SELECT 1 FROM knowledge_chunks c WHERE c.tenant_id = e.tenant_id AND c.source_type = e.dst_type
                    AND c.source_id = e.dst_id AND c.deleted_at IS NULL) LIMIT :n"""),
                                    {"t": tenant, "types": list(types), "n": limit})).all()
        return [(r[0], r[1], r[2]) for r in rows]
