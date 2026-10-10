"""Panel (module) access for the knowledge layer: ONE canonical MODULE -> PANEL map and the rules that turn a
signed identity into the set of modules a caller may retrieve.

Retrieval is deny-by-default. A caller sees a card only if ALL of these hold (see AccessScope.allows and
store_pg.access_clause, which mirror each other):

  (a) the card's module is in the caller's allowed modules (this file),
  (b) the card's role / permission tag matches (card.required_roles / required_permission),
  (c) private cards: owner_id == caller. Tenant / platform admins see every MODULE of their tenant, never other
      users' PRIVATE cards.

Where "allowed modules" come from, in order:
  1. admin (platform admin or a tenant admin role)  -> every module (no module gate; private rule still applies);
  2. an explicit allow-list on the signed identity (x-modules / JWT `modules`) -> exactly that list;
  3. otherwise derived from the caller's roles (x-roles, resolved by the web tier from the admin DB) and
     permissions (`<module>.read|write|admin` rows of the admin RBAC tables, loaded by `load_scope`);
  4. nothing else: `general`, `memory` and `personal` are always allowed, every other module is denied.

Honest limitation (docs/knowledge-access.md): the product has TENANT-level module entitlements (tenant_modules,
the dashboard's allowedSections) and per-role permissions, but no per-user panel allow-list table. Rule 3 is
therefore the per-user approximation; rule 2 takes over automatically if the web tier starts signing x-modules.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from services.tenant_memory.knowledge.cards.base import DEFAULT_MODULE_ACCESS
from services.tenant_memory.knowledge.kdata import ADMIN_ROLES, AccessScope

logger = logging.getLogger("knowledge.access")


@dataclass(frozen=True)
class Panel:
    module: str            # card.module / tenant_modules.key
    label: str             # what the user sees in the sidebar
    section: str           # dashboard section id (apps/web moduleBySection)


# Canonical map. Keys are the module ids stored on knowledge chunks.
PANELS: dict[str, Panel] = {p.module: p for p in [
    Panel("billing", "Billing & Collection", "billing"),
    Panel("crm", "CRM", "crm"),
    Panel("sales", "Sales Management", "sales"),
    Panel("marketing", "Marketing Hub", "marketing"),
    Panel("call_center", "Call Center Operations", "call-center"),
    Panel("support", "Service & Support", "service"),
    Panel("retention", "Retention & Churn Analytics", "retention"),
    Panel("hr", "Staff Dome (Talent)", "talent"),
    Panel("compliance", "Compliance & Security", "compliance"),
    Panel("finance", "Finance & FP&A", "finance"),
    Panel("inventory", "Inventory & Stock Management", "inventory"),
    Panel("iot", "IoT & Device Management", "iot"),
    Panel("network", "Network Operations", "network"),
    Panel("rica", "Network Operations (RICA)", "network"),
    Panel("portal", "Portal Management", "portal"),
    Panel("analytics", "BI Studio", "analytics"),
    Panel("products", "Product Management", "products"),
    Panel("communication", "Team Communication", "communication"),
    Panel("admin", "Platform Administration", "admin"),
]}

# Other spellings seen in the UI, in permission keys and on older cards.
ALIASES = {"talent": "hr", "service": "support", "call-center": "call_center", "callcenter": "call_center",
           "bi": "analytics", "bi_studio": "analytics", "lifecycle": "crm", "journey": "crm", "customer_journey": "crm"}

# Not tied to a panel: shared company memory, un-moduled cards, and the caller's own private cards.
ALWAYS_MODULES = frozenset({"general", "memory", "personal"})

# Modules with no `<module>.read` permission row in the seed: granted to the roles that own the area (plus the
# roles listed in cards.base.DEFAULT_MODULE_ACCESS for that module). communication is staff-wide in the product.
ROLE_GRANTS: dict[str, frozenset] = {
    "communication": frozenset({"*"}),
    "portal": frozenset({"portal_manager", "marketing", "marketing_manager", "manager"}),
    "products": frozenset({"product_manager", "sales_manager", "marketing_manager", "manager"}),
}


def canonical(module: Optional[str]) -> str:
    m = (module or "general").strip().lower().split(".")[0]
    return ALIASES.get(m, m)


def normalise_modules(raw: Iterable[str]) -> frozenset:
    return frozenset(canonical(m) for m in raw if str(m).strip())


def derive_modules(roles: Iterable[str], permissions: Iterable[str]) -> frozenset:
    """Modules implied by roles and `<module>.<verb>` permission keys (no explicit allow-list available)."""
    rs = {str(r).lower() for r in roles}
    allowed = set(ALWAYS_MODULES)
    for perm in permissions:
        head, _, verb = str(perm).lower().partition(".")
        if verb in ("read", "write", "admin", "manage", "*") and canonical(head) in PANELS:
            allowed.add(canonical(head))
    for module, (_vis, role_list) in DEFAULT_MODULE_ACCESS.items():
        if "." not in module and rs & {r.lower() for r in role_list}:
            allowed.add(canonical(module))
    for module, grant in ROLE_GRANTS.items():
        if "*" in grant or rs & grant:
            allowed.add(module)
    if rs & {"admin", "org_admin", "tenant_admin", "owner", "platform_admin"}:
        allowed.add("admin")
    return frozenset(allowed)


def scope_modules(ctx: Any, roles: frozenset, permissions: frozenset, is_admin: bool) -> Optional[frozenset]:
    """None = no module gate (admin). Otherwise the exact allowed set."""
    if is_admin:
        return None
    explicit = list(getattr(ctx, "modules", None) or [])
    base = (normalise_modules(explicit) | ALWAYS_MODULES) if explicit else derive_modules(roles, permissions)
    # chunks may carry an alias spelling (e.g. module "lifecycle" belongs to the CRM panel): allow those too
    return base | frozenset(a for a, target in ALIASES.items() if target in base)


def build_scope(ctx: Any, extra_roles: Iterable[str] = (), extra_permissions: Iterable[str] = ()) -> AccessScope:
    roles = frozenset({r.lower() for r in (ctx.roles or [])} | {r.lower() for r in extra_roles})
    perms = frozenset({p.lower() for p in (ctx.permissions or [])} | {p.lower() for p in extra_permissions})
    admin = bool(getattr(ctx, "is_platform_admin", False)) or bool(roles & ADMIN_ROLES)
    return AccessScope(str(ctx.tenant_id), str(ctx.user_id) if ctx.user_id else None, roles, perms, admin,
                       scope_modules(ctx, roles, perms, admin))


_CACHE: dict[tuple, tuple[float, tuple]] = {}
_TTL_S = 60.0


def _db_lookup_enabled() -> bool:
    return os.getenv("AUTH_DB_ENFORCE", "true").strip().lower() not in {"0", "false", "no", "off"}


async def load_scope(ctx: Any) -> AccessScope:
    """The AccessScope for a request. Sync derivation from the signed identity first; when the identity carries no
    explicit module list, also look up the caller's RBAC rows (cached 60 s). A failed lookup never widens access:
    the scope simply keeps what the signed identity already proved."""
    scope = build_scope(ctx)
    if scope.is_admin or getattr(ctx, "modules", None) or not _db_lookup_enabled() or not scope.user_id:
        return scope
    key = (scope.tenant_id, scope.user_id)
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < _TTL_S:
        roles, perms = hit[1]
    else:
        try:
            from services.common.db import session_scope
            from services.common.rbac import _load_rbac
            probe = type("Probe", (), {})()
            probe.user_id, probe.tenant_id, probe.roles, probe.permissions = ctx.user_id, ctx.tenant_id, [], []
            probe.is_platform_admin, probe.rbac_loaded = False, False
            async with session_scope(ctx.tenant_id) as session:
                await _load_rbac(probe, session)
            roles, perms = tuple(probe.roles), tuple(probe.permissions)
            _CACHE[key] = (time.monotonic(), (roles, perms))
            if len(_CACHE) > 2048:
                _CACHE.clear()
        except Exception as exc:  # noqa: BLE001 - fail closed to what the signed identity proves
            logger.warning("RBAC lookup for knowledge scope failed (%s); using signed identity only", type(exc).__name__)
            return scope
    return build_scope(ctx, roles, perms)


def clear_cache() -> None:
    _CACHE.clear()


def access_meta(scope: AccessScope) -> dict:
    """Included in retrieval responses so the UI / agents can say 'you do not have access to the X panel'."""
    if scope.modules is None:
        allowed = sorted(PANELS)
        denied: list[str] = []
    else:
        allowed = sorted(m for m in scope.modules if m in PANELS)
        denied = sorted(m for m in PANELS if m not in scope.modules)
    return {
        "allowed_modules": allowed,
        "allowed_panels": [{"module": m, "panel": PANELS[m].label} for m in allowed],
        "denied_panels": [{"module": m, "panel": PANELS[m].label} for m in denied],
        "always_modules": sorted(ALWAYS_MODULES),
        "admin_scope": scope.modules is None,
    }
