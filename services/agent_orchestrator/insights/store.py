"""Persistence: the briefing cache, the feedback log and the per-tenant daily LLM budget.

PgStore uses the orchestrator database (raw SQL, tables created on first use). If the database is unreachable the cache and
the budget degrade to process memory (the panel still works); feedback is NOT silently dropped: it raises StoreError so the
caller can tell the user it was not saved.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

from services.agent_orchestrator.insights import config

logger = logging.getLogger(__name__)


class StoreError(RuntimeError):
    pass


def cache_key(tenant: str, user: str, module: str, scope: str, roles_hash: str) -> str:
    return "|".join([tenant, user, module, scope or "-", roles_hash])


class MemoryStore:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}
        self.feedback: list[dict] = []
        self.budget: dict[tuple, int] = {}

    async def get(self, key: str) -> Optional[dict]:
        return self.docs.get(key)

    async def put(self, key: str, doc: dict, evidence_hash: str, tenant: str = "", user: str = "") -> None:
        self.docs[key] = {"doc": doc, "evidence_hash": evidence_hash, "generated_at": time.time(), "tenant": tenant, "user": user}

    async def get_by_id(self, insight_id: str, tenant: str, user: str) -> Optional[dict]:
        for row in self.docs.values():
            if row["doc"].get("id") == insight_id and row.get("tenant") == tenant and row.get("user") == user:
                return row["doc"]
        return None

    async def add_feedback(self, row: dict) -> None:
        self.feedback.append(dict(row))

    async def feedback_for(self, tenant: str, module: Optional[str] = None, limit: int = 200) -> list[dict]:
        rows = [r for r in self.feedback if r["tenant_id"] == tenant and (module is None or r["module"] == module)]
        return rows[-limit:]

    async def dismissed_rec_ids(self, tenant: str, user: str, module: str) -> set:
        return {r["rec_id"] for r in self.feedback if r["tenant_id"] == tenant and r["user_id"] == user
                and r["module"] == module and r.get("rec_id") and r["verdict"] in ("dismissed", "not_helpful")}

    async def take_budget(self, tenant: str, limit: int) -> bool:
        k = (tenant, date.today().isoformat())
        if self.budget.get(k, 0) >= limit:
            return False
        self.budget[k] = self.budget.get(k, 0) + 1
        return True


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS panel_insights (
        cache_key TEXT PRIMARY KEY, id UUID NOT NULL, tenant_id UUID NOT NULL, user_id TEXT NOT NULL, module TEXT NOT NULL,
        doc JSONB NOT NULL, evidence_hash TEXT NOT NULL, generated_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS ix_panel_insights_id ON panel_insights (id)",
    """CREATE TABLE IF NOT EXISTS panel_insight_feedback (
        id UUID PRIMARY KEY, tenant_id UUID NOT NULL, user_id TEXT NOT NULL, insight_id UUID, rec_id TEXT, module TEXT NOT NULL,
        verdict TEXT NOT NULL, note TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS ix_panel_insight_feedback_t ON panel_insight_feedback (tenant_id, module, created_at DESC)",
    """CREATE TABLE IF NOT EXISTS panel_insight_budget (
        tenant_id UUID NOT NULL, day DATE NOT NULL, calls INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (tenant_id, day))""",
]


class PgStore:
    def __init__(self) -> None:
        self._ready = False
        self._fallback = MemoryStore()

    async def _ensure(self) -> None:
        if self._ready:
            return
        from services.common.db import session_scope
        async with session_scope() as s:
            for stmt in SCHEMA:
                await s.execute(text(stmt))
        self._ready = True

    async def get(self, key: str) -> Optional[dict]:
        try:
            await self._ensure()
            from services.common.db import session_scope
            async with session_scope() as s:
                row = (await s.execute(text(
                    "SELECT doc, evidence_hash, extract(epoch from generated_at) AS ts FROM panel_insights WHERE cache_key = :k"),
                    {"k": key})).mappings().first()
            if row:
                doc = row["doc"] if isinstance(row["doc"], dict) else json.loads(row["doc"])
                return {"doc": doc, "evidence_hash": row["evidence_hash"], "generated_at": float(row["ts"])}
        except Exception as exc:  # noqa: BLE001
            logger.warning("insights cache read failed (%s); using memory", type(exc).__name__)
        return await self._fallback.get(key)

    async def put(self, key: str, doc: dict, evidence_hash: str, tenant: str = "", user: str = "") -> None:
        await self._fallback.put(key, doc, evidence_hash, tenant, user)
        try:
            await self._ensure()
            from services.common.db import session_scope
            async with session_scope() as s:
                await s.execute(text(
                    """INSERT INTO panel_insights (cache_key, id, tenant_id, user_id, module, doc, evidence_hash, generated_at)
                       VALUES (:k, CAST(:id AS uuid), CAST(:t AS uuid), :u, :m, CAST(:doc AS jsonb), :h, now())
                       ON CONFLICT (cache_key) DO UPDATE SET id = EXCLUDED.id, doc = EXCLUDED.doc,
                         evidence_hash = EXCLUDED.evidence_hash, generated_at = now()"""),
                    {"k": key, "id": doc["id"], "t": tenant, "u": user, "m": doc["module"], "doc": json.dumps(doc, default=str),
                     "h": evidence_hash})
        except Exception as exc:  # noqa: BLE001
            logger.warning("insights cache write failed (%s); kept in memory only", type(exc).__name__)

    async def get_by_id(self, insight_id: str, tenant: str, user: str) -> Optional[dict]:
        try:
            await self._ensure()
            from services.common.db import session_scope
            async with session_scope() as s:
                row = (await s.execute(text(
                    "SELECT doc FROM panel_insights WHERE id = CAST(:i AS uuid) AND tenant_id = CAST(:t AS uuid) AND user_id = :u"),
                    {"i": insight_id, "t": tenant, "u": user})).mappings().first()
            if row:
                return row["doc"] if isinstance(row["doc"], dict) else json.loads(row["doc"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("insights lookup failed (%s)", type(exc).__name__)
        return await self._fallback.get_by_id(insight_id, tenant, user)

    async def add_feedback(self, row: dict) -> None:
        await self._fallback.add_feedback(row)
        try:
            await self._ensure()
            from services.common.db import session_scope
            async with session_scope() as s:
                await s.execute(text(
                    """INSERT INTO panel_insight_feedback (id, tenant_id, user_id, insight_id, rec_id, module, verdict, note)
                       VALUES (CAST(:id AS uuid), CAST(:t AS uuid), :u, CAST(:i AS uuid), :r, :m, :v, :n)"""),
                    {"id": row["id"], "t": row["tenant_id"], "u": row["user_id"], "i": row.get("insight_id"),
                     "r": row.get("rec_id"), "m": row["module"], "v": row["verdict"], "n": row.get("note")})
        except Exception as exc:  # noqa: BLE001
            logger.error("insights feedback not stored: %s", exc)
            raise StoreError("feedback could not be stored") from exc

    async def feedback_for(self, tenant: str, module: Optional[str] = None, limit: int = 200) -> list[dict]:
        try:
            await self._ensure()
            from services.common.db import session_scope
            async with session_scope() as s:
                rows = (await s.execute(text(
                    """SELECT id::text, tenant_id::text, user_id, insight_id::text, rec_id, module, verdict, note, created_at
                       FROM panel_insight_feedback WHERE tenant_id = CAST(:t AS uuid) AND (:m IS NULL OR module = :m)
                       ORDER BY created_at DESC LIMIT :l"""), {"t": tenant, "m": module, "l": limit})).mappings().all()
            return [dict(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            logger.warning("insights feedback read failed (%s)", type(exc).__name__)
            return []

    async def dismissed_rec_ids(self, tenant: str, user: str, module: str) -> set:
        try:
            await self._ensure()
            from services.common.db import session_scope
            async with session_scope() as s:
                rows = (await s.execute(text(
                    """SELECT DISTINCT rec_id FROM panel_insight_feedback
                       WHERE tenant_id = CAST(:t AS uuid) AND user_id = :u AND module = :m AND rec_id IS NOT NULL
                         AND verdict IN ('dismissed', 'not_helpful') AND created_at > now() - interval '14 days'"""),
                    {"t": tenant, "u": user, "m": module})).all()
            return {r[0] for r in rows}
        except Exception as exc:  # noqa: BLE001
            logger.warning("insights dismissed lookup failed (%s)", type(exc).__name__)
            return await self._fallback.dismissed_rec_ids(tenant, user, module)

    async def take_budget(self, tenant: str, limit: int) -> bool:
        try:
            await self._ensure()
            from services.common.db import session_scope
            async with session_scope() as s:
                n = (await s.execute(text(
                    """INSERT INTO panel_insight_budget (tenant_id, day, calls) VALUES (CAST(:t AS uuid), CURRENT_DATE, 1)
                       ON CONFLICT (tenant_id, day) DO UPDATE SET calls = panel_insight_budget.calls + 1 RETURNING calls"""),
                    {"t": tenant})).scalar_one()
            return int(n) <= limit
        except Exception as exc:  # noqa: BLE001
            logger.warning("insights budget store unavailable (%s); counting in memory", type(exc).__name__)
            return await self._fallback.take_budget(tenant, limit)


_store: Any = None


def get_store() -> Any:
    global _store
    if _store is None:
        _store = MemoryStore() if config.store_kind() == "memory" else PgStore()
    return _store


def set_store(store: Any) -> None:    # tests
    global _store
    _store = store
