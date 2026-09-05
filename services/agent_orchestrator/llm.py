"""LLM client for Ollama + OpenRouter fallback."""

import os
import json
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# OpenRouter model used for all agents when Ollama is unavailable (i.e. on
# Railway, where there is no local Ollama). Env-driven so it can be swapped
# without a code change; sent to OpenRouter verbatim, so use a real slug.
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")

# Model routing per agent type: (ollama_model, openrouter_fallback).
MODEL_ROUTES: Dict[str, tuple] = {
    "customer_facing": ("qwen2.5:7b", OPENROUTER_MODEL),
    "retention": ("llama3.1:70b", OPENROUTER_MODEL),
    "provisioning": ("qwen2.5:7b", OPENROUTER_MODEL),
    "executive": ("llama3.1:70b", OPENROUTER_MODEL),
    "support": ("qwen2.5:7b", OPENROUTER_MODEL),
}

# Agent system prompts
SYSTEM_PROMPTS: Dict[str, str] = {
    "customer_facing": (
        "You are DomeBot, the AI assistant for a South African fibre ISP. "
        "You help customers with: balance inquiries, invoice questions, service status, "
        "coverage checks, support ticket creation, and plan information. "
        "Always be professional, concise, and helpful. Use South African English. "
        "If you cannot resolve the issue, offer to create a support ticket or escalate "
        "to a human agent. Never make up information — only use tool results."
    ),
    "retention": (
        "You are ChurnGuard, an AI retention specialist for a South African ISP. "
        "Your role is to identify at-risk customers and take proactive retention actions. "
        "Analyse churn predictions, evaluate customer profiles, and recommend or execute "
        "retention campaigns (discounts, personal outreach, win-back offers). "
        "Always consider customer lifetime value when making recommendations."
    ),
    "provisioning": (
        "You are ProvisionBot, an AI provisioning agent for a South African fibre ISP. "
        "You automate the new customer onboarding workflow: verify coverage, check RICA identity, "
        "create customer records, reserve equipment, provision network service, "
        "set up billing, and schedule installation. "
        "Follow the exact workflow sequence and report each step's status."
    ),
    "executive": (
        "You are InsightBot, an executive intelligence agent for a South African ISP. "
        "You analyse operational data across all departments and produce natural language "
        "executive briefings with key metrics, trends, anomalies, and actionable recommendations. "
        "Focus on revenue, churn, network health, sales pipeline, and operational efficiency. "
        "Format output as a structured briefing with clear sections."
    ),
    "support": (
        "You are SupportBot, an AI support agent for a South African fibre ISP. "
        "You help with ticket management, network diagnostics, knowledge base searches, "
        "and customer issue resolution. Be methodical in troubleshooting. "
        "If an issue requires field technician dispatch, create the appropriate support ticket."
    ),
}


class LLMClient:
    """Async LLM client supporting Ollama and OpenRouter."""

    def __init__(self):
        self._ollama_available: Optional[bool] = None

    async def _check_ollama(self) -> bool:
        """Quick health check for Ollama."""
        if self._ollama_available is not None:
            return self._ollama_available
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
                self._ollama_available = resp.status_code == 200
        except Exception:
            self._ollama_available = False
        logger.info("Ollama available: %s", self._ollama_available)
        return self._ollama_available

    def _format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict]:
        """Convert tool definitions to Ollama tool format."""
        formatted = []
        for t in tools:
            formatted.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                },
            })
        return formatted

    async def chat(
        self,
        agent_type: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a chat completion request. Returns {content, tool_calls}."""
        primary_model, fallback_model = MODEL_ROUTES.get(
            agent_type, ("qwen2.5:7b", OPENROUTER_MODEL)
        )

        system_prompt = SYSTEM_PROMPTS.get(agent_type, "You are a helpful AI assistant.")
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        # Try Ollama first
        ollama_ok = await self._check_ollama()
        if ollama_ok:
            result = await self._ollama_chat(primary_model, full_messages, tools)
            if result:
                return result

        # Fallback to OpenRouter
        if OPENROUTER_API_KEY:
            result = await self._openrouter_chat(fallback_model, full_messages, tools)
            if result:
                return result

        return {
            "content": "I'm sorry, but the AI service is currently unavailable. Please try again in a moment.",
            "tool_calls": [],
        }

    async def _ollama_chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Call Ollama /api/chat endpoint."""
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1, "num_ctx": 8192},
        }
        if tools:
            payload["tools"] = self._format_tools(tools)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{OLLAMA_BASE_URL}/api/chat",
                    json=payload,
                )
                if resp.status_code != 200:
                    logger.warning("Ollama returned %s: %s", resp.status_code, resp.text[:200])
                    return None
                data = resp.json()
                msg = data.get("message", {})
                result = {
                    "content": msg.get("content", ""),
                    "tool_calls": [],
                }
                raw_tool_calls = msg.get("tool_calls", [])
                for tc in raw_tool_calls:
                    if "function" in tc:
                        result["tool_calls"].append({
                            "name": tc["function"]["name"],
                            "arguments": tc["function"].get("arguments", {}),
                        })
                return result
        except httpx.TimeoutException:
            logger.warning("Ollama request timed out")
            return None
        except Exception as e:
            logger.error("Ollama request failed: %s", e)
            return None

    async def _openrouter_chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Call OpenRouter /api/v1/chat/completions endpoint."""
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 2048,
        }
        if tools:
            payload["tools"] = self._format_tools(tools)
            payload["tool_choice"] = "auto"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "HTTP-Referer": "https://omnidome.local",
                    },
                )
                if resp.status_code != 200:
                    logger.warning("OpenRouter returned %s: %s", resp.status_code, resp.text[:200])
                    return None
                data = resp.json()
                choice = data.get("choices", [{}])[0]
                msg = choice.get("message", {})
                result = {
                    "content": msg.get("content", ""),
                    "tool_calls": [],
                }
                raw_tool_calls = msg.get("tool_calls", [])
                for tc in raw_tool_calls:
                    if "function" in tc:
                        import json
                        args = tc["function"].get("arguments", "{}")
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}
                        result["tool_calls"].append({
                            "name": tc["function"]["name"],
                            "arguments": args,
                        })
                return result
        except httpx.TimeoutException:
            logger.warning("OpenRouter request timed out")
            return None
        except Exception as e:
            logger.error("OpenRouter request failed: %s", e)
            return None

    async def chat_stream(
        self,
        agent_type: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ):
        """Stream chat completion tokens from Ollama. Yields token strings."""
        system_prompt = SYSTEM_PROMPTS.get(agent_type, "You are a helpful AI assistant.")
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        model, fallback = MODEL_ROUTES.get(agent_type, ("qwen2.5:7b", OPENROUTER_MODEL))

        ollama_ok = await self._check_ollama()
        if ollama_ok:
            async for token in self._ollama_stream(model, full_messages, tools):
                yield token
            return

        if OPENROUTER_API_KEY:
            async for token in self._openrouter_stream(fallback, full_messages, tools):
                yield token
            return

        yield "AI service unavailable."

    async def _ollama_stream(self, model, messages, tools):
        """Stream from Ollama /api/chat."""
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": 0.1},
        }
        if tools:
            payload["tools"] = self._format_tools(tools)
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload) as resp:
                    async for line in resp.aiter_lines():
                        if line:
                            try:
                                chunk = json.loads(line)
                                token = chunk.get("message", {}).get("content", "")
                                if token:
                                    yield token
                                if chunk.get("done"):
                                    break
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            logger.error("Ollama stream error: %s", e)
            yield f"[Error: {e}]"

    async def _openrouter_stream(self, model, messages, tools):
        """Stream from OpenRouter SSE."""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "stream": True,
        }
        if tools:
            payload["tools"] = self._format_tools(tools)
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                token = chunk["choices"][0].get("delta", {}).get("content", "")
                                if token:
                                    yield token
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
        except Exception as e:
            logger.error("OpenRouter stream error: %s", e)
            yield f"[Error: {e}]"


# Singleton
llm_client = LLMClient()
