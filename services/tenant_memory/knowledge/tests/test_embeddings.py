import asyncio
import json

import httpx
import pytest

from services.tenant_memory.knowledge.config import get_settings
from services.tenant_memory.knowledge.embeddings import (
    EmbeddingDimensionError, EmbeddingModelMissing, EmbeddingUnavailable, HashEmbedder, OllamaEmbedder, cosine,
)


def make(handler, monkeypatch, dim=4, batch=2, retries=1):
    monkeypatch.setenv("EMBEDDING_DIM", str(dim))
    monkeypatch.setenv("EMBED_BATCH_SIZE", str(batch))
    monkeypatch.setenv("EMBED_RETRIES", str(retries))

    async def nosleep(_):
        return None

    return OllamaEmbedder(get_settings(), transport=httpx.MockTransport(handler), sleep=nosleep)


def test_batches_and_prefixes(monkeypatch):
    seen = []

    def handler(req):
        j = json.loads(req.read().decode())
        seen.append(j["input"])
        return httpx.Response(200, json={"embeddings": [[1, 0, 0, 0]] * len(j["input"])})

    e = make(handler, monkeypatch)
    vecs = asyncio.run(e.embed_documents(["a", "b", "c"]))
    assert len(vecs) == 3 and [len(x) for x in seen] == [2, 1]
    assert all(t.startswith("search_document: ") for batch in seen for t in batch)
    asyncio.run(e.embed_query("q"))
    assert seen[-1] == ["search_query: q"]


def test_dimension_mismatch_fails_loudly(monkeypatch):
    e = make(lambda r: httpx.Response(200, json={"embeddings": [[1, 2, 3]]}), monkeypatch)
    with pytest.raises(EmbeddingDimensionError):
        asyncio.run(e.embed_documents(["a"]))


def test_missing_model_gives_pull_hint_without_tripping_breaker(monkeypatch):
    e = make(lambda r: httpx.Response(404, json={"error": "not found"}), monkeypatch)
    for _ in range(6):
        with pytest.raises(EmbeddingModelMissing, match="ollama pull"):
            asyncio.run(e.embed_documents(["a"]))
    assert not e.breaker.is_open


def test_retry_then_success_and_breaker_opens(monkeypatch):
    calls = {"n": 0}

    def flaky(req):
        calls["n"] += 1
        return httpx.Response(500, text="boom") if calls["n"] == 1 else httpx.Response(200, json={"embeddings": [[1, 0, 0, 0]]})

    e = make(flaky, monkeypatch)
    assert asyncio.run(e.embed_documents(["a"])) and calls["n"] == 2
    down = make(lambda r: httpx.Response(503), monkeypatch, retries=0)
    for _ in range(4):
        with pytest.raises(EmbeddingUnavailable):
            asyncio.run(down.embed_documents(["a"]))
    assert down.breaker.is_open
    with pytest.raises(EmbeddingUnavailable, match="circuit open"):
        asyncio.run(down.embed_documents(["a"]))


def test_health_reports_missing_model(monkeypatch):
    e = make(lambda r: httpx.Response(200, json={"models": [{"name": "gemma3:4b"}]}), monkeypatch)
    h = asyncio.run(e.health())
    assert h["reachable"] and not h["ok"] and "ollama pull" in h["hint"]
    ok = make(lambda r: httpx.Response(200, json={"models": [{"name": "nomic-embed-text:latest"}]}), monkeypatch)
    assert asyncio.run(ok.health())["ok"]


def test_hash_embedder_similarity():
    h = HashEmbedder(64)
    a, b, c = (asyncio.run(h.embed_query(t)) for t in ("fibre outage soweto", "outage in soweto fibre", "invoice vat"))
    assert cosine(a, b) > 0.8 > cosine(a, c)
