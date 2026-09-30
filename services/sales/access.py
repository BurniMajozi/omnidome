"""Role gates for the sales service.

Same model as services/communication/routes/mail.py: roles come from the RBAC
tables (AUTH_ENFORCE_RBAC, default on) or, with enforcement off, from the signed
identity headers. Reads stay open to every member of the tenant; what changes
things needs a role:

    agent    sales staff: email a lead, send a quote
    manager  manager and up: read other agents' commissions, the commission report
    admin    owner / admin level: delete a deal, edit the pipeline, set targets

SALES_ENFORCE_ROLES=false switches the gates off (local development only).
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Iterable, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.common import rbac
from services.common.auth import AuthContext, get_auth_context
from services.sales.database import get_db

logger = logging.getLogger("sales.access")

ADMIN_ROLES = frozenset({"platform_admin", "owner", "org_admin", "admin", "tenant_admin", "super_admin"})
MANAGER_ROLES = ADMIN_ROLES | {"manager", "sales_manager"}
AGENT_ROLES = MANAGER_ROLES | {"sales", "sales_agent", "sales_rep", "agent", "field_agent"}

ADMIN_PERMS = frozenset({"sales.admin"})
MANAGER_PERMS = ADMIN_PERMS | {"sales.manage"}
AGENT_PERMS = MANAGER_PERMS | {"sales.write"}

TIERS = {
    "admin": (ADMIN_ROLES, ADMIN_PERMS),
    "manager": (MANAGER_ROLES, MANAGER_PERMS),
    "agent": (AGENT_ROLES, AGENT_PERMS),
}


def roles_enforced() -> bool:
    return os.getenv("SALES_ENFORCE_ROLES", "true").strip().lower() not in {"0", "false", "no", "off"}


async def effective_access(auth: AuthContext, db: Optional[AsyncSession]) -> tuple[set, set]:
    """(roles, permissions), lower-cased. Fails closed when RBAC is enforced and
    cannot be read: token roles are not trusted in that mode."""
    if not auth.rbac_loaded and db is not None:
        try:
            async with db.begin_nested():  # a missing RBAC table must not poison the request's transaction
                await rbac._load_rbac(auth, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RBAC lookup failed for sales authorization: %s", exc)
            if rbac._enforce_rbac():
                return set(), set()
    return {r.lower() for r in auth.roles or []}, {p.lower() for p in auth.permissions or []}


async def has_tier(auth: AuthContext, db: Optional[AsyncSession], tier: str) -> bool:
    if not roles_enforced() or auth.is_platform_admin:
        return True
    roles, perms = TIERS[tier]
    have_roles, have_perms = await effective_access(auth, db)
    return bool((have_roles & roles) or (have_perms & perms))


async def require(auth: AuthContext, db: Optional[AsyncSession], tier: str) -> None:
    if not await has_tier(auth, db, tier):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"This action needs a sales {tier} role")


def require_tier(tier: str) -> Callable:
    """FastAPI dependency: `Depends(require_tier("manager"))`."""
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}")

    async def dependency(auth: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)) -> AuthContext:
        await require(auth, db, tier)
        return auth

    dependency.__name__ = f"require_sales_{tier}"
    return dependency


AUTOMATION_ROLES = frozenset({"automation", "system", "service", "orchestrator"})


def is_automation_caller(auth: AuthContext, headers: Iterable[tuple[str, str]] | dict) -> bool:
    """True for workflow/automation callers (role or an X-Automation-Run header)."""
    lowered = {(k or "").lower(): v for k, v in (headers.items() if hasattr(headers, "items") else headers)}
    if (lowered.get("x-automation-run") or "").strip():
        return True
    return bool({r.lower() for r in auth.roles or []} & AUTOMATION_ROLES)
