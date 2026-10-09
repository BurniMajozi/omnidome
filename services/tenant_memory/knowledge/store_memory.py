"""In-memory KnowledgeStore for unit tests: pure python, same semantics as the pgvector store."""
from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from services.tenant_memory.knowledge.embeddings import cosine
from services.tenant_memory.knowledge.store import KnowledgeStore, SearchResult
from services.tenant_memory.knowledge.kdata import AccessScope, Chunk, Edge, Filters

_WORD = re.compile(r"[a-z0-9]+")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


class MemoryStore(KnowledgeStore):
    def __init__(self, now=_now):
        self.rows: dict[tuple, Chunk] = {}
        self.edges: dict[str, list[Edge]] = {}           # (tenant|origin) -> edges
        self.watermarks: dict[tuple, dict] = {}
        self.failures: list[dict] = []
        self.jobs: list[dict] = []
        self.locks: set[str] = set()
        self.now = now

    async def ensure_schema(self) -> None:
        return None

    async def ping(self) -> bool:
        return True

    # ── chunks ──
    def _live(self, tenant: str):
        return [c for c in self.rows.values() if c.tenant_id == tenant and c.deleted_at is None]

    async def source_state(self, tenant, source_type, source_id):
        return {c.chunk_no: (c.content_hash, c.embedding_model) for c in self._live(tenant)
                if c.source_type == source_type and c.source_id == source_id}

    async def cached_embeddings(self, tenant, hashes, model):
        want = set(hashes)
        return {c.content_hash: list(c.embedding) for c in self.rows.values()
                if c.tenant_id == tenant and c.content_hash in want and c.embedding is not None
                and c.embedding_model == model}

    async def upsert_chunks(self, tenant, chunks):
        out = {"inserted": 0, "updated": 0, "unchanged": 0}
        for c in chunks:
            if str(c.tenant_id) != tenant:
                raise ValueError("chunk tenant mismatch")
            key = c.key
            old = self.rows.get(key)
            if old is not None and old.deleted_at is None and old.content_hash == c.content_hash \
                    and old.embedding_model == c.embedding_model and old.embedding is not None:
                out["unchanged"] += 1
                continue
            new = copy.deepcopy(c)
            new.id = old.id if old else str(uuid.uuid4())
            new.updated_at, new.deleted_at = self.now(), None
            self.rows[key] = new
            out["updated" if old else "inserted"] += 1
        return out

    async def retire_chunks(self, tenant, source_type, source_id, keep_chunk_nos):
        n = 0
        for c in self._live(tenant):
            if c.source_type == source_type and c.source_id == source_id and c.chunk_no not in keep_chunk_nos:
                c.deleted_at = self.now()
                n += 1
        return n

    async def tombstone_source(self, tenant, source_type, source_id):
        return await self.retire_chunks(tenant, source_type, source_id, [])

    async def live_source_ids(self, tenant, source_type):
        return {c.source_id for c in self._live(tenant) if c.source_type == source_type}

    def _eligible(self, tenant: str, flt: Filters, access: AccessScope) -> list[Chunk]:
        now = self.now()
        out = []
        for c in self._live(tenant):
            if not access.allows(c):
                continue
            if flt.modules and c.module not in flt.modules:
                continue
            if flt.source_types and c.source_type not in flt.source_types:
                continue
            if flt.tags and not set(flt.tags) & set(c.tags):
                continue
            if flt.since and (c.as_of is None or c.as_of < flt.since):
                continue
            if flt.until and (c.as_of is None or c.as_of > flt.until):
                continue
            if flt.min_importance is not None and c.importance < flt.min_importance:
                continue
            if not flt.include_expired and c.valid_to is not None and c.valid_to <= now:
                continue
            out.append(c)
        return out

    async def vector_search(self, tenant, vec, flt, access, limit):
        scored = [(c, cosine(vec, c.embedding)) for c in self._eligible(tenant, flt, access) if c.embedding]
        scored.sort(key=lambda t: (-t[1], t[0].source_id, t[0].chunk_no))
        return [(copy.deepcopy(c), s) for c, s in scored[:limit]]

    async def text_search(self, tenant, query, flt, access, limit):
        q = set(_words(query))
        scored: SearchResult = []
        for c in self._eligible(tenant, flt, access):
            counts = _words(c.title + " " + c.markdown)
            hit = sum(counts.count(w) for w in q)
            if hit:
                scored.append((c, float(hit) / (1 + len(counts) ** 0.5)))
        scored.sort(key=lambda t: (-t[1], t[0].source_id, t[0].chunk_no))
        return [(copy.deepcopy(c), s) for c, s in scored[:limit]]

    async def chunks_for_sources(self, tenant, nodes, flt, access, per_source=1):
        want = {tuple(n) for n in nodes}
        seen: dict[tuple, int] = {}
        out = []
        for c in sorted(self._eligible(tenant, flt, access), key=lambda c: (c.source_id, c.chunk_no)):
            k = (c.source_type, c.source_id)
            if k in want and seen.get(k, 0) < per_source:
                seen[k] = seen.get(k, 0) + 1
                out.append(copy.deepcopy(c))
        return out

    async def near_duplicates(self, tenant, source_type, threshold, limit):
        live = [c for c in self._live(tenant) if c.source_type == source_type and c.embedding]
        pairs = []
        for i, a in enumerate(live):
            for b in live[i + 1:]:
                s = cosine(a.embedding, b.embedding)
                if s >= threshold:
                    pairs.append((a.source_id, b.source_id, s))
        pairs.sort(key=lambda t: -t[2])
        return pairs[:limit]

    # ── graph ──
    async def replace_edges(self, tenant, origin_key, edges):
        self.edges[f"{tenant}|{origin_key}"] = [copy.deepcopy(e) for e in edges]

    async def delete_edges_by_origin(self, tenant, origin_key):
        self.edges.pop(f"{tenant}|{origin_key}", None)

    async def traverse(self, tenant, start, depth, relations, limit):
        all_edges = [e for k, es in self.edges.items() if k.startswith(f"{tenant}|") for e in es]
        seeds = {tuple(s) for s in start}
        seen = set(seeds)
        frontier = list(seeds)
        out: list[dict] = []
        for d in range(1, depth + 1):
            nxt = []
            for node in frontier:
                for e in all_edges:
                    if relations and e.relation not in relations:
                        continue
                    a, b = (e.src_type, e.src_id), (e.dst_type, e.dst_id)
                    other = b if a == node else a if b == node else None
                    if other is None or other in seen:
                        continue
                    seen.add(other)
                    nxt.append(other)
                    out.append({"node_type": other[0], "node_id": other[1], "depth": d, "relation": e.relation})
            frontier = nxt
        return out[:limit]

    # ── bookkeeping ──
    async def get_watermark(self, tenant, source):
        return self.watermarks.get((tenant, source))

    async def set_watermark(self, tenant, source, last_ts, *, full=False, meta=None):
        w = self.watermarks.setdefault((tenant, source), {"last_ts": None, "last_full_at": None, "meta": {}})
        if last_ts is not None:
            w["last_ts"] = last_ts
        if full:
            w["last_full_at"] = self.now()
        w["updated_at"] = self.now()
        if meta:
            w["meta"].update(meta)

    async def record_failure(self, tenant, source, source_ref, error):
        self.failures.append({"tenant": tenant, "source": source, "source_ref": source_ref, "error": error[:300]})

    async def clear_failures(self, tenant, source):
        self.failures = [f for f in self.failures if not (f["tenant"] == tenant and f["source"] == source)]

    async def coverage(self, tenant):
        by: dict[tuple, dict] = {}
        for c in self.rows.values():
            if c.tenant_id != tenant:
                continue
            d = by.setdefault((c.source_type, c.module), {"source_type": c.source_type, "module": c.module,
                                                          "chunks": 0, "tombstoned": 0, "last_indexed": None})
            d["tombstoned" if c.deleted_at else "chunks"] += 1
            if c.updated_at and (d["last_indexed"] is None or c.updated_at > d["last_indexed"]):
                d["last_indexed"] = c.updated_at
        return {"sources": sorted(by.values(), key=lambda d: d["source_type"]),
                "watermarks": [{"source": s, **w} for (t, s), w in self.watermarks.items() if t == tenant],
                "failures": [f for f in self.failures if f["tenant"] == tenant][-50:],
                "queue": {"queued": sum(1 for j in self.jobs if j["tenant_id"] == tenant and j["status"] == "queued"),
                          "running": sum(1 for j in self.jobs if j["tenant_id"] == tenant and j["status"] == "running")}}

    async def enqueue_job(self, tenant, kind, params, requested_by=None):
        jid = str(uuid.uuid4())
        self.jobs.append({"id": jid, "tenant_id": tenant, "kind": kind, "params": params, "status": "queued",
                          "requested_by": requested_by, "result": None})
        return jid

    async def claim_job(self):
        for j in self.jobs:
            if j["status"] == "queued":
                j["status"] = "running"
                return dict(j)
        return None

    async def finish_job(self, job_id, status, result):
        for j in self.jobs:
            if j["id"] == job_id:
                j["status"], j["result"] = status, result

    async def try_lock(self, name):
        if name in self.locks:
            return False
        self.locks.add(name)
        return True

    async def unlock(self, name):
        self.locks.discard(name)

    async def erase(self, tenant, *, source_type=None, source_id=None, module=None):
        doomed = [k for k, c in self.rows.items() if c.tenant_id == tenant
                  and (source_type is None or c.source_type == source_type)
                  and (source_id is None or c.source_id == source_id)
                  and (module is None or c.module == module)]
        for k in doomed:
            del self.rows[k]
        edges_removed = 0
        if source_type is None and source_id is None and module is None:
            for k in [k for k in self.edges if k.startswith(f"{tenant}|")]:
                edges_removed += len(self.edges.pop(k))
            for k in [k for k in self.watermarks if k[0] == tenant]:
                del self.watermarks[k]
            self.failures = [f for f in self.failures if f["tenant"] != tenant]
        elif source_type and source_id:
            edges_removed = len(self.edges.pop(f"{tenant}|{source_type}:{source_id}", []))
        return {"chunks": len(doomed), "edges": edges_removed}

    async def purge_tombstones(self, tenant, older_than):
        doomed = [k for k, c in self.rows.items() if c.tenant_id == tenant and c.deleted_at and c.deleted_at < older_than]
        for k in doomed:
            del self.rows[k]
        return len(doomed)

    async def set_importance(self, tenant, source_type, source_id, importance):
        n = 0
        for c in self._live(tenant):
            if c.source_type == source_type and c.source_id == source_id:
                c.importance, n = importance, n + 1
        return n
