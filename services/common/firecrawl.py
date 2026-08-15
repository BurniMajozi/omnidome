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
    results = await firecrawl search("Vuma Fibre new coverage areas 2026")
"""

from __future__ import annotations

import logging
import os
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
    "OPENROUTER_MODEL", "Owal Alpha"
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
    """Base error for Firecrawl client failures."""


class FirecrawlUnavailable(FirecrawlError):
    """Raised when Firecrawl cannot service the request (no key + keyless-only endpoint)."""

    def __init__(self, message: str = "Firecrawl is not configured for this operation"):
        super().__init__(message)


class FirecrawlClient:
    """Async Firecrawl REST v2 client with circuit breaking and graceful keyless mode."""

    def __init__(self, base_url: str = _BASE_URL, api_key: str = _API_KEY):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._has_key = bool(api_key)

    # ── internal helpers ──────────────────────────────────────────────────
    def _headers(self, require_key: bool = False) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._has_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif require_key:
            raise FirecrawlUnavailable(
                "This endpoint requires a Firecrawl API key (keyless free tier unsupported)."
            )
        return headers

    @circuit_breaker("firecrawl", failure_threshold=5, recovery_timeout=60)
    async def _post(self, path: str, payload: dict, *, require_key: bool = False,
                    timeout: float = 60.0) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = self._headers(require_key=require_key)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 402:
            raise FirecrawlUnavailable("Firecrawl rate limit / paywall — add a paid key.")
        if resp.status_code >= 400:
            raise FirecrawlError(f"Firecrawl {path} → HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    @circuit_breaker("firecrawl", failure_threshold=5, recovery_timeout=60)
    async def _get(self, path: str, params: Optional[dict] = None, *,
                   require_key: bool = False, timeout: float = 30.0) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = self._headers(require_key=require_key)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params or {}, headers=headers)
        if resp.status_code >= 400:
            raise FirecrawlError(f"Firecrawl {path} → HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    # ── capability wrappers (the six use cases) ──────────────────────────
    async def search(self, query: str, *, limit: int = 5,
                     lang: str = "en", country: str = "za") -> dict:
        """Web search → returns result list + optional full-page markdown.

        Powers: product_research, new_site_releases, competitor_analysis.
        """
        payload = {
            "query": query,
            "limit": limit,
            "lang": lang,
            "country": country,
            "scrapeOptions": {"formats": ["markdown"]},
        }
        return await self._post("/search", payload, require_key=False)

    async def scrape(self, url: str, *, formats: Optional[list[str]] = None) -> dict:
        """Scrape a single known URL → clean markdown (and/or HTML).

        Powers: fno_site_message, cancellation_processing, address_lookup.
        Public document URLs (PDF/DOCX) are also accepted here.
        """
        payload = {"url": url, "formats": formats or ["markdown"]}
        return await self._post("/scrape", payload, require_key=False)

    async def interact(self, url: str, actions: list[dict]) -> dict:
        """Browser actions on a live page (clicks/forms/login) for portals that
        need interaction before content is reachable. Keyless-supported."""
        payload = {"url": url, "actions": actions, "formats": ["markdown"]}
        return await self._post("/interact", payload, require_key=False)

    async def parse(self, file_path: str, *, output_format: str = "markdown") -> dict:
        """Parse a *local* document (PDF/DOCX/XLSX) into markdown. Requires key."""
        import httpx as _hx
        upload_url = f"{self.base_url}/parse"
        headers = self._headers(require_key=True)
        headers.pop("Content-Type", None)
        with open(file_path, "rb") as f:
            files = {"file": f}
            data = {"formats": output_format}
            async with _hx.AsyncClient(timeout=120.0) as client:
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
