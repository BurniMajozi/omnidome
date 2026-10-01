"""Home Assistant REST API + WebSocket client.

Handles:
- REST API calls (device control, state reads, service calls)
- WebSocket connection (real-time state change events)
- Token encryption/decryption for secure storage
- Auto-discovery and device sync
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional

import httpx

from services.iot.url_policy import validate_ha_url

logger = logging.getLogger("iot.ha_client")

# ---------------------------------------------------------------------------
# Token encryption (Fernet, key REQUIRED -- fail closed)
# ---------------------------------------------------------------------------

_LEGACY_DEFAULT_SECRET = "omnidome-default-key-change-me"


class TokenEncryptionUnavailable(RuntimeError):
    """IOT_TOKEN_ENCRYPTION_KEY is missing/invalid or `cryptography` is not installed (HTTP 503)."""


class ReconnectRequired(RuntimeError):
    """The stored token cannot be decrypted under any known key: the user must re-enter it."""


def _fernet():
    """Fernet built from IOT_TOKEN_ENCRYPTION_KEY (a Fernet key: 32 url-safe base64 bytes)."""
    key = os.getenv("IOT_TOKEN_ENCRYPTION_KEY", "").strip()
    if not key:
        raise TokenEncryptionUnavailable("IOT_TOKEN_ENCRYPTION_KEY is not set")
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # never fall back to base64
        raise TokenEncryptionUnavailable("cryptography is not installed") from exc
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise TokenEncryptionUnavailable("IOT_TOKEN_ENCRYPTION_KEY is not a valid Fernet key") from exc


def _legacy_fernets() -> list:
    """Keys older releases may have used (sha256 of IOT key string / AUTH_JWT_SECRET / the hard-coded default)."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return []
    secrets = []
    for name in ("IOT_TOKEN_ENCRYPTION_KEY", "AUTH_JWT_SECRET"):
        v = os.getenv(name, "").strip()
        if v:
            secrets.append(v)
    secrets.append(_LEGACY_DEFAULT_SECRET)
    return [Fernet(base64.urlsafe_b64encode(hashlib.sha256(sec.encode()).digest())) for sec in secrets]


def encrypt_token(token: str) -> str:
    """Encrypt a HA token for storage. Raises TokenEncryptionUnavailable when no key is configured."""
    return _fernet().encrypt(token.encode()).decode()


def decrypt_token_ex(encrypted: str) -> tuple:
    """(plaintext, needs_reencrypt). Tries the configured key, then the legacy derived keys once.
    Raises TokenEncryptionUnavailable (no key configured) or ReconnectRequired."""
    from cryptography.fernet import InvalidToken
    primary = _fernet()
    try:
        return primary.decrypt(encrypted.encode()).decode(), False
    except InvalidToken:
        pass
    for legacy in _legacy_fernets():
        try:
            return legacy.decrypt(encrypted.encode()).decode(), True
        except InvalidToken:
            continue
    raise ReconnectRequired("stored token cannot be decrypted; reconnect required")


def decrypt_token(encrypted: str) -> str:
    return decrypt_token_ex(encrypted)[0]


def token_for_integration(integration) -> str:
    """Decrypt an integration's token; a token still under a legacy key is re-encrypted under
    the configured key on the ORM object (persisted when the caller's session commits)."""
    plain, legacy = decrypt_token_ex(integration.ha_token_encrypted)
    if legacy:
        integration.ha_token_encrypted = encrypt_token(plain)
        logger.warning("integration %s token migrated to IOT_TOKEN_ENCRYPTION_KEY", getattr(integration, "id", "?"))
    return plain


def describe_ha_error(exc: BaseException) -> tuple:
    """(code, message) with fixed wording only: never the raw exception text (it can name internal hosts)."""
    from services.common.url_safety import UnsafeUrl
    if isinstance(exc, TokenEncryptionUnavailable):
        return "encryption_unavailable", "Token encryption is not configured"
    if isinstance(exc, ReconnectRequired):
        return "reconnect_required", "Reconnect required: please re-enter the Home Assistant token"
    if isinstance(exc, UnsafeUrl):
        return "url_not_allowed", "The Home Assistant URL is not allowed"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout", "Connection failed (timeout)"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return "auth_failed", "Connection failed (authentication rejected)"
        return f"http_{code}", f"Connection failed (HTTP {code})"
    if isinstance(exc, httpx.HTTPError):
        return "unreachable", "Connection failed"
    return "error", "Connection failed"


def ha_http_error(exc: BaseException):
    """HTTPException for a failed Home Assistant interaction, generic wording only."""
    from fastapi import HTTPException
    from services.common.url_safety import UnsafeUrl
    code, message = describe_ha_error(exc)
    if isinstance(exc, TokenEncryptionUnavailable):
        status = 503
    elif isinstance(exc, ReconnectRequired):
        status = 409
    elif isinstance(exc, UnsafeUrl):
        status = 422
    else:
        status = 502
    return HTTPException(status_code=status, detail={"code": code, "message": message})


# ---------------------------------------------------------------------------
# HA REST API Client
# ---------------------------------------------------------------------------

class HARestClient:
    """Home Assistant REST API client."""

    def __init__(self, ha_url: str, token: str):
        self.ha_url = ha_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._client: Optional[httpx.AsyncClient] = None
        self._validated = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            if not self._validated:
                # Re-check on every client (DNS may have changed since the URL was saved).
                await asyncio.to_thread(validate_ha_url, self.ha_url)
                self._validated = True
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=httpx.Timeout(15.0, connect=5.0),
                follow_redirects=False,  # a redirect could point at an internal address
            )
        return self._client

    async def aclose(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def health_check(self) -> Dict[str, Any]:
        """Check HA API health."""
        client = await self._get_client()
        resp = await client.get(f"{self.ha_url}/api/")
        resp.raise_for_status()
        return resp.json()

    async def get_states(self) -> List[Dict[str, Any]]:
        """Get all entity states from HA."""
        client = await self._get_client()
        resp = await client.get(f"{self.ha_url}/api/states")
        resp.raise_for_status()
        return resp.json()

    async def get_state(self, entity_id: str) -> Dict[str, Any]:
        """Get a single entity state."""
        client = await self._get_client()
        resp = await client.get(f"{self.ha_url}/api/states/{entity_id}")
        resp.raise_for_status()
        return resp.json()

    async def set_state(self, entity_id: str, state: str, attributes: Optional[Dict] = None) -> Dict[str, Any]:
        """Set an entity state."""
        client = await self._get_client()
        body = {"state": state}
        if attributes:
            body["attributes"] = attributes
        resp = await client.post(
            f"{self.ha_url}/api/states/{entity_id}",
            json=body,
        )
        resp.raise_for_status()
        return resp.json()

    async def call_service(self, domain: str, service: str, service_data: Optional[Dict] = None,
                           target: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Call an HA service (e.g., light/turn_on, lock/lock)."""
        client = await self._get_client()
        body = {}
        if service_data:
            body.update(service_data)
        if target:
            body["target"] = target
        resp = await client.post(
            f"{self.ha_url}/api/services/{domain}/{service}",
            json=body,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_config(self) -> Dict[str, Any]:
        """Get HA configuration."""
        client = await self._get_client()
        resp = await client.get(f"{self.ha_url}/api/config")
        resp.raise_for_status()
        return resp.json()

    async def get_areas(self) -> List[Dict[str, Any]]:
        """Get all HA areas."""
        client = await self._get_client()
        resp = await client.get(f"{self.ha_url}/api/config/area_registry/list")
        resp.raise_for_status()
        return resp.json()

    async def get_automations(self) -> List[Dict[str, Any]]:
        """Get all HA automations."""
        client = await self._get_client()
        resp = await client.get(f"{self.ha_url}/api/states")
        resp.raise_for_status()
        states = resp.json()
        return [s for s in states if s.get("entity_id", "").startswith("automation.")]

    async def get_scenes(self) -> List[Dict[str, Any]]:
        """Get all HA scenes."""
        client = await self._get_client()
        resp = await client.get(f"{self.ha_url}/api/states")
        resp.raise_for_status()
        states = resp.json()
        return [s for s in states if s.get("entity_id", "").startswith("scene.")]

    async def get_camera_image(self, entity_id: str) -> bytes:
        """Get a camera snapshot image."""
        client = await self._get_client()
        resp = await client.get(
            f"{self.ha_url}/api/camera_proxy/{entity_id}",
        )
        resp.raise_for_status()
        return resp.content

    async def get_camera_stream(self, entity_id: str) -> str:
        """Get camera stream URL."""
        client = await self._get_client()
        resp = await client.get(
            f"{self.ha_url}/api/camera_proxy_stream/{entity_id}",
        )
        resp.raise_for_status()
        return str(resp.url)

    async def fire_event(self, event_type: str, event_data: Optional[Dict] = None) -> None:
        """Fire a custom HA event."""
        client = await self._get_client()
        body = event_data or {}
        resp = await client.post(
            f"{self.ha_url}/api/events/{event_type}",
            json=body,
        )
        resp.raise_for_status()


# ---------------------------------------------------------------------------
# HA WebSocket Client
# ---------------------------------------------------------------------------

class HAWebSocketClient:
    """Home Assistant WebSocket client for real-time events."""

    def __init__(self, ha_url: str, token: str):
        # Convert http(s) URL to ws(s)
        self._ha_url = ha_url
        self.ws_url = ha_url.replace("http://", "ws://").replace("https://", "wss://").rstrip("/")
        self.token = token
        self._ws = None
        self._message_id = 0
        self._listeners: Dict[str, List[Callable]] = {}
        self._running = False

    async def connect(self):
        """Connect to HA WebSocket API."""
        await asyncio.to_thread(validate_ha_url, self._ha_url)
        try:
            import websockets
            self._ws = await websockets.connect(
                f"{self.ws_url}/api/websocket",
                ping_interval=30,
                ping_timeout=10,
            )
            # Authenticate
            auth_msg = await self._ws.recv()
            auth_data = json.loads(auth_msg)
            if auth_data.get("type") == "auth_required":
                await self._ws.send(json.dumps({
                    "type": "auth",
                    "access_token": self.token,
                }))
                auth_result = await self._ws.recv()
                result_data = json.loads(auth_result)
                if result_data.get("type") != "auth_ok":
                    raise Exception(f"WebSocket auth failed: {result_data}")
            self._running = True
            logger.info("HA WebSocket connected")
        except ImportError:
            logger.warning("websockets not installed — real-time events unavailable")
            self._running = False

    async def subscribe_events(self, event_type: Optional[str] = None) -> int:
        """Subscribe to HA events. Returns subscription ID."""
        if not self._ws:
            raise Exception("WebSocket not connected")
        self._message_id += 1
        msg = {
            "id": self._message_id,
            "type": "subscribe_events",
        }
        if event_type:
            msg["event_type"] = event_type
        await self._ws.send(json.dumps(msg))
        return self._message_id

    async def listen(self):
        """Listen for incoming events and dispatch to listeners."""
        if not self._ws or not self._running:
            return
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                    event_type = data.get("event_type", data.get("type", "unknown"))
                    for callback in self._listeners.get(event_type, []):
                        try:
                            await callback(data)
                        except Exception:
                            logger.exception("Event listener error")
                    # Also dispatch to wildcard listeners
                    for callback in self._listeners.get("*", []):
                        try:
                            await callback(data)
                        except Exception:
                            logger.exception("Wildcard listener error")
                except json.JSONDecodeError:
                    pass
        except Exception as exc:
            logger.error("WebSocket listen error: %s", exc)
            self._running = False

    def on(self, event_type: str, callback: Callable):
        """Register an event listener."""
        self._listeners.setdefault(event_type, []).append(callback)

    async def close(self):
        """Close the WebSocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()


# ---------------------------------------------------------------------------
# Device sync helpers
# ---------------------------------------------------------------------------

def ha_entity_to_device_type(entity_id: str) -> str:
    """Map HA entity domain to OmniDome device type."""
    domain = entity_id.split(".")[0] if "." in entity_id else "other"
    mapping = {
        "camera": "camera",
        "binary_sensor": "sensor",
        "sensor": "sensor",
        "light": "light",
        "lock": "lock",
        "switch": "switch",
        "climate": "climate",
        "alarm_control_panel": "alarm",
        "device_tracker": "presence",
        "person": "presence",
    }
    return mapping.get(domain, "other")


def ha_state_to_device_status(state: str) -> str:
    """Map HA state to OmniDome device status."""
    mapping = {
        "on": "online",
        "off": "online",
        "unavailable": "unavailable",
        "unknown": "unavailable",
        "idle": "online",
        "active": "online",
        "triggered": "online",
        "disarmed": "online",
        "locked": "online",
        "unlocked": "online",
        "open": "online",
        "closed": "online",
        "home": "online",
        "not_home": "online",
    }
    return mapping.get(state, "online")
