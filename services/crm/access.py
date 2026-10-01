"""Role gates and PII redaction for the CRM service.

Same model as services/sales/access.py: roles come from the RBAC tables (AUTH_ENFORCE_RBAC)
or, with enforcement off, from the signed identity headers. Reads stay open to every member
of the tenant; changing records needs a role:

    agent    sales / support staff: create and edit customers, leads, notes, tags,
             companies, segments
    manager  manager and up
    admin    owner / admin level: sees full PII (ID numbers) and may merge / bulk-change

CRM_ENFORCE_ROLES=false switches the gates off (local development only; default true).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, Iterable, List, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.common import rbac
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("crm.access")

ADMIN_ROLES = frozenset({"platform_admin", "owner", "org_admin", "admin", "tenant_admin", "super_admin"})
MANAGER_ROLES = ADMIN_ROLES | {"manager", "sales_manager", "support_manager"}
AGENT_ROLES = MANAGER_ROLES | {
    "sales", "sales_agent", "sales_rep", "agent", "field_agent", "support_agent", "crm_agent", "account_manager",
}

ADMIN_PERMS = frozenset({"crm.admin"})
MANAGER_PERMS = ADMIN_PERMS | {"crm.manage"}
AGENT_PERMS = MANAGER_PERMS | {"crm.write"}

TIERS = {
    "admin": (ADMIN_ROLES, ADMIN_PERMS),
    "manager": (MANAGER_ROLES, MANAGER_PERMS),
    "agent": (AGENT_ROLES, AGENT_PERMS),
}


def roles_enforced() -> bool:
    return os.getenv("CRM_ENFORCE_ROLES", "true").strip().lower() not in {"0", "false", "no", "off"}


async def effective_access(auth: AuthContext, db: Optional[AsyncSession]) -> tuple[set, set]:
    """(roles, permissions), lower-cased. Fails closed when RBAC is enforced and cannot be read."""
    if not auth.rbac_loaded and db is not None:
        try:
            async with db.begin_nested():  # a missing RBAC table must not poison the transaction
                await rbac._load_rbac(auth, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RBAC lookup failed for CRM authorization: %s", exc)
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"This action needs a CRM {tier} role")


def require_tier(tier: str) -> Callable:
    """FastAPI dependency: `Depends(require_tier("agent"))`; returns the AuthContext."""
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}")

    async def dependency(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        from services.crm.database import get_session  # late: keeps this module import-light

        async with get_session() as db:
            await require(auth, db, tier)
        return auth

    dependency.__name__ = f"require_crm_{tier}"
    return dependency


require_write = require_tier("agent")
require_admin = require_tier("admin")


# ---------------------------------------------------------------------------
# PII redaction
# ---------------------------------------------------------------------------

ID_KEYS = frozenset({"id_number", "passport_number", "tax_number"})
BANK_KEYS = frozenset({
    "bank_account", "bank_account_number", "account_holder", "bank_name", "branch_code",
    "card_number", "iban", "debit_order_account",
})


def mask_id(value: Any, keep: int = 4) -> Optional[str]:
    """Last `keep` characters only; None for empty values."""
    if value is None or value == "":
        return None
    s = str(value)
    if len(s) <= keep:
        return "*" * len(s)
    return "*" * (len(s) - keep) + s[-keep:]


def redact_customer(data: Dict[str, Any], is_admin: bool) -> Dict[str, Any]:
    """Customer dict as safe for a non-admin viewer (admins get it unchanged): ID numbers keep
    only the last four characters and banking fields are dropped."""
    if is_admin:
        return data
    out: Dict[str, Any] = {}
    for key, value in data.items():
        if key in BANK_KEYS:
            continue
        out[key] = mask_id(value) if key in ID_KEYS else value
    return out


def redact_many(rows: Iterable[Dict[str, Any]], is_admin: bool) -> List[Dict[str, Any]]:
    return [redact_customer(r, is_admin) for r in rows]
