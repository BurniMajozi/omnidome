"""Shared fakes for the dream-state tests: in-memory store, hash embedder, scripted renderer / ops / metrics / JEV. No network."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from services.tenant_memory.knowledge.cards.base import Card, frontmatter
from services.tenant_memory.knowledge.config import get_settings
from services.tenant_memory.knowledge.dream.engine import DreamEngine
from services.tenant_memory.knowledge.dream.ports import DreamDeps, JevAnswer, Rendered, Telemetry
from services.tenant_memory.knowledge.dream.settings import DreamSettings
from services.tenant_memory.knowledge.dream.store import MemoryDreamStore
from services.tenant_memory.knowledge.embeddings import HashEmbedder
from services.tenant_memory.knowledge.indexer import Indexer
from services.tenant_memory.knowledge.kdata import Edge
from services.tenant_memory.knowledge.store_memory import MemoryStore

T1 = "11111111-1111-1111-1111-111111111111"
T2 = "22222222-2222-2222-2222-222222222222"
NOW = datetime(2026, 10, 10, 0, 30, tzinfo=timezone.utc)      # 02:30 in Africa/Johannesburg


def run(coro):
    return asyncio.run(coro)


class Clock:
    def __init__(self, t: datetime = NOW):
        self.t = t

    def now(self) -> datetime:
        return self.t

    def advance(self, **kw) -> None:
        self.t += timedelta(**kw)


def mk_card(stype: str, sid: str, title: str, body: str, *, as_of: Optional[datetime] = None, module: str = "support",
            importance: float = 0.5, tags: Optional[list] = None, edges: Optional[list] = None, **kw) -> Card:
    as_of = as_of or NOW
    md = frontmatter(stype, sid, module, as_of, tags or []) + f"# {title}\n{body}\n"
    return Card(stype, sid, module, title, md, as_of, list(tags or []), importance, edges=edges or [], **kw)


class FakeRenderer:
    """script: {(source_type, source_id): Card | 'gone' | 'unverifiable' | 'source_missing'}; unknown keys are 'unverifiable'."""

    def __init__(self):
        self.script: dict = {}
        self.calls: list = []

    def reset(self) -> None:
        pass

    async def render(self, tenant, source_type, source_id) -> Rendered:
        self.calls.append((tenant, source_type, source_id))
        v = self.script.get((source_type, source_id), "unverifiable")
        if isinstance(v, Card):
            return Rendered("ok", v)
        return Rendered(v, note="scripted")


class FakeOps:
    def __init__(self):
        self.facts: list[dict] = []
        self.written: list = []
        self.notes: list = []
        self.telemetry = Telemetry(False, note="no retrieval_log")

    async def metric_facts(self, tenant, since):
        return [dict(f) for f in self.facts if f["tenant_id"] == tenant and f["period_end"] >= since]

    async def write_fact(self, tenant, fact):
        self.written.append((tenant, fact))
        return {"id": str(uuid.uuid4()), "inserted": True}

    async def retrieval_telemetry(self, tenant, since):
        return self.telemetry

    async def notify(self, tenant, title, body, severity, link):
        self.notes.append((tenant, title, severity))


class FakeMetrics:
    def __init__(self, ops: FakeOps):
        self.ops, self.calls, self.mutate = ops, 0, None

    def configured(self) -> bool:
        return True

    async def refresh(self, tenant, periods):
        self.calls += 1
        if self.mutate:
            self.mutate(self.ops)
        return {"ok": True}


class FakeJev:
    def __init__(self, script: Optional[dict] = None, cost: float = 0.01):
        self.script, self.cost, self.calls = script or {}, cost, []

    def configured(self) -> bool:
        return True

    async def ask(self, state, questions) -> JevAnswer:
        self.calls.append((state, questions))
        return JevAnswer({k: float(self.script.get(k, 0.5)) for k in questions}, self.cost, "fake-jev")


def fact(tenant, key, ps, pe, value, *, kind="actual", written_by="bi_semantic", model_name=None, model_version="", lo=None, hi=None,
         method="semantic_query", fid=None, level=None, dh="d0"):
    return {"id": fid or str(uuid.uuid4()), "tenant_id": tenant, "metric_key": key, "dimensions": {}, "dimensions_hash": dh, "period_start": ps,
            "period_end": pe, "grain": "month", "value": float(value), "unit": "count", "kind": kind, "lower_bound": lo, "upper_bound": hi,
            "interval_level": level, "model_name": model_name, "model_version": model_version, "method": method, "confidence": None,
            "as_of": NOW, "written_by": written_by}


@dataclass
class Env:
    store: MemoryStore
    dstore: MemoryDreamStore
    emb: HashEmbedder
    renderer: FakeRenderer
    ops: FakeOps
    metrics: FakeMetrics
    jev: FakeJev
    deps: DreamDeps
    engine: DreamEngine
    clock: Clock
    consolidated: list = field(default_factory=list)
    killed: list = field(default_factory=lambda: [False])
    sleeps: list = field(default_factory=list)

    def index(self, tenant, *cards, force=False):
        return run(self.deps.indexer.index_cards(tenant, list(cards), force=force))

    def night(self, tenant=T1, *, dry_run=False, phases=None, **kw):
        return run(self.engine.run_tenant(tenant, dry_run=dry_run, phases=phases, trigger=kw.pop("trigger", "manual"), resume=kw.pop("resume", False), **kw))

    def chunks(self, tenant, stype=None):
        return [c for c in self.store.rows.values() if c.tenant_id == tenant and (stype is None or c.source_type == stype)]

    def live(self, tenant, stype, sid):
        return [c for c in self.store.rows.values() if (c.tenant_id, c.source_type, c.source_id) == (tenant, stype, sid) and c.deleted_at is None]

    def findings(self, tenant=T1, **kw):
        return run(self.dstore.list_findings(tenant, **kw))


def make_env(**overrides) -> Env:
    clock = Clock()
    store = MemoryStore(now=clock.now)
    emb = HashEmbedder(32)
    ops = FakeOps()
    renderer = FakeRenderer()
    metrics = FakeMetrics(ops)
    jev = FakeJev()
    dstore = MemoryDreamStore(store)
    consolidated: list = []

    async def consolidate(tenant, dry_run):
        consolidated.append((tenant, dry_run))
        return {"promotion": {"promoted": [1, 2], "expired_deleted": 3}, "merge": {"groups": 1, "archived": 1},
                "rollup": {"groups": 2, "entries": 5}, "decay": {"archived_low_importance": 4, "chunks_decayed": 6}, "purged_tombstones": 7}

    killed = [False]
    sleeps: list = []

    async def sleep(s):
        sleeps.append(s)

    base = DreamSettings(enabled=True, sleep_s=0.0, batch_size=10, rotation_days=1, max_cards_per_night=500, canary_n=5, jev_enabled=False,
                         reembed_per_night=50, embed_scan_per_night=500, min_samples=3, decay_after_days=30, telemetry_days=30)
    base = replace(base, **overrides)
    deps = DreamDeps(store=dstore, embedder=emb, ops=ops, renderer=renderer, indexer=Indexer(store, emb, settings=get_settings(), sleep=sleep),
                     consolidate=consolidate, jev=jev, metrics=metrics, base_settings=base, now=clock.now, sleep=sleep, kill=lambda: killed[0])
    return Env(store, dstore, emb, renderer, ops, metrics, jev, deps, DreamEngine(deps), clock, consolidated, killed, sleeps)


def edge(src_type, src_id, dst_type, dst_id, rel="about"):
    return Edge(src_type, src_id, dst_type, dst_id, rel)
