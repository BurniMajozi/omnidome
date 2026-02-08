from __future__ import annotations

import os
from typing import Iterable, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_session, session_scope


def _bool_env(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _enforce_rbac() -> bool:
    return _bool_env("AUTH_ENFORCE_RBAC", True)


async def _load_rbac(ctx: AuthContext, session: AsyncSession) -> None:
    if ctx.rbac_loaded:
        return

    roles_result = await session.execute(
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
    )
    role_list = [row[0] for row in roles_result.fetchall()]

    permissions_result = await session.execute(
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
    )
    permission_list = [row[0] for row in permissions_result.fetchall()]

    if _enforce_rbac():
        ctx.roles = role_list
        ctx.permissions = permission_list
    else:
        ctx.roles = sorted(set(ctx.roles).union(role_list))
        ctx.permissions = sorted(set(ctx.permissions).union(permission_list))

    if "platform_admin" in ctx.roles or "platform.admin" in ctx.permissions:
        ctx.is_platform_admin = True

    ctx.rbac_loaded = True


async def has_permission(
    ctx: AuthContext,
    permission_key: str,
    session: Optional[AsyncSession] = None,
) -> bool:
    if ctx.is_platform_admin:
        return True

    if not _enforce_rbac() and permission_key in ctx.permissions:
        return True

    if session is None:
        async with session_scope(ctx.tenant_id) as scoped_session:
            await _load_rbac(ctx, scoped_session)
    else:
        await _load_rbac(ctx, session)

    return permission_key in ctx.permissions


async def has_role(
    ctx: AuthContext,
    role_name: str,
    session: Optional[AsyncSession] = None,
) -> bool:
    if ctx.is_platform_admin:
        return True
    if not _enforce_rbac() and role_name in ctx.roles:
        return True

    if session is None:
        async with session_scope(ctx.tenant_id) as scoped_session:
            await _load_rbac(ctx, scoped_session)
    else:
        await _load_rbac(ctx, session)

    return role_name in ctx.roles


def require_permission(permission_key: str):
    async def dependency(
        ctx: AuthContext = Depends(get_auth_context),
        session: AsyncSession = Depends(get_async_session),
    ) -> None:
        allowed = await has_permission(ctx, permission_key, session)
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    return dependency


def require_role(role_name: str):
    async def dependency(
        ctx: AuthContext = Depends(get_auth_context),
        session: AsyncSession = Depends(get_async_session),
    ) -> None:
        allowed = await has_role(ctx, role_name, session)
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")

    return dependency
