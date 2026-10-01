"""Role tiers for the network service (same model as services/sales/access.py).

    viewer    any member of the tenant: read
    operator  network/NOC/support staff: disconnect a session, reset/push CPE, trigger provisioning
    admin     owner/admin level: create/delete NAS clients, RADIUS accounts, service plans, devices

Roles/permissions come from the signed identity headers (AUTH_MODE=signed; the signature covers
X-Roles/X-Permissions). NETWORK_ENFORCE_ROLES=false switches the gates off (local development only).
"""

from __future__ import annotations

import os
import re
from typing import Callable

from fastapi import Depends, HTTPException, Request, status

from services.common.auth import AuthContext, get_auth_context

ADMIN_ROLES = frozenset({"platform_admin", "owner", "org_admin", "admin", "tenant_admin", "super_admin",
                         "network_admin"})
OPERATOR_ROLES = ADMIN_ROLES | {"manager", "network_operator", "network_engineer", "noc", "technician",
                                 "support_agent", "support_manager", "operator",
                                 "automation", "system", "service", "orchestrator"}
ADMIN_PERMS = frozenset({"network.admin"})
OPERATOR_PERMS = ADMIN_PERMS | {"network.operate", "network.write"}

TIERS = {
    "admin": (ADMIN_ROLES, ADMIN_PERMS),
    "operator": (OPERATOR_ROLES, OPERATOR_PERMS),
    "viewer": (None, None),
}


def roles_enforced() -> bool:
    return os.getenv("NETWORK_ENFORCE_ROLES", "true").strip().lower() not in {"0", "false", "no", "off"}


def has_tier(auth: AuthContext, tier: str) -> bool:
    if not roles_enforced() or auth.is_platform_admin or tier == "viewer":
        return True
    roles, perms = TIERS[tier]
    return bool(({r.lower() for r in auth.roles or []} & roles) or ({p.lower() for p in auth.permissions or []} & perms))


def require_tier(tier: str) -> Callable:
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}")

    async def dependency(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if not has_tier(auth, tier):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"This action needs a network {tier} role")
        return auth

    dependency.__name__ = f"require_network_{tier}"
    return dependency


# ── Route -> tier map (applied to every router in main.py; no per-endpoint edits) ──────────────
_ADMIN_WRITE = re.compile(
    r"/radius/(accounts(/[^/]+)?|nas(/[^/]+)?)$"            # create/update RADIUS accounts, NAS clients
    r"|^/services$|/services/[^/]+/(terminate|speed-change)$"  # service (plan) lifecycle that changes the product
    r"|/performance/sla-profiles"                          # SLA plans
    r"|/config/templates$|/config/push$|/config/pushes/[^/]+/rollback$"
    r"|/devices$|/devices/[^/]+$"                          # create/update device
)


def required_tier(method: str, path: str) -> str:
    """viewer for reads; admin for destructive/credential/plan changes; operator for other writes."""
    method = method.upper()
    if method in {"GET", "HEAD", "OPTIONS"}:
        return "viewer"
    if method == "DELETE":
        return "admin"
    clean = "/" + path.strip("/")
    # strip a gateway prefix such as /api/network
    clean = re.sub(r"^/api/network", "", clean) or "/"
    if _ADMIN_WRITE.search(clean):
        return "admin"
    return "operator"


async def enforce_route_tier(request: Request, auth: AuthContext = Depends(get_auth_context)) -> None:
    tier = required_tier(request.method, request.url.path)
    if not has_tier(auth, tier):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"This action needs a network {tier} role")
