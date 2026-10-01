"""Tenant scoping for the lifecycle service.

The tenant is taken ONLY from the signed identity (AuthContext). A client may still send
`?tenant_id=` or a body `tenant_id` (older callers and the web proxy do): it is ignored when
it equals the signed tenant and refused with 403 when it differs, so a tenant-A user can never
read or write tenant B by passing B in the query string.

Service-to-service bridges (sales close-won, journey engine) sign only X-Tenant-Id, with no
user id. They are accepted on that signed tenant header alone (the signature still has to be
valid in AUTH_MODE=signed); the request body can never widen the scope.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

from fastapi import HTTPException, Query, Request, status

from services.common import internal_auth
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("lifecycle.security")


def _parse(value: Optional[str]) -> Optional[uuid.UUID]:
    if value is None or str(value).strip() == "":
        return None
    try:
        return uuid.UUID(str(value).strip())
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "tenant_id must be a UUID")


def ensure_same_tenant(scope: uuid.UUID, supplied: Optional[str]) -> None:
    """Refuse (403) a client-supplied tenant id that differs from the authenticated one."""
    given = _parse(supplied)
    if given is not None and given != scope:
        logger.warning("tenant mismatch refused: supplied tenant differs from the authenticated tenant")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "tenant_id does not match the authenticated tenant")


async def _service_tenant(request: Request) -> Optional[uuid.UUID]:
    """Tenant of a service-to-service call that carries no user id (None if not applicable)."""
    mode = os.getenv("AUTH_MODE", "header").strip().lower()
    if mode == "jwt":
        return None
    if mode == "signed":
        try:
            internal_auth.verify_request(request.headers, request.method, request.url.path, internal_auth.get_secret())
        except (internal_auth.IdentityError, internal_auth.IdentityConfigError):
            return None
    raw = request.headers.get("X-Tenant-Id")
    return _parse(raw) if raw else None


async def authenticated_tenant(request: Request, allow_service: bool = False) -> uuid.UUID:
    try:
        ctx: AuthContext = await get_auth_context(request)
        return ctx.tenant_id
    except HTTPException as exc:
        if allow_service and exc.status_code == status.HTTP_401_UNAUTHORIZED and "X-User-Id" in str(exc.detail):
            tenant = await _service_tenant(request)
            if tenant is not None:
                return tenant
        raise


async def tenant_scope(request: Request, tenant_id: Optional[str] = Query(None)) -> uuid.UUID:
    """Dependency: the authenticated tenant; a differing ?tenant_id= is a 403."""
    tenant = await authenticated_tenant(request)
    ensure_same_tenant(tenant, tenant_id)
    return tenant


async def bridge_tenant_scope(request: Request, tenant_id: Optional[str] = Query(None)) -> uuid.UUID:
    """Like tenant_scope, for routes called by sibling services (no user id)."""
    tenant = await authenticated_tenant(request, allow_service=True)
    ensure_same_tenant(tenant, tenant_id)
    return tenant
