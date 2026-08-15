"""
FNO Intelligence — Web Intelligence module.

Wraps Firecrawl (extraction) + Open Router (reasoning) into the six web-data
capabilities OmniDome needs from the FNO Intelligence service:

  1. product_research        — research an FNO's products/packages via web search
  2. fno_site_message        — scrape the latest message/announcement off an FNO portal
  3. new_site_releases       — discover newly-released coverage areas / sites
  4. cancellation_processing — pull the cancellation/termination procedure & steps
  5. address_lookup          — resolve a street address to coverage / FNO availability
  6. competitor_analysis      — compare competitors' offerings (LLM-interpreted)

Split of responsibility
------------------------
  * Firecrawl does the **extraction** (search / scrape / parse).
  * Open Router (OPENROUTER_MODEL) does the **reasoning** for capabilities that
    need it (product_research, competitor_analysis). The model used is recorded
    in each response so callers know which brain interpreted the data.

All functions are async and raise `FirecrawlUnavailable` / `FirecrawlError`
(defined in services.common.firecrawl) on failure, which the routes translate
into clean HTTP responses.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

from services.common.firecrawl import (
    CAPABILITY_MODELS,
    FirecrawlError,
    FirecrawlUnavailable,
    firecrawl,
)

logger = logging.getLogger(__name__)

_OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
_OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")


async def _reason(markdown: str, instruction: str, model: str) -> Optional[str]:
    """Send extracted markdown to Open Router and return the structured analysis.

    Mirrors the Open Router call pattern used in agent_orchestrator/llm.py but is
    self-contained so this module has no cross-service import. Returns None if no
    key is configured or the call fails, so the route still returns raw extraction.
    """
    if not _OPENROUTER_API_KEY:
        logger.warning("[web_intel] no OPENROUTER_API_KEY — skipping LLM reasoning")
        return None
    # Cap the source so we stay within the model's context window (Firecrawl can
    # return very large concatenated markdown from many search results).
    MAX_SOURCE_CHARS = 12000
    if markdown and len(markdown) > MAX_SOURCE_CHARS:
        markdown = markdown[:MAX_SOURCE_CHARS] + "\n…[truncated]"
    messages = [
        {
            "role": "system",
            "content": (
                "You are a telecom competitive-intelligence analyst for OmniDome. "
                "Return concise, factual, structured output based ONLY on the web "
                "content provided. Use bullet points or short sections. Never invent "
                "facts not present in the source."
            ),
        },
        {"role": "user", "content": f"{instruction}\n\n--- SOURCE WEB CONTENT ---\n{markdown}"},
    ]
    payload = {"model": model, "messages": messages, "temperature": 0.1, "max_tokens": 4000}
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                f"{_OPENROUTER_BASE_URL}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {_OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://omnidome.local",
                },
            )
        if resp.status_code != 200:
            logger.warning("[web_intel] Open Router %s: %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as exc:  # network / timeout — degrade gracefully
        logger.error("[web_intel] Open Router reasoning failed: %s", exc)
        return None


def _results_list(raw: dict) -> list:
    """Extract the result list from a Firecrawl search response, tolerating shape drift."""
    data = raw.get("data", raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Grouped search: {"web": [...], "news": [...], ...}
        if any(isinstance(v, list) for v in data.values()):
            merged = []
            for v in data.values():
                if isinstance(v, list):
                    merged.extend(v)
            return merged
        return data.get("results", [])
    return []


# ════════════════════════════════════════════════════════════════════════
# 1. PRODUCT RESEARCH
# ════════════════════════════════════════════════════════════════════════
async def product_research(fno_name: str, *, product_query: Optional[str] = None) -> dict:
    """Research an FNO's fibre products / packages via web search + LLM summary."""
    q = product_query or f"{fno_name} fibre packages prices speeds 2026 South Africa"
    raw = await firecrawlsearch(q, limit=6)
    markdown = firecrawl.markdown_from(raw)
    model = CAPABILITY_MODELS["product_research"]["reasoning"]
    analysis = await _reason(
        markdown,
        f"Summarise {fno_name}'s fibre product lineup from the search results: "
        "list packages, speeds, prices (ZAR), and any notable differentiators.",
        model,
    )
    return {
        "capability": "product_research",
        "fno": fno_name,
        "query": q,
        "reasoning_model": model if analysis else None,
        "analysis": analysis,
        "raw_results": _results_list(raw),
    }


# ════════════════════════════════════════════════════════════════════════
# 2. FNO SITE MESSAGE INTEGRATION
# ════════════════════════════════════════════════════════════════════════
async def fno_site_message(portal_url: str) -> dict:
    """Scrape the latest message / announcement banner off an FNO portal page."""
    raw = await firecrawl.scrape(portal_url, formats=["markdown"])
    markdown = firecrawl.markdown_from(raw)
    return {
        "capability": "fno_site_message",
        "source_url": portal_url,
        "message_markdown": markdown,
        "raw": raw.get("data", raw),
    }


# ════════════════════════════════════════════════════════════════════════
# 3. NEW SITE / AREA RELEASES
# ════════════════════════════════════════════════════════════════════════
async def new_site_releases(fno_name: str, *, city: Optional[str] = None) -> dict:
    """Discover newly-released coverage areas / build sites for an FNO."""
    loc = f" in {city}" if city else ""
    q = f"{fno_name} new fibre coverage areas launched 2026{loc} South Africa"
    raw = await firecrawlsearch(q, limit=8)
    markdown = firecrawl.markdown_from(raw)
    return {
        "capability": "new_site_releases",
        "fno": fno_name,
        "city": city,
        "query": q,
        "summary_markdown": markdown,
        "raw_results": _results_list(raw),
    }


# ════════════════════════════════════════════════════════════════════════
# 4. CANCELLATION PROCESSING
# ════════════════════════════════════════════════════════════════════════
async def cancellation_processing(fno_name: str, *, portal_url: Optional[str] = None) -> dict:
    """Extract the cancellation / termination procedure and required steps."""
    url = portal_url or f"https://www.{fno_name.lower().replace(' ', '')}.co.za/cancellation"
    raw = await firecrawl.scrape(url, formats=["markdown"])
    markdown = firecrawl.markdown_from(raw)
    model = CAPABILITY_MODELS["cancellation_processing"].get("reasoning") or CAPABILITY_MODELS["product_research"]["reasoning"]
    steps = None
    if _OPENROUTER_API_KEY:
        steps = await _reason(
            markdown,
            f"Extract the cancellation/termination procedure for {fno_name}. Return a "
            "numbered list of steps, any notice period, fees, and required contact "
            "channels (email/portal/phone). If the page is not a cancellation page, say so.",
            model,
        )
    return {
        "capability": "cancellation_processing",
        "fno": fno_name,
        "source_url": url,
        "procedure_markdown": markdown,
        "extracted_steps": steps,
        "raw": raw.get("data", raw),
    }


# ════════════════════════════════════════════════════════════════════════
# 5. ADDRESS LOOKUP
# ════════════════════════════════════════════════════════════════════════
async def address_lookup(address: str, *, fno_name: Optional[str] = None) -> dict:
    """Resolve a street address to fibre coverage / available FNOs."""
    scope = f" {fno_name}" if fno_name else " available fibre networks"
    q = f'"{address}"{scope} coverage availability South Africa'
    raw = await firecrawlsearch(q, limit=6)
    markdown = firecrawl.markdown_from(raw)
    return {
        "capability": "address_lookup",
        "address": address,
        "fno": fno_name,
        "query": q,
        "coverage_markdown": markdown,
        "raw_results": _results_list(raw),
    }


# ════════════════════════════════════════════════════════════════════════
# 6. COMPETITOR ANALYSIS
# ════════════════════════════════════════════════════════════════════════
async def competitor_analysis(fno_name: str, competitors: list[str]) -> dict:
    """Compare an FNO against named competitors (LLM-interpreted from web data)."""
    comp_block = ", ".join(competitors) if competitors else "major South African fibre networks"
    q = f"{fno_name} vs {comp_block} fibre comparison pricing speed reliability 2026"
    raw = await firecrawlsearch(q, limit=8)
    markdown = firecrawl.markdown_from(raw)
    model = CAPABILITY_MODELS["competitor_analysis"]["reasoning"]
    analysis = await _reason(
        markdown,
        f"Compare {fno_name} against {comp_block}. Produce a side-by-side table of "
        "pricing, speeds, coverage, and stated reliability. Flag where {fno_name} is "
        "stronger or weaker. Base claims only on the source content.",
        model,
    )
    return {
        "capability": "competitor_analysis",
        "fno": fno_name,
        "competitors": competitors,
        "query": q,
        "reasoning_model": model if analysis else None,
        "analysis": analysis,
        "raw_results": _results_list(raw),
    }


# Thin alias used by the capability wrappers above — delegates to the client's search.
async def firecrawlsearch(query: str, *, limit: int = 5) -> dict:
    return await firecrawlsearch_client(query, limit=limit)


firecrawlsearch_client = lambda query, *, limit=5: getattr(firecrawl, "search")(query, limit=limit)
