"""Client for Hermes's OpenAI-compatible API Server (local Gemma via Ollama).

Hermes (the gateway container) is the chat brain: it does its own reasoning,
calls back into this service's tools over MCP (routes/mcp.py), and keeps
its own Obsidian-backed memory. This client just forwards a conversation to
Hermes's /v1/chat/completions and streams the reply back -- no tool-calling
loop here, that happens inside Hermes itself.
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from services.agent_orchestrator.config import settings

logger = logging.getLogger("agent_orchestrator.hermes_client")


class HermesClient:
    """Async client for Hermes's OpenAI-compatible chat completions endpoint."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, timeout: float = 60.0):
        self.base_url = (base_url or settings.hermes_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.hermes_api_key
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """Non-streaming call. Returns the assistant's text content."""
        payload: Dict[str, Any] = {
            "model": "hermes-agent",
            "messages": messages,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=5.0)) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"].get("content", "")

    async def chat_stream(self, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        """Streaming call. Yields content deltas as they arrive."""
        payload: Dict[str, Any] = {
            "model": "hermes-agent",
            "messages": messages,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=5.0)) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions", json=payload, headers=self._headers()
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[len("data: "):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content


# Singleton, matching the existing llm_client convention in llm.py
hermes_client = HermesClient()
