"""Metric catalog validity, deterministic fact writer (idempotent), query hook, endpoints, scheduler. No network."""
from __future__ import annotations

import asyncio
import json
import pathlib
import re
import uuid
from datetime import date, datetime, timezone

import httpx
import pytest
from sqlalchemy import text

from services.fno_intelligence import bi_metrics_writer as w
from services.fno_intelligence import bi_semantic as sem
from services.fno_intelligence import database
from services.fno_intelligence import metric_catalog as mc
from services.fno_intelligence.forecast_models import FORECAST_TABLES
from services.fno_intelligence.models import Base
from services.fno_intelligence.tests.bi_harness import TENANT_A, TENANT_B, env, resp_json, run, seed_billing

TODAY = date(2026, 4, 15)       # seed_billing has invoices in Jan, Feb, Mar 2026
INV = "billing.revenue_invoiced.month"


class FakeSink:
    """Behaves like tenant_memory's upsert: identity-keyed, reports inserted/updated."""
    def __init__(self, configured=True, fail=False):
        self._configured, self.fail, self.store, self.calls = configured, fail, {}, []

    def configured(self):
        return self._configured

    async def write(self, tenant, fact):
        if self.fail:
            raise w.SinkError("down")
        self.calls.append((tenant, fact))
        k = (str(tenant), fact["metric_key"], json.dumps(fact["dimensions"], sort_keys=True), fact["period_start"],
             fact["period_end"], fact["kind"], fact.get("model_version", ""))
        inserted = k not in self.store
        self.store[k] = fact
        return {"id": "id", "inserted": inserted}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("BI_METRICS_METRIC_PAUSE_S", "0")
    w.reset_hook_state()
    yield
    w.set_sink(None)


# ── catalog ──────────────────────────────────────────────────────────────────

def test_catalog_is_valid_against_the_governed_registry():
    keys = set()
    for m in mc.CATALOG:
        assert re.match(r"^[a-z][a-z0-9_.]{0,118}$", m.key), m.key
        assert m.key not in keys
        keys.add(m.key)
        ds = sem.DATASETS[m.dataset]
        assert ds.measure(m.measure) is not None, (m.key, "measure")
        spec = sem.QuerySpec(**m.query_spec(date(2025, 1, 1), date(2026, 1, 1)))
        sem.validate_spec_only(spec)                              # full compile against the registry
        if m.shape == "series":
            td = ds.dim(m.time_dimension)
            assert td is not None and td.type == "time" and m.grain in td.grains, m.key
            assert m.grain in mc.MIN_HISTORY
        else:
            assert not m.forecastable, "snapshots are never forecast"
            for d in m.snapshot_dimensions:
                assert ds.dim(d) is not None and ds.dim(d).type == "category", (m.key, d)
        for f in m.filters:
            assert ds.dim(f["field"]) is not None
        assert m.unit in ("ZAR", "count", "hours", "percent")
        if m.forecastable:
            assert m.history_needed >= 12 and 1 <= m.default_horizon <= mc.MAX_HORIZON[m.grain]
    assert len([m for m in mc.CATALOG if m.forecastable]) >= 10


def test_catalog_covers_the_required_business_metrics():
    need = {"billing.revenue_invoiced.month", "billing.revenue_collected.month", "billing.outstanding_by_aging", "crm.new_customers.month",
            "sales.leads_created.month", "sales.leads_won.month", "sales.pipeline_value_by_stage", "support.tickets_opened.week",
            "support.avg_resolution_hours.week", "billing.cancellations.month", "network.sla_breaches.month",
            "marketing.campaign_sends.month", "marketing.campaign_conversions.month"}
    assert need <= set(mc.BY_KEY)


def test_period_arithmetic():
    assert mc.period_end(date(2026, 2, 1), "month") == date(2026, 2, 28)
    assert mc.period_end(date(2026, 12, 1), "month") == date(2026, 12, 31)
    assert mc.period_start_for(date(2026, 10, 10), "week") == date(2026, 10, 5)         # Monday
    assert mc.add_periods(date(2026, 1, 1), "month", -2) == date(2025, 11, 1)
    assert mc.add_periods(date(2026, 11, 1), "month", 3) == date(2027, 2, 1)


# ── pure result -> facts ─────────────────────────────────────────────────────

COLS = [{"id": "created_at", "kind": "time"}, {"id": "invoiced", "kind": "measure"}]
M = mc.BY_KEY[INV]


def test_series_facts_zero_fill_and_skip_in_progress_period():
    rows = [["2026-01-01", 10.0], ["2026-03-01", 30.0], ["2026-04-01", 99.0]]
    facts = w.facts_from_series(M, COLS, rows, spec={"dataset": "billing_invoices", "measures": ["invoiced"]}, today=TODAY)
    assert [(f["period_start"], f["value"]) for f in facts] == [("2026-01-01", 10.0), ("2026-02-01", 0.0), ("2026-03-01", 30.0)]
    f = facts[0]
    assert (f["kind"], f["written_by"], f["method"], f["period_end"], f["grain"], f["unit"]) == \
           ("actual", "bi_semantic", "semantic_query", "2026-01-31", "month", "ZAR")


def test_averages_are_not_zero_filled_and_negatives_clipped():
    avg = mc.BY_KEY["support.avg_resolution_hours.week"]
    cols = [{"id": "resolved_at", "kind": "time"}, {"id": "avg_resolution_hours", "kind": "measure"}]
    facts = w.facts_from_series(avg, cols, [["2026-01-05", 4.0], ["2026-01-19", 6.0]], spec={}, today=TODAY)
    assert [f["period_start"] for f in facts] == ["2026-01-05", "2026-01-19"]
    assert w.facts_from_series(M, COLS, [["2026-01-01", -5.0]], spec={}, today=TODAY)[0]["value"] == 0.0


def test_partial_window_buckets_are_dropped():
    rows = [["2026-01-01", 1.0], ["2026-02-01", 2.0], ["2026-03-01", 3.0]]
    facts = w.facts_from_series(M, COLS, rows, spec={}, today=TODAY, date_from=date(2026, 1, 15), date_to=date(2026, 3, 15))
    assert [f["period_start"] for f in facts] == ["2026-02-01"]


def test_snapshot_shape_dimension_facts():
    m = mc.BY_KEY["sales.pipeline_value_by_stage"]
    cols = [{"id": "stage", "kind": "dimension"}, {"id": "open_value", "kind": "measure"}]
    facts = w.facts_from_snapshot(m, cols, [["Proposal", 5000.0], ["Won", None], ["Qualified", 1200.0]], spec={}, today=TODAY)
    assert [f["dimensions"] for f in facts] == [{"stage": "Proposal"}, {"stage": "Qualified"}]
    assert all(f["period_start"] == f["period_end"] == "2026-04-15" and f["grain"] == "day" for f in facts)


# ── snapshot against the real governed query path ────────────────────────────

def test_snapshot_writes_actuals_idempotently_and_tenant_scoped(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            await seed_billing(e)
            sink = FakeSink()
            async with database.get_session_factory()() as db:
                s1 = await w.snapshot_metrics(db, TENANT_A, [INV], sink=sink, today=TODAY)
                s2 = await w.snapshot_metrics(db, TENANT_A, [INV], sink=sink, today=TODAY)
            assert s1[INV] == {"facts": 3, "inserted": 3, "updated": 0}
            assert s2[INV] == {"facts": 3, "inserted": 0, "updated": 3}           # same rows refreshed, none duplicated
            assert len(sink.store) == 3
            vals = {f["period_start"]: f["value"] for f in sink.store.values()}
            assert vals == {"2026-01-01": 1000.0, "2026-02-01": 1100.0, "2026-03-01": 1800.0}   # drafts/voided excluded
            assert 777777.0 not in vals.values()                                    # tenant B never leaks
            f = next(iter(sink.store.values()))
            assert f["source_query"]["dataset"] == "billing_invoices" and f["source_query"]["time"]["grain"] == "month"
            assert all(t == TENANT_A for t, _ in sink.calls)
    run(scenario())


def test_snapshot_isolates_failures_and_requires_configured_sink(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            await seed_billing(e)
            async with database.get_session_factory()() as db:
                with pytest.raises(w.SinkError):
                    await w.snapshot_metrics(db, TENANT_A, [INV], sink=FakeSink(configured=False), today=TODAY)
                out = await w.snapshot_metrics(db, TENANT_A, [INV, "crm.new_customers.month"], sink=FakeSink(fail=True), today=TODAY)
            assert "error" in out[INV] and out[INV]["facts"] == 0
            assert set(out) == {INV, "crm.new_customers.month"}                       # the second metric still ran
            with pytest.raises(KeyError):
                mc.select(["nope"])
    run(scenario())


def test_every_catalogued_metric_snapshots_against_empty_tables(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            async with database.get_session_factory()() as db:
                out = await w.snapshot_metrics(db, TENANT_A, sink=FakeSink(), today=TODAY)
            assert len(out) == len(mc.CATALOG)
            assert not [k for k, v in out.items() if v.get("error")], out
    run(scenario())


# ── writer permission path ───────────────────────────────────────────────────

def test_http_sink_posts_to_metric_facts_api_with_writer_identity():
    seen = []

    async def handler(req: httpx.Request):
        seen.append(req)
        return httpx.Response(201, json={"id": "1", "inserted": True})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            sink = w.HttpFactSink("http://tenant_memory:8025/", client=c)
            assert sink.configured()
            fact = w.facts_from_series(M, COLS, [["2026-01-01", 10.0]], spec={"dataset": "billing_invoices", "measures": ["invoiced"]},
                                       today=TODAY)[0]
            await sink.write(TENANT_A, fact)
    run(scenario())
    req = seen[0]
    assert req.url.path == "/api/v1/metrics/facts" and req.method == "POST"
    assert req.headers["x-tenant-id"] == str(TENANT_A)
    assert "metrics.write" in req.headers["x-permissions"].split(",")
    body = json.loads(req.content)
    assert body["written_by"] == "bi_semantic" and body["kind"] == "actual"
    mod = pytest.importorskip("services.tenant_memory.knowledge.metrics")
    mod.MetricFactIn(**body)                                                          # the real schema accepts what we send
    with pytest.raises(Exception):
        mod.MetricFactIn(**{**body, "written_by": "agent"})                           # and rejects non-deterministic writers


def test_http_sink_surfaces_api_refusal_and_unconfigured_state():
    async def handler(req):
        return httpx.Response(403, json={"detail": "metrics.write permission required"})

    async def scenario():
        assert not w.HttpFactSink("").configured()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            with pytest.raises(w.SinkError, match="403"):
                await w.HttpFactSink("http://x", client=c).write(TENANT_A, {})
    run(scenario())


# ── hook on bi query ─────────────────────────────────────────────────────────

BODY = {"dataset": "billing_invoices", "measures": ["invoiced"], "time": {"dimension": "created_at", "grain": "month"}}


def test_query_hook_records_actuals_best_effort_and_rate_limited(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            await seed_billing(e)
            sink = FakeSink()
            w.set_sink(sink)
            assert resp_json(await e.req("POST", "/query", json=BODY))["rows"]
            await asyncio.sleep(0.05)
            assert {f["period_start"] for f in sink.store.values()} >= {"2026-01-01", "2026-02-01", "2026-03-01"}
            n = len(sink.calls)
            await e.req("POST", "/query", json=BODY)                                  # inside the interval: no refresh
            await asyncio.sleep(0.05)
            assert len(sink.calls) == n
            monkeypatch.setenv("BI_METRIC_HOOK_MIN_INTERVAL_S", "0")
            await e.req("POST", "/query", json=BODY)
            await asyncio.sleep(0.05)
            assert len(sink.calls) > n and len(sink.store) == len({k for k in sink.store})   # refreshed, still same identities
    run(scenario())


def test_query_hook_ignores_non_catalogued_shapes_and_never_fails_the_query(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            await seed_billing(e)
            sink = FakeSink()
            w.set_sink(sink)
            other = {**BODY, "dimensions": ["status"]}                                # extra dimension: not the catalogued metric
            assert resp_json(await e.req("POST", "/query", json=other))
            filtered = {**BODY, "filters": [{"field": "status", "op": "eq", "value": "paid"}]}
            assert resp_json(await e.req("POST", "/query", json=filtered))
            await asyncio.sleep(0.05)
            assert sink.calls == []
            w.set_sink(FakeSink(fail=True))
            monkeypatch.setenv("BI_METRIC_HOOK_MIN_INTERVAL_S", "0")
            assert resp_json(await e.req("POST", "/query", json=BODY))["rows"]        # sink down: query unaffected
            await asyncio.sleep(0.05)
            monkeypatch.setenv("BI_METRIC_HOOK_ENABLED", "false")
            sink2 = FakeSink()
            w.set_sink(sink2)
            await e.req("POST", "/query", json=BODY)
            await asyncio.sleep(0.05)
            assert sink2.calls == []
    run(scenario())


def test_hook_is_inert_without_a_configured_sink(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            await seed_billing(e)
            monkeypatch.delenv("TENANT_MEMORY_SERVICE_URL", raising=False)
            assert resp_json(await e.req("POST", "/query", json=BODY))["rows"]
    run(scenario())


def test_match_metric_resolves_default_time_dimension():
    assert w.match_metric(sem.QuerySpec(dataset="billing_invoices", measures=["invoiced"],
                                        time={"dimension": "created_at", "grain": "month"})).key == INV
    assert w.match_metric(sem.QuerySpec(dataset="billing_invoices", measures=["invoiced"], time={"grain": "month"})).key == INV
    assert w.match_metric(sem.QuerySpec(dataset="billing_invoices", measures=["invoiced"], time={"grain": "week"})) is None
    assert w.match_metric(sem.QuerySpec(dataset="billing_invoices", measures=["invoiced", "collected"],
                                        time={"grain": "month"})) is None
    assert w.match_metric(sem.QuerySpec(dataset="sales_pipeline", measures=["open_value"], dimensions=["stage"])).key == \
           "sales.pipeline_value_by_stage"


# ── endpoints ────────────────────────────────────────────────────────────────

def test_endpoints_catalog_snapshot_and_forecast_queue(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            async with e.engine.begin() as conn:
                await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=FORECAST_TABLES))
            await seed_billing(e)
            cat = resp_json(await e.req("GET", "/metrics/catalog", roles="viewer"))
            assert len(cat["metrics"]) == len(mc.CATALOG) and cat["history_rules"]["min_history"]["month"] == 12
            assert next(m for m in cat["metrics"] if m["key"] == INV)["forecastable"] is True
            monkeypatch.delenv("TENANT_MEMORY_SERVICE_URL", raising=False)
            assert (await e.req("POST", "/metrics/snapshot", json={"metrics": [INV]}, roles="admin")).status_code == 503
            w.set_sink(FakeSink())
            r = resp_json(await e.req("POST", "/metrics/snapshot", json={"metrics": [INV]}, roles="admin"))
            assert r["errors"] == 0 and r["metrics"][INV]["facts"] >= 3
            assert (await e.req("POST", "/metrics/snapshot", json={"metrics": ["bogus"]}, roles="admin")).status_code == 422
            # forecast queue: only enqueues, dedupes, validates
            q1 = resp_json(await e.req("POST", "/forecast/runs", json={"metrics": [INV], "horizon": 3}, roles="admin"), 202)
            assert q1["status"] == "queued" and q1["deduplicated"] is False and q1["metrics"] == [INV]
            q2 = resp_json(await e.req("POST", "/forecast/runs", json={}, roles="admin"), 202)
            assert q2["id"] == q1["id"] and q2["deduplicated"] is True
            assert (await e.req("POST", "/forecast/runs", json={"metrics": ["sales.pipeline_value_by_stage"]}, roles="admin")).status_code == 422
            assert (await e.req("POST", "/forecast/runs", json={"metrics": [INV], "horizon": 99}, tenant=TENANT_B, roles="admin")).status_code == 422
            lst = resp_json(await e.req("GET", "/forecast/runs", roles="viewer"))
            assert [x["id"] for x in lst["runs"]] == [q1["id"]]
            assert resp_json(await e.req("GET", "/forecast/runs", tenant=TENANT_B, roles="viewer"))["runs"] == []   # tenant scoped
    run(scenario())


def test_admin_tier_required_when_roles_are_enforced(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            monkeypatch.setenv("ANALYTICS_ENFORCE_ROLES", "true")
            assert (await e.req("POST", "/metrics/snapshot", json={}, roles="viewer")).status_code == 403
            assert (await e.req("POST", "/forecast/runs", json={}, roles="analyst")).status_code == 403
    run(scenario())


# ── scheduler ────────────────────────────────────────────────────────────────

def test_daily_snapshot_is_tenant_sequential(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            await e.sql("CREATE TABLE tenants (id CHAR(32))")
            await e.insert("tenants", id=TENANT_A)
            await e.insert("tenants", id=TENANT_B)
            await seed_billing(e)
            sink = FakeSink()
            rep = await w.run_snapshot_for_all_tenants(database.get_session_factory(), sink=sink, today=TODAY, tenant_pause_s=0)
            assert set(rep) == {str(TENANT_A), str(TENANT_B)}
            order = [t for t, _ in sink.calls]
            assert order == sorted(order, key=lambda t: [str(TENANT_A), str(TENANT_B)].index(str(t)))   # A's writes then B's
    run(scenario())


def test_scheduler_gates(monkeypatch):
    monkeypatch.setenv("BI_METRICS_SNAPSHOT_ENABLED", "false")
    assert not w.scheduler_enabled()
    assert asyncio.run(w.run_metrics_scheduler()) is None
    monkeypatch.setenv("BI_METRICS_SNAPSHOT_ENABLED", "true")
    monkeypatch.delenv("TENANT_MEMORY_SERVICE_URL", raising=False)
    assert w.scheduler_enabled() and asyncio.run(w.run_metrics_scheduler()) is None      # idle: no sink URL


def test_writer_has_no_llm_dependency():
    root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("bi_metrics_writer.py", "metric_catalog.py", "bi_metrics_routes.py"):
        src = (root / name).read_text(encoding="utf-8").lower()
        for banned in ("llm_complete", "openrouter", "anthropic", "openai", "ollama", "bi_ai"):
            assert banned not in src, (name, banned)
