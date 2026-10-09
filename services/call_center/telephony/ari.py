"""Thin async ARI client (REST via httpx, events via websockets).

ARI is only reachable on the internal Docker network. Credentials are sent as HTTP basic auth / an
Authorization header and are never put in URLs, logs or exceptions.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

logger = logging.getLogger("call_center.telephony.ari")


class AriError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class AriNotConfigured(AriError):
    pass


def ari_settings() -> Optional[Dict[str, str]]:
    """None when ARI is not configured (the telephony features then report 'unavailable')."""
    url = os.getenv("ASTERISK_ARI_URL", "").strip().rstrip("/")
    password = os.getenv("ASTERISK_ARI_PASSWORD", "")
    if not url or not password:
        return None
    return {"url": url, "user": os.getenv("ASTERISK_ARI_USER", "omnidome"), "password": password,
            "app": os.getenv("ASTERISK_ARI_APP", "omnidome")}


class AriClient:
    def __init__(self, url: str, user: str, password: str, app: str = "omnidome",
                 http: Optional[httpx.AsyncClient] = None):
        self._url = url.rstrip("/")
        self._user = user
        self._password = password
        self.app = app
        self._http = http or httpx.AsyncClient(timeout=10.0, auth=(user, password))

    def __repr__(self) -> str:
        return f"AriClient(url={self._url!r}, app={self.app!r})"

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _req(self, method: str, path: str, *, params: Optional[dict] = None,
                   json_body: Optional[dict] = None, ok_404: bool = False) -> Any:
        try:
            resp = await self._http.request(method, f"{self._url}/ari{path}", params=params, json=json_body)
        except httpx.HTTPError as exc:
            raise AriError(f"ARI unreachable ({type(exc).__name__})") from None
        if resp.status_code == 404 and ok_404:
            return None
        if resp.status_code >= 400:
            raise AriError(f"ARI {method} {path.split('?')[0]} failed: HTTP {resp.status_code}", resp.status_code)
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    # ── channels ──────────────────────────────────────────────────────
    async def originate(self, *, endpoint: str, app_args: List[str], channel_id: str,
                        caller_id: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
        params = {"endpoint": endpoint, "app": self.app, "appArgs": ",".join(app_args),
                  "channelId": channel_id, "timeout": timeout}
        if caller_id:
            params["callerId"] = caller_id
        return await self._req("POST", "/channels", params=params)

    async def answer(self, channel_id: str) -> None:
        await self._req("POST", f"/channels/{channel_id}/answer", ok_404=True)

    async def hangup(self, channel_id: str, reason: str = "normal") -> None:
        await self._req("DELETE", f"/channels/{channel_id}", params={"reason": reason}, ok_404=True)

    async def hold(self, channel_id: str) -> None:
        await self._req("POST", f"/channels/{channel_id}/hold")

    async def unhold(self, channel_id: str) -> None:
        await self._req("DELETE", f"/channels/{channel_id}/hold")

    async def send_dtmf(self, channel_id: str, digits: str) -> None:
        await self._req("POST", f"/channels/{channel_id}/dtmf", params={"dtmf": digits})

    async def moh_start(self, channel_id: str) -> None:
        await self._req("POST", f"/channels/{channel_id}/moh", ok_404=True)

    async def moh_stop(self, channel_id: str) -> None:
        await self._req("DELETE", f"/channels/{channel_id}/moh", ok_404=True)

    async def play(self, channel_id: str, media: str, playback_id: str) -> None:
        await self._req("POST", f"/channels/{channel_id}/play/{playback_id}", params={"media": media})

    async def list_channels(self) -> List[Dict[str, Any]]:
        return await self._req("GET", "/channels") or []

    # ── bridges / recording ───────────────────────────────────────────
    async def create_bridge(self, bridge_id: str) -> Dict[str, Any]:
        return await self._req("POST", f"/bridges/{bridge_id}", params={"type": "mixing"})

    async def add_to_bridge(self, bridge_id: str, channel_id: str) -> None:
        await self._req("POST", f"/bridges/{bridge_id}/addChannel", params={"channel": channel_id})

    async def remove_from_bridge(self, bridge_id: str, channel_id: str) -> None:
        await self._req("POST", f"/bridges/{bridge_id}/removeChannel", params={"channel": channel_id}, ok_404=True)

    async def destroy_bridge(self, bridge_id: str) -> None:
        await self._req("DELETE", f"/bridges/{bridge_id}", ok_404=True)

    async def record_bridge(self, bridge_id: str, name: str) -> None:
        await self._req("POST", f"/bridges/{bridge_id}/record",
                        params={"name": name, "format": "wav", "ifExists": "fail", "beep": "false"})

    # ── endpoints ─────────────────────────────────────────────────────
    async def endpoint_state(self, resource: str) -> Optional[str]:
        """'online' | 'offline' | 'unknown' or None when the endpoint does not exist."""
        data = await self._req("GET", f"/endpoints/PJSIP/{resource}", ok_404=True)
        return None if data is None else str(data.get("state") or "unknown")

    # ── events ────────────────────────────────────────────────────────
    async def events(self, on_open=None) -> AsyncIterator[Dict[str, Any]]:
        import websockets  # local import: only needed at runtime
        ws_url = self._url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        token = base64.b64encode(f"{self._user}:{self._password}".encode()).decode()
        async with websockets.connect(f"{ws_url}/ari/events?app={self.app}&subscribeAll=false",
                                      additional_headers={"Authorization": f"Basic {token}"},
                                      max_size=2 ** 20, ping_interval=20) as ws:
            if on_open:
                on_open()
            async for raw in ws:
                try:
                    yield json.loads(raw)
                except ValueError:
                    logger.warning("dropping non-JSON ARI event")


async def run_forever(client: AriClient, on_event, on_state=None, *, backoff_max: float = 30.0) -> None:
    """Consume events, reconnecting with backoff. `on_state(connected: bool, error: str|None)`."""
    delay = 1.0
    while True:
        try:
            async for event in client.events(on_open=(lambda: on_state(True, None)) if on_state else None):
                delay = 1.0
                try:
                    await on_event(event)
                except Exception:  # noqa: BLE001 - one bad event must not kill the loop
                    logger.exception("error handling ARI event type=%s", event.get("type"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            if on_state:
                on_state(False, f"ARI event stream down ({type(exc).__name__})")
            logger.warning("ARI event stream down (%s); retrying in %.0fs", type(exc).__name__, delay)
        await asyncio.sleep(delay)
        delay = min(delay * 2, backoff_max)
