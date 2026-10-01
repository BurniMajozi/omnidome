"""
WebSocket endpoint for real-time channel updates.

URL: /api/v1/ws?channel_id=<uuid>&token=<jwt>

Auth: The JWT is passed as a query parameter because WebSocket
      upgrades cannot carry custom headers in browsers.
      The token is validated with the same logic used by REST routes.

After auth, the connection is registered in the ConnectionManager
and all further logic is delegated to realtime.handle_connection().
"""

import os
import uuid
from typing import Mapping, Optional, Tuple

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from services.common import internal_auth
from services.common.auth import decode_token_payload, AuthContext
from services.common.db import session_scope
from services.communication.access import user_channel_access
from services.communication.realtime import (
    check_origin, connect, handle_connection, max_connections_per_user, user_connection_count,
)

router = APIRouter(tags=["Real-time WebSocket"])


async def _check_channel_access(tenant_id: uuid.UUID, channel_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Public channel -> any tenant member; private -> creator, ChannelMember, or admin tier."""
    async with session_scope() as session:
        return await user_channel_access(tenant_id, user_id, channel_id, session)


def authenticate_ws(
    headers: Mapping[str, str], path: str, token: Optional[str]
) -> Tuple[uuid.UUID, uuid.UUID]:
    """Return (tenant_id, user_id) or raise ValueError.

    AUTH_MODE=signed (the deployed mode): identity comes ONLY from the HMAC-signed
    X-User-Id/X-Tenant-Id headers that the web tier (proxy.ts) added after verifying the
    Supabase session; the ?token= query param is ignored (proxy.ts already consumed it) and
    any unsigned/forged tenant is rejected. Other modes keep the legacy JWT check.
    """
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
    payload = decode_token_payload(token)
    return uuid.UUID(payload["tenant_id"]), uuid.UUID(payload["sub"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    channel_id: uuid.UUID = Query(...),
    token: Optional[str] = Query(None),
):
    if not check_origin(websocket):
        await websocket.close(code=4003, reason="Origin not allowed")
        return

    # Validate the token before accepting the connection
    try:
        tenant_id, user_id = authenticate_ws(websocket.headers, websocket.url.path, token)
    except Exception:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    # Check channel access via RBAC/visibility rules
    if not await _check_channel_access(tenant_id, channel_id, user_id):
        await websocket.close(code=4003, reason="Channel access denied")
        return

    if user_connection_count(str(tenant_id), str(user_id)) >= max_connections_per_user():
        await websocket.close(code=4429, reason="Too many connections")
        return

    # Register and drive the connection
    await connect(websocket, str(tenant_id), str(channel_id), str(user_id))
    try:
        await handle_connection(websocket, str(tenant_id), str(channel_id), str(user_id))
    except WebSocketDisconnect:
        pass
