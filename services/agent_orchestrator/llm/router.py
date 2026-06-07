"""Model router — routes agent_type to (primary_model, fallback_model) with usage tracking."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx

from config import settings
from llm.ollama import OllamaClient

logger = logging.getLogger("llm.router")

# Simple in-memory usage counter per tenant
# In production: use Redis or DB
_usage_counts: Dict[str, Dict[str, int]] = {}


class ModelRouter:
    """Routes agent types to model pairs, tracks usage, and enforces timeouts."""

    def __init__(self):
        self._ollama = OllamaClient()
        self.timeout = 30.0  # hard timeout on all LLM calls

    def resolve(self, agent_type: str) -> Tuple[str, str]:
        """Return (primary_model, fallback_model) for the given agent_type."""
        routes = settings.model_routes
        if agent_type in routes:
            return tuple(routes[agent_type])  # type: ignore[return-value]
        # Default to domebot config
        return tuple(routes.get("domebot", ("qwen2.5:7b", "openrouter/qwen/qwen-2.5-7b-instruct")))  # type: ignore[return-value]

    def record_usage(self, tenant_id: str, model: str) -> None:
        """Track model usage per tenant."""
        if tenant_id not in _usage_counts:
            _usage_counts[tenant_id] = {}
        _usage_counts[tenant_id][model] = _usage_counts[tenant_id].get(model, 0) + 1

    def get_usage(self, tenant_id: str) -> Dict[str, int]:
        """Return usage counts for a tenant."""
        return _usage_counts.get(tenant_id, {}).copy()

    async def invoke(
        self,
        agent_type: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tenant_id: str = "default",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """Non-streaming invocation with timeout + fallback."""
        primary, fallback = self.resolve(agent_type)

        formatted_tools = None
        if tools:
            formatted_tools = OllamaClient.format_tools_for_ollama(tools)

        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self._ollama.chat_with_fallback(
                    model=primary,
                    fallback_model=fallback,
                    messages=messages,
                    tools=formatted_tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=self.timeout,
            )
            elapsed = time.monotonic() - start
            model_used = result.get("model", primary)
            self.record_usage(tenant_id, model_used)
            logger.info(
                "LLM invoke agent=%s model=%.20s tenant=%s %.2fs",
                agent_type, model_used, tenant_id, elapsed,
            )
            return result
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start
            logger.error("LLM invoke timed out after %.1fs (agent=%s, tenant=%s)", elapsed, agent_type, tenant_id)
            raise RuntimeError(f"LLM call timed out after {self.timeout}s")
        except Exception as exc:
            logger.error("LLM invoke error (agent=%s, tenant=%s): %s", agent_type, tenant_id, exc)
            raise

    async def invoke_stream(
        self,
        agent_type: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tenant_id: str = "default",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """Streaming invocation with timeout wrapping."""
        primary, fallback = self.resolve(agent_type)

        formatted_tools = None
        if tools:
            formatted_tools = OllamaClient.format_tools_for_ollama(tools)

        # We wrap the async generator in a timeout monkey-patch:
        # collect tokens with a deadline.
        stream_gen = self._ollama.chat_stream_with_fallback(
            model=primary,
            fallback_model=fallback,
            messages=messages,
            tools=formatted_tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        deadline = time.monotonic() + self.timeout
        model_used = primary  # assume primary
        token_count = 0

        try:
            async for token in stream_gen:
                if time.monotonic() > deadline:
                    logger.error("LLM stream timed out (agent=%s, tenant=%s)", agent_type, tenant_id)
                    yield "\n\n[Request timed out]"
                    break
                if token.startswith("__DONE__"):
                    try:
                        meta = json.loads(token[8:])
                        model_used = meta.get("model", model_used)
                    except Exception:
                        pass
                    break
                token_count += 1
                yield token
        except Exception as exc:
            logger.error("LLM stream error (agent=%s, tenant=%s): %s", agent_type, tenant_id, exc)
            raise
        finally:
            self.record_usage(tenant_id, model_used)
            logger.info(
                "LLM stream agent=%s model=%.20s tenant=%s tokens=%d",
                agent_type, model_used, tenant_id, token_count,
            )

    async def close(self) -> None:
        await self._ollama.close()


# Module-level singleton
router = ModelRouter()

