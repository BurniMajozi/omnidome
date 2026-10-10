"""Who may see / change a skill. Pure functions so they are easy to test (docs/skills.md)."""
from __future__ import annotations

from typing import Any, Iterable, Optional

ADMIN_ROLES = frozenset({"admin", "org_admin", "tenant_admin", "owner"})
AUTHOR_ROLES = ADMIN_ROLES | frozenset({"manager", "org_manager", "analyst", "org_analyst", "team_lead", "power_user", "editor"})
SCOPE_RANK = {"user": 0, "team": 1, "tenant": 2, "platform": 3}   # lower = takes precedence when slugs collide


def _lower(values: Optional[Iterable[str]]) -> set[str]:
    return {str(v).lower() for v in (values or [])}


def is_admin(ctx: Any) -> bool:
    return bool(getattr(ctx, "is_platform_admin", False) or _lower(ctx.roles) & ADMIN_ROLES
                or "agents.manage" in _lower(getattr(ctx, "permissions", [])))


def is_author(ctx: Any) -> bool:
    return is_admin(ctx) or bool(_lower(ctx.roles) & AUTHOR_ROLES) or "skills.write" in _lower(getattr(ctx, "permissions", []))


def _same(a: Any, b: Any) -> bool:
    return a is not None and b is not None and str(a) == str(b)


def visible(skill: dict, *, tenant_id: Any, user_id: Any, roles: Iterable[str], admin: bool) -> bool:
    """Tenant isolation + scope rules. `skill` is a row dict."""
    scope = skill.get("scope") or "tenant"
    status = skill.get("status") or ("active" if skill.get("is_active", True) else "deprecated")
    if scope == "platform":
        return status == "active" or admin
    if not _same(skill.get("tenant_id"), tenant_id):
        return False
    if scope == "user":
        return _same(skill.get("owner_user_id"), user_id)
    mine = _same(skill.get("created_by"), user_id)
    if status != "active" and not (admin or mine):
        return False
    if scope == "team":
        wanted = _lower(skill.get("visibility_roles"))
        return admin or mine or not wanted or bool(wanted & _lower(roles))
    return True


def can_edit(skill: dict, *, tenant_id: Any, user_id: Any, admin: bool, author: bool) -> bool:
    scope = skill.get("scope") or "tenant"
    if scope == "platform" or not _same(skill.get("tenant_id"), tenant_id):
        return False
    if scope == "user":
        return _same(skill.get("owner_user_id"), user_id) and author
    if admin:
        return True
    return author and skill.get("status") == "draft" and _same(skill.get("created_by"), user_id)


def can_publish(skill: dict, *, tenant_id: Any, user_id: Any, admin: bool, author: bool) -> bool:
    """Activate / deprecate. User-private skills are the owner's call (unless they can act)."""
    scope = skill.get("scope") or "tenant"
    if scope == "platform" or not _same(skill.get("tenant_id"), tenant_id):
        return False
    if scope == "user":
        return _same(skill.get("owner_user_id"), user_id) and author and (skill.get("safety_class") != "can_act" or admin)
    return admin


def dedupe_by_slug(skills: list[dict]) -> list[dict]:
    """A user's fork beats the tenant skill, which beats the platform original with the same slug."""
    best: dict[str, dict] = {}
    for s in skills:
        key = s.get("slug") or s.get("skill_name")
        cur = best.get(key)
        if cur is None or SCOPE_RANK.get(s.get("scope") or "tenant", 2) < SCOPE_RANK.get(cur.get("scope") or "tenant", 2):
            best[key] = s
    keep = {id(v) for v in best.values()}
    return [s for s in skills if id(s) in keep]
