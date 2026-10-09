"""Storage contract for the knowledge layer.

All vector SQL lives behind this interface. Two implementations:
  * store_pg.PgVectorStore    - production (pgvector, tsvector, RLS), separate `knowledge_db`
  * store_memory.MemoryStore  - in-process (pure python cosine + token match) for unit tests

Everything is tenant scoped: every method takes the tenant id explicitly and an
implementation must never return another tenant's rows.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from services.tenant_memory.knowledge.kdata import AccessScope, Chunk, Edge, Filters

SearchResult = list[tuple[Chunk, float]]


class KnowledgeStore(ABC):
    # ── lifecycle ──────────────────────────────────────────────────────────
    @abstractmethod
    async def ensure_schema(self) -> None: ...

    @abstractmethod
    async def ping(self) -> bool: ...

    # ── chunks ─────────────────────────────────────────────────────────────
    @abstractmethod
    async def source_state(self, tenant: str, source_type: str, source_id: str) -> dict[int, tuple[str, Optional[str]]]:
        """{chunk_no: (content_hash, embedding_model)} of the live chunks of one source."""

    @abstractmethod
    async def cached_embeddings(self, tenant: str, hashes: list[str], model: str) -> dict[str, list[float]]:
        """Embeddings already computed (live or tombstoned rows) for these content hashes."""

    @abstractmethod
    async def upsert_chunks(self, tenant: str, chunks: list[Chunk]) -> dict:
        """Insert/refresh by (tenant, source_type, source_id, chunk_no); revives tombstones.
        Returns {'inserted': n, 'updated': n, 'unchanged': n}."""

    @abstractmethod
    async def retire_chunks(self, tenant: str, source_type: str, source_id: str, keep_chunk_nos: list[int]) -> int:
        """Tombstone chunks of a source whose chunk_no is not in keep_chunk_nos (a card got shorter)."""

    @abstractmethod
    async def tombstone_source(self, tenant: str, source_type: str, source_id: str) -> int: ...

    @abstractmethod
    async def live_source_ids(self, tenant: str, source_type: str) -> set[str]: ...

    @abstractmethod
    async def vector_search(self, tenant: str, vec: list[float], flt: Filters, access: AccessScope, limit: int) -> SearchResult:
        """Cosine similarity, best first (score = 1 - cosine distance)."""

    @abstractmethod
    async def text_search(self, tenant: str, query: str, flt: Filters, access: AccessScope, limit: int) -> SearchResult:
        """Full-text rank, best first (OR semantics over the query words)."""

    @abstractmethod
    async def chunks_for_sources(self, tenant: str, nodes: list[tuple[str, str]], flt: Filters,
                                 access: AccessScope, per_source: int = 1) -> list[Chunk]: ...

    @abstractmethod
    async def near_duplicates(self, tenant: str, source_type: str, threshold: float, limit: int) -> list[tuple[str, str, float]]:
        """Pairs of live chunk source_ids of one source_type with cosine >= threshold."""

    # ── graph ──────────────────────────────────────────────────────────────
    @abstractmethod
    async def replace_edges(self, tenant: str, origin_key: str, edges: list[Edge]) -> None:
        """Replace every edge previously emitted by `origin_key` (e.g. 'invoice:<id>')."""

    @abstractmethod
    async def delete_edges_by_origin(self, tenant: str, origin_key: str) -> None: ...

    @abstractmethod
    async def traverse(self, tenant: str, start: list[tuple[str, str]], depth: int, relations: Optional[list[str]],
                       limit: int) -> list[dict]:
        """Undirected walk, depth-capped, cycle-safe. [{'node_type','node_id','depth','relation'}] excluding the seeds."""

    # ── indexing bookkeeping ───────────────────────────────────────────────
    @abstractmethod
    async def get_watermark(self, tenant: str, source: str) -> Optional[dict]: ...

    @abstractmethod
    async def set_watermark(self, tenant: str, source: str, last_ts: Optional[datetime], *, full: bool = False,
                            meta: Optional[dict] = None) -> None: ...

    @abstractmethod
    async def record_failure(self, tenant: str, source: str, source_ref: str, error: str) -> None: ...

    @abstractmethod
    async def clear_failures(self, tenant: str, source: str) -> None: ...

    @abstractmethod
    async def coverage(self, tenant: str) -> dict:
        """{'sources': [{source_type, module, chunks, tombstoned, last_indexed}], 'watermarks': [...], 'failures': [...], 'queue': {...}}"""

    @abstractmethod
    async def enqueue_job(self, tenant: str, kind: str, params: dict, requested_by: Optional[str] = None) -> str: ...

    @abstractmethod
    async def claim_job(self) -> Optional[dict]:
        """Atomically take the oldest queued job (any tenant), marking it running."""

    @abstractmethod
    async def finish_job(self, job_id: str, status: str, result: dict) -> None: ...

    @abstractmethod
    async def try_lock(self, name: str) -> bool:
        """Non-blocking cross-process lock (pg advisory lock). Must be released with unlock()."""

    @abstractmethod
    async def unlock(self, name: str) -> None: ...

    # ── erasure / retention ────────────────────────────────────────────────
    @abstractmethod
    async def erase(self, tenant: str, *, source_type: Optional[str] = None, source_id: Optional[str] = None,
                    module: Optional[str] = None) -> dict:
        """HARD delete (no tombstone) of chunks, their edges, watermarks (when whole tenant). POPIA erasure."""

    @abstractmethod
    async def purge_tombstones(self, tenant: str, older_than: datetime) -> int: ...

    @abstractmethod
    async def set_importance(self, tenant: str, source_type: str, source_id: str, importance: float) -> int: ...


def vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in vec) + "]"
