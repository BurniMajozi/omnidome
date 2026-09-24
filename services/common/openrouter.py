"""OpenRouter chat completions with a model fallback chain.

Free OpenRouter models (":free") share one capacity pool across every
OpenRouter user, so any of them can answer 429 or an "overloaded" error at any
moment, regardless of our own volume. Some providers report that failure inside
an HTTP 200 body. Callers therefore walk a chain of models:

    OPENROUTER_MODEL                 primary
    OPENROUTER_FALLBACK_MODELS       comma-separated, tried in order

and take the first real answer.

Model limiter (spec A4, SPEC-orchestrator-memory-hardening.md): at most
OPENROUTER_MAX_CONCURRENCY requests per model at once in this process, and a
model that answers 429 / rate-limited / overloaded is skipped for COOLDOWN_S so
later calls go straight to the next fallback instead of queueing on it.
"""

import asyncio
import logging
import os
import re
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "anthropic/claude-haiku-4.5"


def base_url() -> str:
    return os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")


def api_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "")


def model_chain(primary: Optional[str] = None) -> list[str]:
    """Models to try, in order, without duplicates. An explicit `primary`
    (e.g. a per-capability model) goes first, then the env chain."""
    candidates = [primary, os.getenv("OPENROUTER_MODEL")]
    candidates += os.getenv("OPENROUTER_FALLBACK_MODELS", "").split(",")
    chain: list[str] = []
    for model in candidates:
        model = (model or "").strip()
        if model and model not in chain:
            chain.append(model)
    return chain or [DEFAULT_MODEL]


# ── Model limiter (A4) ─────────────────────────────────────────────────────

COOLDOWN_S = float(os.getenv("OPENROUTER_COOLDOWN_S", "60"))
_RATE_LIMITED = re.compile(r"rate.?limit|overloaded|too many requests|capacity", re.IGNORECASE)
_now = time.monotonic
_cooldown_until: dict[str, float] = {}
_semaphores: dict[tuple[int, str], asyncio.Semaphore] = {}


def reset_limits() -> None:
    _cooldown_until.clear()
    _semaphores.clear()


def mark_cooldown(model: str) -> None:
    _cooldown_until[model] = _now() + COOLDOWN_S


def in_cooldown(model: str) -> bool:
    return _cooldown_until.get(model, 0.0) > _now()


def is_rate_limited(status: int, problem: Optional[str]) -> bool:
    return status == 429 or bool(problem and _RATE_LIMITED.search(problem))


def available_models(primary: Optional[str] = None) -> list[str]:
    """The chain without models cooling down; the whole chain if all are
    (better to try a busy model than to give up without asking)."""
    chain = model_chain(primary)
    ready = [m for m in chain if not in_cooldown(m)]
    return ready or chain


def _semaphore(model: str) -> asyncio.Semaphore:
    """Per event loop and model (asyncio primitives belong to one loop)."""
    key = (id(asyncio.get_running_loop()), model)
    if key not in _semaphores:
        limit = max(1, int(os.getenv("OPENROUTER_MAX_CONCURRENCY", "2")))
        _semaphores[key] = asyncio.Semaphore(limit)
    return _semaphores[key]


def completion_error(status: int, body: Any) -> Optional[str]:
    """Why a chat-completion response is unusable, or None when it's a real answer."""
    error = body.get("error") if isinstance(body, dict) else None
    if status != 200 or error:
        message = error.get("message") if isinstance(error, dict) else error
        raw = error.get("metadata", {}).get("raw") if isinstance(error, dict) else None
        return f"HTTP {status}: {raw or message or 'error'}"
    if not isinstance(body, dict) or not body.get("choices"):
        return "no choices in response"
    return None


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key()}", "HTTP-Referer": "https://omnidome.local"}


async def chat_completion(
    payload: dict,
    *,
    primary: Optional[str] = None,
    timeout: float = 45.0,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Optional[tuple[dict, str]]:
    """POST /chat/completions, trying each model in the chain. `payload` is the
    request body without "model". Returns (response_json, model_used), or None
    when there is no key or every model failed."""
    if not api_key():
        logger.warning("[openrouter] no OPENROUTER_API_KEY configured")
        return None
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        for model in available_models(primary):
            try:
                async with _semaphore(model):
                    resp = await client.post(
                        f"{base_url()}/chat/completions",
                        json={**payload, "model": model},
                        headers=_headers(),
                    )
                try:
                    body = resp.json()
                except ValueError:
                    body = {"error": {"message": resp.text[:200]}}
            except httpx.HTTPError as exc:
                logger.warning("[openrouter] %s failed: %s", model, exc)
                continue
            problem = completion_error(resp.status_code, body)
            if problem is None:
                return body, model
            if is_rate_limited(resp.status_code, problem):
                mark_cooldown(model)
            logger.warning("[openrouter] %s unusable, trying next: %s", model, problem[:200])
    return None


def stream_request(model: str, payload: dict) -> dict:
    """Keyword arguments for httpx `client.stream("POST", ...)` for one model."""
    return {
        "url": f"{base_url()}/chat/completions",
        "json": {**payload, "model": model, "stream": True},
        "headers": _headers(),
    }
