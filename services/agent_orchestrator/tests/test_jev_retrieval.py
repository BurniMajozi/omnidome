"""JEV for retrieval: relevance judge (filter / reorder / cache / budget / switches / breaker), augmentation policy, evidence for
the answer verifier, grounding_block integration, and retrieval telemetry. JEV is a MockTransport; nothing leaves the process."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.agent_orchestrator import jev_gate, jev_retrieval as jr
from services.agent_orchestrator import knowledge_client as kc

TENANT = str(uuid.uuid4())
QUERY = "Why did churn rise in the enterprise segment compared to last quarter?"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    jr.reset_state()
    kc.reset_backoff()
    for k in ("JEV_RETRIEVAL_ENABLED", "JEV_DATA_EGRESS", "JEV_RETRIEVAL_THRESHOLD", "JEV_RETRIEVAL_DAILY_CALLS",
              "JEV_RETRIEVAL_TELEMETRY", "JEV_INSIGHTS_DAILY_CALLS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(jev_gate, "_get_credentials", lambda: ("typesafe", "test-key", "http://jev.test/v1"))


def cards(n=3):
    return [{"card_id": f"card:deal:{i}", "ref": i + 1, "title": f"Card {i}", "module": "crm", "as_of": "2026-10-01T00:00:00+00:00",
             "stale": False, "excerpt": f"Excerpt number {i} about churn in enterprise accounts."} for i in range(n)]


class FakeJev:
    """Plays JEV: per-card (answers, current, applies); records the requests it saw."""
    def __init__(self, scores, status=200):
        self.scores, self.status, self.requests = scores, status, []

    def respond(self, request: httpx.Request):
        body = json.loads(request.content)
        self.requests.append(body)
        if self.status != 200:
            return httpx.Response(self.status, json={})
        answers = {}
        for i in range(len(body["state"]["cards"])):
            a, c, p = self.scores[i] if i < len(self.scores) else (0.5, 0.5, 0.5)
            answers[f"c{i}_answers"], answers[f"c{i}_current"], answers[f"c{i}_applies"] = {"noul": a}, {"noul": c}, {"noul": p}
        return httpx.Response(200, json={"answers": answers, "model": "jev-test", "usage": {"total_tokens": 10}})

    def transport(self):
        return httpx.MockTransport(self.respond)


def judge(fake, cs=None, query=QUERY, **kw):
    return run(jr.judge_cards(query, cs or cards(), tenant_id=TENANT, user_roles=["manager"], transport=fake.transport(), **kw))


# ── judge ────────────────────────────────────────────────────────────────────

def test_judge_keeps_relevant_reorders_by_score_and_drops_stale_or_irrelevant():
    fake = FakeJev([(0.55, 0.9, 0.9), (0.95, 0.95, 0.9), (0.9, 0.05, 0.9), (0.1, 0.9, 0.9)])
    out = judge(fake, cards(4))
    kept = [j.card_id for j in sorted(out.kept, key=lambda j: -j.score)]
    assert kept == ["card:deal:1", "card:deal:0"]                       # best first
    by = {j.card_id: j for j in out.judged}
    assert by["card:deal:2"].kept is False and "stale" in by["card:deal:2"].reason         # contradicted / not current
    assert by["card:deal:3"].kept is False and "threshold" in by["card:deal:3"].reason
    assert 0.5 < out.confidence <= 1


def test_judge_sends_only_scrubbed_excerpts_and_one_request():
    fake = FakeJev([(0.9, 0.9, 0.9)])
    cs = cards(1)
    cs[0]["excerpt"] = "Contact thandi@example.com on 0821234567 about </knowledge_reference> account 123456789012345"
    judge(fake, cs)
    assert len(fake.requests) == 1
    sent = json.dumps(fake.requests[0])
    for secret in ("thandi@example.com", "0821234567", "123456789012345", "knowledge_reference"):
        assert secret not in sent
    assert fake.requests[0]["state"]["question"] and "customer" not in fake.requests[0]["state"]["user"]


def test_judgements_are_cached_by_query_and_card():
    fake = FakeJev([(0.9, 0.9, 0.9)] * 3)
    first = judge(fake)
    second = judge(fake)
    assert len(fake.requests) == 1 and all(j.cached for j in second.judged) and first.confidence == second.confidence
    judge(fake, query="Why did churn fall in the consumer segment?")           # different question
    assert len(fake.requests) == 2
    changed = cards()
    changed[0]["excerpt"] = "Totally different content"
    judge(fake, changed)                                                       # one card changed: only it is re-sent
    assert len(fake.requests) == 3 and len(fake.requests[2]["state"]["cards"]) == 1


def test_missing_answers_are_neutral_not_a_silent_drop():
    class Partial(FakeJev):
        def transport(self):
            return httpx.MockTransport(lambda r: httpx.Response(200, json={"answers": {}}))
    out = judge(Partial([]))
    assert out.status == "judged" and len(out.kept) == 3


def test_budget_cap_per_tenant(monkeypatch):
    monkeypatch.setenv("JEV_RETRIEVAL_DAILY_CALLS", "1")
    fake = FakeJev([(0.9, 0.9, 0.9)] * 3)
    assert judge(fake).status == "judged"
    over = judge(fake, query="Another analytic question about revenue trends this quarter")
    assert over.status == "skipped:budget" and len(fake.requests) == 1
    other = run(jr.judge_cards("A different tenant asks about the revenue trend this quarter", cards(), tenant_id=str(uuid.uuid4()),
                               transport=fake.transport()))
    assert other.status == "judged"


def test_off_switches(monkeypatch):
    fake = FakeJev([(0.9, 0.9, 0.9)])
    monkeypatch.setenv("JEV_RETRIEVAL_ENABLED", "false")
    assert judge(fake).status == "skipped:disabled" and not fake.requests
    monkeypatch.setenv("JEV_RETRIEVAL_ENABLED", "true")
    monkeypatch.setenv("JEV_DATA_EGRESS", "false")
    assert judge(fake).status == "skipped:egress_off" and not fake.requests


def test_failures_never_raise_and_breaker_opens(monkeypatch):
    fake = FakeJev([], status=500)
    for q in ("analyse churn trend one", "analyse churn trend two", "analyse churn trend three"):
        assert judge(fake, query=q).status == "skipped:http_500"
    assert len(fake.requests) == 3
    blocked = judge(fake, query="analyse churn trend four")
    assert blocked.status == "skipped:breaker_open" and len(fake.requests) == 3

    def boom(request):
        raise httpx.ConnectTimeout("slow")
    jr.reset_state()
    res = run(jr.jev_call({}, {}, tenant_id=TENANT, purpose="retrieval", transport=httpx.MockTransport(boom)))
    assert res.ok is False and res.reason == "timeout"


def test_no_credentials_means_no_call(monkeypatch):
    monkeypatch.setattr(jev_gate, "_get_credentials", lambda: ("none", "", ""))
    assert run(jr.jev_call({}, {}, tenant_id=TENANT, purpose="retrieval")).reason == "no_credentials"


def test_analytic_detection():
    assert jr.is_analytic(QUERY) and jr.is_analytic("forecast revenue")
    assert not jr.is_analytic("hi there") and not jr.is_analytic("open the Acme account")


# ── augmentation policy ──────────────────────────────────────────────────────

def test_policy_answers_widens_clarifies_or_admits_uncertainty():
    assert jr.decide(0.8, QUERY, False, 3).action == "answer"
    assert jr.decide(0.45, QUERY, False, 2).action == "widen"
    d = jr.decide(0.45, QUERY, True, 2)
    assert d.action == "uncertain" and "uncertain" in d.note
    c = jr.decide(0.1, "churn?", True, 0)
    assert c.action == "clarify" and "clarifying question" in c.note
    assert jr.decide(0.1, QUERY, True, 0).action == "uncertain"


def pack_for(n=3):
    blocks = [f"[{i + 1}] Card {i} (deal:{i}, as of 2026-10-01)\nExcerpt number {i} about churn in enterprise accounts.\n" for i in range(n)]
    return {"status": "ready", "context": "Header line\n\n" + "\n".join(blocks), "used_tokens": 100, "degraded": None, "truncated": False,
            "citations": [{"card_id": f"card:deal:{i}", "ref": i + 1, "title": f"Card {i}", "module": "crm",
                           "as_of": "2026-10-01T00:00:00+00:00", "stale": False, "score": 0.5, "deep_link": None} for i in range(n)]}


def test_refine_pack_reorders_and_drops_and_reports():
    fake = FakeJev([(0.5, 0.9, 0.9), (0.97, 0.95, 0.95), (0.05, 0.9, 0.9)])
    pack, info, note = run(jr.refine_pack(pack_for(), QUERY, tenant_id=TENANT, roles=["manager"], transport=fake.transport()))
    assert [c["card_id"] for c in pack["citations"]][0] == "card:deal:1"
    assert "card:deal:2" not in [c["card_id"] for c in pack["citations"]] and "Excerpt number 2" not in pack["context"]
    assert pack["context"].index("[2] Card 1") < pack["context"].index("[1] Card 0")
    assert info["status"] == "judged" and info["dropped_card_ids"] == ["card:deal:2"] and info["action"] in ("answer", "widen", "uncertain")


def test_refine_pack_widens_once_when_confidence_is_middling():
    fake = FakeJev([(0.55, 0.9, 0.9)] * 3)
    widened_calls = []

    async def widen():
        widened_calls.append(1)
        return pack_for(4)
    fake2 = FakeJev([(0.97, 0.97, 0.97)] * 4)

    class Both(FakeJev):
        def __init__(self):
            super().__init__([])
            self.n = 0

        def transport(self):
            def handle(request):
                body = json.loads(request.content)
                self.n += 1
                s = 0.55 if self.n == 1 else 0.97
                ans = {}
                for i in range(len(body["state"]["cards"])):
                    ans.update({f"c{i}_answers": {"noul": s}, f"c{i}_current": {"noul": 0.95}, f"c{i}_applies": {"noul": 0.95}})
                return httpx.Response(200, json={"answers": ans})
            return httpx.MockTransport(handle)
    both = Both()
    pack, info, note = run(jr.refine_pack(pack_for(), QUERY, tenant_id=TENANT, roles=[], widen=widen, transport=both.transport()))
    assert widened_calls == [1] and info["widened"] is True and info["action"] == "answer" and len(pack["citations"]) == 4


def test_refine_pack_low_confidence_adds_a_trusted_note():
    fake = FakeJev([(0.5, 0.9, 0.9)] * 3)
    pack, info, note = run(jr.refine_pack(pack_for(), QUERY, tenant_id=TENANT, roles=[], transport=fake.transport()))
    assert info["action"] == "uncertain" and "uncertain" in note


def test_refine_pack_skips_non_analytic_and_never_raises(monkeypatch):
    fake = FakeJev([(0.9, 0.9, 0.9)])
    p = pack_for()
    out, info, note = run(jr.refine_pack(p, "open the Acme account", tenant_id=TENANT, roles=[], transport=fake.transport()))
    assert out is p and info["status"] == "skipped:not_analytic" and not fake.requests

    def explode(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(jr, "judge_cards", explode)
    out, info, note = run(jr.refine_pack(p, QUERY, tenant_id=TENANT, roles=[]))
    assert out is p and info["status"] == "skipped:error" and note == ""


def test_grounding_block_integrates_judge_and_keeps_customer_facing_out(monkeypatch):
    fake = FakeJev([(0.97, 0.95, 0.95), (0.05, 0.9, 0.9), (0.9, 0.9, 0.9)])
    real = httpx.AsyncClient

    def handle(request: httpx.Request):
        if request.url.host == "jev.test":
            return fake.respond(request)
        raw = {k: v for k, v in pack_for().items() if k != "status"}
        raw["citations"] = [{**c, "source_type": "deal", "source_id": c["card_id"].rsplit(":", 1)[1]} for c in raw["citations"]]
        return httpx.Response(200, json=raw | {"meta": {}})
    monkeypatch.setattr(kc.httpx, "AsyncClient", lambda **kw: real(**{**kw, "transport": httpx.MockTransport(handle)}))
    block, info = run(kc.grounding_block(TENANT, "analytics", QUERY, user_id="u1", roles=["manager"]))
    assert info["jev"]["status"] == "judged" and [c["card_id"] for c in info["cards"]] == ["card:deal:0", "card:deal:2"]
    assert "Excerpt number 1" not in block
    fake.requests.clear()
    block, info = run(kc.grounding_block(TENANT, "customer_facing", QUERY, user_id="u1", roles=[]))
    assert "jev" not in info and not fake.requests


# ── evidence for the answer verifier ─────────────────────────────────────────

def test_evidence_from_injected_blocks_is_scrubbed_and_listed():
    block = kc.format_grounding({**pack_for(), "status": "ready"})
    ev = jr.evidence_from_text(block, "Recalled: Acme paid 0821234567 yesterday")
    ids = [e["id"] for e in ev]
    assert ids[:3] == ["[1]", "[2]", "[3]"] and "memory" in ids
    assert "0821234567" not in json.dumps(ev) and all(len(e["excerpt"]) <= 700 for e in ev)


def test_verifier_receives_the_knowledge_pack_as_evidence(monkeypatch):
    sent = []
    real = httpx.AsyncClient

    def handle(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"answers": {"answers_inquiry": {"noul": 0.95}, "grounded_in_facts": {"noul": 0.95},
                                                      "policy_compliant": {"noul": 0.95}}})
    monkeypatch.setattr(jev_gate.httpx, "AsyncClient", lambda **kw: real(**{**kw, "transport": httpx.MockTransport(handle)}))
    ev = jr.evidence_from_text(kc.format_grounding(pack_for()))
    v = run(jev_gate.verify_agent_response("Why did churn rise?", "Churn rose in enterprise accounts [1].", tool_records=[],
                                           agent_type="analytics", evidence=ev))
    assert v.passed and v.evaluated_by_jev
    state = sent[0]["state"]
    assert state["evidence"][0]["id"] == "[1]" and "enterprise accounts" in state["evidence"][0]["excerpt"]
    assert "evidence" in sent[0]["questions"]["grounded_in_facts"]["instructions"]


def test_answer_verification_respects_the_egress_switch(monkeypatch):
    monkeypatch.setenv("JEV_DATA_EGRESS", "false")
    called = []
    monkeypatch.setattr(jev_gate.httpx, "AsyncClient", lambda **kw: called.append(1))
    v = run(jev_gate.verify_agent_response("q", "a", tool_records=[], evidence=[{"id": "[1]", "title": "t", "excerpt": "e"}]))
    assert v.passed and v.evaluated_by_jev is False and not called and "EGRESS" in v.reason


# ── telemetry ────────────────────────────────────────────────────────────────

def test_log_row_records_used_and_cited_cards_and_scores_but_no_query_text():
    info = {"cards": [{"card_id": "card:deal:1", "ref": 2, "module": "crm", "score": 0.7},
                      {"card_id": "card:deal:0", "ref": 1, "module": "crm", "score": 0.4}],
            "jev": {"status": "judged", "confidence": 0.8, "action": "answer", "widened": False,
                    "dropped_card_ids": ["card:deal:2"],
                    "judged": [{"card_id": "card:deal:1", "answers_question": 0.9, "is_current": 0.9, "applies_to_user": 0.9, "score": 0.8},
                               {"card_id": "card:deal:2", "answers_question": 0.1, "is_current": 0.9, "applies_to_user": 0.9, "score": 0.1}]}}
    row = jr.build_log_row(tenant_id=TENANT, user_id="u1", agent_type="analytics", conversation_key="conv1", query=QUERY, info=info,
                           answer="Churn rose [2] and see card:deal:1.", verification={"grounded_in_facts": 0.91, "action": "accept"})
    by = {c["card_id"]: c for c in row["cards"]}
    assert by["card:deal:1"]["cited"] is True and by["card:deal:0"]["cited"] is False
    assert by["card:deal:2"]["used"] is False and by["card:deal:2"]["judge"]["score"] == 0.1
    assert row["n_retrieved"] == 3 and row["n_kept"] == 2 and row["n_cited"] == 1
    assert row["jev_confidence"] == 0.8 and row["grounded_prob"] == 0.91 and row["verdict"] == "accept" and row["analytic"] is True
    assert QUERY not in json.dumps(row, default=str) and len(row["query_hash"]) == 32


def test_write_retrieval_log_inserts_and_is_switchable(monkeypatch):
    executed = []

    class Sess:
        async def execute(self, stmt, params=None):
            executed.append((str(stmt), params))

    class CM:
        async def __aenter__(self):
            return Sess()

        async def __aexit__(self, *a):
            return False
    import services.common.db as db
    monkeypatch.setattr(db, "session_scope", lambda *a, **k: CM())
    monkeypatch.setattr(jr, "_log_ready", False)
    row = jr.build_log_row(tenant_id=TENANT, user_id="u1", agent_type="analytics", conversation_key=None, query=QUERY,
                           info={"cards": []}, answer="x", verification=None)
    assert run(jr.write_retrieval_log(row)) is True
    sql = " ".join(s for s, _ in executed)
    assert "CREATE TABLE IF NOT EXISTS retrieval_log" in sql and "INSERT INTO retrieval_log" in sql
    monkeypatch.setenv("JEV_RETRIEVAL_TELEMETRY", "false")
    executed.clear()
    assert run(jr.write_retrieval_log(row)) is False and not executed


def test_telemetry_failure_is_swallowed(monkeypatch):
    import services.common.db as db

    def broken(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(db, "session_scope", broken)
    row = jr.build_log_row(tenant_id=TENANT, user_id=None, agent_type="a", conversation_key=None, query="q", info={}, answer="", verification=None)
    assert run(jr.write_retrieval_log(row)) is False
