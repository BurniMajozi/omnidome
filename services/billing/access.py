"""Role gates for the billing service.

Roles come from the signed identity / RBAC tables exactly like services/hr/access.py and
services/sales/access.py: with AUTH_ENFORCE_RBAC on (default) the RBAC tables are authoritative,
token roles are not trusted, and an unreadable RBAC table fails closed.

Tiers (each includes the ones above it):

    admin   BILLING_ADMIN_ROLES: billing_admin, finance, finance_admin, admin, tenant_admin, owner,
            platform_admin. ``org_admin`` counts ONLY when BILLING_ADMIN_EXTRA_ROLES lists it
            (same stance as HR). Permission ``billing.admin`` also counts.
            May: credit notes, generate invoices, void, suspend/reinstate, plans/bundles/
            subscriptions/arrangements/billing accounts, Paystack initialize + recurring, outbox retry.
    clerk   manager, billing, billing_clerk, finance_clerk, finance_manager (+ admin).
            May: record manual payments, send invoices, start/advance cancellations, create transfers.
            Permission ``billing.write`` / ``billing.manage``.
    reader  billing_viewer, finance_viewer, billing_readonly, auditor (+ clerk, admin).
            Read-only. A generic ``viewer`` role is NOT a billing role. There is no customer<->user
            linkage in this service, so members cannot read "their own" invoices: billing roles only.
            Permission ``billing.read``.

BILLING_ENFORCE_ROLES=false switches the gates off (local development only).
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request, status

from services.common import rbac
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("billing.access")

ADMIN_ROLES = frozenset({"billing_admin", "finance", "finance_admin", "admin", "tenant_admin", "owner", "platform_admin"})
CLERK_ROLES = frozenset({"manager", "billing", "billing_clerk", "finance_clerk", "finance_manager"})
READER_ROLES = frozenset({"billing_viewer", "finance_viewer", "billing_readonly", "auditor"})

ADMIN_PERMS = frozenset({"billing.admin"})
CLERK_PERMS = frozenset({"billing.write", "billing.manage"})
READER_PERMS = frozenset({"billing.read"})


def roles_enforced() -> bool:
    return os.getenv("BILLING_ENFORCE_ROLES", "true").strip().lower() not in {"0", "false", "no", "off"}


def _extra_admin_roles() -> frozenset:
    return frozenset(r.strip().lower() for r in os.getenv("BILLING_ADMIN_EXTRA_ROLES", "").split(",") if r.strip())


def tier_sets(tier: str) -> tuple[frozenset, frozenset]:
    admin_roles = ADMIN_ROLES | _extra_admin_roles()
    if tier == "admin":
        return admin_roles, ADMIN_PERMS
    if tier == "clerk":
        return admin_roles | CLERK_ROLES, ADMIN_PERMS | CLERK_PERMS
    if tier == "reader":
        return admin_roles | CLERK_ROLES | READER_ROLES, ADMIN_PERMS | CLERK_PERMS | READER_PERMS
    raise ValueError(f"unknown tier {tier!r}")


async def effective_access(auth: AuthContext) -> tuple[set, set]:
    """(roles, permissions) lower-cased; empty when RBAC is enforced but unreadable (fail closed)."""
    if not auth.rbac_loaded:
        try:
            from services.common.db import session_scope
            async with session_scope(auth.tenant_id) as db:
                await rbac._load_rbac(auth, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RBAC lookup failed for billing authorization: %s", type(exc).__name__)
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"This action needs a billing {tier} role")


def require_tier(tier: str) -> Callable:
    """FastAPI dependency: ``dependencies=[Depends(require_tier("admin"))]``."""
    tier_sets(tier)  # validate

    async def dependency(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        await require(auth, tier)
        return auth

    dependency.__name__ = f"require_billing_{tier}"
    return dependency


def internal_key_ok(request: Request) -> bool:
    """True when the caller presents the shared INTERNAL_SERVICE_KEY (constant-time compare)."""
    expected = os.getenv("INTERNAL_SERVICE_KEY", "")
    provided = request.headers.get("x-internal-key") or ""
    return bool(expected) and secrets.compare_digest(provided.encode(), expected.encode())
