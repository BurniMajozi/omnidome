import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from services.tenant_memory.knowledge import consolidation as C
from services.tenant_memory.knowledge import tiers
from services.tenant_memory.knowledge.cards import builders as B
from services.tenant_memory.knowledge.cards.sources import Page, Source
from services.tenant_memory.knowledge.config import get_settings
from services.tenant_memory.knowledge.embeddings import EmbeddingUnavailable, HashEmbedder
from services.tenant_memory.knowledge.indexer import Indexer
from services.tenant_memory.knowledge.kdata import AccessScope, Filters
from services.tenant_memory.knowledge.metrics import MetricFactIn, dimensions_hash, query_key
from services.tenant_memory.knowledge.store_memory import MemoryStore
from services.tenant_memory.knowledge.store_pg import TRAVERSE_SQL, access_clause, filter_clause, migration_statements

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
T = "11111111-1111-1111-1111-111111111111"


def run(c):
    return asyncio.run(c)


class FakeDB:
    """Stands in for the operational DB: tickets keyed by id, with a change timestamp."""
    def __init__(self):
        self.tickets = {}

    def put(self, tid, subject, ts):
        self.tickets[tid] = {"id": tid, "customer_id": "c1", "subject": subject, "description": "", "priority": "NORMAL", "status": "OPEN",
                             "category": "net", "created_at": ts, "ts": ts}

    async def fetch(self, session, tenant, wm, limit):
        last = (wm or {}).get("last_ts")
        rows = sorted((r for r in self.tickets.values() if last is None or r["ts"] > last), key=lambda r: (r["ts"], r["id"]))[:limit]
        p = Page(rows=len(rows))
        if rows:
            p.last_ts, p.last_id = rows[-1]["ts"], rows[-1]["id"]
        p.cards = [B.ticket_card(r, [], r["ts"]) for r in rows]
        return p

    async def ids(self, session, tenant):
        return {"ticket": set(self.tickets)}


def make(db, monkeypatch, store=None, embedder=None, batch=2):
    monkeypatch.setenv("INDEX_BATCH_SIZE", str(batch))
    monkeypatch.setenv("INDEX_SLEEP_S", "0")
    store = store or MemoryStore(now=lambda: NOW)
    emb = embedder or HashEmbedder(32)

    @asynccontextmanager
    async def sess():
        yield None

    async def nosleep(_):
        return None

    src = {"tickets": Source("tickets", "support", ("ticket",), db.fetch, db.ids)}
    return Indexer(store, emb, sess, get_settings(), src, nosleep), store, emb


def test_incremental_indexing_is_idempotent_and_skips_unchanged(monkeypatch):
    db = FakeDB()
    for i in range(5):
        db.put(f"t{i}", f"No sync {i}", NOW + timedelta(minutes=i))
    ix, store, emb = make(db, monkeypatch)
    r1 = run(ix.run_source(T, "tickets"))
    assert r1["cards"] == 5 and r1["pages"] == 3 and r1["chunks_embedded"] == 5
    assert (run(store.get_watermark(T, "tickets")))["last_ts"] == NOW + timedelta(minutes=4)
    calls = len(emb.calls)
    r2 = run(ix.run_source(T, "tickets"))                       # nothing new
    assert r2["cards"] == 0 and len(emb.calls) == calls
    r3 = run(ix.run_source(T, "tickets", full=True))            # full rebuild: same text => no embedding, no rewrite
    assert r3["chunks_embedded"] == 0 and r3["chunks_unchanged"] == 5 and len(emb.calls) == calls


def test_changed_row_is_reembedded_and_new_rows_picked_up(monkeypatch):
    db = FakeDB()
    db.put("t1", "No sync", NOW)
    ix, store, emb = make(db, monkeypatch)
    run(ix.run_source(T, "tickets"))
    db.put("t1", "Router replaced", NOW + timedelta(hours=1))
    db.put("t2", "Billing question", NOW + timedelta(hours=2))
    r = run(ix.run_source(T, "tickets"))
    assert r["cards"] == 2 and r["chunks_embedded"] == 2
    hits = run(store.text_search(T, "router replaced", Filters(), AccessScope(T, "u", frozenset(), frozenset(), True), 5))
    assert [c.source_id for c, _ in hits] == ["t1"]


def test_identical_text_across_sources_reuses_embedding(monkeypatch):
    db = FakeDB()
    db.put("a", "Same", NOW)
    ix, store, emb = make(db, monkeypatch, batch=10)
    run(ix.run_source(T, "tickets"))
    c = run(store.cached_embeddings(T, [ch.content_hash for ch in store.rows.values()], emb.model))
    assert len(c) == 1


def test_tombstone_propagation_on_full_reconcile(monkeypatch):
    db = FakeDB()
    db.put("t1", "keep", NOW)
    db.put("t2", "gone", NOW)
    ix, store, _ = make(db, monkeypatch)
    run(ix.run_source(T, "tickets"))
    del db.tickets["t2"]
    rep = run(ix.run_source(T, "tickets", full=True))
    assert rep["tombstoned"] == 1
    assert run(store.live_source_ids(T, "ticket")) == {"t1"}
    assert store.rows[(T, "ticket", "t2", 0)].deleted_at is not None
    # a revived source row un-tombstones
    db.put("t2", "back", NOW + timedelta(days=1))
    run(ix.run_source(T, "tickets"))
    assert run(store.live_source_ids(T, "ticket")) == {"t1", "t2"}


def test_one_bad_card_does_not_stop_the_run_and_is_recorded(monkeypatch):
    db = FakeDB()
    db.put("t1", "ok", NOW)
    db.put("t2", "boom", NOW + timedelta(minutes=1))
    ix, store, _ = make(db, monkeypatch, batch=10)
    orig = store.upsert_chunks

    async def flaky(tenant, chunks):
        if chunks and chunks[0].source_id == "t2":
            raise RuntimeError("disk full")
        return await orig(tenant, chunks)

    store.upsert_chunks = flaky
    r = run(ix.run_source(T, "tickets"))
    assert r["cards"] == 1 and r["failed"] == 1 and store.failures[0]["source_ref"] == "t2"
    assert run(store.coverage(T))["failures"]


def test_embedding_outage_stops_cleanly_and_keeps_watermark(monkeypatch):
    class Down(HashEmbedder):
        async def embed_documents(self, texts):
            raise EmbeddingUnavailable("ollama down")

    db = FakeDB()
    db.put("t1", "x", NOW)
    ix, store, _ = make(db, monkeypatch, embedder=Down(32))
    out = run(ix.run_tenant(T))
    assert out[0].get("blocked") and run(store.get_watermark(T, "tickets")) is None
    assert not store.locks                                       # lock released


def test_lock_prevents_double_indexing(monkeypatch):
    db = FakeDB()
    db.put("t1", "x", NOW)
    ix, store, _ = make(db, monkeypatch)
    run(store.try_lock(f"knowledge:{T}:tickets"))
    assert "skipped" in run(ix.run_source(T, "tickets"))


def test_force_rewrites_visibility_without_reembedding(monkeypatch):
    db = FakeDB()
    db.put("t1", "x", NOW)
    ix, store, emb = make(db, monkeypatch)
    run(ix.run_source(T, "tickets"))
    store.rows[(T, "ticket", "t1", 0)].visibility = "tenant"
    n = len(emb.calls)
    r = run(ix.run_source(T, "tickets", full=True, force=True))
    assert r["chunks_embedded"] == 0 and len(emb.calls) == n


def test_erasure_is_hard_and_scoped_per_tenant(monkeypatch):
    db = FakeDB()
    db.put("t1", "x", NOW)
    ix, store, _ = make(db, monkeypatch)
    run(ix.run_source(T, "tickets"))
    other = "22222222-2222-2222-2222-222222222222"
    run(ix.run_source(other, "tickets"))
    out = run(C.erase_tenant_knowledge(store, T, source_type="ticket", source_id="t1"))
    assert out["chunks"] == 1 and (T, "ticket", "t1", 0) not in store.rows and (other, "ticket", "t1", 0) in store.rows
    run(C.erase_tenant_knowledge(store, other))
    assert not any(k[0] == other for k in store.rows) and not any(k[0] == other for k in store.watermarks)


# ── tiers + consolidation (pure parts) ─────────────────────────────────────

def test_promotion_rules():
    base = {"kind": "note", "importance": "normal", "repeat_count": 1, "pinned": False}
    assert tiers.promotion_reason(base) is None
    assert tiers.promotion_reason({**base, "pinned": True}) == "pinned"
    assert tiers.promotion_reason({**base, "importance": "high"}) == "importance"
    assert tiers.promotion_reason({**base, "repeat_count": 3}) == "repetition"
    assert tiers.promotion_reason({**base, "kind": "state", "pinned": True}) is None
    assert tiers.promotion_reason({**base, "pinned": True, "promoted_entry_id": "x"}) is None
    assert tiers.content_key("Hello   World") == tiers.content_key("hello world")


def test_merge_groups_union_find():
    pairs = [("a", "b", 0.99), ("b", "c", 0.98), ("x", "y", 0.90), ("p", "q", 0.975)]
    assert C.merge_groups(pairs, 0.97) == [["a", "b", "c"], ["p", "q"]]
    assert C.choose_canonical([{"id": "2", "importance": "normal", "occurred_at": "2026-01-01"},
                               {"id": "1", "importance": "high", "occurred_at": "2026-02-01"}])["id"] == "1"


def test_near_duplicate_pairs_from_store():
    from services.tenant_memory.knowledge.kdata import Chunk, content_hash
    s = MemoryStore()
    e = HashEmbedder(32)
    for sid, text in (("m1", "customer prefers email contact"), ("m2", "customer prefers email contact"), ("m3", "router firmware upgrade plan")):
        md = f"# {text}"
        c = Chunk(T, "memory_entry", sid, 0, "memory", text, md, content_hash(md), embedding=run(e.embed_documents([md]))[0], embedding_model="hash-test")
        run(s.upsert_chunks(T, [c]))
    pairs = run(s.near_duplicates(T, "memory_entry", 0.97, 10))
    assert [(a, b) for a, b, _ in pairs] == [("m1", "m2")]


def test_decay_and_rollup_planning_respect_retention():
    assert C.decayed_importance(0.5, 0) == 0.5
    assert C.IMPORTANCE_FLOOR <= C.decayed_importance(0.75, 365) < 0.75
    assert C.decayed_importance(0.75, 10_000) == C.IMPORTANCE_FLOOR
    old = NOW - timedelta(days=C.ROLLUP_DAYS + C.ROLLUP_GRACE_DAYS + 1)
    entries = [{"id": "1", "module": "crm", "scope_key": "customer:1", "occurred_at": old, "importance": "normal"},
               {"id": "2", "module": "crm", "scope_key": "customer:1", "occurred_at": NOW - timedelta(days=5), "importance": "normal"},
               {"id": "3", "module": "crm", "scope_key": "customer:1", "occurred_at": old, "importance": "critical"},
               {"id": "4", "module": "crm", "scope_key": "customer:1", "occurred_at": old, "importance": "normal", "archived_at": NOW}]
    plan = C.plan_rollup(entries, NOW)
    assert [e["id"] for e in plan[("crm", "customer:1")]] == ["1"]
    text = C.deterministic_summary("prior", [{"id": "1", "title": "Deal agreed", "content": "15% off", "occurred_at": old}])
    assert text.startswith("prior") and "Deal agreed" in text


# ── metric facts ───────────────────────────────────────────────────────────

def fact(**kw):
    base = dict(metric_key="revenue", period_start="2026-03-01", period_end="2026-03-31", value=1.0, method="sum", written_by="bi_semantic")
    return MetricFactIn(**{**base, **kw})


def test_metric_fact_write_rules():
    fact()
    fact(kind="forecast", written_by="forecast_run", model_name="ets", model_version="1", lower_bound=0, upper_bound=2, interval_level=0.8)
    for bad in (dict(written_by="llm"), dict(kind="forecast", written_by="forecast_run"),
                dict(kind="actual", written_by="forecast_run", model_name="m", model_version="1"),
                dict(kind="forecast", written_by="bi_semantic", model_name="m", model_version="1"),
                dict(period_end="2026-02-01"), dict(lower_bound=1.0), dict(source_query={"dataset": "billing"}), dict(unknown_field=1)):
        with pytest.raises(ValidationError):
            fact(**bad)
    assert dimensions_hash({"a": 1, "b": 2}) == dimensions_hash({"b": 2, "a": 1})
    assert query_key({"dataset": "billing", "measures": ["revenue"]}) == query_key({"measures": ["revenue"], "dataset": "billing"})


def test_metric_facts_table_forbids_non_deterministic_writers():
    from services.tenant_memory.database import CREATE_TABLES_SQL
    assert "CHECK (written_by IN ('bi_semantic', 'forecast_run', 'system'))" in CREATE_TABLES_SQL
    assert ";" not in CREATE_TABLES_SQL.split("tenant_metric_facts (")[1].split("CREATE UNIQUE INDEX")[0].replace("\n);", "")


# ── pgvector SQL shape (cannot run without a server; see test_pg_integration) ──

def test_pg_sql_always_filters_tenant_and_roles():
    adm = AccessScope(T, "u", frozenset(), frozenset(), True)
    usr = AccessScope(T, "u", frozenset({"finance"}), frozenset({"x.y"}), False)
    sql_a, p_a = access_clause(adm)
    sql_u, p_u = access_clause(usr)
    for sql, p in ((sql_a, p_a), (sql_u, p_u)):
        assert "tenant_id = CAST(:tenant_id AS uuid)" in sql and "deleted_at IS NULL" in sql and p["tenant_id"] == T
    assert "required_roles" not in sql_a and "required_roles" in sql_u and p_u["roles"] == ["finance"]
    fl, fp = filter_clause(Filters(modules=["crm"], tags=["vip"]))
    assert "c.module = ANY" in fl and fp["f_tags"] == ["vip"] and "valid_to" in fl
    ddl = "\n".join(migration_statements(get_settings()))
    for needle in ("USING hnsw", "vector_cosine_ops", "USING gin (tsv)", "FORCE ROW LEVEL SECURITY", "app.tenant_id",
                   "UNIQUE (tenant_id, source_type, source_id, chunk_no)", "vector(768)"):
        assert needle in ddl
    assert "depth < :depth" in TRAVERSE_SQL and "= ANY(w.path)" in TRAVERSE_SQL
