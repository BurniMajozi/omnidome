"""Skills API: /api/v1/skills (docs/skills.md). Backwards compatible with the first OKF endpoints."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_session
from services.tenant_memory.skills import access, catalog, portable, store
from services.tenant_memory.skills.spec import SkillSpec

logger = logging.getLogger("tenant_memory.skills")
router = APIRouter(prefix="/api/v1/skills", tags=["skills"])

SPEC_FIELDS = ("skill_name", "slug", "description", "instructions", "category", "tags", "target_agent_types",
               "source_agent_type", "tools_required", "tools_optional", "inputs", "triggers", "examples",
               "safety_class", "version", "changelog", "visibility_roles")


class SkillWrite(BaseModel):
    """Create/update body. Accepts the legacy fields (guidance_prompt) as well as the new ones."""
    model_config = ConfigDict(extra="ignore")
    skill_name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    guidance_prompt: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    target_agent_types: Optional[list[str]] = None
    source_agent_type: Optional[str] = None
    tools_required: Optional[list[str]] = None
    tools_optional: Optional[list[str]] = None
    inputs: Optional[list[dict[str, Any]]] = None
    triggers: Optional[list[str]] = None
    examples: Optional[list[dict[str, Any]]] = None
    safety_class: Optional[str] = None
    version: Optional[str] = None
    changelog: Optional[str] = None
    visibility_roles: Optional[list[str]] = None
    scope: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class ForkBody(BaseModel):
    scope: str = "user"
    skill_name: Optional[str] = None


class ImportBody(BaseModel):
    markdown: str = Field(..., min_length=1, max_length=60_000)
    scope: str = "user"


class UsageBody(BaseModel):
    skill_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    agent_type: Optional[str] = None
    run_id: Optional[str] = None


class FeedbackBody(BaseModel):
    helpful: bool
    run_id: Optional[str] = None


# -- helpers ----------------------------------------------------------------------

def _perm(ctx: AuthContext) -> dict:
    return {"tenant_id": ctx.tenant_id, "user_id": ctx.user_id, "admin": access.is_admin(ctx), "author": access.is_author(ctx)}


def _visible(row: dict, ctx: AuthContext) -> bool:
    return access.visible(row, tenant_id=ctx.tenant_id, user_id=ctx.user_id, roles=ctx.roles, admin=access.is_admin(ctx))


def _read(row: dict, ctx: AuthContext, overrides: Optional[dict] = None) -> dict:
    out = store.to_read(row, caller={"perm": _perm(ctx)})
    if row.get("tenant_id") is None and overrides is not None:
        out.update(overrides.get(row["id"], {"usage_count": 0, "helpful_count": 0, "unhelpful_count": 0, "last_used_at": None}))
    return out


def _validation_detail(exc: ValidationError) -> list[dict]:
    return [{"loc": [str(p) for p in e.get("loc", ())], "msg": str(e.get("msg", "")).removeprefix("Value error, ")} for e in exc.errors()]


def _spec(data: dict) -> SkillSpec:
    try:
        return SkillSpec.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_detail(exc)) from exc


def _row_spec_dict(row: dict) -> dict:
    r = store.to_read(row)
    return {k: r.get(k) for k in SPEC_FIELDS}


async def _owned(session: AsyncSession, skill_id: uuid.UUID, ctx: AuthContext) -> dict:
    row = await store.get_row(session, skill_id)
    if not row or not _visible(row, ctx):
        raise HTTPException(status_code=404, detail="Skill not found")
    return row


async def _exists(session: AsyncSession, tenant_id, slug: str, version: str, owner) -> Optional[dict]:
    res = await session.execute(text(
        "SELECT * FROM tenant_agent_skills WHERE tenant_id IS NOT DISTINCT FROM :t AND slug = :s AND version = :v "
        "AND owner_user_id IS NOT DISTINCT FROM :o"), {"t": tenant_id, "s": slug, "v": version, "o": owner})
    row = res.mappings().first()
    return dict(row) if row else None


def _require_author(ctx: AuthContext) -> dict:
    p = _perm(ctx)
    if not p["author"]:
        raise HTTPException(status_code=403, detail="Viewers can read skills; an analyst, manager or admin role is needed to create them")
    return p


# -- reads ------------------------------------------------------------------------

@router.get("/meta")
async def skills_meta(ctx: AuthContext = Depends(get_auth_context)):
    p = _perm(ctx)
    return {"tools": catalog.registry_listing(), "agent_types": list(catalog.AGENT_TYPES), "categories": list(catalog.CATEGORIES),
            "safety_classes": list(catalog.SAFETY_CLASSES), "scopes": list(catalog.SCOPES), "statuses": list(catalog.STATUSES),
            "caller": {"admin": p["admin"], "author": p["author"]}}


@router.get("")
async def list_skills(
    scope: Optional[str] = Query(None, description="platform | tenant | team | user"),
    status: Optional[str] = Query("active", description="active | draft | deprecated | all"),
    source_agent_type: Optional[str] = None,
    target_agent_type: Optional[str] = None,
    agent_type: Optional[str] = None,
    category: Optional[str] = None,
    safety_class: Optional[str] = None,
    q: Optional[str] = None,
    mine: bool = False,
    dedupe: bool = False,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    admin = access.is_admin(ctx)
    rows = [r for r in await store.fetch_candidates(session, ctx.tenant_id)
            if access.visible(r, tenant_id=ctx.tenant_id, user_id=ctx.user_id, roles=ctx.roles, admin=admin)]
    rows = store.latest_versions(rows)
    wanted_agent = target_agent_type or agent_type
    needle = (q or "").strip().lower()

    def keep(r: dict) -> bool:
        st = r.get("status") or ("active" if r.get("is_active", True) else "deprecated")
        if status and status != "all" and st != status:
            return False
        if scope and (r.get("scope") or "tenant") != scope:
            return False
        if source_agent_type and r.get("source_agent_type") != source_agent_type:
            return False
        if wanted_agent and r.get("target_agent_types") and wanted_agent not in r["target_agent_types"]:
            return False
        if category and r.get("category") != category:
            return False
        if safety_class and (r.get("safety_class") or "read_only") != safety_class:
            return False
        if mine and str(r.get("owner_user_id")) != str(ctx.user_id) and str(r.get("created_by")) != str(ctx.user_id):
            return False
        if needle:
            hay = " ".join([r.get("skill_name") or "", r.get("description") or "", " ".join(r.get("tags") or []),
                            " ".join(r.get("triggers") or [])]).lower()
            if needle not in hay:
                return False
        return True

    rows = [r for r in rows if keep(r)]
    if dedupe:
        rows = access.dedupe_by_slug(rows)
    rows.sort(key=lambda r: (r.get("scope") != "platform", str(r.get("skill_name")).lower()))
    overrides = await store.usage_overrides(session, ctx.tenant_id) if any(r.get("tenant_id") is None for r in rows) else {}
    items = [_read(r, ctx, overrides) for r in rows]
    return {"items": items, "count": len(items)}


@router.get("/{skill_id}")
async def get_skill(skill_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_async_session)):
    row = await _owned(session, skill_id, ctx)
    overrides = await store.usage_overrides(session, ctx.tenant_id) if row.get("tenant_id") is None else None
    return _read(row, ctx, overrides)


@router.get("/{skill_id}/versions")
async def skill_versions(skill_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_async_session)):
    row = await _owned(session, skill_id, ctx)
    res = await session.execute(text(
        "SELECT * FROM tenant_agent_skills WHERE tenant_id IS NOT DISTINCT FROM :t AND slug = :s AND scope = :sc "
        "AND owner_user_id IS NOT DISTINCT FROM :o"), {"t": row["tenant_id"], "s": row["slug"], "sc": row["scope"], "o": row.get("owner_user_id")})
    items = [store.to_read(dict(r)) for r in res.mappings().all()]
    items.sort(key=lambda r: store.semver_key(r["version"]), reverse=True)
    return {"items": [{k: i[k] for k in ("id", "version", "status", "changelog", "created_at", "updated_at", "created_by")} for i in items],
            "count": len(items)}


@router.get("/{skill_id}/export")
async def export_skill(skill_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_async_session)):
    row = store.to_read(await _owned(session, skill_id, ctx))
    return {"filename": f"{row['slug']}-{row['version']}.SKILL.md", "markdown": portable.to_markdown(row)}


# -- writes -----------------------------------------------------------------------

def _merge(base: dict, body: SkillWrite) -> dict:
    data = dict(base)
    patch = body.model_dump(exclude_unset=True)
    if "guidance_prompt" in patch and "instructions" not in patch:
        patch["instructions"] = patch["guidance_prompt"]
    for k in SPEC_FIELDS:
        if k in patch and patch[k] is not None:
            data[k] = patch[k]
    return data


@router.post("", status_code=201)
async def create_skill(body: SkillWrite, ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_async_session)):
    p = _require_author(ctx)
    scope = body.scope or "tenant"
    if scope == "platform":
        raise HTTPException(status_code=403, detail="Platform skills ship with the product. Fork one to customise it.")
    if scope not in ("tenant", "team", "user"):
        raise HTTPException(status_code=422, detail="scope must be tenant, team or user")
    spec = _spec(_merge({}, body))
    if spec.safety_class == "can_act" and not p["admin"]:
        raise HTTPException(status_code=403, detail="can_act skills need an admin to create them")
    if scope == "team" and not p["admin"]:
        raise HTTPException(status_code=403, detail="Only admins create team skills")
    if body.status not in (None, "draft", "active"):
        raise HTTPException(status_code=422, detail="status must be draft or active")
    shared = scope in ("tenant", "team")
    if shared and not p["admin"]:
        status = "draft"                    # submitted for an admin to activate
    else:
        status = body.status or "active"
    owner = ctx.user_id if scope == "user" else None
    existing = await _exists(session, ctx.tenant_id, spec.slug, spec.version, owner)
    meta = body.metadata or {}
    if existing:
        # Legacy behaviour: registering the same name + version again updates and re-activates it.
        if not access.can_edit(existing, **{k: p[k] for k in ("tenant_id", "user_id", "admin", "author")}):
            raise HTTPException(status_code=409, detail=f"{spec.skill_name} v{spec.version} already exists")
        row = await _overwrite(session, existing["id"], spec, status, meta)
        if status == "active":
            row = await store.set_status(session, row, "active")
    else:
        row = await store.insert_skill(session, spec, tenant_id=ctx.tenant_id, scope=scope, status=status, owner_user_id=owner,
                                       created_by=ctx.user_id, metadata=meta)
        if status == "active":
            row = await store.set_status(session, row, "active")
    logger.info("skill %s v%s created (scope=%s status=%s tenant=%s)", spec.slug, spec.version, scope, row["status"], ctx.tenant_id)
    return _read(row, ctx)


async def _overwrite(session: AsyncSession, row_id, spec: SkillSpec, status: str, metadata: dict) -> dict:
    params = store._insert_params(spec, tenant_id=None, scope="x", status=status, metadata=metadata)
    keep = {k: params[k] for k in ("skill_name", "description", "category", "source_agent_type", "target_agent_types", "tools_required",
                                   "tools_optional", "instructions", "metadata", "visibility_roles", "inputs", "triggers", "examples",
                                   "tags", "safety_class", "changelog", "content_hash", "slug")}
    keep.update(id=row_id, status=status, is_active=status == "active")
    sql = ("UPDATE tenant_agent_skills SET skill_name=:skill_name, description=:description, category=:category, "
           "source_agent_type=:source_agent_type, target_agent_types=:target_agent_types, tools_required=:tools_required, "
           "tools_optional=:tools_optional, guidance_prompt=:instructions, metadata=:metadata, visibility_roles=:visibility_roles, "
           "inputs=:inputs, triggers=:triggers, examples=:examples, tags=:tags, safety_class=:safety_class, changelog=:changelog, "
           "content_hash=:content_hash, status=:status, is_active=:is_active, updated_at=current_timestamp WHERE id=:id RETURNING *")
    res = await session.execute(store._bind(sql), keep)
    return dict(res.mappings().one())


@router.put("/{skill_id}")
async def update_skill(skill_id: uuid.UUID, body: SkillWrite, ctx: AuthContext = Depends(get_auth_context),
                       session: AsyncSession = Depends(get_async_session)):
    """Edit. A draft is edited in place; an active/deprecated skill gets a new version (the old one stays as history)."""
    p = _perm(ctx)
    row = await _owned(session, skill_id, ctx)
    if row.get("scope") == "platform":
        raise HTTPException(status_code=403, detail="Platform skills are read-only. Fork it to customise.")
    if not access.can_edit(row, tenant_id=p["tenant_id"], user_id=p["user_id"], admin=p["admin"], author=p["author"]):
        raise HTTPException(status_code=403, detail="You cannot edit this skill")
    data = _merge(_row_spec_dict(row), body)
    new_row_status = row["status"]
    if row["status"] != "draft":
        data["version"] = body.version or store.bump_patch(max(
            (r["version"] for r in await _versions(session, row)), key=store.semver_key))
        data["changelog"] = body.changelog or "Edited"
    spec = _spec(data)
    if spec.safety_class == "can_act" and not p["admin"]:
        raise HTTPException(status_code=403, detail="can_act skills need an admin")
    if row["status"] == "draft":
        out = await _overwrite(session, row["id"], spec, "draft", row.get("metadata") or {})
        return _read(out, ctx)
    if await _exists(session, row["tenant_id"], spec.slug, spec.version, row.get("owner_user_id")):
        raise HTTPException(status_code=409, detail=f"version {spec.version} already exists")
    publish = access.can_publish(row, tenant_id=p["tenant_id"], user_id=p["user_id"], admin=p["admin"], author=p["author"])
    new_row_status = "active" if (publish and row["status"] == "active") else "draft"
    out = await store.insert_skill(session, spec, tenant_id=row["tenant_id"], scope=row["scope"], status="draft",
                                   owner_user_id=row.get("owner_user_id"), created_by=ctx.user_id,
                                   forked_from_id=row.get("forked_from_id"), forked_from_version=row.get("forked_from_version"),
                                   metadata=row.get("metadata") or {})
    if new_row_status == "active":
        out = await store.set_status(session, out, "active")
    return _read(out, ctx)


async def _versions(session: AsyncSession, row: dict) -> list[dict]:
    res = await session.execute(text(
        "SELECT version FROM tenant_agent_skills WHERE tenant_id IS NOT DISTINCT FROM :t AND slug = :s AND scope = :sc "
        "AND owner_user_id IS NOT DISTINCT FROM :o"), {"t": row["tenant_id"], "s": row["slug"], "sc": row["scope"], "o": row.get("owner_user_id")})
    return [dict(r) for r in res.mappings().all()]


async def _publish(skill_id: uuid.UUID, status: str, ctx: AuthContext, session: AsyncSession) -> dict:
    p = _perm(ctx)
    row = await _owned(session, skill_id, ctx)
    if not access.can_publish(row, tenant_id=p["tenant_id"], user_id=p["user_id"], admin=p["admin"], author=p["author"]):
        raise HTTPException(status_code=403, detail="Only an admin can activate or retire this skill" if row.get("scope") != "platform"
                            else "Platform skills are managed by the product")
    if status == "active":
        _spec(_row_spec_dict(row))          # tools may have changed since it was saved
    return _read(await store.set_status(session, row, status), ctx)


@router.post("/{skill_id}/activate")
async def activate_skill(skill_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_async_session)):
    return await _publish(skill_id, "active", ctx, session)


@router.post("/{skill_id}/deprecate")
async def deprecate_skill(skill_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_async_session)):
    return await _publish(skill_id, "deprecated", ctx, session)


@router.post("/{skill_id}/deactivate")
async def deactivate_skill(skill_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_async_session)):
    """Legacy alias of deprecate (the Agent Manager's OKF skills tab)."""
    return await _publish(skill_id, "deprecated", ctx, session)


@router.post("/{skill_id}/fork", status_code=201)
async def fork_skill(skill_id: uuid.UUID, body: ForkBody, ctx: AuthContext = Depends(get_auth_context),
                     session: AsyncSession = Depends(get_async_session)):
    """Copy-on-write: a private or organisation copy you can edit. Lineage is recorded; the original is untouched."""
    p = _require_author(ctx)
    src = await _owned(session, skill_id, ctx)
    if body.scope not in ("user", "tenant"):
        raise HTTPException(status_code=422, detail="scope must be user or tenant")
    if body.scope == "tenant" and not p["admin"]:
        raise HTTPException(status_code=403, detail="Only admins can fork into the organisation library")
    data = _row_spec_dict(src)
    data.update(version="1.0.0", changelog=f"Forked from {src['skill_name']} v{src['version']}", source_agent_type="shared")
    if body.skill_name:
        data["skill_name"] = body.skill_name
        data["slug"] = None
    spec = _spec(data)
    owner = ctx.user_id if body.scope == "user" else None
    if await _exists(session, ctx.tenant_id, spec.slug, spec.version, owner):
        raise HTTPException(status_code=409, detail="You already have a copy of this skill; edit it or give the fork a new name")
    row = await store.insert_skill(session, spec, tenant_id=ctx.tenant_id, scope=body.scope, status="draft", owner_user_id=owner,
                                   created_by=ctx.user_id, forked_from_id=src["id"], forked_from_version=src["version"])
    return _read(row, ctx)


@router.post("/{skill_id}/share")
async def share_skill(skill_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_async_session)):
    """Offer a private skill to the organisation. An admin's share is live; anyone else's waits as a draft for an admin."""
    p = _require_author(ctx)
    row = await _owned(session, skill_id, ctx)
    if row.get("scope") != "user" or str(row.get("owner_user_id")) != str(ctx.user_id):
        raise HTTPException(status_code=403, detail="Only the owner can share a private skill")
    if await _exists(session, ctx.tenant_id, row["slug"], row["version"], None):
        raise HTTPException(status_code=409, detail="The organisation already has this skill and version")
    status = "active" if (p["admin"] and row.get("status") == "active") else "draft"
    if row.get("safety_class") == "can_act" and not p["admin"]:
        status = "draft"
    res = await session.execute(text(
        "UPDATE tenant_agent_skills SET scope = 'tenant', owner_user_id = NULL, created_by = COALESCE(created_by, :u), status = :st, "
        "is_active = :a, updated_at = current_timestamp WHERE id = :id RETURNING *"),
        {"u": ctx.user_id, "st": status, "a": status == "active", "id": row["id"]})
    return _read(dict(res.mappings().one()), ctx)


@router.post("/import/preview")
async def import_preview(body: ImportBody, ctx: AuthContext = Depends(get_auth_context)):
    _require_author(ctx)
    return portable.preview(body.markdown)


@router.post("/import", status_code=201)
async def import_skill(body: ImportBody, ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_async_session)):
    """Create from a SKILL.md file. Always a draft in the importer's private scope (admins may choose tenant); the file's
    own scope/status are ignored. Anything the sanitiser blocks is refused."""
    p = _require_author(ctx)
    result = portable.preview(body.markdown)
    if not result["ok"]:
        raise HTTPException(status_code=422, detail=[{"loc": ["markdown"], "msg": m} for m in result["errors"]])
    spec = _spec(result["skill"])
    scope = "tenant" if (body.scope == "tenant" and p["admin"]) else "user"
    owner = ctx.user_id if scope == "user" else None
    if await _exists(session, ctx.tenant_id, spec.slug, spec.version, owner):
        raise HTTPException(status_code=409, detail=f"{spec.skill_name} v{spec.version} already exists; change the version in the file")
    row = await store.insert_skill(session, spec, tenant_id=ctx.tenant_id, scope=scope, status="draft", owner_user_id=owner,
                                   created_by=ctx.user_id, metadata={"imported": True})
    out = _read(row, ctx)
    out["import_warnings"] = result["warnings"]
    return out


@router.post("/usage")
async def usage(body: UsageBody, ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_async_session)):
    """Called by the orchestrator when skills were applied to a run. Only skills the caller can see are counted."""
    ids = []
    for sid in body.skill_ids:
        row = await store.get_row(session, sid)
        if row and _visible(row, ctx):
            ids.append(sid)
    n = await store.record_usage(session, skill_ids=ids, tenant_id=ctx.tenant_id, user_id=ctx.user_id, agent_type=body.agent_type, run_id=body.run_id)
    return {"recorded": n}


@router.post("/{skill_id}/feedback")
async def feedback(skill_id: uuid.UUID, body: FeedbackBody, ctx: AuthContext = Depends(get_auth_context),
                   session: AsyncSession = Depends(get_async_session)):
    await _owned(session, skill_id, ctx)
    await store.record_usage(session, skill_ids=[skill_id], tenant_id=ctx.tenant_id, user_id=ctx.user_id, agent_type=None,
                             run_id=body.run_id, outcome="helpful" if body.helpful else "unhelpful")
    return {"ok": True}
