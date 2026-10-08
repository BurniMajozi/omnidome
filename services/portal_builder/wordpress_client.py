"""Bounded outbound client for the adapter's 2025-11-25 Streamable HTTP profile.

No redirects, ambient proxies, arbitrary tool execution, or automatic write retries.
DNS validation uses the same public-URL policy as the site importer.
"""
from __future__ import annotations

import asyncio
import json
from urllib.parse import urlsplit, urlunsplit

import httpx

from services.common.url_safety import UnsafeUrl, validate_public_url

PROTOCOL = "2025-11-25"
ABILITIES = frozenset({"omnidome/site-info", "omnidome/upsert-page-draft",
                       "omnidome/publish-page", "omnidome/get-publication-status"})
MAX_RESPONSE = 1_000_000
_transport = None  # injectable in tests
_resolver = None


class WordPressError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


async def site_url(value: str) -> str:
    try:
        async with asyncio.timeout(10):
            await asyncio.to_thread(validate_public_url, value, resolver=_resolver, allow_http=False)
        p = urlsplit(value.strip())
        if p.query or p.fragment or "/wp-json" in p.path:
            raise UnsafeUrl("Enter the WordPress site URL, without wp-json, query, or fragment")
        return urlunsplit(("https", p.netloc.lower(), p.path.rstrip("/"), "", ""))
    except UnsafeUrl as exc:
        raise WordPressError(str(exc), 422) from exc
    except TimeoutError as exc:
        raise WordPressError("WordPress DNS lookup timed out") from exc


def tool_data(result: dict) -> dict:
    if not isinstance(result, dict):
        raise WordPressError("WordPress returned an invalid tool result")
    if result.get("isError"):
        raise WordPressError("WordPress rejected the operation. Check site permissions and the companion plugin.", 409)
    data = result.get("structuredContent")
    if data is None:
        content = result.get("content", [])
        if not isinstance(content, list):
            raise WordPressError("WordPress returned an invalid tool result")
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                try:
                    data = json.loads(block["text"])
                    break
                except (KeyError, TypeError, ValueError):
                    continue
    if not isinstance(data, dict):
        raise WordPressError("WordPress returned an invalid tool result")
    if data.get("success") is False:
        raise WordPressError("WordPress rejected the operation. Refresh status and check for external edits.", 409)
    if data.get("success") is True:
        data = data.get("data")
    if not isinstance(data, dict):
        raise WordPressError("WordPress returned an invalid ability result")
    return data


class WordPressClient:
    def __init__(self, url: str, username: str, password: str):
        self.endpoint = url.rstrip("/") + "/wp-json/mcp/mcp-adapter-default-server"
        self.session = None
        self.counter = 0
        self.http = httpx.AsyncClient(auth=(username, password), timeout=8,
                                     follow_redirects=False, trust_env=False, transport=_transport)

    async def __aenter__(self):
        try:
            result = await self.rpc("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                "clientInfo": {"name": "OmniDome Website Builder", "version": "1.0.0"}})
            if result.get("protocolVersion") != PROTOCOL or not self.session:
                raise WordPressError("The adapter must support the 2025-11-25 session protocol")
            await self.rpc("notifications/initialized", notification=True)
            return self
        except BaseException:
            await self.http.aclose()
            raise

    async def __aexit__(self, *args):
        # Session termination is best effort; it must not mask a successful write.
        try:
            if self.session:
                async with asyncio.timeout(3):
                    await asyncio.to_thread(validate_public_url, self.endpoint, resolver=_resolver, allow_http=False)
                    await self.http.delete(self.endpoint, headers=self.headers())
        except (httpx.HTTPError, UnsafeUrl, TimeoutError):
            pass
        finally:
            await self.http.aclose()

    def headers(self):
        h = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": PROTOCOL}
        if self.session:
            h["Mcp-Session-Id"] = self.session
        return h

    async def rpc(self, method: str, params: dict | None = None, *, notification=False) -> dict:
        try:
            async with asyncio.timeout(10):
                return await self._rpc(method, params, notification=notification)
        except TimeoutError as exc:
            raise WordPressError("WordPress did not confirm the request. Refresh publication status before retrying.") from exc

    async def _rpc(self, method: str, params: dict | None = None, *, notification=False) -> dict:
        try:
            await asyncio.to_thread(validate_public_url, self.endpoint, resolver=_resolver, allow_http=False)
        except UnsafeUrl as exc:
            raise WordPressError("WordPress endpoint is not a public HTTPS URL", 422) from exc
        self.counter += 1
        request_id = self.counter
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notification:
            payload["id"] = request_id
        try:
            async with self.http.stream("POST", self.endpoint, json=payload, headers=self.headers()) as response:
                if response.status_code in (401, 403):
                    raise WordPressError("WordPress authentication failed. Check the integration user and Application Password.", 422)
                if response.status_code >= 300:
                    raise WordPressError("WordPress endpoint failed or redirected. Use its canonical HTTPS site URL.")
                if method == "initialize":
                    self.session = response.headers.get("Mcp-Session-Id")
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE:
                        raise WordPressError("WordPress response exceeds the size limit")
                    if "text/event-stream" in response.headers.get("content-type", ""):
                        # Finish on our response instead of waiting for an open SSE stream to close.
                        blocks = bytes(raw).decode("utf-8", errors="replace").replace("\r\n", "\n").split("\n\n")
                        for block in blocks[:-1]:
                            text = "\n".join(line[5:].lstrip() for line in block.splitlines() if line.startswith("data:"))
                            if not text:
                                continue
                            event = json.loads(text)
                            if not isinstance(event, dict):
                                raise WordPressError("Invalid WordPress MCP event")
                            if event.get("id") == request_id:
                                return self._result(event, request_id)
                if notification:
                    return {}
                return self._result(json.loads(raw), request_id)
        except (httpx.HTTPError, UnicodeError, ValueError, TypeError) as exc:
            raise WordPressError("WordPress did not confirm the request. Refresh publication status before retrying.") from exc

    @staticmethod
    def _result(envelope: dict, request_id: int) -> dict:
        if not isinstance(envelope, dict) or envelope.get("id") != request_id or envelope.get("jsonrpc") != "2.0":
            raise WordPressError("Invalid WordPress MCP response")
        if "error" in envelope:
            raise WordPressError("WordPress MCP rejected the request. Check adapter compatibility and permissions.")
        if not isinstance(envelope.get("result"), dict):
            raise WordPressError("Missing WordPress MCP result")
        return envelope["result"]

    async def discover(self) -> list[str]:
        result = await self.rpc("tools/call", {"name": "mcp-adapter-discover-abilities", "arguments": {}})
        data = tool_data(result)
        abilities = data.get("abilities", [])
        if not isinstance(abilities, list):
            raise WordPressError("WordPress returned an invalid ability list")
        return [a["name"] for a in abilities if isinstance(a, dict) and a.get("name") in ABILITIES]

    async def execute(self, name: str, params: dict) -> dict:
        if name not in ABILITIES:
            raise WordPressError("Ability is not allowed", 422)
        result = await self.rpc("tools/call", {"name": "mcp-adapter-execute-ability",
                               "arguments": {"ability_name": name, "parameters": params}})
        return tool_data(result)
