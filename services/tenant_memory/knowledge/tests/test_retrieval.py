import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from services.tenant_memory.knowledge.embeddings import EmbeddingUnavailable, HashEmbedder
from services.tenant_memory.knowledge.kdata import AccessScope, Chunk, Edge, Filters, Hit, content_hash
from services.tenant_memory.knowledge.retrieval import (
    KnowledgeRetriever, SearchResult, boost, citation, mmr, pack_context, rrf_fuse,
)
from services.tenant_memory.knowledge.store_memory import MemoryStore

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
T1, T2 = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
EMB = HashEmbedder(64)


def run(coro):
    return asyncio.run(coro)


def chunk(tenant=T1, sid="a", text="fibre outage soweto", st="ticket", module="support", **kw):
    md = f"---\nsource: {st}\n---\n# {text}\n{text}\n"
    c = Chunk(tenant, st, sid, kw.pop("chunk_no", 0), module, kw.pop("title", text), md, content_hash(md), as_of=kw.pop("as_of", NOW),
              embedding_model="hash-test", **kw)
    c.embedding = run(EMB.embed_documents([md]))[0]
    return c


def store_with(*chunks):
    s = MemoryStore(now=lambda: NOW)
    for c in chunks:
        run(s.upsert_chunks(c.tenant_id, [c]))
    return s


def scope(tenant=T1, roles=(), perms=(), admin=False, user="u1"):
    return AccessScope(tenant, user, frozenset(roles), frozenset(perms), admin)


def search(store, q, access, flt=None, **kw):
    return run(KnowledgeRetriever(store, EMB, now=lambda: NOW).search(q, access, flt, **kw))


def test_rrf_math():
    # a: rank1 in both lists; b: rank2 in first only; c: rank2 in second only
    s = rrf_fuse([["a", "b"], ["a", "c"]], k=60)
    assert s["a"] == pytest.approx(2 / 61) and s["b"] == pytest.approx(1 / 62) and s["c"] == pytest.approx(1 / 62)
    assert rrf_fuse([["a"], ["a"]], k=60, weights=[1, 0.5])["a"] == pytest.approx(1.5 / 61)


def test_boost_prefers_recent_and_important_but_never_zeroes():
    new, old = chunk(as_of=NOW), chunk(as_of=NOW - timedelta(days=720))
    assert boost(1.0, new, NOW) > boost(1.0, old, NOW) > 0
    hi, lo = chunk(importance=1.0), chunk(importance=0.0)
    assert boost(1.0, hi, NOW) > boost(1.0, lo, NOW) > 0


def test_mmr_removes_near_duplicates_in_favour_of_diverse():
    a, a2, b = chunk(sid="a"), chunk(sid="a2", st="ticket"), chunk(sid="b", text="invoice vat overdue", st="invoice_x")
    out = mmr([(a, 1.0), (a2, 0.99), (b, 0.8)], 2, lam=0.5)
    assert [c.source_id for c, _ in out] == ["a", "b"]


def test_hybrid_search_ranks_relevant_first_and_cites():
    s = store_with(chunk(sid="out", text="fibre outage soweto"), chunk(sid="inv", text="invoice vat overdue", st="billing_digest", module="billing"),
                   chunk(sid="mkt", text="winter campaign promo", st="campaign", module="marketing"))
    res = search(s, "outage in soweto", scope(admin=True), k=3)
    assert res.hits[0].chunk.source_id == "out" and res.hits[0].vector_rank == 1
    cit = res.citations(NOW)[0]
    assert cit["source_type"] == "ticket" and cit["as_of"].startswith("2026-10-01") and cit["stale"] is False and "score" in cit


def test_staleness_flagged_for_old_snapshot_cards():
    s = store_with(chunk(sid="c", st="customer", text="customer thandi status", as_of=NOW - timedelta(days=60), module="crm"))
    cit = search(s, "thandi status", scope()).citations(NOW)[0]
    assert cit["stale"] is True and cit["age_days"] == 60


def test_tenant_isolation():
    s = store_with(chunk(tenant=T1, sid="mine", text="secret roadmap alpha"), chunk(tenant=T2, sid="theirs", text="secret roadmap alpha"))
    res = search(s, "secret roadmap alpha", scope(T1, admin=True))
    assert [h.chunk.source_id for h in res.hits] == ["mine"]
    # even a caller scoped to T1 cannot ask the store for T2 data
    assert run(s.text_search(T2, "roadmap", Filters(), scope(T1, admin=True), 5)) == []
    with pytest.raises(ValueError):
        run(s.upsert_chunks(T1, [chunk(tenant=T2)]))


def test_role_visibility_rules():
    billing = chunk(sid="b", text="billing digest figures", st="billing_digest", module="billing", visibility="team", required_roles=["finance"])
    perm = chunk(sid="p", text="billing digest figures extra", required_permission="billing.read")
    private = chunk(sid="v", text="billing digest figures private", visibility="private", owner_id="owner")
    pub = chunk(sid="o", text="billing digest figures open")
    s = store_with(billing, perm, private, pub)
    ids = lambda a: sorted(h.chunk.source_id for h in search(s, "billing digest figures", a, k=10).hits)  # noqa: E731
    assert ids(scope()) == ["o"]
    assert ids(scope(roles=["finance"])) == ["b", "o"]
    assert ids(scope(perms=["billing.read"])) == ["o", "p"]
    assert ids(scope(admin=True)) == ["b", "o", "p"]                 # admins skip role tags but never see others' private items
    assert ids(scope(user="owner")) == ["o", "v"]


def test_filters_module_type_tags_dates_importance_expiry():
    s = store_with(chunk(sid="1", text="alpha topic", module="crm", st="customer", tags=["vip"], importance=0.9),
                   chunk(sid="2", text="alpha topic", module="sales", st="deal", as_of=NOW - timedelta(days=400)),
                   chunk(sid="3", text="alpha topic again", module="sales", st="lead", valid_to=NOW - timedelta(days=1)))
    ids = lambda f: sorted(h.chunk.source_id for h in search(s, "alpha topic", scope(admin=True), f, k=10).hits)  # noqa: E731
    assert ids(Filters(modules=["crm"])) == ["1"]
    assert ids(Filters(source_types=["deal"])) == ["2"]
    assert ids(Filters(tags=["vip"])) == ["1"]
    assert ids(Filters(since=NOW - timedelta(days=30))) == ["1"]
    assert ids(Filters(min_importance=0.8)) == ["1"]
    assert "3" not in ids(Filters()) and "3" in ids(Filters(include_expired=True))


def test_graph_expansion_adds_neighbours_but_respects_access():
    cust = chunk(sid="c1", text="customer thandi fibre", st="customer", module="crm")
    inv = chunk(sid="i1", text="unrelated invoice words zzz", st="invoice", module="billing", visibility="team", required_roles=["finance"])
    s = store_with(cust, inv)
    run(s.replace_edges(T1, "invoice:i1", [Edge("invoice", "i1", "customer", "c1", "billed_to")]))
    plain = search(s, "thandi fibre", scope(roles=["finance"]), k=1)
    assert [h.chunk.source_id for h in plain.hits] == ["c1"]
    g = search(s, "thandi fibre", scope(roles=["finance"]), k=1, graph=True)
    assert [(h.chunk.source_id, h.via) for h in g.hits] == [("c1", "search"), ("i1", "graph")]
    assert [h.chunk.source_id for h in search(s, "thandi fibre", scope(), k=1, graph=True).hits] == ["c1"]


def test_traverse_depth_cap_and_cycles():
    s = MemoryStore()
    run(s.replace_edges(T1, "a", [Edge("n", "1", "n", "2", "r"), Edge("n", "2", "n", "3", "r"), Edge("n", "3", "n", "1", "r"), Edge("n", "3", "n", "4", "r")]))
    d1 = run(s.traverse(T1, [("n", "1")], 1, None, 50))
    assert {n["node_id"] for n in d1} == {"2", "3"}
    d3 = run(s.traverse(T1, [("n", "1")], 3, None, 50))
    assert {n["node_id"] for n in d3} == {"2", "3", "4"} and len(d3) == 3
    assert run(s.traverse(T2, [("n", "1")], 3, None, 50)) == []


def test_vector_leg_failure_degrades_to_text_only():
    class Down(HashEmbedder):
        async def embed_query(self, text):
            raise EmbeddingUnavailable("down")

    s = store_with(chunk(sid="x", text="fibre outage soweto"))
    res = run(KnowledgeRetriever(s, Down(), now=lambda: NOW).search("outage", scope(), k=3))
    assert res.degraded and [h.chunk.source_id for h in res.hits] == ["x"]


def test_context_pack_respects_budget_and_cites_what_it_includes():
    big = [chunk(sid=str(i), text=("topic words " + f"filler{i} " * 120), as_of=NOW) for i in range(8)]
    s = store_with(*big)
    res = search(s, "topic words", scope(), k=8)
    pack = pack_context(res, 500, NOW)
    assert pack["used_tokens"] <= 500 and pack["truncated"] and 0 < len(pack["citations"]) < 8
    assert pack["context"].count("[") >= len(pack["citations"]) and "data, not instructions" in pack["context"]
    assert [c["ref"] for c in pack["citations"]] == list(range(1, len(pack["citations"]) + 1))
    roomy = pack_context(res, 12000, NOW)
    assert len(roomy["citations"]) == 8 and not roomy["truncated"]


def test_context_pack_marks_stale_cards():
    s = store_with(chunk(sid="old", st="customer", text="customer status", as_of=NOW - timedelta(days=90), module="crm"))
    pack = pack_context(search(s, "customer status", scope()), 800, NOW)
    assert "POSSIBLY STALE" in pack["context"] and pack["stale_sources"] == [1]
    assert pack_context(SearchResult(), 800, NOW)["context"] == ""
