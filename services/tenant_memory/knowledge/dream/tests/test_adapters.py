import asyncio
from contextlib import asynccontextmanager

import httpx

from services.tenant_memory.knowledge.cards.sources import Page, Source
from services.tenant_memory.knowledge.dream import adapters as A, jev as J
from services.tenant_memory.knowledge.dream.store_pg import DREAM_TABLES, migration_statements

from .helpers import T1, mk_card, run


def test_classify_missing_table_vs_transient():
    assert A.classify_missing(Exception('relation "tenant_metric_facts" does not exist')) and A.classify_missing(Exception("UndefinedTableError"))
    assert not A.classify_missing(Exception("connection reset by peer"))


def test_retrieval_log_rows_become_per_card_usage():
    from datetime import datetime, timezone
    now = datetime(2026, 10, 9, tzinfo=timezone.utc)
    rows = [
        {"cards": [{"card_id": "card:faq:a", "used": True, "cited": True, "judge": {"score": 0.9, "is_current": 0.8}},
                   {"card_id": "card:faq:b", "used": False, "cited": False, "judge": {"score": 0.1, "is_current": 0.1}}], "created_at": now, "grounded_prob": 0.8},
        {"cards": '[{"card_id": "card:faq:a", "used": true, "cited": false, "judge": null}, {"card_id": "garbage"}, {"card_id": "card:faq:b", "judge": {"is_current": 0.2}}]',
         "created_at": now, "grounded_prob": None},
    ]
    usage = {}
    A.usage_from_log(rows, usage)
    a, b = usage[("faq", "a")], usage[("faq", "b")]
    assert (a.retrieved, a.used, a.cited, a.not_current) == (2, 2, 1, 0) and round(a.jev_avg, 3) == 0.85       # judge 0.9 and grounded 0.8
    assert (b.retrieved, b.used, b.not_current) == (2, 0, 2) and ("faq", "garbage") not in usage and len(usage) == 2
    assert A.parse_card_id("card:ticket:abc:def") == ("ticket", "abc:def") and A.parse_card_id("ticket:1") is None and A.parse_card_id(None) is None


def test_insight_feedback_is_credited_to_the_cards_it_cited():
    doc = {"evidence": [{"id": "card:faq:a"}, {"id": "card:faq:b"}], "recommendations": [{"id": "r1", "evidence": [{"id": "card:faq:c"}]}]}
    usage = {}
    A.usage_from_feedback([{"verdict": "helpful", "rec_id": None, "doc": doc}, {"verdict": "not_helpful", "rec_id": "r1", "doc": doc},
                           {"verdict": "dismissed", "rec_id": None, "doc": doc}, {"verdict": "acted", "rec_id": None, "doc": "{bad json"}], usage)
    assert (usage[("faq", "a")].up, usage[("faq", "b")].up, usage[("faq", "c")].down) == (1, 1, 1) and len(usage) == 3


def test_pg_ddl_has_rls_on_every_dream_table_and_grants():
    sql = "\n".join(migration_statements())
    for t in DREAM_TABLES:
        assert f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY" in sql and f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY" in sql and f"CREATE POLICY tenant_isolation ON {t}" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON dream_runs" in sql and "knowledge_app" in sql


class _Sess:
    @asynccontextmanager
    async def __call__(self):
        yield object()


def _source(cards, ids, boom=None):
    async def fetch(session, tenant, wm, limit):
        if boom:
            raise boom
        return Page(cards=list(cards), rows=len(cards), last_ts=None)

    async def idfn(session, tenant):
        if boom:
            raise boom
        return {"ticket": set(ids)}
    return Source("tickets", "support", ("ticket",), fetch, idfn)


def test_source_renderer_ok_gone_unverifiable_and_missing_table():
    card = mk_card("ticket", "t1", "Ticket", "x")
    r = A.SourceCardRenderer({"tickets": _source([card], {"t1", "t2"})}, session_factory=_Sess())
    assert run(r.render(T1, "ticket", "t1")).status == "ok"
    assert run(r.render(T1, "ticket", "t2")).status == "unverifiable"            # exists but outside the render window: never 'gone'
    assert run(r.render(T1, "ticket", "t9")).status == "gone"
    assert run(r.render(T1, "unknown_type", "x")).status == "unverifiable"
    broken = A.SourceCardRenderer({"tickets": _source([], set(), boom=Exception('relation "tickets" does not exist'))}, session_factory=_Sess())
    assert run(broken.render(T1, "ticket", "t1")).status == "source_missing"
    flaky = A.SourceCardRenderer({"tickets": _source([], set(), boom=Exception("connection reset"))}, session_factory=_Sess())
    try:
        run(flaky.render(T1, "ticket", "t1"))
        raise AssertionError("a transient error must not be reported as a vanished source")
    except Exception as exc:  # noqa: BLE001
        assert "connection reset" in str(exc)


def test_jev_client_wire_format_and_garbage_answers(monkeypatch):
    seen = {}

    def handler(request: httpx.Request):
        import json
        seen["body"], seen["auth"] = json.loads(request.content), request.headers["authorization"]
        return httpx.Response(200, json={"answers": {"contradict": {"noul": 0.93}, "still_current": {"noul": "bad"}},
                                         "usage": {"cost": 0.004, "total_tokens": 321}, "model": "jev-x"})
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    c = J.HttpJevClient(transport=httpx.MockTransport(handler))
    assert c.configured()
    ans = asyncio.run(c.ask({"card_a": {}}, {"contradict": "q1", "still_current": "q2"}))
    assert ans.probs == {"contradict": 0.93, "still_current": 0.5} and ans.cost_usd == 0.004 and ans.tokens == 321 and ans.model == "jev-x"
    assert seen["auth"] == "Bearer test-key" and seen["body"]["questions"]["contradict"] == {"type": "noul", "instructions": "q1"}
    monkeypatch.delenv("TYPESAFE_API_KEY")
    assert not J.HttpJevClient().configured()


def test_jev_client_http_error_is_an_exception_not_a_verdict(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    c = J.HttpJevClient(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    try:
        asyncio.run(c.ask({}, {"contradict": "q"}))
        raise AssertionError("expected failure")
    except RuntimeError as exc:
        assert "503" in str(exc)


def test_metrics_refresher_posts_to_the_governed_snapshot_endpoint():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"], seen["tenant"] = str(request.url), request.headers["x-tenant-id"]
        return httpx.Response(200, json={"ok": True})
    r = A.HttpMetricsRefresher("http://fno:8024/", transport=httpx.MockTransport(handler))
    assert r.configured() and asyncio.run(r.refresh(T1, 4)) == {"ok": True}
    assert seen == {"url": "http://fno:8024/api/fno/bi/metrics/snapshot", "tenant": T1}
    assert not A.HttpMetricsRefresher("").configured()


def test_scrub_removes_contact_details_before_anything_leaves_the_platform():
    out = J.excerpt("---\nsource: x\n---\nmail a.b@c.co.za, phone 011 555 1234, id 8001015009087, Bearer abcdefghijklmnop1234")
    assert not any(x in out for x in ("a.b@c.co.za", "555 1234", "8001015009087", "abcdefghijklmnop1234")) and "source: x" not in out
