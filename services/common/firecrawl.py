"""
Shared Firecrawl client for OmniDome.

Thin async wrapper over the Firecrawl REST API (v2) used by any service that
needs web data: the FNO Intelligence service (product research, FNO site
message scraping, new-site releases, cancellation-page processing, address
lookup, competitor analysis) is the primary consumer, but the client is
generic and lives in `services.common` so other services can import it.

Design notes
------------
* Uses the project's existing `httpx` + `circuit_breaker` primitives.
* Firecrawl is the **extraction** layer only. Cases that need an LLM to
  *interpret* scraped content (competitor analysis, product research) send the
  returned markdown to the agent orchestrator's LLM router (OPENROUTER_MODEL)
  — Firecrawl does not do the reasoning. See `CAPABILITY_MODELS` below.
* Keyless free tier: if `FIRECRAWL_API_KEY` is empty, the keyless endpoints
  (search / scrape / interact / parse) still work but are rate-limited. The
  `monitor` / `extract` / `crawl` endpoints require a key and will raise
  `FirecrawlUnavailable` when keyless.

Usage
-----
    from services.common.firecrawl import firecrawl

    md = await firecrawl.scrape("https://fno.example.com/coverage")
    results = await firecrawl.search("Vuma Fibre new coverage areas 2026")
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Optional

import httpx

from services.common.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)

_BASE_URL = os.getenv("FIRECRAWL_API_BASE_URL", "https://api.firecrawl.dev/v2").rstrip("/")
_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")

# Reasoning model used to interpret scraped content. Falls back to the
# project-wide Open Router model so the service stays consistent with the
# rest of the agent stack.
REASONING_MODEL = os.getenv("FIRECRAWL_REASONING_MODEL") or os.getenv(
    "OPENROUTER_MODEL", "anthropic/claude-haiku-4.5"
)

# Which capability needs an LLM to *interpret* the extracted web data, and
# which Firecrawl endpoint powers the raw extraction. Used by routes to decide
# whether to additionally call the orchestrator LLM.
CAPABILITY_MODELS: dict[str, dict[str, str]] = {
    "product_research":      {"extraction": "search",   "reasoning": REASONING_MODEL},
    "fno_site_message":      {"extraction": "scrape",   "reasoning": ""},
    "new_site_releases":     {"extraction": "search",   "reasoning": ""},
    "cancellation_processing":{"extraction": "scrape",  "reasoning": ""},
    "address_lookup":        {"extraction": "scrape",   "reasoning": ""},
    "competitor_analysis":   {"extraction": "search",   "reasoning": REASONING_MODEL},
}


class FirecrawlError(Exception):
    """Base error for Firecrawl client failures.

    `breaker_ignore` tells the shared circuit breaker not to count the error
    (client 4xx errors mean Firecrawl is up; only 5xx/timeouts/connection
    errors should trip it).
    """

    breaker_ignore = False


class FirecrawlUnavailable(FirecrawlError):
    """Raised when Firecrawl cannot service the request (no/invalid key, paywall)."""

    breaker_ignore = True

    def __init__(self, message: str = "Firecrawl is not configured for this operation"):
        super().__init__(message)


def _client_error(message: str) -> FirecrawlError:
    err = FirecrawlError(message)
    err.breaker_ignore = True
    return err


def _retry_after_seconds(resp: httpx.Response, default: float) -> float:
    try:
        return min(max(float(resp.headers.get("Retry-After", default)), 0.0), 30.0)
    except (TypeError, ValueError):
        return default


class FirecrawlClient:
    """Async Firecrawl REST v2 client with circuit breaking and graceful keyless mode."""

    def __init__(self, base_url: str = _BASE_URL, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        # None -> read FIRECRAWL_API_KEY lazily on every call.
        self._explicit_key = api_key

    @property
    def api_key(self) -> str:
        if self._explicit_key is not None:
            return self._explicit_key
        return os.getenv("FIRECRAWL_API_KEY", "") or _API_KEY

    @property
    def _has_key(self) -> bool:
        return bool(self.api_key)

    # ── internal helpers ──────────────────────────────────────────────────
    def _headers(self, require_key: bool = False) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = self.api_key
        if key:
            headers["Authorization"] = f"Bearer {key}"
        elif require_key:
            raise FirecrawlUnavailable(
                "This Firecrawl endpoint requires an API key. Set FIRECRAWL_API_KEY "
                "(the keyless free tier only supports search/scrape)."
            )
        return headers

    async def _request(self, method: str, path: str, *, payload: Optional[dict] = None,
                       params: Optional[dict] = None, require_key: bool = False,
                       timeout: float = 60.0) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = self._headers(require_key=require_key)
        attempts_5xx = 0
        attempts_429 = 0
        while True:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == "GET":
                    resp = await client.get(url, params=params or {}, headers=headers)
                else:
                    resp = await client.post(url, json=payload, headers=headers)
            code = resp.status_code
            if code == 429 and attempts_429 < 2:  # max 3 tries
                attempts_429 += 1
                await asyncio.sleep(_retry_after_seconds(resp, 2.0 * attempts_429))
                continue
            if code >= 500 and attempts_5xx < 1:  # transient 5xx: retry once
                attempts_5xx += 1
                await asyncio.sleep(1.0)
                continue
            break
        if code == 402:
            raise FirecrawlUnavailable("Firecrawl rate limit / paywall — add a paid key.")
        if code == 401:
            raise FirecrawlUnavailable("Firecrawl rejected the API key (401) — set a valid FIRECRAWL_API_KEY.")
        if code >= 400:
            msg = f"Firecrawl {path} → HTTP {code}: {resp.text[:300]}"
            if code < 500:  # 4xx (incl. exhausted 429): Firecrawl is up, don't trip the breaker
                raise _client_error(msg)
            raise FirecrawlError(msg)
        try:
            return resp.json()
        except ValueError as exc:
            raise FirecrawlError(f"Firecrawl {path} returned invalid JSON: {exc}") from exc

    @circuit_breaker("firecrawl", failure_threshold=5, recovery_timeout=60)
    async def _post(self, path: str, payload: dict, *, require_key: bool = False,
                    timeout: float = 60.0) -> dict:
        return await self._request("POST", path, payload=payload, require_key=require_key, timeout=timeout)

    @circuit_breaker("firecrawl", failure_threshold=5, recovery_timeout=60)
    async def _get(self, path: str, params: Optional[dict] = None, *,
                   require_key: bool = False, timeout: float = 30.0) -> dict:
        return await self._request("GET", path, params=params, require_key=require_key, timeout=timeout)

    # ── capability wrappers (the six use cases) ──────────────────────────
    async def search(self, query: str, *, limit: int = 5,
                     lang: str = "en", country: str = "za",
                     scrape_formats: Optional[list] = None, timeout: float = 60.0) -> dict:
        """Web search → returns result list + optional full-page markdown.

        Powers: product_research, new_site_releases, competitor_analysis.
        """
        payload = {
            "query": query,
            "limit": limit,
            "lang": lang,
            "country": country,
            "scrapeOptions": {"formats": scrape_formats or ["markdown"]},
        }
        return await self._post("/search", payload, require_key=False, timeout=timeout)

    async def scrape(self, url: str, *, formats: Optional[list] = None,
                     timeout: float = 60.0, only_main_content: Optional[bool] = None) -> dict:
        """Scrape a single known URL → clean markdown (and/or HTML).

        Powers: fno_site_message, cancellation_processing, address_lookup.
        Public document URLs (PDF/DOCX) are also accepted here.
        """
        payload: dict[str, Any] = {"url": url, "formats": formats or ["markdown"]}
        if only_main_content is not None:
            payload["onlyMainContent"] = only_main_content
        return await self._post("/scrape", payload, require_key=False, timeout=timeout)

    async def scrape_json(self, url: str, *, prompt: str, schema: Optional[dict] = None,
                          timeout: float = 90.0) -> dict:
        """Scrape one URL with LLM JSON extraction (v2 formats entry
        {"type": "json", "prompt", "schema"}). Returns the extracted object
        from `data.json` ({} when absent)."""
        fmt: dict[str, Any] = {"type": "json", "prompt": prompt}
        if schema:
            fmt["schema"] = schema
        result = await self._post("/scrape", {"url": url, "formats": [fmt]},
                                  require_key=False, timeout=timeout)
        data = result.get("data") if isinstance(result, dict) else None
        js = data.get("json") if isinstance(data, dict) else None
        return js if isinstance(js, dict) else {}

    async def interact(self, url: str, actions: list[dict]) -> dict:
        """Browser actions on a live page (clicks/forms/login) for portals that
        need interaction before content is reachable. Keyless-supported."""
        payload = {"url": url, "actions": actions, "formats": ["markdown"]}
        return await self._post("/interact", payload, require_key=False)

    async def map_site(self, url: str, *, search: Optional[str] = None, limit: int = 100,
                       timeout: float = 60.0) -> dict:
        """Discover URLs on a site (v2 POST /map). Result: {"links": [{"url", "title", ...}]}."""
        payload: dict[str, Any] = {"url": url, "limit": limit}
        if search:
            payload["search"] = search
        return await self._post("/map", payload, require_key=False, timeout=timeout)

    async def crawl(self, url: str, *, limit: int = 10, scrape_formats: Optional[list] = None,
                    include_paths: Optional[list] = None, poll_interval: float = 3.0,
                    max_wait: float = 180.0) -> dict:
        """Start a crawl (v2 POST /crawl) and poll GET /crawl/{id} until it finishes.

        Returns the final status payload ({"status", "data": [...]}). Raises
        FirecrawlError on failure or when `max_wait` seconds elapse. Requires a key.
        """
        payload: dict[str, Any] = {
            "url": url, "limit": limit,
            "scrapeOptions": {"formats": scrape_formats or ["markdown"]},
        }
        if include_paths:
            payload["includePaths"] = include_paths
        started = await self._post("/crawl", payload, require_key=True, timeout=60.0)
        job_id = started.get("id")
        if not job_id:
            raise FirecrawlError(f"Firecrawl /crawl did not return a job id: {str(started)[:200]}")
        final = await self._poll(f"/crawl/{job_id}", ok={"completed"}, bad={"failed", "cancelled"},
                                 poll_interval=poll_interval, max_wait=max_wait)
        # GET /crawl/{id} returns at most ~10MB per page and links the rest via `next`.
        data = list(final.get("data") or [])
        nxt = final.get("next")
        for _ in range(50):
            if not nxt:
                break
            path = nxt[len(self.base_url):] if str(nxt).startswith(self.base_url) else nxt
            page = await self._get(path, require_key=True)
            data.extend(page.get("data") or [])
            nxt = page.get("next")
        final["data"] = data
        final["next"] = None
        return final

    async def extract(self, urls: list[str], *, prompt: Optional[str] = None,
                      schema: Optional[dict] = None, poll_interval: float = 3.0,
                      max_wait: float = 180.0) -> dict:
        """Structured extraction over one or more URLs (v2 POST /extract + poll).

        Provide a `schema` (JSON schema) and/or a `prompt`. Requires a key.
        """
        if not prompt and not schema:
            raise ValueError("extract() needs a prompt and/or a schema")
        payload: dict[str, Any] = {"urls": urls}
        if prompt:
            payload["prompt"] = prompt
        if schema:
            payload["schema"] = schema
        started = await self._post("/extract", payload, require_key=True, timeout=60.0)
        job_id = started.get("id")
        if not job_id:
            return started  # some responses return data synchronously
        return await self._poll(f"/extract/{job_id}", ok={"completed"}, bad={"failed", "cancelled"},
                                poll_interval=poll_interval, max_wait=max_wait)

    async def _poll(self, path: str, *, ok: set, bad: set, poll_interval: float,
                    max_wait: float) -> dict:
        deadline = time.monotonic() + max_wait
        while True:
            status = await self._get(path, require_key=True)
            state = str(status.get("status", "")).lower()
            if state in ok:
                return status
            if state in bad:
                raise FirecrawlError(f"Firecrawl {path} ended with status '{state}'")
            if time.monotonic() + poll_interval > deadline:
                raise FirecrawlError(f"Firecrawl {path} still '{state}' after {max_wait:.0f}s")
            await asyncio.sleep(poll_interval)

    async def parse(self, file_path: str, *, output_format: str = "markdown") -> dict:
        """Parse a *local* document (PDF/DOCX/XLSX) into markdown. Requires key."""
        upload_url = f"{self.base_url}/parse"
        headers = self._headers(require_key=True)
        headers.pop("Content-Type", None)
        with open(file_path, "rb") as f:
            files = {"file": f}
            data = {"formats": output_format}
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(upload_url, headers=headers, files=files, data=data)
        if resp.status_code >= 400:
            raise FirecrawlError(f"Firecrawl /parse → HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    # ── convenience extractors (post-process raw Firecrawl payloads) ──────
    @staticmethod
    def markdown_from(result: dict) -> str:
        """Pull the markdown string out of a scrape/search result uniformly.

        Firecrawl v2 shapes:
          * scrape:  {"data": {"markdown": "..."}}
          * search:  {"data": [ {"markdown": "..."}, ... ]}
          * search:  {"data": {"web": [ {"markdown": "..."}, ... ],
                               "news": [ ... ]}}
        """
        if not result:
            return ""
        data = result.get("data", result)
        # Direct markdown on the data dict (scrape)
        if isinstance(data, dict) and data.get("markdown"):
            return data["markdown"]
        # Flat list of result items (search)
        if isinstance(data, list):
            return "\n\n".join(
                (r.get("markdown") or "") for r in data if isinstance(r, dict) and r.get("markdown")
            )
        # Grouped search results: {"web": [...], "news": [...], ...}
        if isinstance(data, dict):
            parts = []
            for key, group in data.items():
                if isinstance(group, list):
                    for r in group:
                        if isinstance(r, dict) and r.get("markdown"):
                            parts.append(r["markdown"])
            if parts:
                return "\n\n".join(parts)
            if isinstance(data.get("results"), list):
                return "\n\n".join(
                    (r.get("markdown") or "") for r in data["results"] if isinstance(r, dict) and r.get("markdown")
                )
        return ""


# Module-level singleton (mirrors how the rest of the codebase uses `http_client`).
firecrawl = FirecrawlClient()
