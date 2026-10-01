"""
OmniDome Communication Service — Real-time WebSocket manager.

Manages connected WebSocket clients per tenant and channel. When a message is posted (REST), the
route calls broadcast_message() after the commit, which pushes the payload to every connected
client of that channel (and, with REDIS_URL, to other replicas).

Connection URL:
  ws://<host>/api/v1/ws?channel_id=<uuid>&token=<jwt>

Events emitted to clients (JSON):
  { "type": "message",   "data": <MessageRead>      }
  { "type": "typing",    "data": { "user_id": "..." } }
  { "type": "presence",  "data": { "user_id": "...", "online": true } }
  { "type": "ping",      "data": {}                 }   # keepalive

Events accepted from clients (JSON):
  { "type": "typing" }      # always applies to the connection's own channel; any channel_id is ignored
  { "type": "pong"   }

Close codes: 4001 bad identity, 4003 channel/origin denied, 4408 idle (no inbound frame), 4429 too many
connections / inbound flood, 1009 frame too large.

Env: WS_MAX_CONNECTIONS_PER_USER (5), WS_MAX_MESSAGE_BYTES (65536), WS_INBOUND_PER_10S (50),
WS_IDLE_TIMEOUT (75 s), WS_SEND_TIMEOUT (5 s), WS_ALLOWED_ORIGINS (comma list, "*" = any), APP_PUBLIC_URL.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Optional, Set
from urllib.parse import urlparse

from fastapi import WebSocket

logger = logging.getLogger("communication.realtime")

# { tenant_id: { channel_id: { (user_id, websocket) } } }
_connections: Dict[str, Dict[str, Set[tuple]]] = defaultdict(lambda: defaultdict(set))

PING_INTERVAL = 25  # seconds — keeps proxies from closing idle connections

# Unique per process: published payloads carry it so a replica ignores its own echo.
ORIGIN_ID = uuid.uuid4().hex


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, "") or default))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.getenv(name, "") or default))
    except ValueError:
        return default


def max_connections_per_user() -> int:
    return _env_int("WS_MAX_CONNECTIONS_PER_USER", 5)


def max_message_bytes() -> int:
    return _env_int("WS_MAX_MESSAGE_BYTES", 64 * 1024)


def idle_timeout() -> float:
    return _env_float("WS_IDLE_TIMEOUT", PING_INTERVAL * 3)


def send_timeout() -> float:
    return _env_float("WS_SEND_TIMEOUT", 5.0)


class SlidingWindow:
    """Per-connection inbound rate limit: at most `limit` events per `window` seconds."""

    def __init__(self, limit: int, window: float):
        self.limit = limit
        self.window = window
        self._hits: Deque[float] = deque()

    def allow(self, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        while self._hits and self._hits[0] <= now - self.window:
            self._hits.popleft()
        if len(self._hits) >= self.limit:
            return False
        self._hits.append(now)
        return True


def new_inbound_limiter() -> SlidingWindow:
    return SlidingWindow(_env_int("WS_INBOUND_PER_10S", 50), 10.0)


def frame_too_large(raw: str) -> bool:
    return len(raw.encode("utf-8", "ignore")) > max_message_bytes()


def _origin_parts(value: str) -> tuple:
    p = urlparse(value if "://" in value else f"//{value}")
    return (p.scheme or "").lower(), (p.hostname or "").lower(), p.port


def origin_allowed(
    origin: Optional[str],
    host_header: Optional[str] = None,
    allowed: Optional[str] = None,
    public_url: Optional[str] = None,
) -> bool:
    """Reject upgrades whose Origin is present and not allowed. No Origin (non-browser client) is allowed."""
    if not origin:
        return True
    o_scheme, o_host, o_port = _origin_parts(origin)
    if not o_host:
        return False
    entries = [e.strip() for e in (allowed or "").split(",") if e.strip()]
    if "*" in entries:
        return True
    for e in entries:
        e_scheme, e_host, e_port = _origin_parts(e)
        if e_host == o_host and (not e_port or e_port == o_port) and (not ("://" in e) or e_scheme == o_scheme):
            return True
    if o_host in {"localhost", "127.0.0.1", "::1"} or o_host.endswith(".localhost"):
        return True
    if public_url:
        _, p_host, _ = _origin_parts(public_url)
        if p_host and p_host == o_host:
            return True
    if host_header:
        _, h_host, _ = _origin_parts(host_header)
        if h_host and h_host == o_host:
            return True
    return False


def check_origin(websocket: WebSocket) -> bool:
    return origin_allowed(
        websocket.headers.get("origin"),
        websocket.headers.get("host"),
        os.getenv("WS_ALLOWED_ORIGINS"),
        os.getenv("APP_PUBLIC_URL"),
    )


def user_connection_count(tenant_id: str, user_id: str) -> int:
    return sum(1 for chans in _connections.get(tenant_id, {}).values() for (uid, _ws) in chans if uid == user_id)


def _sockets(tenant_id: str, channel_id: str) -> list:
    return list(_connections.get(tenant_id, {}).get(channel_id, ()))


# ── Redis fan-out ─────────────────────────────────────────────────────────

REDIS_URL = os.getenv("REDIS_URL")
_redis_client = None
_redis_pubsub = None
_redis_listener_task: Optional[asyncio.Task] = None
_subscribed_topics: Set[str] = set()


def _topic(tenant_id: str, channel_id: str) -> str:
    return f"comm:ws:{tenant_id}:{channel_id}"


async def _get_redis():
    global _redis_client
    if not REDIS_URL:
        return None
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis
            _redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
            logger.info("Connected to Redis for WebSocket fan-out")
        except Exception as exc:
            logger.warning("Redis pub/sub not initialized: %s (using process-local broadcast)", exc)
            return None
    return _redis_client


async def _ensure_redis_sub(tenant_id: str, channel_id: str) -> None:
    global _redis_pubsub
    topic = _topic(tenant_id, channel_id)
    if not REDIS_URL or topic in _subscribed_topics:
        _ensure_listener()
        return
    r = await _get_redis()
    if not r:
        return
    try:
        if _redis_pubsub is None:
            _redis_pubsub = r.pubsub()
        await _redis_pubsub.subscribe(topic)
        _subscribed_topics.add(topic)
        _ensure_listener()
    except Exception as exc:
        logger.warning("Failed to subscribe to Redis topic: %s", exc)


async def _maybe_unsubscribe(tenant_id: str, channel_id: str) -> None:
    """Unsubscribe when the last local socket of the channel has left."""
    topic = _topic(tenant_id, channel_id)
    if topic not in _subscribed_topics or _sockets(tenant_id, channel_id):
        return
    _subscribed_topics.discard(topic)
    if _redis_pubsub is not None:
        try:
            await _redis_pubsub.unsubscribe(topic)
        except Exception as exc:
            logger.debug("Redis unsubscribe failed: %s", exc)


def _ensure_listener() -> None:
    global _redis_listener_task
    if _redis_listener_task is None or _redis_listener_task.done():
        _redis_listener_task = asyncio.create_task(_listener_supervisor())


async def deliver_redis_payload(raw: Any, channel: Optional[str] = None) -> bool:
    """Validate and deliver one pub/sub payload to local sockets. Returns True when delivered.

    Skips our own echo (ORIGIN_ID), requires tenant_id + channel_id + type + data, and requires the
    payload to match the topic it arrived on; delivery is looked up by the payload's tenant, so a
    payload can only ever reach sockets of its own tenant+channel."""
    try:
        payload = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        if not isinstance(payload, dict):
            return False
        tenant_id, channel_id = payload.get("tenant_id"), payload.get("channel_id")
        etype, data = payload.get("type"), payload.get("data")
        if not (isinstance(tenant_id, str) and isinstance(channel_id, str) and isinstance(etype, str)
                and isinstance(data, dict)):
            return False
        if payload.get("origin") == ORIGIN_ID:
            return False
        if channel is not None and channel != _topic(tenant_id, channel_id):
            return False
        await _local_broadcast(tenant_id, channel_id, etype, data, exclude_user=payload.get("exclude_user"))
        return True
    except Exception as exc:
        logger.debug("Error processing redis ws event: %s", exc)
        return False


async def _listen_once() -> None:
    """Blocks in get_message(timeout) — no busy loop — until no topics remain."""
    global _redis_pubsub
    while _subscribed_topics and _redis_pubsub is not None:
        message = await _redis_pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        if message and message.get("type") == "message":
            await deliver_redis_payload(message.get("data"), message.get("channel"))


async def _listener_supervisor(sleep=asyncio.sleep) -> None:
    """Restarts the listener with exponential backoff (1..30 s) if it crashes."""
    global _redis_pubsub
    backoff = 1.0
    while _subscribed_topics:
        try:
            await _listen_once()
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Redis pubsub listener crashed: %s (restarting in %.0fs)", exc, backoff)
            await sleep(backoff)
            backoff = min(backoff * 2, 30.0)
            try:
                r = await _get_redis()
                _redis_pubsub = r.pubsub() if r else None
                for topic in list(_subscribed_topics):
                    if _redis_pubsub is not None:
                        await _redis_pubsub.subscribe(topic)
            except Exception as exc2:
                logger.warning("Redis resubscribe failed: %s", exc2)


async def _publish(tenant_id: str, channel_id: str, event_type: str, data: dict,
                   exclude_user: Optional[str] = None) -> bool:
    if not REDIS_URL:
        return False
    r = await _get_redis()
    if not r:
        return False
    try:
        msg = json.dumps({
            "origin": ORIGIN_ID, "tenant_id": tenant_id, "channel_id": channel_id,
            "type": event_type, "data": data, "exclude_user": exclude_user,
        })
        await r.publish(_topic(tenant_id, channel_id), msg)
        return True
    except Exception as exc:
        logger.debug("Failed publishing event to Redis: %s", exc)
        return False


# ── Public API ────────────────────────────────────────────────────────────

async def connect(websocket: WebSocket, tenant_id: str, channel_id: str, user_id: str) -> None:
    await websocket.accept()
    _connections[tenant_id][channel_id].add((user_id, websocket))
    logger.info("WS connected  tenant=%s channel=%s user=%s", tenant_id, channel_id, user_id)
    if REDIS_URL:
        await _ensure_redis_sub(tenant_id, channel_id)
    await broadcast_event(tenant_id, channel_id, "presence", {"user_id": user_id, "online": True})


def disconnect(websocket: WebSocket, tenant_id: str, channel_id: str, user_id: str) -> None:
    chans = _connections.get(tenant_id)
    if chans is None:
        return
    chans.get(channel_id, set()).discard((user_id, websocket))
    if channel_id in chans and not chans[channel_id]:
        del chans[channel_id]
    if not chans:
        _connections.pop(tenant_id, None)
    logger.info("WS disconnected  tenant=%s channel=%s user=%s", tenant_id, channel_id, user_id)


# Strong references to fire-and-forget broadcast tasks (so they are not garbage collected mid-flight).
_background: Set[asyncio.Task] = set()


def spawn_broadcast(tenant_id: str, channel_id: str, message_data: dict) -> asyncio.Task:
    """Schedule broadcast_message after the DB commit; keeps a reference and logs failures."""
    task = asyncio.create_task(broadcast_message(tenant_id, channel_id, message_data))
    _background.add(task)

    def _done(t: asyncio.Task) -> None:
        _background.discard(t)
        if not t.cancelled() and t.exception() is not None:
            logger.warning("message broadcast failed: %s", t.exception())

    task.add_done_callback(_done)
    return task


async def broadcast_message(tenant_id: str, channel_id: str, message_data: dict) -> None:
    await broadcast_event(tenant_id, channel_id, "message", message_data)


async def _send_one(entry: tuple, payload: str) -> Optional[tuple]:
    """Send to one socket; return the entry when it must be dropped (error or slower than the timeout)."""
    _uid, ws = entry
    try:
        await asyncio.wait_for(ws.send_text(payload), timeout=send_timeout())
        return None
    except Exception:
        try:
            await asyncio.wait_for(ws.close(code=1013), timeout=1.0)
        except Exception:
            pass
        return entry


async def _send_all(tenant_id: str, channel_id: str, payload: str, exclude_user: Optional[str] = None) -> None:
    entries = [e for e in _sockets(tenant_id, channel_id) if exclude_user is None or e[0] != exclude_user]
    if not entries:
        return
    results = await asyncio.gather(*(_send_one(e, payload) for e in entries))
    chans = _connections.get(tenant_id)
    for dead in results:
        if dead is not None and chans is not None and channel_id in chans:
            chans[channel_id].discard(dead)


async def _local_broadcast(
    tenant_id: str, channel_id: str, event_type: str, data: dict, exclude_user: Optional[str] = None
) -> None:
    await _send_all(tenant_id, channel_id, json.dumps({"type": event_type, "data": data}), exclude_user)


async def broadcast_event(
    tenant_id: str,
    channel_id: str,
    event_type: str,
    data: dict,
    *,
    from_pubsub: bool = False,
    exclude_user: Optional[str] = None,
) -> None:
    """Deliver to local sockets and publish for other replicas. Local delivery is always immediate; the
    published payload carries ORIGIN_ID so this process ignores its own echo (no duplicates)."""
    await _local_broadcast(tenant_id, channel_id, event_type, data, exclude_user)
    if not from_pubsub:
        await _publish(tenant_id, channel_id, event_type, data, exclude_user)


# ── Per-connection handler ────────────────────────────────────────────────

async def handle_connection(websocket: WebSocket, tenant_id: str, channel_id: str, user_id: str) -> None:
    """Drives one WebSocket: ping loop, bounded inbound events (typing/pong), cleanup."""
    ping_task = asyncio.create_task(_ping_loop(websocket, tenant_id, channel_id, user_id))
    limiter = new_inbound_limiter()
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=idle_timeout())
            except asyncio.TimeoutError:
                await websocket.close(code=4408, reason="Idle timeout")
                break
            if frame_too_large(raw):
                await websocket.close(code=1009, reason="Message too large")
                break
            if not limiter.allow():
                await websocket.close(code=4429, reason="Too many events")
                break
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue

            if event.get("type") == "typing":
                # Scope is the connection's own (already authorised) channel; a client-supplied
                # channel_id is ignored.
                await _broadcast_except(
                    tenant_id, channel_id, user_id,
                    {"type": "typing", "data": {"user_id": user_id}},
                )
            # "pong" and unknown types: keepalive only
    except Exception:
        logger.debug("Client disconnected or ping failed, cleaning up")
    finally:
        ping_task.cancel()
        disconnect(websocket, tenant_id, channel_id, user_id)
        await _maybe_unsubscribe(tenant_id, channel_id)
        await broadcast_event(tenant_id, channel_id, "presence", {"user_id": user_id, "online": False})


async def _ping_loop(websocket: WebSocket, tenant_id: str, channel_id: str, user_id: str) -> None:
    try:
        while True:
            await asyncio.sleep(PING_INTERVAL)
            await asyncio.wait_for(
                websocket.send_text(json.dumps({"type": "ping", "data": {}})), timeout=send_timeout()
            )
    except Exception:
        logger.debug("Ping loop exited, connection likely closed")


async def _broadcast_except(tenant_id: str, channel_id: str, exclude_user: str, payload: dict) -> None:
    """Typing indicators: this replica's sockets plus other replicas (excluding the sender's user)."""
    await _send_all(tenant_id, channel_id, json.dumps(payload), exclude_user)
    await _publish(tenant_id, channel_id, payload["type"], payload["data"], exclude_user)
