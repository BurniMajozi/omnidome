"""Role gates for the portal builder (mirrors services/billing/access.py).

Tiers (each includes the ones above it):

    manager  PORTAL_MANAGER roles + admins: publish, unpublish, delete, share links, launch campaigns.
             Permission ``portal.admin`` / ``portal.publish`` / ``portal.manage``.
    write    editors (+ manager): create/edit pages, import a site, SEO audits, read submissions (PII).
             Permission ``portal.write``.

Plain reads of the tenant's own pages need only an authenticated tenant identity.
PORTAL_ENFORCE_ROLES=false switches the gates off (local development only).
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from fastapi import Depends, HTTPException, status

from services.common import rbac
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("portal_builder.access")

ADMIN_ROLES = frozenset({"owner", "org_admin", "admin", "tenant_admin", "platform_admin", "portal_admin"})
MANAGER_ROLES = frozenset({"manager", "marketing_manager", "portal_manager"})
EDITOR_ROLES = frozenset({"marketing", "content_editor", "portal_editor", "editor"})

ADMIN_PERMS = frozenset({"portal.admin"})
MANAGER_PERMS = frozenset({"portal.publish", "portal.manage"})
EDITOR_PERMS = frozenset({"portal.write"})


def roles_enforced() -> bool:
    return os.getenv("PORTAL_ENFORCE_ROLES", "true").strip().lower() not in {"0", "false", "no", "off"}


def tier_sets(tier: str) -> tuple[frozenset, frozenset]:
    if tier == "manager":
        return ADMIN_ROLES | MANAGER_ROLES, ADMIN_PERMS | MANAGER_PERMS
    if tier == "write":
        return ADMIN_ROLES | MANAGER_ROLES | EDITOR_ROLES, ADMIN_PERMS | MANAGER_PERMS | EDITOR_PERMS
    raise ValueError(f"unknown tier {tier!r}")


async def effective_access(auth: AuthContext) -> tuple[set, set]:
    """(roles, permissions) lower-cased; empty when RBAC is enforced but unreadable (fail closed)."""
    if not auth.rbac_loaded:
        try:
            from services.common.db import session_scope
            async with session_scope(auth.tenant_id) as db:
                await rbac._load_rbac(auth, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RBAC lookup failed for portal authorization: %s", type(exc).__name__)
            if rbac._enforce_rbac():
                return set(), set()
    return ({str(r).strip().lower() for r in auth.roles or []},
            {str(p).strip().lower() for p in auth.permissions or []})


async def has_tier(auth: AuthContext, tier: str) -> bool:
    if not roles_enforced() or auth.is_platform_admin:
        return True
    roles, perms = tier_sets(tier)
    have_roles, have_perms = await effective_access(auth)
    return bool((have_roles & roles) or (have_perms & perms))


async def require(auth: AuthContext, tier: str) -> None:
    if not await has_tier(auth, tier):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"This action needs a portal {tier} role")


def require_tier(tier: str) -> Callable:
    """FastAPI dependency: ``dependencies=[Depends(require_tier("manager"))]``."""
    tier_sets(tier)  # validate

    async def dependency(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        await require(auth, tier)
        return auth

    dependency.__name__ = f"require_portal_{tier}"
    return dependency
