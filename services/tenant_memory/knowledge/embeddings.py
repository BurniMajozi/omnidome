"""Local embedding client (Ollama /api/embed). Tenant text never leaves the platform.

Readiness: Ollama must already have the model (`ollama pull nomic-embed-text`).
This client never downloads anything; a missing model is reported by health()
and raised as EmbeddingModelMissing so the indexer waits instead of failing rows.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
import time
from typing import Optional, Protocol

import httpx

from services.tenant_memory.knowledge.config import Settings, get_settings

logger = logging.getLogger("knowledge.embeddings")


class EmbeddingError(RuntimeError):
    pass


class EmbeddingUnavailable(EmbeddingError):
    """Transport/5xx failure or open circuit: try again later."""


class EmbeddingModelMissing(EmbeddingError):
    pass


class EmbeddingDimensionError(EmbeddingError):
    pass


class Embedder(Protocol):
    model: str
    dim: int

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...
    async def health(self) -> dict: ...


class _Breaker:
    """Open after `threshold` consecutive failures; half-open probe after `cooldown` seconds."""

    def __init__(self, threshold: int = 4, cooldown: float = 30.0, clock=time.monotonic):
        self.threshold, self.cooldown, self.clock = threshold, cooldown, clock
        self.failures = 0
        self.opened_at: Optional[float] = None

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        return self.clock() - self.opened_at < self.cooldown   # past cooldown: half-open, let a probe through

    def success(self) -> None:
        self.failures, self.opened_at = 0, None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = self.clock()


class OllamaEmbedder:
    def __init__(self, settings: Optional[Settings] = None, transport: Optional[httpx.AsyncBaseTransport] = None,
                 sleep=asyncio.sleep):
        self.s = settings or get_settings()
        self.model = self.s.embedding_model
        self.dim = self.s.embedding_dim
        self._transport = transport
        self._sleep = sleep
        self.breaker = _Breaker()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.s.ollama_base_url, timeout=self.s.embed_timeout_s,
                                 transport=self._transport)

    async def _post_embed(self, inputs: list[str]) -> list[list[float]]:
        if self.breaker.is_open:
            raise EmbeddingUnavailable("embedding circuit open (Ollama failing); retry later")
        last: Optional[Exception] = None
        for attempt in range(self.s.embed_retries + 1):
            try:
                async with self._client() as c:
                    r = await c.post("/api/embed", json={"model": self.model, "input": inputs, "truncate": True})
                if r.status_code == 404:
                    # Not a transport failure: the model simply is not pulled. Do not trip the breaker.
                    raise EmbeddingModelMissing(
                        f"model '{self.model}' not found in Ollama; run: ollama pull {self.model}")
                if r.status_code >= 500:
                    last = EmbeddingUnavailable(f"ollama {r.status_code}: {r.text[:120]}")
                elif r.status_code >= 400:
                    raise EmbeddingError(f"ollama {r.status_code}: {r.text[:120]}")
                else:
                    vecs = r.json().get("embeddings")
                    if not isinstance(vecs, list) or len(vecs) != len(inputs):
                        raise EmbeddingError("ollama returned a different number of embeddings than inputs")
                    for v in vecs:
                        if len(v) != self.dim:
                            raise EmbeddingDimensionError(
                                f"model '{self.model}' returned {len(v)} dims, schema expects {self.dim}")
                    self.breaker.success()
                    return vecs
            except EmbeddingError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
            if attempt < self.s.embed_retries:
                await self._sleep(min(8.0, 0.5 * 2 ** attempt))
        self.breaker.failure()
        raise EmbeddingUnavailable(f"ollama embed failed after retries: {last}")

    async def _embed(self, texts: list[str], prefix: str) -> list[list[float]]:
        out: list[list[float]] = []
        n = max(1, self.s.embed_batch_size)
        for i in range(0, len(texts), n):
            out.extend(await self._post_embed([prefix + t for t in texts[i:i + n]]))
        return out

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, self.s.doc_prefix) if texts else []

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], self.s.query_prefix))[0]

    async def health(self) -> dict:
        try:
            async with self._client() as c:
                r = await c.get("/api/tags")
            r.raise_for_status()
            names = {m.get("name", "") for m in r.json().get("models", [])}
            present = any(n == self.model or n.split(":")[0] == self.model.split(":")[0] for n in names)
            return {"ok": present, "model": self.model, "dim": self.dim, "reachable": True,
                    "circuit_open": self.breaker.is_open,
                    "hint": None if present else f"ollama pull {self.model}"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "model": self.model, "dim": self.dim, "reachable": False,
                    "circuit_open": self.breaker.is_open, "error": str(exc)[:160]}


class HashEmbedder:
    """Deterministic bag-of-words hashing embedder for tests/dev (no model, no network).
    Texts sharing words get high cosine similarity, which is enough to exercise ranking."""

    def __init__(self, dim: int = 64, model: str = "hash-test"):
        self.dim, self.model = dim, model
        self.calls: list[int] = []     # batch sizes, to assert caching/batching

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(len(texts))
        return [self._vec(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vec(text)

    async def health(self) -> dict:
        return {"ok": True, "model": self.model, "dim": self.dim, "reachable": True, "circuit_open": False}


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
