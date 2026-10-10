from datetime import timedelta

from services.tenant_memory.knowledge.dream.drift import in_sample, sla_days
from services.tenant_memory.knowledge.dream.settings import DreamSettings
from services.tenant_memory.knowledge.dream.store import STALE_TAG

from .helpers import NOW, T1, T2, edge, make_env, mk_card, run


def test_changed_source_is_refreshed_with_before_after():
    e = make_env()
    e.index(T1, mk_card("ticket", "t1", "Soweto outage", "fibre cut on main road", importance=0.8))
    e.renderer.script[("ticket", "t1")] = mk_card("ticket", "t1", "Soweto outage", "fibre repaired, service restored", importance=0.8)
    res = e.night(phases=["drift"])
    assert res["status"] == "completed" and res["phase_results"]["drift"]["counts"]["content_drift"] == 1
    assert "restored" in e.live(T1, "ticket", "t1")[0].markdown
    f = e.findings(type="content_drift")[0]
    assert f["status"] == "auto_applied" and "cut on main road" in f["detail"]["before"]["preview"] and "restored" in f["detail"]["after"]["preview"]
    assert f["action"]["kind"] == "refresh"


def test_unchanged_source_is_only_verified_and_not_re_embedded():
    e = make_env()
    c = mk_card("ticket", "t1", "Soweto outage", "same text", importance=0.8)
    e.index(T1, c)
    calls = len(e.emb.calls)
    e.renderer.script[("ticket", "t1")] = mk_card("ticket", "t1", "Soweto outage", "same text", importance=0.8)
    res = e.night(phases=["drift"])
    assert res["phase_results"]["drift"]["counts"]["verified"] == 1 and len(e.emb.calls) == calls
    assert e.findings(type="content_drift") == []


def test_vanished_source_is_tombstoned_and_edges_removed_but_missing_table_is_not():
    e = make_env()
    e.index(T1, mk_card("ticket", "gone", "Old ticket", "x", importance=0.9, edges=[edge("ticket", "gone", "customer", "c1")]),
            mk_card("ticket", "ok", "Fine ticket", "y", importance=0.9), mk_card("campaign", "c1", "Campaign one", "z", importance=0.9))
    e.renderer.script[("ticket", "gone")] = "gone"
    e.renderer.script[("campaign", "c1")] = "source_missing"
    e.night(phases=["drift"])
    assert e.live(T1, "ticket", "gone") == [] and not any(k.endswith("ticket:gone") for k in e.store.edges if e.store.edges[k])
    assert e.live(T1, "campaign", "c1")                                  # table disappeared: cards are NOT removed
    types = {f["type"] for f in e.findings()}
    assert {"source_vanished", "source_table_missing"} <= types
    assert e.findings(type="source_table_missing")[0]["severity"] == "high"


def test_unverifiable_cards_are_left_alone():
    e = make_env()
    e.index(T1, mk_card("ticket", "t1", "Ticket", "x", importance=0.9))
    res = e.night(phases=["drift"])
    assert res["phase_results"]["drift"]["counts"]["unverifiable"] == 1 and e.live(T1, "ticket", "t1")


def test_stale_marking_and_clearing():
    e = make_env()
    old = NOW - timedelta(days=60)
    e.index(T1, mk_card("ticket", "old", "Old ticket", "unverifiable one", as_of=old), mk_card("ticket", "ver", "Verified old ticket", "fine", as_of=old),
            mk_card("ticket", "new", "New ticket", "fresh", as_of=NOW))
    e.renderer.script[("ticket", "ver")] = mk_card("ticket", "ver", "Verified old ticket", "fine", as_of=old)
    e.night(phases=["drift"])
    assert STALE_TAG in e.live(T1, "ticket", "old")[0].tags                  # 60d > 30d SLA, not verifiable
    assert STALE_TAG not in e.live(T1, "ticket", "ver")[0].tags              # the source says it is still true
    assert STALE_TAG not in e.live(T1, "ticket", "new")[0].tags
    f = e.findings(type="stale_cards")[0]
    assert f["detail"]["count"] == 1 and f["detail"]["sla_days"] == 30
    # the source now confirms the card: marker cleared next night
    e.renderer.script[("ticket", "old")] = mk_card("ticket", "old", "Old ticket", "unverifiable one", as_of=old)
    e.night(phases=["drift"])
    assert STALE_TAG not in e.live(T1, "ticket", "old")[0].tags


def test_stale_marker_is_in_the_retrieval_citation_flag():
    from services.tenant_memory.knowledge.kdata import Hit
    from services.tenant_memory.knowledge.retrieval import citation
    e = make_env()
    e.index(T1, mk_card("ticket", "old", "Old", "x", as_of=NOW - timedelta(days=60)))
    e.night(phases=["drift"])
    assert citation(Hit(e.live(T1, "ticket", "old")[0]), NOW)["stale"] is True
    e.index(T1, mk_card("ticket", "fresh", "Fresh", "x", as_of=NOW, tags=["dream:stale"]))
    assert citation(Hit(e.live(T1, "ticket", "fresh")[0]), NOW)["stale"] is True


def test_orphan_edges_are_removed_dangling_only_reported():
    e = make_env()
    e.index(T1, mk_card("ticket", "t1", "Ticket", "x", importance=0.9, edges=[edge("ticket", "t1", "ticket", "nobody")]))
    run(e.store.replace_edges(T1, "ticket:deleted", [edge("ticket", "deleted", "customer", "c1")]))
    res = e.night(phases=["drift"])
    assert res["phase_results"]["drift"]["counts"]["orphan_edge_origins"] == 1
    assert f"{T1}|ticket:deleted" not in e.store.edges or not e.store.edges[f"{T1}|ticket:deleted"]
    assert e.store.edges[f"{T1}|ticket:t1"]                                  # edge from a live card is kept even though the target is unindexed
    assert e.findings(type="orphan_edges") and e.findings(type="dangling_edges")


def test_rotation_covers_every_card_once_per_cycle_and_high_importance_every_night():
    ids = [f"id{i}" for i in range(40)]
    seen = set()
    for day in range(7):
        picked = {i for i in ids if in_sample("ticket", i, day, 7)}
        assert not (picked & seen)
        seen |= picked
    assert seen == set(ids)
    e = make_env(rotation_days=60)
    e.index(T1, mk_card("ticket", "hi", "Important", "x", importance=0.9))
    for _ in range(2):
        e.night(phases=["drift"])
    assert [c[2] for c in e.renderer.calls].count("hi") == 2


def test_sla_override_and_defaults():
    assert sla_days(DreamSettings(), "customer") == 14 and sla_days(DreamSettings(), "skill") == 365
    assert sla_days(DreamSettings(stale_days={"customer": 3}), "customer") == 3


def test_cursor_rotates_across_nights_when_the_budget_is_small():
    e = make_env(max_cards_per_night=2, high_importance=0.0)
    e.index(T1, *[mk_card("ticket", f"t{i}", f"Ticket number {i}", "x") for i in range(5)])
    e.night(phases=["drift"])
    first = [c[2] for c in e.renderer.calls]
    e.renderer.calls.clear()
    e.night(phases=["drift"])
    second = [c[2] for c in e.renderer.calls]
    assert first == ["t0", "t1"] and second == ["t2", "t3"]


def test_tenant_isolation_of_drift():
    e = make_env()
    e.index(T1, mk_card("ticket", "t1", "Ticket", "old", importance=0.9))
    e.index(T2, mk_card("ticket", "t1", "Ticket", "old", importance=0.9))
    e.renderer.script[("ticket", "t1")] = mk_card("ticket", "t1", "Ticket", "new", importance=0.9)
    e.night(T1, phases=["drift"])
    assert "new" in e.live(T1, "ticket", "t1")[0].markdown and "old" in e.live(T2, "ticket", "t1")[0].markdown
    assert e.findings(T2) == [] and run(e.dstore.list_runs(T2)) == []
