"""
WebSocket endpoint for real-time channel updates.

URL: /api/v1/ws?channel_id=<uuid>&token=<jwt>

Auth: The JWT is passed as a query parameter because WebSocket
      upgrades cannot carry custom headers in browsers.
      The token is validated with the same logic used by REST routes.

After auth, the connection is registered in the ConnectionManager
and all further logic is delegated to realtime.handle_connection().
"""

import uuid
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from services.common.auth import decode_token_payload, AuthContext
from services.common.db import session_scope
from services.communication.models import Channel
from services.communication.realtime import connect, handle_connection

router = APIRouter(tags=["Real-time WebSocket"])


async def _check_channel_access(tenant_id: uuid.UUID, channel_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Check if user has access to channel (RBAC-based visibility)."""
    async with session_scope() as session:
        stmt = select(Channel).where(
            Channel.id == channel_id,
            Channel.tenant_id == tenant_id
        )
        result = await session.execute(stmt)
        channel = result.scalar_one_or_none()
        if not channel:
            return False
        # Public channel (not private) or user is creator -> allow
        if not channel.is_private or channel.created_by == user_id:
            return True
        # TODO: extend with explicit channel membership table if needed
        return False


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    channel_id: uuid.UUID = Query(...),
    token: str = Query(...),
):
    # Validate the token before accepting the connection
    try:
        payload = decode_token_payload(token)
        tenant_id = uuid.UUID(payload["tenant_id"])
        user_id = uuid.UUID(payload["sub"])
    except Exception:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    # Check channel access via RBAC/visibility rules
    if not await _check_channel_access(tenant_id, channel_id, user_id):
        await websocket.close(code=4003, reason="Channel access denied")
        return

    # Register and drive the connection
    await connect(websocket, str(tenant_id), str(channel_id), str(user_id))
    try:
        await handle_connection(websocket, str(tenant_id), str(channel_id), str(user_id))
    except WebSocketDisconnect:
        pass
