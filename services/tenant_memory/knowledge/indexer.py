"""Indexer: cards -> chunks -> embeddings -> store, incremental, idempotent and gentle on a small VM.

  * incremental by (updated_at, id) watermark per tenant+source; periodic full reconcile also
    tombstones rows that vanished from the source (delete propagation);
  * idempotent: chunks are keyed (tenant, source_type, source_id, chunk_no) and carry a content hash
    computed without volatile frontmatter, so unchanged text is never re-embedded or rewritten;
  * embeddings already known for a hash (live or tombstoned row) are reused;
  * rate limited: small batches, <= INDEX_CONCURRENCY (1-2) embedding calls in flight, sleep between batches;
  * a per-tenant+source advisory lock keeps the two uvicorn workers / a manual trigger from double-indexing;
  * database sessions are opened per page and closed before embedding (no transaction held across Ollama calls).
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from services.tenant_memory.knowledge.cards.base import Card, stable_text
from services.tenant_memory.knowledge.cards.sources import SOURCES, Page, Source, source_enabled
from services.tenant_memory.knowledge.config import Settings, get_settings
from services.tenant_memory.knowledge.embeddings import (
    Embedder, EmbeddingModelMissing, EmbeddingUnavailable,
)
from services.tenant_memory.knowledge.kdata import Chunk, content_hash
from services.tenant_memory.knowledge.store import KnowledgeStore
from services.tenant_memory.knowledge.textutil import chunk_markdown

logger = logging.getLogger("knowledge.indexer")

SessionFactory = Callable[[], Any]     # async context manager yielding an AsyncSession on the operational DB


class EmbeddingBlocked(RuntimeError):
    """The embedding service cannot serve right now; the run stops cleanly and is retried later."""


def card_to_chunks(tenant: str, card: Card, model: str, max_chars: int, overlap: int) -> list[Chunk]:
    visibility, roles = card.access()
    pieces = chunk_markdown(card.markdown, max_chars, overlap)
    out = []
    for i, md in enumerate(pieces):
        title = card.title if len(pieces) == 1 else f"{card.title} (part {i + 1}/{len(pieces)})"
        out.append(Chunk(
            tenant_id=tenant, source_type=card.source_type, source_id=card.source_id, chunk_no=i, module=card.module,
            title=title, markdown=md, content_hash=content_hash(stable_text(md), model), source_ref=card.source_ref,
            visibility=visibility, required_roles=list(roles), required_permission=card.required_permission, owner_id=card.owner_id, as_of=card.as_of,
            valid_to=card.valid_to, importance=card.importance, tags=list(card.tags), embedding_model=model,
        ))
    return out


class Indexer:
    def __init__(self, store: KnowledgeStore, embedder: Embedder, session_factory: Optional[SessionFactory] = None,
                 settings: Optional[Settings] = None, sources: Optional[dict[str, Source]] = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.store, self.embedder = store, embedder
        self.s = settings or get_settings()
        self.sources = sources if sources is not None else SOURCES
        self._session_factory = session_factory
        self._sleep = sleep
        self._sem = asyncio.Semaphore(self.s.index_concurrency)

    def enabled_names(self) -> list[str]:
        """Sources switched on by KNOWLEDGE_SOURCES, in registration order (sequential, never parallel)."""
        return [n for n in self.sources if source_enabled(n)]

    @asynccontextmanager
    async def _session(self):
        if self._session_factory is None:
            from services.common.db import session_scope
            async with session_scope() as sess:
                yield sess
        else:
            async with self._session_factory() as sess:
                yield sess

    # ── cards -> store ──
    async def index_cards(self, tenant: str, cards: list[Card], *, force: bool = False) -> dict:
        stats = {"cards": 0, "chunks_embedded": 0, "chunks_reused": 0, "chunks_unchanged": 0, "inserted": 0,
                 "updated": 0, "retired": 0, "failed": 0}
        model = self.embedder.model
        for card in cards:
            try:
                await self._index_one(tenant, card, model, force, stats)
                stats["cards"] += 1
            except (EmbeddingUnavailable, EmbeddingModelMissing) as exc:
                raise EmbeddingBlocked(str(exc)) from exc
            except Exception as exc:  # noqa: BLE001 - one bad card must not stop the run
                stats["failed"] += 1
                logger.warning("card %s:%s failed: %s", card.source_type, card.source_id, exc)
                await self.store.record_failure(tenant, card.source_type, card.source_id, f"{type(exc).__name__}: {exc}")
        return stats

    async def _index_one(self, tenant: str, card: Card, model: str, force: bool, stats: dict) -> None:
        chunks = card_to_chunks(tenant, card, model, self.s.chunk_chars, self.s.chunk_overlap)
        state = await self.store.source_state(tenant, card.source_type, card.source_id)
        todo = [c for c in chunks if force or state.get(c.chunk_no) != (c.content_hash, model)]
        stats["chunks_unchanged"] += len(chunks) - len(todo)
        if not todo and card.valid_to is not None:        # unchanged but short-lived (personal cards): keep it alive
            await self.store.refresh_valid_to(tenant, card.source_type, card.source_id, card.valid_to)
        if todo:
            hashes = sorted({c.content_hash for c in todo})
            known = await self.store.cached_embeddings(tenant, hashes, model)
            missing = [h for h in hashes if h not in known]
            if missing:
                by_hash = {c.content_hash: c for c in todo}
                async with self._sem:
                    vecs = await self.embedder.embed_documents([by_hash[h].markdown for h in missing])
                known.update(dict(zip(missing, vecs)))
                stats["chunks_embedded"] += len(missing)
            stats["chunks_reused"] += len(todo) - len(missing)
            for c in todo:
                c.embedding = known[c.content_hash]
            res = await self.store.upsert_chunks(tenant, todo)
            stats["inserted"] += res["inserted"]
            stats["updated"] += res["updated"]
        stats["retired"] += await self.store.retire_chunks(tenant, card.source_type, card.source_id, [c.chunk_no for c in chunks])
        if todo or force:
            await self.store.replace_edges(tenant, f"{card.source_type}:{card.source_id}", card.edges)

    # ── a source for a tenant ──
    async def run_source(self, tenant: str, name: str, *, full: bool = False, force: bool = False,
                         max_pages: Optional[int] = None) -> dict:
        src = self.sources[name]
        lock = f"knowledge:{tenant}:{name}"
        if not await self.store.try_lock(lock):
            return {"source": name, "skipped": "another indexer holds the lock"}
        report: dict[str, Any] = {"source": name, "pages": 0, "cards": 0, "tombstoned": 0, "failed": 0, "full": full}
        try:
            wm = None if full else await self.store.get_watermark(tenant, name)
            if wm is not None:
                wm = {"last_ts": wm.get("last_ts"), "meta": wm.get("meta") or {}}
            while True:
                async with self._session() as sess:
                    page: Page = await src.fetch(sess, tenant, wm, self.s.index_batch_size)
                stats = await self.index_cards(tenant, page.cards, force=force)
                for stype, sid in page.tombstones:
                    report["tombstoned"] += await self.store.tombstone_source(tenant, stype, sid)
                    await self.store.delete_edges_by_origin(tenant, f"{stype}:{sid}")
                report["pages"] += 1
                report["cards"] += stats["cards"]
                report["failed"] += stats["failed"]
                for k in ("chunks_embedded", "chunks_reused", "chunks_unchanged", "inserted", "updated"):
                    report[k] = report.get(k, 0) + stats[k]
                if page.last_ts is not None:
                    wm = {"last_ts": page.last_ts, "meta": {"last_id": page.last_id}}
                    await self.store.set_watermark(tenant, name, page.last_ts, meta={"last_id": page.last_id})
                if src.snapshot or page.rows < self.s.index_batch_size or (max_pages and report["pages"] >= max_pages):
                    break
                await self._sleep(self.s.index_sleep_s)
            if full:
                report["tombstoned"] += await self.reconcile(tenant, src)
                await self.store.set_watermark(tenant, name, None, full=True)
            if report["failed"] == 0:
                await self.store.clear_failures(tenant, src.source_types[0])
            return report
        finally:
            await self.store.unlock(lock)

    async def reconcile(self, tenant: str, src: Source) -> int:
        """Tombstone indexed rows whose source row no longer exists (delete propagation)."""
        async with self._session() as sess:
            present = await src.ids(sess, tenant)
        n = 0
        for stype, ids in present.items():
            for sid in sorted(await self.store.live_source_ids(tenant, stype) - ids):
                n += await self.store.tombstone_source(tenant, stype, sid)
                await self.store.delete_edges_by_origin(tenant, f"{stype}:{sid}")
        return n

    async def run_tenant(self, tenant: str, *, modules: Optional[list[str]] = None, names: Optional[list[str]] = None,
                         full: bool = False, force: bool = False) -> list[dict]:
        out = []
        for name in self.enabled_names():
            src = self.sources[name]
            if modules and src.module not in modules:
                continue
            if names and name not in names:
                continue
            try:
                out.append(await self.run_source(tenant, name, full=full, force=force))
            except EmbeddingBlocked as exc:
                out.append({"source": name, "blocked": str(exc)})
                break                                  # no point trying the other sources
            except Exception as exc:  # noqa: BLE001
                logger.exception("source %s failed for tenant %s", name, tenant)
                await self.store.record_failure(tenant, name, "-", f"{type(exc).__name__}: {exc}")
                out.append({"source": name, "error": str(exc)[:200]})
            await self._sleep(self.s.index_sleep_s)
        return out

    def needs_full(self, wm: Optional[dict], now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        last = (wm or {}).get("last_full_at")
        return last is None or (now - last).total_seconds() >= self.s.reconcile_hours * 3600
