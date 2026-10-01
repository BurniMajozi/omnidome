"""Role tiers and tenant helpers for the compliance service.

Same model as services/sales/access.py: roles come from the RBAC tables
(AUTH_ENFORCE_RBAC, default on) or, with enforcement off, from the signed
identity headers. Reads stay open to every member of the tenant; mutations and
sensitive data need a role:

    member     any signed-in member of the tenant (reads of non-sensitive data)
    write      compliance_officer, or manager / admin roles (create + update)
    sensitive  compliance / hr / finance admin tiers: statutory payroll, employee
               tax and ID numbers, DSAR subject data, audit trail, marking a
               return as filed

COMPLIANCE_ENFORCE_ROLES=false switches the gates off (local development only).
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.common import rbac
from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_session as get_db

logger = logging.getLogger("compliance.access")

ADMIN_ROLES = frozenset({"platform_admin", "owner", "org_admin", "admin", "tenant_admin", "super_admin"})
MANAGER_ROLES = ADMIN_ROLES | {"manager", "compliance_manager", "hr_manager", "finance_manager", "ops_manager"}
WRITE_ROLES = MANAGER_ROLES | {"compliance_officer", "compliance_admin"}
SENSITIVE_ROLES = ADMIN_ROLES | {
    "compliance_admin", "compliance_manager", "compliance_officer",
    "hr_admin", "hr_manager", "finance_admin", "finance_manager", "payroll_admin",
}
# Marking a statutory return as filed: hr / finance admin tiers only (not every compliance officer).
FILING_ROLES = ADMIN_ROLES | {"hr_admin", "hr_manager", "finance_admin", "finance_manager", "payroll_admin"}

ADMIN_PERMS = frozenset({"compliance.admin", "platform.admin"})
WRITE_PERMS = ADMIN_PERMS | {"compliance.write", "compliance.manage"}
SENSITIVE_PERMS = WRITE_PERMS | {"hr.admin", "finance.admin", "payroll.admin"}
FILING_PERMS = ADMIN_PERMS | {"hr.admin", "finance.admin", "payroll.admin"}

TIERS = {
    "write": (WRITE_ROLES, WRITE_PERMS),
    "sensitive": (SENSITIVE_ROLES, SENSITIVE_PERMS),
    "filing": (FILING_ROLES, FILING_PERMS),
}


def roles_enforced() -> bool:
    return os.getenv("COMPLIANCE_ENFORCE_ROLES", "true").strip().lower() not in {"0", "false", "no", "off"}


def tenant_str(ctx: AuthContext) -> str:
    """The caller's tenant as the string stored in the String(100) tenant_id columns."""
    return str(ctx.tenant_id)


async def effective_access(auth: AuthContext, db: Optional[AsyncSession]) -> tuple[set, set]:
    """(roles, permissions), lower-cased. Fails closed when RBAC is enforced and cannot be read."""
    if not auth.rbac_loaded and db is not None:
        try:
            async with db.begin_nested():  # a missing RBAC table must not poison the request transaction
                await rbac._load_rbac(auth, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RBAC lookup failed for compliance authorization: %s", exc)
            if rbac._enforce_rbac():
                return set(), set()
    return {r.lower() for r in auth.roles or []}, {p.lower() for p in auth.permissions or []}


def tier_allows(tier: str, roles: set, perms: set) -> bool:
    tier_roles, tier_perms = TIERS[tier]
    return bool((roles & tier_roles) or (perms & tier_perms))


async def has_tier(auth: AuthContext, db: Optional[AsyncSession], tier: str) -> bool:
    if not roles_enforced() or auth.is_platform_admin:
        return True
    roles, perms = await effective_access(auth, db)
    return tier_allows(tier, roles, perms)


async def require(auth: AuthContext, db: Optional[AsyncSession], tier: str) -> None:
    if not await has_tier(auth, db, tier):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"This action needs a compliance '{tier}' role")


def require_tier(tier: str) -> Callable:
    """FastAPI dependency: `ctx = Depends(require_tier("write"))` returns the AuthContext."""
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}")

    async def dependency(auth: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)) -> AuthContext:
        await require(auth, db, tier)
        return auth

    dependency.__name__ = f"require_compliance_{tier}"
    return dependency


# Convenience dependencies
member_ctx = get_auth_context
write_ctx = require_tier("write")
sensitive_ctx = require_tier("sensitive")
filing_ctx = require_tier("filing")
