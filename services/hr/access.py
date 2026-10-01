"""Role gates, caller->employee resolution and redaction for the HR service.

Tiers (roles come from the signed identity / RBAC tables, exactly like services/sales/access.py
and services/communication/routes/mail.py: with AUTH_ENFORCE_RBAC on (default) the RBAC tables are
authoritative, token roles are not trusted and an unreadable RBAC table fails closed):

    hr_admin   HR_ADMIN_ROLES: hr_manager, hr, hr_admin, admin, tenant_admin, owner, platform_admin.
               ``org_admin`` is deliberately NOT in this set: the pre-existing helper in main.py
               never counted it and this change keeps that behaviour. A tenant that wants it can set
               HR_ADMIN_EXTRA_ROLES=org_admin (comma separated). Permission ``hr.admin`` also counts.
    manager    manager / line_manager (plus hr_admin): may act on their own reports (direct or
               indirect, resolved through Employee.manager_id) only.
    self       any authenticated tenant member whose verified identity matches an Employee row.

Caller -> employee matching: Employee.user_id == verified user id; otherwise Employee.email equal
(case-insensitively) to an e-mail that arrived inside a *verified token payload* (jwt mode). The
signed-identity headers do not carry an e-mail (x-user-email is stripped by the web tier and is not
signed), so in signed mode only the user_id link counts. An unmatched caller is simply "not an
employee": every rule below fails closed for them. HR admins can link a user with
PUT /employees/{id}/link-user.

HR_ENFORCE_ROLES=false switches the gates off (local development only).
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common import rbac
from services.common.auth import AuthContext, get_auth_context
from services.hr.database import Employee, get_session

logger = logging.getLogger("hr.access")

HR_ADMIN_ROLES = frozenset({"admin", "hr", "hr_admin", "hr_manager", "tenant_admin", "owner", "platform_admin"})
MANAGER_ROLES = frozenset({"manager", "line_manager"})
HR_ADMIN_PERMS = frozenset({"hr.admin"})
MAX_CHAIN = 50


def roles_enforced() -> bool:
    return os.getenv("HR_ENFORCE_ROLES", "true").strip().lower() not in {"0", "false", "no", "off"}


def _admin_roles() -> frozenset:
    extra = {r.strip().lower() for r in os.getenv("HR_ADMIN_EXTRA_ROLES", "").split(",") if r.strip()}
    return HR_ADMIN_ROLES | extra


async def effective_access(auth: AuthContext, db: Optional[AsyncSession]) -> Tuple[set, set]:
    """(roles, permissions) lower-cased; empty when RBAC is enforced but unreadable (fail closed)."""
    if not auth.rbac_loaded and db is not None:
        try:
            async with db.begin_nested():  # a missing RBAC table must not poison the request transaction
                await rbac._load_rbac(auth, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RBAC lookup failed for HR authorization: %s", type(exc).__name__)
            if rbac._enforce_rbac():
                return set(), set()
    return {str(r).strip().lower() for r in auth.roles or []}, {str(p).strip().lower() for p in auth.permissions or []}


async def is_hr_admin(auth: AuthContext, db: Optional[AsyncSession]) -> bool:
    if not roles_enforced() or auth.is_platform_admin:
        return True
    roles, perms = await effective_access(auth, db)
    return bool((roles & _admin_roles()) or (perms & HR_ADMIN_PERMS))


async def has_manager_role(auth: AuthContext, db: Optional[AsyncSession]) -> bool:
    if not roles_enforced() or auth.is_platform_admin:
        return True
    roles, _ = await effective_access(auth, db)
    return bool(roles & (MANAGER_ROLES | _admin_roles()))


def token_email(auth: AuthContext) -> Optional[str]:
    """E-mail from a verified token payload only (jwt mode). Never from a raw header."""
    payload = getattr(auth, "token_payload", None) or {}
    if getattr(auth, "auth_mode", "") != "jwt":
        return None
    for key in ("email", "user_email"):
        v = payload.get(key)
        if isinstance(v, str) and "@" in v:
            return v.strip().lower()
    return None


async def resolve_caller_employee(auth: AuthContext, db: AsyncSession) -> Optional[Employee]:
    """The Employee row the verified identity belongs to, or None (never guesses)."""
    emp = (await db.execute(
        select(Employee).where(Employee.tenant_id == auth.tenant_id, Employee.user_id == auth.user_id)
    )).scalars().first()
    if emp is not None:
        return emp
    email = token_email(auth)
    if email:
        rows = (await db.execute(
            select(Employee).where(Employee.tenant_id == auth.tenant_id)
        )).scalars().all()
        matches = [e for e in rows if (e.email or "").strip().lower() == email]
        if len(matches) == 1:  # ambiguous e-mail -> no match
            return matches[0]
    return None


def manager_chain(emp_id: Any, parent_of: Dict[Any, Any]) -> Tuple[List[Any], bool]:
    """Managers above ``emp_id`` (nearest first) and whether the chain loops."""
    chain: List[Any] = []
    seen = {emp_id}
    cur = parent_of.get(emp_id)
    while cur is not None:
        if cur in seen:
            return chain, True
        chain.append(cur)
        seen.add(cur)
        if len(chain) > MAX_CHAIN:
            return chain, True
        cur = parent_of.get(cur)
    return chain, False


def would_create_cycle(emp_id: Any, new_manager_id: Any, parent_of: Dict[Any, Any]) -> bool:
    """True if making ``new_manager_id`` the manager of ``emp_id`` creates a loop."""
    if new_manager_id is None:
        return False
    if new_manager_id == emp_id:
        return True
    chain, cyclic = manager_chain(new_manager_id, parent_of)
    return cyclic or emp_id in chain


def reports_of(manager_emp_id: Any, parent_of: Dict[Any, Any]) -> set:
    """All direct and indirect reports of a manager (cycle safe)."""
    children: Dict[Any, List[Any]] = {}
    for child, parent in parent_of.items():
        if parent is not None:
            children.setdefault(parent, []).append(child)
    out: set = set()
    stack = list(children.get(manager_emp_id, []))
    while stack:
        n = stack.pop()
        if n in out or n == manager_emp_id:
            continue
        out.add(n)
        stack.extend(children.get(n, []))
    return out


async def parent_map(db: AsyncSession, tenant_id: uuid.UUID) -> Dict[Any, Any]:
    rows = (await db.execute(
        select(Employee.id, Employee.manager_id).where(Employee.tenant_id == tenant_id)
    )).all()
    return {r[0]: r[1] for r in rows}


@dataclass
class Caller:
    auth: AuthContext
    is_admin: bool
    is_manager: bool
    employee: Optional[Employee]
    unrestricted: bool = False  # HR_ENFORCE_ROLES=false

    @property
    def employee_id(self) -> Optional[uuid.UUID]:
        return self.employee.id if self.employee is not None else None

    def is_self(self, emp_id: uuid.UUID) -> bool:
        return self.employee is not None and self.employee.id == emp_id

    async def manages(self, db: AsyncSession, target_emp_id: uuid.UUID) -> bool:
        """Caller holds a manager role AND sits above the target in the manager chain."""
        if self.is_admin:
            return True
        if not self.is_manager or self.employee is None:
            return False
        pm = await parent_map(db, self.auth.tenant_id)
        chain, cyclic = manager_chain(target_emp_id, pm)
        return (not cyclic) and self.employee.id in chain


async def load_caller(auth: AuthContext, db: AsyncSession) -> Caller:
    admin = await is_hr_admin(auth, db)
    manager = admin or await has_manager_role(auth, db)
    emp = None if not roles_enforced() else await resolve_caller_employee(auth, db)
    return Caller(auth=auth, is_admin=admin, is_manager=manager, employee=emp, unrestricted=not roles_enforced())


async def get_caller(auth: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_session)) -> Caller:
    return await load_caller(auth, db)


async def require_hr_admin(auth: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_session)) -> AuthContext:
    """FastAPI dependency: HR admin only."""
    if not await is_hr_admin(auth, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This action needs an HR admin role")
    return auth


async def require_self_or_admin(caller: Caller, emp_id: uuid.UUID) -> None:
    if caller.is_admin or caller.is_self(emp_id):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You may only access your own record")


# ── redaction ────────────────────────────────────────────────────────────

SALARY_KEYS = frozenset({
    "base_salary", "salary", "gross", "net", "tax", "tax_rebate", "annual_taxable", "uif", "uif_employer",
    "sdl", "basic_salary", "commission", "allowances", "other_deductions", "total_gross", "total_net",
})
BANK_KEYS = frozenset({"account_number", "bank_account", "bank_account_number"})
ID_KEYS = frozenset({"id_number", "tax_number", "passport_number"})
DROP_KEYS = frozenset({"paystack_recipient_code", "paystack_transfer_code", "paystack_reference", "bank_code", "account_name"})


def mask_tail(value: Any, keep: int = 4, char: str = "•") -> Optional[str]:
    if value is None or value == "":
        return None
    s = str(value)
    if len(s) <= keep:
        return char * len(s)
    return char * 4 + s[-keep:]


_LONG_DIGITS = re.compile(r"\d{6,}")


def scrub_text(text: Optional[str]) -> Optional[str]:
    """Mask long digit runs (account / ID / card numbers) in free text before it is stored or logged."""
    if text is None:
        return None
    return _LONG_DIGITS.sub(lambda m: "•" * 4 + m.group(0)[-4:], str(text))


def redact_employee(data: Dict[str, Any], is_admin: bool) -> Dict[str, Any]:
    """Employee/payroll dict as safe for a non-admin viewer. Admins get the dict unchanged.
    Bank account numbers keep the last 4 digits, ID/tax numbers are masked, salary and payout
    figures are removed."""
    if is_admin:
        return data
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if k in SALARY_KEYS or k in DROP_KEYS:
            continue
        if k in BANK_KEYS:
            out[k] = mask_tail(v)
        elif k in ID_KEYS:
            out[k] = mask_tail(v, keep=2)
        else:
            out[k] = v
    return out


def redact_many(rows: Iterable[Dict[str, Any]], is_admin: bool) -> List[Dict[str, Any]]:
    return [redact_employee(r, is_admin) for r in rows]


def redact_payslip(data: Dict[str, Any], is_admin: bool) -> Dict[str, Any]:
    """Payslip dict for its own employee (non-admin): pay figures stay, but bank account / ID / tax
    numbers are masked and Paystack identifiers are dropped. Admins get the dict unchanged."""
    if is_admin:
        return data
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if k in DROP_KEYS and k != "account_name":
            continue
        if k in BANK_KEYS:
            out[k] = mask_tail(v)
        elif k in ID_KEYS:
            out[k] = mask_tail(v, keep=2)
        else:
            out[k] = v
    return out
