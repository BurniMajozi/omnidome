"""Persistence for skills: idempotent migration, platform seed, queries (docs/skills.md)."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from sqlalchemy import String, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from services.tenant_memory.skills import access
from services.tenant_memory.skills.spec import SkillSpec

logger = logging.getLogger("tenant_memory.skills")

LOCK_KEY = 727401  # pg_advisory_xact_lock key for the skills migration/seed

MIGRATION_STATEMENTS = [
    "ALTER TABLE tenant_agent_skills ALTER COLUMN tenant_id DROP NOT NULL",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS slug VARCHAR(80)",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS scope VARCHAR(12) NOT NULL DEFAULT 'tenant'",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS status VARCHAR(12) NOT NULL DEFAULT 'active'",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS owner_user_id UUID",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS visibility_roles TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS tools_optional TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS inputs JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS triggers TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS examples JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS safety_class VARCHAR(12) NOT NULL DEFAULT 'read_only'",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS changelog TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS forked_from_id UUID",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS forked_from_version VARCHAR(20)",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS content_hash VARCHAR(40)",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS created_by UUID",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS usage_count INT NOT NULL DEFAULT 0",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS helpful_count INT NOT NULL DEFAULT 0",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS unhelpful_count INT NOT NULL DEFAULT 0",
    "ALTER TABLE tenant_agent_skills ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMP WITH TIME ZONE",
    # Backfill rows written before this migration (slug IS NULL marks them): keep status in step with is_active.
    "UPDATE tenant_agent_skills SET status = CASE WHEN is_active THEN 'active' ELSE 'deprecated' END WHERE slug IS NULL",
    ("UPDATE tenant_agent_skills SET slug = COALESCE(NULLIF(trim(both '-' from lower(regexp_replace(skill_name, '[^a-zA-Z0-9]+', '-', 'g'))), ''), 'skill'), "
     "scope = 'tenant' WHERE slug IS NULL"),
    # Personal skills of different people may share a name, so the old (tenant, name, version) constraint goes.
    "ALTER TABLE tenant_agent_skills DROP CONSTRAINT IF EXISTS tenant_agent_skills_tenant_id_skill_name_version_key",
    ("CREATE UNIQUE INDEX IF NOT EXISTS uq_skills_tenant_slug_version ON tenant_agent_skills "
     "(tenant_id, slug, version, COALESCE(owner_user_id, '00000000-0000-0000-0000-000000000000'::uuid)) WHERE tenant_id IS NOT NULL"),
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_skills_platform_slug_version ON tenant_agent_skills (slug, version) WHERE tenant_id IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_skills_tenant_slug ON tenant_agent_skills (tenant_id, slug)",
    "CREATE INDEX IF NOT EXISTS idx_skills_scope_status ON tenant_agent_skills (scope, status)",
    """CREATE TABLE IF NOT EXISTS tenant_agent_skill_usage (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        skill_id UUID NOT NULL REFERENCES tenant_agent_skills(id) ON DELETE CASCADE,
        tenant_id UUID NOT NULL,
        user_id UUID,
        agent_type VARCHAR(80),
        run_id VARCHAR(80),
        outcome VARCHAR(20) NOT NULL DEFAULT 'selected',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_skill_usage_skill ON tenant_agent_skill_usage (skill_id, created_at DESC)",
]

_ARRAYS = ("target_agent_types", "tools_required", "tools_optional", "triggers", "tags", "visibility_roles")


def _bind(sql: str, *extra_arrays: str):
    stmt = text(sql)
    names = set(_ARRAYS) | set(extra_arrays)
    binds = [bindparam(n, type_=ARRAY(String())) for n in names if f":{n}" in sql]
    binds += [bindparam(n, type_=JSONB) for n in ("inputs", "examples", "protocol_schema", "metadata") if f":{n}" in sql]
    return stmt.bindparams(*binds)


# -- migration + seed -----------------------------------------------------------

async def ensure_schema(session: AsyncSession) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK_KEY})
    for stmt in MIGRATION_STATEMENTS:
        await session.execute(text(stmt))


INSERT_SQL = """
INSERT INTO tenant_agent_skills (
    id, tenant_id, slug, skill_name, description, category, source_agent_type, target_agent_types, protocol_schema,
    tools_required, tools_optional, guidance_prompt, version, metadata, is_active, status, scope, owner_user_id,
    visibility_roles, inputs, triggers, examples, tags, safety_class, changelog, forked_from_id, forked_from_version,
    content_hash, created_by)
VALUES (
    :id, :tenant_id, :slug, :skill_name, :description, :category, :source_agent_type, :target_agent_types, '{}'::jsonb,
    :tools_required, :tools_optional, :instructions, :version, :metadata, :is_active, :status, :scope, :owner_user_id,
    :visibility_roles, :inputs, :triggers, :examples, :tags, :safety_class, :changelog, :forked_from_id, :forked_from_version,
    :content_hash, :created_by)
"""


def _insert_params(spec: SkillSpec, *, tenant_id, scope: str, status: str, owner_user_id=None, created_by=None,
                   forked_from_id=None, forked_from_version=None, metadata: Optional[dict] = None) -> dict:
    data = spec.model_dump()
    return {
        "id": uuid.uuid4(), "tenant_id": tenant_id, "slug": data["slug"], "skill_name": data["skill_name"],
        "description": data["description"], "category": data["category"], "source_agent_type": data["source_agent_type"],
        "target_agent_types": data["target_agent_types"], "tools_required": data["tools_required"],
        "tools_optional": data["tools_optional"], "instructions": data["instructions"], "version": data["version"],
        "metadata": metadata or {}, "is_active": status == "active", "status": status, "scope": scope,
        "owner_user_id": owner_user_id, "visibility_roles": data["visibility_roles"], "inputs": data["inputs"],
        "triggers": data["triggers"], "examples": data["examples"], "tags": data["tags"],
        "safety_class": data["safety_class"], "changelog": data["changelog"], "forked_from_id": forked_from_id,
        "forked_from_version": forked_from_version, "content_hash": spec.content_hash(), "created_by": created_by,
    }


async def insert_skill(session: AsyncSession, spec: SkillSpec, **kw) -> dict:
    params = _insert_params(spec, **kw)
    await session.execute(_bind(INSERT_SQL), params)
    row = (await session.execute(text("SELECT * FROM tenant_agent_skills WHERE id = :id"), {"id": params["id"]})).mappings().one()
    return dict(row)


async def seed_platform(session: AsyncSession) -> dict:
    """Load the shipped library as platform skills. Idempotent: one row per (slug, version); older active
    versions of a slug are deprecated when a newer one is seeded."""
    from services.tenant_memory.skills.library import library
    added = skipped = 0
    for item in library():
        spec = SkillSpec.model_validate({**item, "source_agent_type": "platform", "changelog": item.get("changelog") or "Platform library"})
        exists = (await session.execute(
            text("SELECT id FROM tenant_agent_skills WHERE tenant_id IS NULL AND slug = :s AND version = :v"),
            {"s": spec.slug, "v": spec.version})).first()
        if exists:
            skipped += 1
            continue
        await insert_skill(session, spec, tenant_id=None, scope="platform", status="active", metadata={"library": True})
        await session.execute(text(
            "UPDATE tenant_agent_skills SET status = 'deprecated', is_active = false, updated_at = current_timestamp "
            "WHERE tenant_id IS NULL AND slug = :s AND version <> :v AND status = 'active'"), {"s": spec.slug, "v": spec.version})
        added += 1
    return {"added": added, "unchanged": skipped}


async def bootstrap(session_scope) -> dict:
    """Migrate then seed, in one transaction under an advisory lock. Never raises (the service must still start)."""
    try:
        async with session_scope() as session:
            await ensure_schema(session)
            return await seed_platform(session)
    except Exception as exc:  # noqa: BLE001
        logger.warning("skills migration/seed skipped: %s", exc)
        return {"error": str(exc)}


# -- reading --------------------------------------------------------------------

def semver_key(v: str) -> tuple:
    try:
        return tuple(int(p) for p in str(v).split("."))
    except ValueError:
        return (0, 0, 0)


def bump_patch(v: str) -> str:
    a = list(semver_key(v)) + [0, 0, 0]
    return f"{a[0]}.{a[1]}.{a[2] + 1}"


def to_read(row: dict, *, caller: Optional[dict] = None) -> dict:
    """Row dict -> API shape (keeps the legacy field names too)."""
    r = dict(row)
    r["instructions"] = r.get("guidance_prompt")
    r["status"] = r.get("status") or ("active" if r.get("is_active", True) else "deprecated")
    r["scope"] = r.get("scope") or "tenant"
    for k in ("target_agent_types", "tools_required", "tools_optional", "triggers", "tags", "visibility_roles"):
        r[k] = list(r.get(k) or [])
    for k in ("inputs", "examples"):
        v = r.get(k)
        r[k] = json.loads(v) if isinstance(v, str) else (v or [])
    r["protocol_schema"] = r.get("protocol_schema") or {}
    r["metadata"] = r.get("metadata") or {}
    r["slug"] = r.get("slug") or r.get("skill_name")
    for k in ("usage_count", "helpful_count", "unhelpful_count"):
        r[k] = int(r.get(k) or 0)
    r["changelog"] = r.get("changelog") or ""
    r["safety_class"] = r.get("safety_class") or "read_only"
    if caller:
        r["can_edit"] = access.can_edit(r, **caller["perm"])
        r["can_publish"] = access.can_publish(r, **caller["perm"])
    return r


def latest_versions(rows: list[dict]) -> list[dict]:
    """One row per (tenant, owner, slug): the highest version. Older versions are history."""
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (str(r.get("tenant_id")), str(r.get("owner_user_id")), r.get("slug") or r.get("skill_name"), r.get("scope"))
        cur = best.get(key)
        if cur is None or semver_key(r["version"]) > semver_key(cur["version"]):
            best[key] = r
    return list(best.values())


async def fetch_candidates(session: AsyncSession, tenant_id) -> list[dict]:
    res = await session.execute(
        text("SELECT * FROM tenant_agent_skills WHERE tenant_id = :t OR tenant_id IS NULL ORDER BY updated_at DESC"),
        {"t": tenant_id})
    return [dict(r) for r in res.mappings().all()]


async def get_row(session: AsyncSession, skill_id) -> Optional[dict]:
    row = (await session.execute(text("SELECT * FROM tenant_agent_skills WHERE id = :id"), {"id": skill_id})).mappings().first()
    return dict(row) if row else None


async def set_status(session: AsyncSession, row: dict, status: str) -> dict:
    """Activate / deprecate. Activating a version deprecates the other active versions of the same slug and owner."""
    if status == "active":
        await session.execute(text(
            "UPDATE tenant_agent_skills SET status = 'deprecated', is_active = false, updated_at = current_timestamp "
            "WHERE slug = :s AND id <> :id AND status = 'active' AND tenant_id IS NOT DISTINCT FROM :t "
            "AND owner_user_id IS NOT DISTINCT FROM :o AND scope = :sc"),
            {"s": row["slug"], "id": row["id"], "t": row["tenant_id"], "o": row.get("owner_user_id"), "sc": row["scope"]})
    res = await session.execute(text(
        "UPDATE tenant_agent_skills SET status = :st, is_active = :a, updated_at = current_timestamp WHERE id = :id RETURNING *"),
        {"st": status, "a": status == "active", "id": row["id"]})
    return dict(res.mappings().one())


async def record_usage(session: AsyncSession, *, skill_ids: list, tenant_id, user_id, agent_type: Optional[str],
                       run_id: Optional[str], outcome: str = "selected") -> int:
    """Log a use (or feedback). Platform skills are shared by every tenant, so their per-tenant numbers come from the
    log (usage_overrides) and the shared row's counters are never touched."""
    col = {"selected": "usage_count", "helpful": "helpful_count", "unhelpful": "unhelpful_count"}.get(outcome)
    n = 0
    for sid in skill_ids:
        row = (await session.execute(text("SELECT tenant_id FROM tenant_agent_skills WHERE id = :id"), {"id": sid})).first()
        if not row:
            continue
        if row[0] is not None and col:
            touch = ", last_used_at = current_timestamp" if outcome == "selected" else ""
            await session.execute(text(f"UPDATE tenant_agent_skills SET {col} = {col} + 1{touch} WHERE id = :id"), {"id": sid})
        await session.execute(text(
            "INSERT INTO tenant_agent_skill_usage (skill_id, tenant_id, user_id, agent_type, run_id, outcome) "
            "VALUES (:s, :t, :u, :a, :r, :o)"),
            {"s": sid, "t": tenant_id, "u": user_id, "a": agent_type, "r": run_id, "o": outcome})
        n += 1
    return n


async def usage_overrides(session: AsyncSession, tenant_id) -> dict:
    """Per-tenant usage of platform skills: skill_id -> {usage_count, helpful_count, unhelpful_count, last_used_at}."""
    res = await session.execute(text(
        "SELECT skill_id, count(*) FILTER (WHERE outcome = 'selected') AS used, "
        "count(*) FILTER (WHERE outcome = 'helpful') AS up, count(*) FILTER (WHERE outcome = 'unhelpful') AS down, "
        "max(created_at) FILTER (WHERE outcome = 'selected') AS last FROM tenant_agent_skill_usage "
        "WHERE tenant_id = :t GROUP BY skill_id"), {"t": tenant_id})
    return {r[0]: {"usage_count": r[1], "helpful_count": r[2], "unhelpful_count": r[3], "last_used_at": r[4]} for r in res.all()}
