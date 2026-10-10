import math

from services.tenant_memory.knowledge.dream import embedding_health as EH
from services.tenant_memory.knowledge.embeddings import HashEmbedder

from .helpers import T1, make_env, mk_card, run


def test_vector_problem_and_outliers_are_pure():
    assert EH.vector_problem(None, 4) == "missing" and EH.vector_problem([1, 2], 4) == "bad_dim"
    assert EH.vector_problem([0.0] * 4, 4) == "invalid" and EH.vector_problem([1, float("nan"), 0, 0], 4) == "invalid"
    assert EH.vector_problem([1, float("inf"), 0, 0], 4) == "invalid" and EH.vector_problem([1, 0, 0, 0], 4) is None
    norms = [1.0] * 12 + [0.1, 5.0]
    assert EH.outliers(norms) == {12, 13} and EH.outliers([1.0, 9.0]) == set()          # too few vectors: no verdict
    assert EH.fingerprint([1.0, 2.0]) == EH.fingerprint([1.00001, 2.0]) != EH.fingerprint([1.0, 2.1])


def _seed(e, n=6):
    e.index(T1, *[mk_card("ticket", f"t{i}", f"Ticket number {i} about router", f"unique words alpha{i} beta{i}", importance=0.5 + i / 100) for i in range(n)])


def test_invalid_vectors_are_detected_and_re_embedded_within_the_nightly_budget():
    e = make_env(reembed_per_night=1)
    _seed(e)
    zero, nan = e.live(T1, "ticket", "t0")[0], e.live(T1, "ticket", "t1")[0]
    zero.embedding = [0.0] * 32
    nan.embedding = [float("nan")] + [0.1] * 31
    res = e.night(phases=["embeddings"])
    c = res["phase_results"]["embeddings"]["counts"]
    assert c["vec_invalid"] == 2 and c["reembedded"] == 1                              # rate limited to 1 per night
    assert e.findings(type="embedding_invalid")[0]["severity"] in ("high", "medium")
    e.night(phases=["embeddings"])
    assert all(not math.isnan(x) for x in e.live(T1, "ticket", "t1")[0].embedding) and any(e.live(T1, "ticket", "t0")[0].embedding)


def test_model_change_is_detected_and_queued_for_rate_limited_re_embedding():
    e = make_env(reembed_per_night=2)
    _seed(e, 5)
    e.deps.embedder = HashEmbedder(32, model="hash-v2")
    res = e.night(phases=["embeddings"])
    c = res["phase_results"]["embeddings"]["counts"]
    assert c["vec_model_mismatch"] == 5 and c["reembedded"] == 2
    assert sum(1 for ch in e.chunks(T1) if ch.embedding_model == "hash-v2") == 2
    done = [ch for ch in e.chunks(T1) if ch.embedding_model == "hash-v2"][0]
    from services.tenant_memory.knowledge.cards.base import stable_text
    from services.tenant_memory.knowledge.kdata import content_hash
    assert done.content_hash == content_hash(stable_text(done.markdown), "hash-v2")       # same recipe as the indexer: it will not re-embed again
    assert e.findings(type="embedding_model_changed")


def test_wrong_dimension_is_reported_not_force_fixed():
    e = make_env()
    _seed(e, 2)
    e.live(T1, "ticket", "t0")[0].embedding = [0.1] * 8
    res = e.night(phases=["embeddings"])
    assert res["phase_results"]["embeddings"]["counts"]["vec_bad_dim"] == 1 and res["phase_results"]["embeddings"]["counts"]["reembedded"] == 0
    assert e.findings(type="embedding_dimension_mismatch")[0]["severity"] == "high"


def test_duplicate_vectors_identical_text_is_info_collapse_is_medium():
    e = make_env()
    e.index(T1, mk_card("ticket", "a", "Alpha", "text one"), mk_card("ticket", "b", "Beta", "text two"), mk_card("ticket", "c", "Gamma", "text three"))
    a, b = e.live(T1, "ticket", "a")[0], e.live(T1, "ticket", "b")[0]
    b.embedding = list(a.embedding)                                                   # different text, same vector
    e.night(phases=["embeddings"])
    assert e.findings(type="embedding_collapse")[0]["severity"] == "medium"
    assert not e.findings(type="duplicate_vectors")


def test_semantic_drift_between_old_and_new_embedding_is_recorded():
    e = make_env(semantic_drift=0.1)
    e.index(T1, mk_card("ticket", "t1", "Ticket", "fibre outage soweto router red light", importance=0.9),
            mk_card("ticket", "t2", "Other", "billing invoice debit order", importance=0.9))
    e.renderer.script[("ticket", "t1")] = mk_card("ticket", "t1", "Ticket", "completely different subject matter entirely new words", importance=0.9)
    e.renderer.script[("ticket", "t2")] = mk_card("ticket", "t2", "Other", "billing invoice debit order now", importance=0.9)     # tiny edit
    res = e.night(phases=["drift", "embeddings"])
    c = res["phase_results"]["embeddings"]["counts"]
    assert c["refreshed_compared"] == 2 and c["semantic_drift"] == 1
    f = e.findings(type="semantic_drift")[0]
    assert f["source_id"] == "t1" and f["detail"]["cosine_distance"] > 0.1


class _FakeRetriever:
    """Finds only cards whose id is in `finds`; lets us drive the recall number without a real index problem."""
    finds: set = set()

    def __init__(self, *a, **k):
        pass

    async def search(self, query, scope, flt, k=3):
        from services.tenant_memory.knowledge.kdata import Chunk, Hit
        from services.tenant_memory.knowledge.retrieval import SearchResult
        hits = [Hit(Chunk(scope.tenant_id, "ticket", sid, 0, "support", "t", "m", "h")) for sid in sorted(self.finds)]
        return SearchResult(hits=hits)


def test_canary_recall_is_computed_and_a_drop_raises_a_finding(monkeypatch):
    e = make_env(canary_n=5)
    _seed(e, 6)
    # seed a previous run that reported perfect recall, then break retrieval
    run(e.dstore.create_run(T1, {"run_date": "2026-10-09", "trigger": "nightly", "dry_run": False, "status": "completed",
                                 "report": {"canary": {"recall_at_3": 1.0}}, "started_at": "2026-10-09T00:30:00+00:00"}))
    monkeypatch.setattr(EH, "KnowledgeRetriever", _FakeRetriever)
    _FakeRetriever.finds = {"t5", "t4"}                                               # 2 of 5 probes retrieve themselves
    res2 = e.night(phases=["embeddings"])
    c = res2["phase_results"]["embeddings"]["counts"]
    assert c["canary_n"] == 5 and c["canary_hits"] == 2 and c["canary_recall_at_3"] == 0.4
    f = e.findings(type="canary_recall_drop")[0]
    assert f["severity"] == "high" and f["detail"]["previous"] == 1.0 and len(f["detail"]["misses"]) == 3


def test_canary_healthy_index_scores_full_recall_and_no_alert():
    e = make_env(canary_n=5)
    _seed(e, 6)
    res = e.night(phases=["embeddings"])
    assert res["phase_results"]["embeddings"]["counts"]["canary_recall_at_3"] == 1.0
    assert e.findings(type="canary_recall_drop") == []


def test_canary_skips_ambiguous_titles():
    e = make_env(canary_n=5)
    e.index(T1, *[mk_card("ticket", f"d{i}", "Same title everywhere", f"body {i}") for i in range(3)])
    res = e.night(phases=["embeddings"])
    assert "canary_n" not in res["phase_results"]["embeddings"]["counts"]
    assert any("no canary probes" in n for n in res["phase_results"]["embeddings"]["notes"])
