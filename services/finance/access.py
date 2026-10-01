"""Role gates for the finance service (same model as services/sales/access.py).

    reader  any finance / billing role: read the ledger and reports
    clerk   may create DRAFT journal entries, receipts, records, POs
    admin   finance admin: post, auto-post, reverse, close/reopen periods,
            manage accounts, run the billing sync

System callers (billing, sales, inventory) carry the shared INTERNAL_SERVICE_KEY in
`x-internal-key`; that is accepted wherever `internal_ok=True` is passed (journal create
incl. auto_post). FINANCE_ENFORCE_ROLES=false switches the gates off (local development only).
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.common import rbac
from services.common.auth import AuthContext, get_auth_context
from services.finance.database import get_session

logger = logging.getLogger("finance.access")

ADMIN_ROLES = frozenset({"platform_admin", "super_admin", "owner", "org_admin", "admin", "tenant_admin",
                         "billing_admin", "finance_admin", "finance_manager"})
CLERK_ROLES = ADMIN_ROLES | {"finance", "accountant", "bookkeeper", "finance_clerk", "manager"}
READER_ROLES = CLERK_ROLES | {"billing", "billing_manager", "finance_viewer", "auditor"}

ADMIN_PERMS = frozenset({"finance.admin"})
CLERK_PERMS = ADMIN_PERMS | {"finance.write"}
READER_PERMS = CLERK_PERMS | {"finance.read", "billing.read"}

TIERS = {"admin": (ADMIN_ROLES, ADMIN_PERMS), "clerk": (CLERK_ROLES, CLERK_PERMS), "reader": (READER_ROLES, READER_PERMS)}


def roles_enforced() -> bool:
    return os.getenv("FINANCE_ENFORCE_ROLES", "true").strip().lower() not in {"0", "false", "no", "off"}


def has_internal_key(request: Optional[Request]) -> bool:
    expected = os.getenv("INTERNAL_SERVICE_KEY", "")
    provided = (request.headers.get("x-internal-key") if request is not None else "") or ""
    return bool(expected) and secrets.compare_digest(provided, expected)


async def effective_access(auth: AuthContext, db: Optional[AsyncSession]) -> tuple[set, set]:
    if not auth.rbac_loaded and db is not None:
        try:
            async with db.begin_nested():
                await rbac._load_rbac(auth, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RBAC lookup failed for finance authorization: %s", exc)
            if rbac._enforce_rbac():
                return set(), set()
    return {r.lower() for r in auth.roles or []}, {p.lower() for p in auth.permissions or []}


async def has_tier(auth: AuthContext, db: Optional[AsyncSession], tier: str, request: Optional[Request] = None,
                   internal_ok: bool = False) -> bool:
    if not roles_enforced() or auth.is_platform_admin:
        return True
    if internal_ok and has_internal_key(request):
        return True
    roles, perms = TIERS[tier]
    have_roles, have_perms = await effective_access(auth, db)
    return bool((have_roles & roles) or (have_perms & perms))


async def require(auth, db, tier: str, request: Optional[Request] = None, internal_ok: bool = False) -> None:
    if not await has_tier(auth, db, tier, request, internal_ok):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"This action needs a finance {tier} role")


def require_tier(tier: str, internal_ok: bool = False) -> Callable:
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}")

    async def dependency(request: Request, auth: AuthContext = Depends(get_auth_context),
                         db: AsyncSession = Depends(get_session)) -> AuthContext:
        await require(auth, db, tier, request, internal_ok)
        return auth

    dependency.__name__ = f"require_finance_{tier}"
    return dependency
