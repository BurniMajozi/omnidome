"""Caller-identity helpers shared by the orchestrator routes.

Identity comes only from the signed AuthContext. Anything a client puts in a
request body (tenant_id, context.user_id, context.draft_only, ...) is untrusted.

Conversation ownership: new conversations are stamped with the creator's user id
(context.owner_user_id). A conversation with NO recorded owner (created before
stamping) fails closed: only admins can list/read/continue/delete it, non-admins
get 404. Owners are never guessed or backfilled; an admin may claim or reassign
one explicitly with PUT /api/conversations/{id}/owner {"user_id": ...}.

Service-to-service roles: bind_identity_context() publishes the verified
AuthContext (tenant, user, roles, permissions) in
services.common.internal_auth.identity_context so outgoing tool/memory/skills/
voicebox calls are signed with roles, but only when the call already names the
same tenant+user.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException, Request

from services.common import internal_auth
from services.common.auth import AuthContext, get_auth_context

ADMIN_ROLES = {"admin", "org_admin", "tenant_admin", "owner"}

# The only keys a client may set in `context`. Everything else (user_id,
# draft_only, customer_id, roster_mandate, run_guidance, *_briefing, run_id,
# conversation_id, skill_agent_type, memory_agent_type, ...) is server-owned.
CLIENT_CONTEXT_KEYS = {"history", "requested_model", "page", "locale", "timezone", "title", "metadata"}
MAX_HISTORY_TURNS = 50
MAX_HISTORY_CHARS = 8000

OWNER_KEY = "owner_user_id"


def is_admin(ctx: AuthContext) -> bool:
    return bool(ctx.is_platform_admin or ({r.lower() for r in ctx.roles} & ADMIN_ROLES))


def sanitize_client_context(raw: Optional[Dict[str, Any]], ctx: AuthContext) -> Dict[str, Any]:
    """Whitelist client context and stamp the signed identity over it."""
    clean: Dict[str, Any] = {}
    for key, value in (raw or {}).items():
        if key in CLIENT_CONTEXT_KEYS and not str(key).startswith("_"):
            clean[key] = value
    history = []
    for turn in clean.get("history") or []:
        # Only user/assistant turns: a client-supplied "system"/"tool" turn is injection.
        if isinstance(turn, dict) and turn.get("role") in ("user", "assistant"):
            history.append({"role": turn["role"], "content": str(turn.get("content", ""))[:MAX_HISTORY_CHARS]})
    clean["history"] = history[-MAX_HISTORY_TURNS:]
    clean["user_id"] = str(ctx.user_id)
    clean["roles"] = list(ctx.roles)
    return clean


def conversation_owner(conv) -> Optional[str]:
    owner = (getattr(conv, "context", None) or {}).get(OWNER_KEY)
    return str(owner) if owner else None


def check_conversation_access(conv, ctx: AuthContext) -> None:
    """The caller must own the conversation or be an admin. A conversation with no
    recorded owner is admin-only (fail closed)."""
    if is_admin(ctx):
        return
    owner = conversation_owner(conv)
    if not owner or owner != str(ctx.user_id):
        # 404, not 403: do not confirm that another user's conversation exists.
        raise HTTPException(status_code=404, detail="Conversation not found")


def bind_identity_context(ctx: AuthContext):
    """Publish the verified identity for outgoing service calls; returns the reset token."""
    return internal_auth.set_identity_context(ctx.tenant_id, ctx.user_id, ctx.roles, ctx.permissions)


def bind_job_identity(tenant_id, checkpoint: Optional[Dict[str, Any]]):
    """Background jobs: use the creator identity stored on the job. No stored roles
    (older jobs) means no roles are attached: fail closed."""
    cp = checkpoint or {}
    actor = cp.get("actor_id")
    if not actor:
        return internal_auth.identity_context.set(None)
    return internal_auth.set_identity_context(
        tenant_id, actor, cp.get("actor_roles") or [], cp.get("actor_permissions") or [])


async def identity_context_dependency(request: Request) -> None:
    """App-level dependency: bind the verified AuthContext for this request. Runs
    async so the contextvar is visible to the endpoint. Routes without valid auth
    (health, public chat, webhooks) simply bind nothing; their own auth rejects them."""
    try:
        ctx = await get_auth_context(request)
    except HTTPException:
        return
    except Exception:  # noqa: BLE001 - never let binding break a request
        return
    bind_identity_context(ctx)
