"""Role tiers for the call-center service.

    agent  call-center staff (and anyone above): everything not listed as admin
    admin  owner/admin/manager level: delete session/agent/queue, provider credentials, CDR import/export,
           recording download (recording_url is redacted from responses for non-admins)

Roles come from the signed identity headers (AUTH_MODE=signed). CALL_CENTER_ENFORCE_ROLES=false switches
the gates off (local development only).
"""

from __future__ import annotations

import os
import re
from contextvars import ContextVar
from typing import Iterable

from fastapi import Depends, HTTPException, Request, status

from services.common.auth import AuthContext, get_auth_context

ADMIN_ROLES = frozenset({"platform_admin", "owner", "org_admin", "admin", "tenant_admin", "super_admin",
                         "call_center_admin", "call_center_manager"})
AGENT_ROLES = ADMIN_ROLES | {"manager", "supervisor", "agent", "call_center_agent", "support_agent",
                              "sales", "sales_agent", "sales_rep", "field_agent", "team_lead",
                              "automation", "system", "service", "orchestrator"}
ADMIN_PERMS = frozenset({"call_center.admin"})
AGENT_PERMS = ADMIN_PERMS | {"call_center.write", "call_center.agent"}

# True for the current request when the caller is admin tier (read by response redaction).
request_is_admin: ContextVar[bool] = ContextVar("call_center_request_is_admin", default=False)


def roles_enforced() -> bool:
    return os.getenv("CALL_CENTER_ENFORCE_ROLES", "true").strip().lower() not in {"0", "false", "no", "off"}


def _have(auth: AuthContext, roles: Iterable[str], perms: Iterable[str]) -> bool:
    return bool(({r.lower() for r in auth.roles or []} & set(roles)) or
                ({p.lower() for p in auth.permissions or []} & set(perms)))


def has_tier(auth: AuthContext, tier: str) -> bool:
    if not roles_enforced() or auth.is_platform_admin:
        return True
    if tier == "admin":
        return _have(auth, ADMIN_ROLES, ADMIN_PERMS)
    return _have(auth, AGENT_ROLES, AGENT_PERMS)


_ADMIN_PATH = re.compile(r"^/(provider-credentials(/|$)|reports/import$)|/export(/|$)|/recordings?(/|$)")


def required_tier(method: str, path: str) -> str:
    if method.upper() == "DELETE" or _ADMIN_PATH.search(path):
        return "admin"
    return "agent"


async def enforce_route_tier(request: Request, auth: AuthContext = Depends(get_auth_context)) -> None:
    tier = required_tier(request.method, request.url.path)
    if not has_tier(auth, tier):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"This action needs a call-center {tier} role")
    request_is_admin.set(has_tier(auth, "admin"))
