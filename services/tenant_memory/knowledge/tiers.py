"""Short-term (working) memory tier: per-session scratchpad with TTL, plus promotion rules.

Long-term tiers already exist and are unchanged: episodic = tenant_memory_entries, semantic =
tenant_memory_summaries, procedural = tenant_agent_skills (all embedded via the knowledge cards).
Working memory lives in the operational Postgres (tenant_memory_working) - not Redis, which is not
in this stack - and expires on its own; the consolidation job promotes what deserves to last.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import String, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from services.tenant_memory.knowledge.config import get_settings

PROMOTE_IMPORTANCE = {"high", "critical"}
PROMOTE_REPEATS = int(os.getenv("WORKING_PROMOTE_REPEATS", "3"))
NEVER_PROMOTE_KINDS = {"state", "context_ref"}     # task state and retrieved-context ids are session mechanics


def content_key(content: str) -> str:
    return hashlib.sha256(" ".join(content.lower().split()).encode()).hexdigest()[:32]


@dataclass
class PromotionRules:
    repeats: int = PROMOTE_REPEATS
    importances: frozenset = frozenset(PROMOTE_IMPORTANCE)


def promotion_reason(row: dict, rules: Optional[PromotionRules] = None) -> Optional[str]:
    """Why a working-memory item should become a durable entry, or None. Pure."""
    rules = rules or PromotionRules()
    if row.get("promoted_entry_id") or row.get("kind") in NEVER_PROMOTE_KINDS:
        return None
    if row.get("pinned"):
        return "pinned"
    if str(row.get("importance")) in rules.importances:
        return "importance"
    if int(row.get("repeat_count") or 1) >= rules.repeats:
        return "repetition"
    return None


async def add_working(session, tenant: str, session_key: str, content: str, *, kind: str = "note", module: Optional[str] = None,
                      title: Optional[str] = None, importance: str = "normal", pinned: bool = False,
                      metadata: Optional[dict] = None, user_id: Optional[str] = None, ttl_minutes: Optional[int] = None,
                      now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    ttl = ttl_minutes or get_settings().working_ttl_minutes
    expires = now + timedelta(minutes=ttl)
    key = content_key(content)
    if kind in ("note", "turn"):
        # Same fact seen again (any session of this tenant): count the repetition instead of storing a copy.
        row = (await session.execute(text("""
            UPDATE tenant_memory_working SET repeat_count = repeat_count + 1, expires_at = GREATEST(expires_at, :exp),
                   pinned = pinned OR :pinned, updated_at = now()
            WHERE id = (SELECT id FROM tenant_memory_working WHERE tenant_id = CAST(:t AS uuid) AND content_key = :k
                        AND kind = :kind AND expires_at > :now AND promoted_entry_id IS NULL ORDER BY created_at DESC LIMIT 1)
            RETURNING *"""), {"t": tenant, "k": key, "exp": expires, "pinned": pinned, "kind": kind, "now": now})).mappings().first()
        if row:
            return dict(row)
    row = (await session.execute(text("""
        INSERT INTO tenant_memory_working (id, tenant_id, session_key, kind, module, title, content, importance, pinned,
                                           content_key, metadata, created_by, expires_at)
        VALUES (CAST(:id AS uuid), CAST(:t AS uuid), :sk, :kind, :module, :title, :content, :imp, :pinned, :k, :meta, CAST(:uid AS uuid), :exp)
        RETURNING *""").bindparams(bindparam("meta", type_=JSONB)),
        {"id": str(uuid.uuid4()), "t": tenant, "sk": session_key, "kind": kind, "module": module, "title": title,
         "content": content, "imp": importance, "pinned": pinned, "k": key, "meta": metadata or {}, "uid": user_id,
         "exp": expires})).mappings().one()
    return dict(row)


async def get_session_items(session, tenant: str, session_key: str, limit: int = 50, now: Optional[datetime] = None) -> list[dict]:
    rows = (await session.execute(text("""
        SELECT * FROM (SELECT * FROM tenant_memory_working WHERE tenant_id = CAST(:t AS uuid) AND session_key = :sk
                       AND expires_at > :now ORDER BY created_at DESC LIMIT :lim) x ORDER BY created_at"""),
        {"t": tenant, "sk": session_key, "now": now or datetime.now(timezone.utc), "lim": limit})).mappings().all()
    return [dict(r) for r in rows]


async def clear_session(session, tenant: str, session_key: str) -> int:
    r = await session.execute(text("DELETE FROM tenant_memory_working WHERE tenant_id = CAST(:t AS uuid) AND session_key = :sk"),
                              {"t": tenant, "sk": session_key})
    return r.rowcount


async def pin_item(session, tenant: str, item_id: str, pinned: bool = True) -> bool:
    r = await session.execute(text("UPDATE tenant_memory_working SET pinned = :p, updated_at = now() "
                                   "WHERE id = CAST(:i AS uuid) AND tenant_id = CAST(:t AS uuid)"), {"p": pinned, "i": item_id, "t": tenant})
    return r.rowcount > 0


async def promote_working(session, tenant: str, now: Optional[datetime] = None, rules: Optional[PromotionRules] = None) -> dict:
    """Promote deserving live items into tenant_memory_entries (episodic), then delete expired leftovers."""
    now = now or datetime.now(timezone.utc)
    rows = (await session.execute(text("""
        SELECT * FROM tenant_memory_working WHERE tenant_id = CAST(:t AS uuid) AND promoted_entry_id IS NULL
        ORDER BY created_at LIMIT 500"""), {"t": tenant})).mappings().all()
    promoted = []
    for r in rows:
        r = dict(r)
        reason = promotion_reason(r, rules)
        if not reason:
            continue
        eid = str(uuid.uuid4())
        imp = r["importance"] if r["importance"] in PROMOTE_IMPORTANCE else "normal"
        await session.execute(text("""
            INSERT INTO tenant_memory_entries (id, tenant_id, source_type, source_id, module, scope_key, title, content, visibility,
                                               importance, tags, metadata, occurred_at)
            VALUES (CAST(:id AS uuid), CAST(:t AS uuid), 'working_memory', :sid, :module, :scope, :title, :content, 'tenant', :imp, :tags, :meta, :occ)
            """).bindparams(bindparam("tags", type_=ARRAY(String())), bindparam("meta", type_=JSONB)),
            {"id": eid, "t": tenant, "sid": str(r["id"]), "module": r.get("module"), "scope": f"session:{r['session_key']}"[:160],
             "title": (r.get("title") or r["content"][:80]).strip()[:240], "content": r["content"], "imp": imp,
             "tags": ["working-memory", f"promoted-{reason}"],
             "meta": {"promoted_reason": reason, "working_id": str(r["id"]), "repeat_count": r["repeat_count"]},
             "occ": r["created_at"] or now})
        await session.execute(text("UPDATE tenant_memory_working SET promoted_entry_id = CAST(:e AS uuid), expires_at = :exp WHERE id = CAST(:i AS uuid)"),
                              {"e": eid, "i": str(r["id"]), "exp": now + timedelta(hours=1)})
        promoted.append({"working_id": str(r["id"]), "entry_id": eid, "reason": reason})
    purged = (await session.execute(text("DELETE FROM tenant_memory_working WHERE tenant_id = CAST(:t AS uuid) AND expires_at <= :now"),
                                    {"t": tenant, "now": now})).rowcount
    return {"promoted": promoted, "expired_deleted": purged}
