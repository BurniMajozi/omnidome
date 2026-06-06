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

logger = logging.getLogger("iot.ha_client")

# ---------------------------------------------------------------------------
# Token encryption (AES-256-GCM via Fernet-like approach)
# ---------------------------------------------------------------------------

def _get_encryption_key() -> bytes:
    """Derive a 32-byte key from the configured secret."""
    secret = os.getenv("IOT_TOKEN_ENCRYPTION_KEY", os.getenv("AUTH_JWT_SECRET", "omnidome-default-key-change-me"))
    return hashlib.sha256(secret.encode()).digest()


def encrypt_token(token: str) -> str:
    """Encrypt a HA token for storage. Returns base64-encoded ciphertext."""
    try:
        from cryptography.fernet import Fernet
        key = base64.urlsafe_b64encode(_get_encryption_key())
        f = Fernet(key)
        return f.encrypt(token.encode()).decode()
    except ImportError:
        # Fallback: base64 encode (not encrypted — install cryptography for real encryption)
        logger.warning("cryptography not installed — tokens stored as base64 (not encrypted)")
        return base64.b64encode(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt a stored HA token."""
    try:
        from cryptography.fernet import Fernet
        key = base64.urlsafe_b64encode(_get_encryption_key())
        f = Fernet(key)
        return f.decrypt(encrypted.encode()).decode()
    except ImportError:
        return base64.b64decode(encrypted.encode()).decode()
    except Exception as exc:
        logger.error("Failed to decrypt token: %s", exc)
        raise


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

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
        return self._client

    async def close(self):
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
        self.ws_url = ha_url.replace("http://", "ws://").replace("https://", "wss://").rstrip("/")
        self.token = token
        self._ws = None
        self._message_id = 0
        self._listeners: Dict[str, List[Callable]] = {}
        self._running = False

    async def connect(self):
        """Connect to HA WebSocket API."""
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
