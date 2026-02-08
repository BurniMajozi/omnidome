import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import jwt
from fastapi import Depends, HTTPException, status
from starlette.requests import Request

from services.common.db import set_tenant_context


def _bool_env(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_uuid(value: Optional[str], field_name: str) -> uuid.UUID:
    if not value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Missing {field_name}")
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid {field_name}") from exc


@dataclass
class AuthContext:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    is_platform_admin: bool = False
    token_payload: Dict[str, Any] = field(default_factory=dict)
    auth_mode: str = "header"
    act_as_tenant_id: Optional[uuid.UUID] = None
    rbac_loaded: bool = False
    access_loaded: bool = False
    module_access: Dict[str, bool] = field(default_factory=dict)


def _decode_jwt(token: str) -> Dict[str, Any]:
    verify = _bool_env("AUTH_JWT_VERIFY", True)
    algorithm = os.getenv("AUTH_JWT_ALGORITHM", "HS256")
    options = {"verify_aud": False}
    if verify:
        key = os.getenv("AUTH_JWT_PUBLIC_KEY") or os.getenv("AUTH_JWT_SECRET")
        if not key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="JWT verification key not configured",
            )
        try:
            return jwt.decode(token, key, algorithms=[algorithm], options=options)
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def _roles_from_payload(payload: Dict[str, Any]) -> list[str]:
    raw = payload.get("roles")
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        return _split_csv(raw)
    return []


def _permissions_from_payload(payload: Dict[str, Any]) -> list[str]:
    raw = payload.get("permissions")
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        return _split_csv(raw)
    return []


def _modules_from_payload(payload: Dict[str, Any]) -> list[str]:
    raw = payload.get("modules")
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        return _split_csv(raw)
    return []


async def get_auth_context(request: Request) -> AuthContext:
    existing = getattr(request.state, "auth", None)
    if isinstance(existing, AuthContext):
        return existing

    mode = os.getenv("AUTH_MODE", "header").strip().lower()
    allow_anonymous = _bool_env("AUTH_ALLOW_ANONYMOUS", False)

    user_id: Optional[uuid.UUID] = None
    tenant_id: Optional[uuid.UUID] = None
    roles: list[str] = []
    permissions: list[str] = []
    modules: list[str] = []
    payload: Dict[str, Any] = {}

    if mode == "jwt":
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
        token = auth_header.split(" ", 1)[1].strip()
        payload = _decode_jwt(token)
        user_id = _parse_uuid(payload.get("sub") or payload.get("user_id"), "user_id")
        tenant_raw = payload.get("tenant_id") or payload.get("org_id")
        tenant_id = _parse_uuid(tenant_raw, "tenant_id") if tenant_raw else None
        roles = _roles_from_payload(payload)
        permissions = _permissions_from_payload(payload)
        modules = _modules_from_payload(payload)
    elif mode in {"header", "dev"}:
        user_raw = request.headers.get("X-User-Id") or (os.getenv("DEFAULT_USER_ID") if allow_anonymous else None)
        tenant_raw = request.headers.get("X-Tenant-Id") or (os.getenv("DEFAULT_TENANT_ID") if allow_anonymous else None)
        if not user_raw or not tenant_raw:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-User-Id or X-Tenant-Id")
        user_id = _parse_uuid(user_raw, "user_id")
        tenant_id = _parse_uuid(tenant_raw, "tenant_id")
        roles = _split_csv(request.headers.get("X-Roles"))
        permissions = _split_csv(request.headers.get("X-Permissions"))
        modules = _split_csv(request.headers.get("X-Modules"))
    else:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AUTH_MODE invalid")

    is_platform_admin = (
        bool(payload.get("is_platform_admin"))
        or "platform_admin" in roles
        or "platform.admin" in permissions
    )

    org_override = request.headers.get("X-Org-Id")
    original_tenant_id = tenant_id
    if tenant_id is None:
        if is_platform_admin and org_override:
            tenant_id = _parse_uuid(org_override, "org_id")
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing tenant scope")

    ctx = AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles,
        permissions=permissions,
        modules=modules,
        is_platform_admin=is_platform_admin,
        token_payload=payload,
        auth_mode=mode,
    )

    if org_override and ctx.is_platform_admin:
        override_id = _parse_uuid(org_override, "org_id")
        if original_tenant_id and original_tenant_id != override_id:
            ctx.act_as_tenant_id = original_tenant_id
        ctx.tenant_id = override_id

    set_tenant_context(ctx.tenant_id)
    request.state.auth = ctx
    return ctx


async def get_current_tenant_id(ctx: AuthContext = Depends(get_auth_context)) -> uuid.UUID:
    return ctx.tenant_id


async def get_current_user_id(ctx: AuthContext = Depends(get_auth_context)) -> uuid.UUID:
    return ctx.user_id
