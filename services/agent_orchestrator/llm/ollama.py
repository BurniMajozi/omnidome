"""Async Ollama client with streaming, tool calling, and OpenRouter fallback."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from config import settings

logger = logging.getLogger("llm.ollama")


class OllamaClient:
    """Async HTTP client for Ollama's /api/chat endpoint.

    Supports:
    - Streaming token generation (yields partial tokens)
    - Non-streaming chat (returns full response)
    - Tool calling (Ollama native tool format)
    - Health checks
    - OpenRouter fallback when Ollama is unreachable
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=5.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def health(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            client = await self._get_client()
            resp = await client.get("/api/tags")
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("Ollama health check failed: %s", exc)
            return False

    async def chat(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """Non-streaming chat call. Returns the full response dict."""
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if tools:
            payload["tools"] = tools

        client = await self._get_client()
        try:
            resp = await client.post("/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama chat HTTP error %s: %s", exc.response.status_code, exc.response.text)
            raise
        except httpx.RequestError as exc:
            logger.error("Ollama chat request error: %s", exc)
            raise

    async def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat call. Yields individual content tokens."""
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if tools:
            payload["tools"] = tools

        client = await self._get_client()
        try:
            async with client.stream("POST", "/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("done"):
                        # Final chunk — may contain tool_calls
                        yield f"__DONE__{json.dumps(chunk)}"
                        break
                    message = chunk.get("message", {})
                    content = message.get("content", "")
                    if content:
                        yield content
        except httpx.RequestError as exc:
            logger.error("Ollama stream request error: %s", exc)
            raise

    async def chat_with_fallback(
        self,
        model: str,
        fallback_model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """Try Ollama first, fall back to OpenRouter if Ollama is unhealthy."""
        if await self.health():
            try:
                return await asyncio.wait_for(
                    self.chat(model, messages, tools, temperature, max_tokens),
                    timeout=self.timeout,
                )
            except Exception as exc:
                logger.warning("Ollama primary failed (%s), trying OpenRouter fallback", exc)

        return await self._openrouter_chat(
            fallback_model, messages, tools, temperature, max_tokens
        )

    async def chat_stream_with_fallback(
        self,
        model: str,
        fallback_model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """Try Ollama streaming first, fall back to OpenRouter streaming."""
        if await self.health():
            try:
                async for token in self.chat_stream(
                    model, messages, tools, temperature, max_tokens
                ):
                    yield token
                return
            except Exception as exc:
                logger.warning("Ollama stream failed (%s), trying OpenRouter fallback", exc)

        async for token in self._openrouter_stream(
            fallback_model, messages, tools, temperature, max_tokens
        ):
            yield token

    async def _openrouter_chat(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """Non-streaming call to OpenRouter."""
        if not settings.openrouter_api_key:
            raise RuntimeError("OpenRouter API key not configured")

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools

        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(
            base_url=settings.openrouter_base_url,
            timeout=httpx.Timeout(self.timeout, connect=5.0),
        ) as client:
            resp = await client.post("/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            # Normalize OpenRouter response to Ollama-like format
            choice = data["choices"][0]
            message = choice["message"]
            return {
                "model": model,
                "message": {
                    "role": message.get("role", "assistant"),
                    "content": message.get("content", ""),
                    "tool_calls": message.get("tool_calls"),
                },
                "done": True,
            }

    async def _openrouter_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """Streaming call to OpenRouter."""
        if not settings.openrouter_api_key:
            raise RuntimeError("OpenRouter API key not configured")

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(
            base_url=settings.openrouter_base_url,
            timeout=httpx.Timeout(self.timeout, connect=5.0),
        ) as client:
            async with client.stream(
                "POST", "/chat/completions", json=payload, headers=headers
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip() or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        yield "__DONE__{}"
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content

    @staticmethod
    def format_tools_for_ollama(
        tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convert tool definitions to Ollama's native tool format.

        Input format: list of Tool dataclass dicts with
          name, description, parameters (JSON schema)
        Output: Ollama tools list.
        """
        formatted = []
        for tool in tools:
            formatted.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                },
            })
        return formatted
