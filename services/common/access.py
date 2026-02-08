import os
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import text

from services.common.auth import AuthContext
from services.common.db import get_engine


def _bool_env(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _db_enforced() -> bool:
    return _bool_env("AUTH_DB_ENFORCE", True)


def _ensure_engine():
    if not _db_enforced():
        return None
    return get_engine()


def _load_access(ctx: AuthContext) -> None:
    if getattr(ctx, "access_loaded", False) or not _db_enforced():
        return
    engine = _ensure_engine()
    if engine is None:
        return
    with engine.connect() as conn:
        roles = conn.execute(
            text(
                """
                select r.name
                from user_roles ur
                join roles r on r.id = ur.role_id
                where ur.user_id = :user_id
                  and (ur.tenant_id = :tenant_id or r.scope = 'PLATFORM')
                """
            ),
            {"user_id": str(ctx.user_id), "tenant_id": str(ctx.tenant_id)},
        ).fetchall()
        _merge_list(ctx, "roles", [row[0] for row in roles])

        permissions = conn.execute(
            text(
                """
                select p.key
                from user_roles ur
                join roles r on r.id = ur.role_id
                join role_permissions rp on rp.role_id = r.id
                join permissions p on p.id = rp.permission_id
                where ur.user_id = :user_id
                  and (ur.tenant_id = :tenant_id or r.scope = 'PLATFORM')
                """
            ),
            {"user_id": str(ctx.user_id), "tenant_id": str(ctx.tenant_id)},
        ).fetchall()
        _merge_list(ctx, "permissions", [row[0] for row in permissions])

    if "platform_admin" in ctx.roles or "platform.admin" in ctx.permissions:
        ctx.is_platform_admin = True
    ctx.access_loaded = True


def _merge_list(ctx: AuthContext, field_name: str, values: list[str]) -> None:
    current = getattr(ctx, field_name, [])
    existing = set(current)
    for value in values:
        if value not in existing:
            current.append(value)
            existing.add(value)
    setattr(ctx, field_name, current)


def has_permission(ctx: AuthContext, permission_key: str) -> bool:
    if ctx.is_platform_admin:
        return True
    if permission_key in ctx.permissions:
        return True
    _load_access(ctx)
    return permission_key in ctx.permissions


def has_role(ctx: AuthContext, role_name: str) -> bool:
    if role_name in ctx.roles:
        return True
    _load_access(ctx)
    return role_name in ctx.roles


def module_enabled(ctx: AuthContext, module_key: str) -> bool:
    if ctx.is_platform_admin:
        return True
    cached = ctx.module_access.get(module_key)
    if cached is not None:
        return cached
    if not _db_enforced():
        allowed = module_key in ctx.modules
        ctx.module_access[module_key] = allowed
        return allowed
    engine = _ensure_engine()
    if engine is None:
        return False
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                select tm.status
                from tenant_modules tm
                join modules m on m.id = tm.module_id
                where tm.tenant_id = :tenant_id
                  and m.key = :module_key
                """
            ),
            {"tenant_id": str(ctx.tenant_id), "module_key": module_key},
        ).fetchone()
    allowed = bool(row and row[0] in {"ENABLED", "TRIAL"})
    ctx.module_access[module_key] = allowed
    return allowed


def permission_for_request(module_key: Optional[str], method: str) -> Optional[str]:
    if not module_key:
        return None
    normalized = method.upper()
    if normalized in {"GET", "HEAD", "OPTIONS"}:
        return f"{module_key}.read"
    if normalized in {"POST", "PUT", "PATCH", "DELETE"}:
        return f"{module_key}.write"
    return None
