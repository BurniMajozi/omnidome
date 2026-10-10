"""Knowledge worker: ONE process (compose service `knowledge_indexer`, same image as tenant_memory).

    python -m services.tenant_memory.knowledge.worker

Loop: apply schema -> claim admin-triggered jobs -> periodic incremental sweep of every active tenant ->
daily full reconcile per source -> daily consolidation. Gentle by design: small batches, sleeps, concurrency 1-2.
Run a single replica; an advisory lock also stops a second one from sweeping at the same time.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

from services.common.db import run_with_db_retry, session_scope
from services.tenant_memory.knowledge import consolidation
from services.tenant_memory.knowledge.config import get_settings
from services.tenant_memory.knowledge.embeddings import OllamaEmbedder
from services.tenant_memory.knowledge.indexer import EmbeddingBlocked, Indexer
from services.tenant_memory.knowledge.store import KnowledgeStore
from services.tenant_memory.knowledge.store_pg import PgVectorStore

logger = logging.getLogger("knowledge.worker")
CONSOLIDATION_EVERY = timedelta(hours=int(os.getenv("CONSOLIDATION_EVERY_HOURS", "24")))


async def active_tenants() -> list[str]:
    allow = {t.strip() for t in os.getenv("KNOWLEDGE_TENANTS", "").split(",") if t.strip()}
    async with session_scope() as s:
        rows = (await s.execute(text("SELECT id::text FROM tenants WHERE COALESCE(active, true) = true ORDER BY id::text"))).all()
    ids = [r[0] for r in rows]
    return [i for i in ids if not allow or i in allow]


async def process_job(indexer: Indexer, store: KnowledgeStore, job: dict) -> dict:
    tenant, params = job["tenant_id"], job.get("params") or {}
    if job["kind"] == "reindex":
        return {"sources": await indexer.run_tenant(tenant, modules=params.get("modules"), names=params.get("sources"),
                                                    full=bool(params.get("full")), force=bool(params.get("force")))}
    if job["kind"] == "consolidate":
        async with session_scope() as s:
            return await consolidation.consolidate_tenant(s, store, tenant, dry_run=bool(params.get("dry_run", True)))
    if job["kind"] == "dream":
        from services.tenant_memory.knowledge.dream import runner as dream_runner
        return await dream_runner.run_dream_job(store, indexer.embedder, job)
    raise ValueError(f"unknown job kind {job['kind']}")


async def sweep(indexer: Indexer, store: KnowledgeStore, tenants: list[str]) -> None:
    now = datetime.now(timezone.utc)
    for tenant in tenants:
        for name in indexer.enabled_names():
            wm = await store.get_watermark(tenant, name)
            full = indexer.needs_full(wm, now)
            try:
                res = await indexer.run_source(tenant, name, full=full)
            except EmbeddingBlocked:
                return                                   # embedding service is down: stop the whole sweep, retry later
            except Exception as exc:  # noqa: BLE001 - one broken source must not starve the others
                logger.exception("source %s failed for tenant %s", name, tenant)
                await store.record_failure(tenant, name, "-", f"{type(exc).__name__}: {exc}")
                continue
            if res.get("blocked"):
                return
        cwm = await store.get_watermark(tenant, "consolidation")
        last = (cwm or {}).get("last_full_at")
        if last is None or now - last >= CONSOLIDATION_EVERY:
            async with session_scope() as s:
                await consolidation.consolidate_tenant(s, store, tenant)
            await store.set_watermark(tenant, "consolidation", None, full=True)


async def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    s = get_settings()
    store = PgVectorStore()
    await run_with_db_retry(store.ensure_schema, logger=logger)
    embedder = OllamaEmbedder()
    from services.tenant_memory.knowledge.dream import runner as dream_runner
    try:
        await dream_runner.ensure_schema(store, embedder)
    except Exception:  # noqa: BLE001 - the dream tables are optional: never keep the indexer from starting
        logger.exception("dream schema setup failed; the nightly dream state stays idle until it succeeds")
    last_dream = None
    indexer = Indexer(store, embedder)
    logger.info("knowledge worker up: model=%s dim=%s batch=%s sleep=%ss", s.embedding_model, s.embedding_dim, s.index_batch_size, s.index_sleep_s)
    last_sweep = datetime.min.replace(tzinfo=timezone.utc)
    while True:
        try:
            health = await embedder.health()
            if not health.get("ok"):
                logger.warning("embedding not ready (%s); waiting. Fix: %s", health.get("error") or health.get("hint"), health.get("hint"))
                await asyncio.sleep(60)
                continue
            job = await store.claim_job()
            if job:
                try:
                    await store.finish_job(job["id"], "done", await process_job(indexer, store, job))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("job %s failed", job["id"])
                    await store.finish_job(job["id"], "failed", {"error": str(exc)[:300]})
                continue
            last_dream = await dream_runner.tick(store, embedder, active_tenants, last_dream)
            if datetime.now(timezone.utc) - last_sweep >= timedelta(seconds=s.poll_seconds * 4) and await store.try_lock("knowledge:sweep"):
                try:
                    await sweep(indexer, store, await active_tenants())
                finally:
                    await store.unlock("knowledge:sweep")
                last_sweep = datetime.now(timezone.utc)
        except Exception:  # noqa: BLE001
            logger.exception("worker loop error")
        await asyncio.sleep(s.poll_seconds)


if __name__ == "__main__":
    asyncio.run(main())
