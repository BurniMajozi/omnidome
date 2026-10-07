"""Caller-identity helpers shared by the orchestrator routes.

Identity comes only from the signed AuthContext. Anything a client puts in a
request body (tenant_id, context.user_id, context.draft_only, ...) is untrusted.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException

from services.common.auth import AuthContext

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
    """The caller must own the conversation unless an admin. Conversations that
    predate ownership stamping (no owner recorded) stay tenant-visible."""
    owner = conversation_owner(conv)
    if owner and owner != str(ctx.user_id) and not is_admin(ctx):
        # 404, not 403: do not confirm that another user's conversation exists.
        raise HTTPException(status_code=404, detail="Conversation not found")
