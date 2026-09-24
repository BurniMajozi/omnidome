"""OpenRouter model fallback in the orchestrator LLM client.

Free models 429 or stream an error chunk when their shared pool is busy; the
client must move to the next model in OPENROUTER_FALLBACK_MODELS.
Run with cwd = services/agent_orchestrator:  python -m pytest tests -q
"""

import asyncio
import json
import os
import sys

import httpx

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator import llm  # noqa: E402


def _sse(*chunks):
    return "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"


def _patch_client(monkeypatch, answers):
    tried = []

    def handler(request):
        model = json.loads(request.content)["model"]
        tried.append(model)
        status, body = answers[model]
        if isinstance(body, str):
            return httpx.Response(status, text=body, headers={"content-type": "text/event-stream"})
        return httpx.Response(status, json=body)

    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(handler)}),
    )
    return tried


def _env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "qwen/a:free")
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "google/b:free,nvidia/c:free")


def _collect(agen):
    async def run():
        return [t async for t in agen]
    return asyncio.run(run())


def test_stream_skips_rate_limited_and_error_chunk_models(monkeypatch):
    _env(monkeypatch)
    tried = _patch_client(monkeypatch, {
        "qwen/a:free": (429, {"error": {"message": "rate-limited"}}),
        "google/b:free": (200, _sse({"error": {"message": "overloaded"}})),
        "nvidia/c:free": (200, _sse({"choices": [{"delta": {"content": "Hel"}}]},
                                    {"choices": [{"delta": {"content": "lo"}}]})),
    })
    tokens = _collect(llm.LLMClient()._openrouter_stream("qwen/a:free", [], None))
    assert tried == ["qwen/a:free", "google/b:free", "nvidia/c:free"]
    assert "".join(tokens) == "Hello"


def test_stream_reports_error_when_all_models_fail(monkeypatch):
    _env(monkeypatch)
    _patch_client(monkeypatch, {
        "qwen/a:free": (429, {"error": {"message": "rate-limited"}}),
        "google/b:free": (503, {"error": {"message": "down"}}),
        "nvidia/c:free": (429, {"error": {"message": "rate-limited"}}),
    })
    tokens = _collect(llm.LLMClient()._openrouter_stream("qwen/a:free", [], None))
    assert len(tokens) == 1 and tokens[0].startswith("[Error:")


def test_chat_uses_next_model_after_429(monkeypatch):
    _env(monkeypatch)
    tried = _patch_client(monkeypatch, {
        "qwen/a:free": (429, {"error": {"message": "rate-limited"}}),
        "google/b:free": (200, {"choices": [{"message": {"content": "OK"}}]}),
    })
    result = asyncio.run(llm.LLMClient()._openrouter_chat("qwen/a:free", [], None))
    assert tried == ["qwen/a:free", "google/b:free"]
    assert result["content"] == "OK"
