"""WebSocket authentication from the signed identity headers (tenant never comes from the query string).

Same contract as services/communication/routes/ws.py::authenticate_ws. In AUTH_MODE=signed the
HMAC-signed X-User-Id/X-Tenant-Id headers added by the web tier are the only accepted source; the
?token= parameter is ignored. In other modes (dev) the legacy JWT is decoded with the REST decoder
and AUTH_JWT_VERIFY=false is refused for websockets.
"""

from __future__ import annotations

import os
import uuid
from typing import Mapping, Optional, Tuple

from services.common import internal_auth


def authenticate_ws(headers: Mapping[str, str], path: str, token: Optional[str]) -> Tuple[uuid.UUID, uuid.UUID]:
    """Return (tenant_id, user_id) or raise ValueError."""
    mode = os.getenv("AUTH_MODE", "header").strip().lower()
    if mode == "signed":
        try:
            internal_auth.verify_request(headers, "GET", path, internal_auth.get_secret())
            user = headers.get("x-user-id") or headers.get("X-User-Id")
            tenant = headers.get("x-tenant-id") or headers.get("X-Tenant-Id")
            return uuid.UUID(str(tenant)), uuid.UUID(str(user))
        except Exception as exc:
            raise ValueError("invalid signed identity") from exc
    if not token:
        raise ValueError("missing token")
    if os.getenv("AUTH_JWT_VERIFY", "true").strip().lower() in {"0", "false", "no", "off"}:
        raise ValueError("unverified tokens are not accepted for websockets")
    from services.common.auth import decode_token_payload
    payload = decode_token_payload(token)
    return uuid.UUID(str(payload["tenant_id"])), uuid.UUID(str(payload["sub"]))


def ws_roles(headers: Mapping[str, str]) -> set:
    """Roles from the signed identity headers (covered by the signature, so only call this AFTER
    authenticate_ws succeeded in signed mode). Empty set in other modes."""
    if os.getenv("AUTH_MODE", "header").strip().lower() != "signed":
        return set()
    raw = headers.get("x-roles") or headers.get("X-Roles") or ""
    return {r.strip().lower() for r in raw.split(",") if r.strip()}
