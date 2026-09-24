"""Tests for services/common/openrouter.py — model fallback chain.

Free OpenRouter models share a pool across all OpenRouter users, so any one
of them can answer 429 (or an "overloaded" error inside a 200) at any time.
The helper walks OPENROUTER_MODEL then OPENROUTER_FALLBACK_MODELS.

Run with cwd = services/fno_intelligence:  python -m pytest tests/ -q
"""

import asyncio
import json
import os
import sys

import httpx

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.common import openrouter  # noqa: E402
from services.common.openrouter import chat_completion, completion_error, model_chain  # noqa: E402


def test_model_chain_is_primary_then_fallbacks(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "qwen/a:free")
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "google/b:free, nvidia/c:free")
    assert model_chain() == ["qwen/a:free", "google/b:free", "nvidia/c:free"]


def test_model_chain_explicit_primary_wins_and_duplicates_drop(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "qwen/a:free")
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "qwen/a:free,,google/b:free")
    assert model_chain("x/special") == ["x/special", "qwen/a:free", "google/b:free"]


def test_model_chain_without_env_uses_default(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_FALLBACK_MODELS", raising=False)
    assert model_chain() == [openrouter.DEFAULT_MODEL]


def test_completion_error_flags_http_errors():
    assert "429" in completion_error(429, {"error": {"message": "rate-limited"}})


def test_completion_error_flags_error_inside_200():
    # NVIDIA free tier answers 200 with {"error": ...} when overloaded.
    body = {"error": {"message": "Upstream error from Nvidia: Service temporarily overloaded"}}
    assert "overloaded" in completion_error(200, body)


def test_completion_error_flags_missing_choices():
    assert completion_error(200, {"choices": []})


def test_completion_error_accepts_normal_answer():
    assert completion_error(200, {"choices": [{"message": {"content": "OK"}}]}) is None


def _fake_transport(answers: dict):
    """answers: model -> (status, body). Records the models tried in order."""
    tried = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        tried.append(model)
        status, body = answers[model]
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler), tried


def test_chat_completion_falls_back_to_next_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "qwen/a:free")
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "google/b:free,nvidia/c:free")
    transport, tried = _fake_transport({
        "qwen/a:free": (429, {"error": {"message": "rate-limited upstream"}}),
        "google/b:free": (200, {"error": {"message": "overloaded"}}),
        "nvidia/c:free": (200, {"choices": [{"message": {"content": "OK"}}]}),
    })
    result = asyncio.run(chat_completion({"messages": []}, transport=transport))
    assert tried == ["qwen/a:free", "google/b:free", "nvidia/c:free"]
    assert result is not None
    data, model = result
    assert model == "nvidia/c:free"
    assert data["choices"][0]["message"]["content"] == "OK"


def test_chat_completion_returns_none_when_every_model_fails(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "qwen/a:free")
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "google/b:free")
    transport, tried = _fake_transport({
        "qwen/a:free": (429, {"error": {"message": "rate-limited"}}),
        "google/b:free": (503, {"error": {"message": "down"}}),
    })
    assert asyncio.run(chat_completion({"messages": []}, transport=transport)) is None
    assert tried == ["qwen/a:free", "google/b:free"]


def test_chat_completion_without_key_skips_network(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    transport, tried = _fake_transport({})
    assert asyncio.run(chat_completion({"messages": []}, transport=transport)) is None
    assert tried == []
