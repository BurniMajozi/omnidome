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

from services.common.auth import decode_token_payload, AuthContext
from services.communication.realtime import connect, handle_connection

router = APIRouter(tags=["Real-time WebSocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    channel_id: uuid.UUID = Query(...),
    token: str = Query(...),
):
    # Validate the token before accepting the connection
    try:
        payload = decode_token_payload(token)
        tenant_id = str(payload["tenant_id"])
        user_id = str(payload["sub"])
    except Exception:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    # Register and drive the connection
    await connect(websocket, tenant_id, str(channel_id), user_id)
    try:
        await handle_connection(websocket, tenant_id, str(channel_id), user_id)
    except WebSocketDisconnect:
        pass
