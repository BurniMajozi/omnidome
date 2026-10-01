"""
OmniDome Communication Service — Real-time WebSocket manager.

Manages connected WebSocket clients per tenant and channel.
When a message is posted (REST), the route calls broadcast_message()
which pushes the payload to every connected client in that channel.

Connection URL:
  ws://<host>/api/v1/ws?channel_id=<uuid>&token=<jwt>

Events emitted to clients (JSON):
  { "type": "message",   "data": <MessageRead>      }
  { "type": "typing",    "data": { "user_id": "..." } }
  { "type": "presence",  "data": { "user_id": "...", "online": true } }
  { "type": "ping",      "data": {}                 }   # keepalive

Events accepted from clients (JSON):
  { "type": "typing",   "channel_id": "..." }
  { "type": "pong"                          }
"""

import asyncio
import json
import logging
import os
import uuid
from collections import defaultdict
from typing import Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger("communication.realtime")

# ── Connection registry ───────────────────────────────────────────────────
#
# Structure:  { tenant_id: { channel_id: { (user_id, websocket) } } }
#
# Using a set of tuples so we can look up sockets by user_id if needed.

_connections: Dict[str, Dict[str, Set[tuple]]] = defaultdict(lambda: defaultdict(set))

PING_INTERVAL = 25  # seconds — keeps proxies from closing idle connections

REDIS_URL = os.getenv("REDIS_URL")
_redis_client = None
_redis_pubsub = None
_redis_listener_task: Optional[asyncio.Task] = None
_subscribed_topics: Set[str] = set()


async def _get_redis():
    global _redis_client
    if not REDIS_URL:
        return None
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis
            _redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
            logger.info("Connected to Redis for WebSocket fan-out at %s", REDIS_URL)
        except Exception as exc:
            logger.warning("Redis pub/sub not initialized: %s (using process-local broadcast)", exc)
            return None
    return _redis_client


async def _ensure_redis_sub(tenant_id: str, channel_id: str) -> None:
    global _redis_pubsub, _redis_listener_task
    topic = f"comm:ws:{tenant_id}:{channel_id}"
    if topic in _subscribed_topics or not REDIS_URL:
        return
    r = await _get_redis()
    if not r:
        return
    try:
        if _redis_pubsub is None:
            _redis_pubsub = r.pubsub()
        await _redis_pubsub.subscribe(topic)
        _subscribed_topics.add(topic)

        if _redis_listener_task is None or _redis_listener_task.done():
            _redis_listener_task = asyncio.create_task(_redis_listen_loop())
    except Exception as exc:
        logger.warning("Failed to subscribe to Redis topic %s: %s", topic, exc)


async def _redis_listen_loop() -> None:
    global _redis_pubsub
    try:
        while _redis_pubsub and _subscribed_topics:
            message = await _redis_pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                try:
                    payload = json.loads(message["data"])
                    await _local_broadcast(
                        payload["tenant_id"], payload["channel_id"],
                        payload["type"], payload["data"]
                    )
                except Exception as exc:
                    logger.debug("Error processing redis ws event: %s", exc)
            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.warning("Redis pubsub listener exited: %s", exc)


# ── Public API ────────────────────────────────────────────────────────────

async def connect(
    websocket: WebSocket,
    tenant_id: str,
    channel_id: str,
    user_id: str,
) -> None:
    await websocket.accept()
    _connections[tenant_id][channel_id].add((user_id, websocket))
    logger.info("WS connected  tenant=%s channel=%s user=%s", tenant_id, channel_id, user_id)

    if REDIS_URL:
        await _ensure_redis_sub(tenant_id, channel_id)

    # Announce presence to channel peers
    await broadcast_event(tenant_id, channel_id, "presence", {"user_id": user_id, "online": True})


def disconnect(
    websocket: WebSocket,
    tenant_id: str,
    channel_id: str,
    user_id: str,
) -> None:
    _connections[tenant_id][channel_id].discard((user_id, websocket))
    if not _connections[tenant_id][channel_id]:
        del _connections[tenant_id][channel_id]
    logger.info("WS disconnected  tenant=%s channel=%s user=%s", tenant_id, channel_id, user_id)


async def broadcast_message(tenant_id: str, channel_id: str, message_data: dict) -> None:
    """Called by the send_message route after a message is persisted."""
    await broadcast_event(tenant_id, channel_id, "message", message_data)


async def _local_broadcast(
    tenant_id: str,
    channel_id: str,
    event_type: str,
    data: dict,
) -> None:
    payload = json.dumps({"type": event_type, "data": data})
    dead: list[tuple] = []

    for entry in list(_connections[tenant_id].get(channel_id, set())):
        user_id, ws = entry
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(entry)

    for entry in dead:
        _connections[tenant_id][channel_id].discard(entry)


async def broadcast_event(
    tenant_id: str,
    channel_id: str,
    event_type: str,
    data: dict,
    *,
    from_pubsub: bool = False,
) -> None:
    await _local_broadcast(tenant_id, channel_id, event_type, data)

    if not from_pubsub and REDIS_URL:
        r = await _get_redis()
        if r:
            try:
                msg = json.dumps({
                    "tenant_id": tenant_id,
                    "channel_id": channel_id,
                    "type": event_type,
                    "data": data,
                })
                await r.publish(f"comm:ws:{tenant_id}:{channel_id}", msg)
            except Exception as exc:
                logger.debug("Failed publishing event to Redis: %s", exc)


# ── Per-connection handler ────────────────────────────────────────────────

async def handle_connection(
    websocket: WebSocket,
    tenant_id: str,
    channel_id: str,
    user_id: str,
) -> None:
    """
    Drives a single WebSocket connection:
    - Runs a ping loop to keep the connection alive
    - Handles incoming events from the client (typing, pong)
    - Cleans up on disconnect
    """
    ping_task = asyncio.create_task(_ping_loop(websocket, tenant_id, channel_id, user_id))
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue

            etype = event.get("type")

            if etype == "typing":
                # Fan out typing indicator to channel peers (excluding sender)
                ch_id = event.get("channel_id", channel_id)
                await _broadcast_except(
                    tenant_id, ch_id, user_id,
                    {"type": "typing", "data": {"user_id": user_id}},
                )
            elif etype == "pong":
                pass  # Keepalive acknowledged — nothing to do

    except Exception:
        logger.debug("Client disconnected or ping failed, cleaning up")
    finally:
        ping_task.cancel()
        disconnect(websocket, tenant_id, channel_id, user_id)
        # Announce offline presence
        await broadcast_event(
            tenant_id, channel_id,
            "presence", {"user_id": user_id, "online": False},
        )


async def _ping_loop(
    websocket: WebSocket,
    tenant_id: str,
    channel_id: str,
    user_id: str,
) -> None:
    try:
        while True:
            await asyncio.sleep(PING_INTERVAL)
            await websocket.send_text(json.dumps({"type": "ping", "data": {}}))
    except Exception:
        logger.debug("Ping loop exited, connection likely closed")


async def _broadcast_except(
    tenant_id: str,
    channel_id: str,
    exclude_user: str,
    payload: dict,
) -> None:
    raw = json.dumps(payload)
    dead: list[tuple] = []
    for entry in list(_connections[tenant_id].get(channel_id, set())):
        uid, ws = entry
        if uid == exclude_user:
            continue
        try:
            await ws.send_text(raw)
        except Exception:
            dead.append(entry)
    for entry in dead:
        _connections[tenant_id][channel_id].discard(entry)
