"""Role gates for the support service (same model as services/sales/access.py).

    viewer      any tenant member: reads (tickets, stats, the job stream)
    technician  technician / support agent and up: accept, start and resolve jobs ASSIGNED TO THEM
                (or still unassigned); update the status of their own jobs
    manager     manager and up: create tickets, escalate to the FNO, act on anyone's job
    admin       owner / admin level: delete tickets, network-wide broadcasts

SUPPORT_ENFORCE_ROLES=false switches the gates off (local development only).
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Callable, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.common import rbac
from services.common.auth import AuthContext, get_auth_context
from services.support.database import get_session

logger = logging.getLogger("support.access")

ADMIN_ROLES = frozenset({"platform_admin", "owner", "org_admin", "admin", "tenant_admin", "super_admin"})
MANAGER_ROLES = ADMIN_ROLES | {"manager", "support_manager", "team_lead", "dispatcher"}
TECH_ROLES = MANAGER_ROLES | {"technician", "field_technician", "field_tech", "support_agent", "support", "agent"}

ADMIN_PERMS = frozenset({"support.admin"})
MANAGER_PERMS = ADMIN_PERMS | {"support.manage"}
TECH_PERMS = MANAGER_PERMS | {"support.write", "support.technician"}

TIERS = {
    "admin": (ADMIN_ROLES, ADMIN_PERMS),
    "manager": (MANAGER_ROLES, MANAGER_PERMS),
    "technician": (TECH_ROLES, TECH_PERMS),
}


def roles_enforced() -> bool:
    return os.getenv("SUPPORT_ENFORCE_ROLES", "true").strip().lower() not in {"0", "false", "no", "off"}


async def effective_access(auth: AuthContext, db: Optional[AsyncSession]) -> tuple[set, set]:
    """(roles, permissions), lower-cased; empty when RBAC is enforced but unreadable (fail closed)."""
    if not auth.rbac_loaded and db is not None:
        try:
            async with db.begin_nested():
                await rbac._load_rbac(auth, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RBAC lookup failed for support authorization: %s", type(exc).__name__)
            if rbac._enforce_rbac():
                return set(), set()
    return {r.lower() for r in auth.roles or []}, {p.lower() for p in auth.permissions or []}


async def has_tier(auth: AuthContext, db: Optional[AsyncSession], tier: str) -> bool:
    if tier == "viewer" or not roles_enforced() or auth.is_platform_admin:
        return True
    roles, perms = TIERS[tier]
    have_roles, have_perms = await effective_access(auth, db)
    return bool((have_roles & roles) or (have_perms & perms))


async def require(auth: AuthContext, db: Optional[AsyncSession], tier: str) -> None:
    if not await has_tier(auth, db, tier):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"This action needs a support {tier} role")


def require_tier(tier: str) -> Callable:
    """FastAPI dependency: `auth: AuthContext = Depends(require_tier("manager"))`."""
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}")

    async def dependency(auth: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_session)) -> AuthContext:
        await require(auth, db, tier)
        return auth

    dependency.__name__ = f"require_support_{tier}"
    return dependency


async def require_job_access(auth: AuthContext, db: Optional[AsyncSession], assigned_to: Optional[uuid.UUID]) -> None:
    """A technician may act on a job that is unassigned or assigned to them; anyone else's job needs manager."""
    if assigned_to is None or assigned_to == auth.user_id:
        return
    await require(auth, db, "manager")
