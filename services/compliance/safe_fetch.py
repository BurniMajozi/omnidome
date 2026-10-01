"""Guarded outbound fetch for user-supplied URLs (SSRF-safe).

* every URL, including EVERY redirect hop (max 3, followed manually), passes
  services.common.url_safety.validate_public_url: https only unless
  COMPLIANCE_ALLOW_HTTP=true, no credentials / odd ports / internal names /
  private, loopback, link-local, metadata or CGNAT addresses (v4 and v6, numeric
  encodings), DNS result checked;
* response size capped (COMPLIANCE_MAX_FETCH_MB, default 10) while streaming;
* content-type allow-list; overall timeout; proxies from the environment ignored.

Residual risk: DNS may change between validation and connect (rebinding). When a
Firecrawl key is configured, prefer it (the fetch then happens off our network).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urljoin

import httpx

from services.common.url_safety import UnsafeUrl, validate_public_url

ALLOW_HTTP_ENV = "COMPLIANCE_ALLOW_HTTP"
MAX_REDIRECTS = 3
ALLOWED_CONTENT_TYPES = frozenset({
    "text/html", "application/xhtml+xml", "text/plain", "text/markdown", "text/csv", "application/pdf",
})


class FetchRefused(ValueError):
    """The fetch was blocked or failed a safety limit."""


@dataclass
class FetchResult:
    url: str
    content_type: str
    content: bytes
    redirects: int = 0


def max_fetch_bytes() -> int:
    try:
        mb = float(os.getenv("COMPLIANCE_MAX_FETCH_MB", "10"))
    except ValueError:
        mb = 10.0
    return int(mb * 1024 * 1024)


async def check_url(url: str, *, resolver=None) -> str:
    """Validate off the event loop (DNS is blocking). Raises FetchRefused."""
    try:
        return await asyncio.to_thread(
            lambda: validate_public_url(url, resolver=resolver, allow_http_env=ALLOW_HTTP_ENV)
        )
    except UnsafeUrl as exc:
        raise FetchRefused(str(exc)) from None


async def fetch_public(
    url: str,
    *,
    max_bytes: Optional[int] = None,
    timeout: float = 20.0,
    resolver=None,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> FetchResult:
    limit = max_bytes if max_bytes is not None else max_fetch_bytes()
    try:
        return await asyncio.wait_for(_fetch(url, limit, timeout, resolver, transport), timeout=timeout + 5)
    except asyncio.TimeoutError:
        raise FetchRefused("Fetch timed out") from None


async def _fetch(url, limit, timeout, resolver, transport) -> FetchResult:
    current = await check_url(url, resolver=resolver)
    async with httpx.AsyncClient(
        follow_redirects=False, timeout=httpx.Timeout(timeout), trust_env=False, transport=transport,
    ) as client:
        for hop in range(MAX_REDIRECTS + 1):
            async with client.stream("GET", current, headers={"Accept": "text/html,application/pdf,text/plain"}) as resp:
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location")
                    if not location:
                        raise FetchRefused("Redirect without a Location header")
                    if hop >= MAX_REDIRECTS:
                        raise FetchRefused("Too many redirects")
                    current = await check_url(urljoin(current, location), resolver=resolver)  # re-validate EVERY hop
                    continue
                if resp.status_code >= 400:
                    raise FetchRefused(f"Remote server answered HTTP {resp.status_code}")
                ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                if ctype not in ALLOWED_CONTENT_TYPES:
                    raise FetchRefused(f"Content type {ctype or '(none)'} is not allowed")
                declared = resp.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > limit:
                    raise FetchRefused("Response is too large")
                chunks, total = [], 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > limit:
                        raise FetchRefused("Response is too large")
                    chunks.append(chunk)
                return FetchResult(url=current, content_type=ctype, content=b"".join(chunks), redirects=hop)
    raise FetchRefused("Too many redirects")
