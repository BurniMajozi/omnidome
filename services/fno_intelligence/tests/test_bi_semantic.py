"""Semantic layer: registry validation, parameterised SQL, injection resistance, tenant isolation, caps."""

import uuid

import pytest

from services.fno_intelligence import bi_semantic as sem
from services.fno_intelligence.tests.bi_harness import TENANT_A, TENANT_B, env, resp_json, run, seed_billing


def q(**kw):
    return {"dataset": "billing_invoices", **kw}


def test_catalog_has_datasets_skips_and_limits(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            cat = resp_json(await e.req("GET", "/datasets", roles="viewer"))
            ids = {d["id"] for d in cat["datasets"]}
            assert {"billing_invoices", "billing_payments", "billing_subscriptions", "crm_customers", "sales_leads", "sales_pipeline",
                    "support_tickets", "network_services", "marketing_campaigns", "social_daily", "social_posts", "competitor_changes",
                    "campaign_sentiment"} <= ids
            assert cat["skipped"] and all("reason" in s for s in cat["skipped"])
            inv = next(d for d in cat["datasets"] if d["id"] == "billing_invoices")
            assert {m["id"] for m in inv["measures"]} >= {"invoiced", "collected", "outstanding", "arpu"}
            assert not any(m["id"].startswith("_") for d in cat["datasets"] for m in d["measures"])
            assert cat["limits"]["max_rows"] == 1000
    run(scenario())


def test_every_dataset_runs_against_empty_tables(tmp_path, monkeypatch):
    """Every measure x dimension x grain compiles to valid SQL (catches typos in registry fragments)."""
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            for ds in sem.DATASETS.values():
                measures = [m.id for m in ds.measures if not m.id.startswith("_")]
                cats = [d.id for d in ds.dimensions if d.type == "category"]
                body = {"dataset": ds.id, "measures": measures, "dimensions": cats[:2],
                        "time": {"dimension": ds.default_time, "grain": "month", "from": "2026-01-01", "to": "2026-12-31"}}
                r = await e.req("POST", "/query", json=body)
                assert r.status_code == 200, (ds.id, r.text)
                for d in ds.dimensions:
                    if d.type == "time":
                        for g in d.grains:
                            r = await e.req("POST", "/query", json={"dataset": ds.id, "measures": measures[:1],
                                                                    "time": {"dimension": d.id, "grain": g}})
                            assert r.status_code == 200, (ds.id, d.id, g, r.text)
                    else:
                        r = await e.req("POST", "/query", json={"dataset": ds.id, "measures": measures[:2], "dimensions": [d.id]})
                        assert r.status_code == 200, (ds.id, d.id, r.text)
    run(scenario())


def test_invoice_numbers_and_exclusions(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            await seed_billing(e)
            r = resp_json(await e.req("POST", "/query", json=q(measures=["invoiced", "collected", "outstanding", "overdue_amount",
                                                                          "invoice_count", "customers_billed", "collection_rate"])))
            t = r["totals"]
            assert t["invoiced"] == pytest.approx(3900)        # drafts, voided and tenant B are excluded
            assert t["collected"] == pytest.approx(2200)
            assert t["outstanding"] == pytest.approx(1700)
            assert t["overdue_amount"] == pytest.approx(400)   # the 2099 invoice is not overdue
            assert t["invoice_count"] == 4 and t["customers_billed"] == 3
            assert t["collection_rate"] == pytest.approx(2200 / 3900)
            assert [c["id"] for c in r["columns"]] == ["invoiced", "collected", "outstanding", "overdue_amount", "invoice_count",
                                                       "customers_billed", "collection_rate"]
            assert r["meta"]["row_count"] == 1 and r["meta"]["truncated"] is False and r["meta"]["dataset"] == "billing_invoices"

            r = resp_json(await e.req("POST", "/query", json=q(measures=["invoiced"], time={"dimension": "created_at", "grain": "month"})))
            assert r["rows"] == [["2026-01-01", 1000.0], ["2026-02-01", 1100.0], ["2026-03-01", 1800.0]]
            assert r["columns"][0]["kind"] == "time" and r["columns"][0]["grain"] == "month"
            assert r["totals"]["invoiced"] == pytest.approx(3900)

            r = resp_json(await e.req("POST", "/query", json=q(measures=["outstanding"], dimensions=["aging_bucket"])))
            buckets = [row[0] for row in r["rows"]]
            assert buckets.index("Current") < buckets.index("90+ days") < buckets.index("Settled")  # ordered by the bucket sort key
            assert dict(map(tuple, r["rows"]))["Current"] == pytest.approx(1300)

            r = resp_json(await e.req("POST", "/query", json=q(measures=["arpu"], time={"grain": "quarter"})))
            assert r["rows"][0][0] == "2026-01-01"
            r = resp_json(await e.req("POST", "/query", json=q(measures=["invoiced"], dimensions=["plan"])))
            assert dict(map(tuple, r["rows"])) == {"Unassigned": pytest.approx(2900), "Fibre 100": pytest.approx(1000)}
    run(scenario())


def test_tenant_isolation(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            await seed_billing(e)
            b = resp_json(await e.req("POST", "/query", tenant=TENANT_B, json=q(measures=["invoiced"])))
            assert b["totals"]["invoiced"] == pytest.approx(777777)
            a = resp_json(await e.req("POST", "/query", tenant=TENANT_A, json=q(measures=["invoiced"])))
            assert a["totals"]["invoiced"] == pytest.approx(3900)
            c = resp_json(await e.req("POST", "/query", tenant=uuid.uuid4(), json=q(measures=["invoiced"])))
            assert c["totals"]["invoiced"] == 0
    run(scenario())


def test_unknown_fields_and_bad_ops_are_422(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            bad = [
                {"dataset": "nope", "measures": ["x"]},
                q(measures=["revenue"]),
                q(measures=["invoiced"], dimensions=["nope"]),
                q(measures=["invoiced"], dimensions=["created_at"]),                    # time dim must go through `time`
                q(measures=["invoiced"], time={"dimension": "status", "grain": "month"}),
                q(measures=["invoiced"], time={"dimension": "created_at", "grain": "decade"}),
                q(measures=["invoiced"], filters=[{"field": "status", "op": "like", "value": "x"}]),
                q(measures=["invoiced"], filters=[{"field": "status", "op": "gt", "value": "x"}]),   # not allowed on category
                q(measures=["invoiced"], filters=[{"field": "invoiced", "op": "gt", "value": 1}]),   # measures are not filter fields
                q(measures=["invoiced"], filters=[{"field": "created_at", "op": "gte", "value": "not-a-date"}]),
                q(measures=["invoiced"], filters=[{"field": "status", "op": "in", "value": []}]),
                q(measures=["invoiced"], order_by=[{"field": "collected", "dir": "asc"}]),            # not selected
                q(measures=["invoiced"], limit=5000),
                q(measures=["invoiced"], limit=0),
                q(measures=["invoiced"], extra_field=1),
                q(measures=["invoiced", "invoiced"]),
                q(),                                                                                  # nothing selected
                q(measures=["Invoiced"]),
                q(measures=["invoiced; DROP TABLE invoices"]),
                q(measures=["invoiced"], time={"from": "2026-03-01", "to": "2026-01-01"}),
            ]
            for body in bad:
                r = await e.req("POST", "/query", json=body)
                assert r.status_code == 422, (body, r.status_code, r.text[:200])
            assert resp_json(await e.req("POST", "/query", json=q(measures=["invoice_count"])))["totals"]["invoice_count"] == 0
    run(scenario())


def test_sql_is_parameterised_and_injection_values_stay_data(tmp_path, monkeypatch):
    evil = "x' OR '1'='1'; DROP TABLE invoices; --"
    spec = sem.QuerySpec.model_validate(q(measures=["invoiced"], dimensions=["status"], filters=[
        {"field": "status", "op": "eq", "value": evil},
        {"field": "plan", "op": "in", "value": [evil, "Fibre 100"]},
        {"field": "plan", "op": "contains", "value": "100%_"}]))
    for d in ("sqlite", "postgresql"):
        c = sem.compile_query(spec, d, TENANT_A)
        assert "DROP" not in c.sql and "OR '1'" not in c.sql and "1=1" not in c.sql
        assert evil in c.params.values()
        assert ":tenant" in c.sql and c.params["tenant"] in (TENANT_A, TENANT_A.hex)
        assert "ESCAPE" in c.sql
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            await seed_billing(e)
            r = resp_json(await e.req("POST", "/query", json=q(measures=["invoiced"], filters=[{"field": "status", "op": "eq", "value": evil}])))
            assert r["totals"]["invoiced"] == 0                    # a literal that matches nothing, not "OR 1=1"
            r = resp_json(await e.req("POST", "/query", json=q(measures=["invoiced"], filters=[{"field": "status", "op": "eq", "value": "paid"}])))
            assert r["totals"]["invoiced"] == pytest.approx(2100)
            n = await e.client.get("http://t/api/fno/bi/datasets", headers=e.h())
            assert n.status_code == 200
            r = resp_json(await e.req("POST", "/query", json=q(measures=["invoice_count"])))
            assert r["totals"]["invoice_count"] == 4              # table still intact
    run(scenario())


def test_filters_in_between_contains_and_dates(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            await seed_billing(e)
            f = lambda *fl, **kw: q(measures=["invoiced"], filters=list(fl), **kw)  # noqa: E731
            async def total(body):
                return resp_json(await e.req("POST", "/query", json=body))["totals"]["invoiced"]
            assert await total(f({"field": "status", "op": "in", "value": ["paid", "sent"]})) == pytest.approx(3400)
            assert await total(f({"field": "status", "op": "not_in", "value": ["paid"]})) == pytest.approx(1800)
            assert await total(f({"field": "plan", "op": "contains", "value": "FIBRE"})) == pytest.approx(1000)
            assert await total(f({"field": "created_at", "op": "between", "value": ["2026-02-01", "2026-02-28"]})) == pytest.approx(1100)
            assert await total(f({"field": "created_at", "op": "eq", "value": "2026-03-10"})) == pytest.approx(1300)
            assert await total(f({"field": "created_at", "op": "lte", "value": "2026-03-10"})) == pytest.approx(3400)
            assert await total(f({"field": "created_at", "op": "gt", "value": "2026-03-10"})) == pytest.approx(500)
            assert await total(q(measures=["invoiced"], time={"dimension": "created_at", "from": "2026-02-01", "to": "2026-02-28"})) == pytest.approx(1100)
            assert await total(f({"field": "due_date", "op": "gte", "value": "2099-01-01"})) == pytest.approx(1300)
            assert await total(f({"field": "plan", "op": "is_null"})) == 0
    run(scenario())


def test_limit_truncation_and_order(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            await seed_billing(e)
            r = resp_json(await e.req("POST", "/query", json=q(measures=["invoiced"], time={"grain": "day"}, limit=2)))
            assert r["meta"]["truncated"] is True and r["meta"]["row_count"] == 2
            assert r["totals"]["invoiced"] == pytest.approx(3900)      # totals cover ALL rows, not just the page
            r = resp_json(await e.req("POST", "/query", json=q(measures=["invoiced"], dimensions=["status"], order_by=[{"field": "invoiced", "dir": "desc"}])))
            vals = [row[1] for row in r["rows"]]
            assert vals == sorted(vals, reverse=True)
    run(scenario())


def test_missing_source_table_is_503_not_500(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            await e.sql("DROP TABLE tickets")
            r = await e.req("POST", "/query", json={"dataset": "support_tickets", "measures": ["ticket_count"]})
            assert r.status_code == 503 and "could not be read" in r.json()["detail"]
            assert resp_json(await e.req("POST", "/query", json={"dataset": "crm_customers", "measures": ["customer_count"]}))
    run(scenario())


def test_rate_limit_per_tenant(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            monkeypatch.setenv("BI_QUERY_RATE_PER_MIN", "3")
            sem.reset_rate_limits()
            body = {"dataset": "crm_customers", "measures": ["customer_count"]}
            for _ in range(3):
                assert (await e.req("POST", "/query", json=body)).status_code == 200
            assert (await e.req("POST", "/query", json=body)).status_code == 429
            assert (await e.req("POST", "/query", tenant=TENANT_B, json=body)).status_code == 200   # other tenant unaffected
    run(scenario())


def test_roles_and_auth(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            assert (await e.req("POST", "/query", roles="viewer", json={"dataset": "crm_customers", "measures": ["customer_count"]})).status_code == 200
            r = await e.client.post("http://t/api/fno/bi/query", json={"dataset": "crm_customers", "measures": ["customer_count"]})
            assert r.status_code in (401, 403)
    run(scenario())


def test_chart_suggestions_rules():
    s = lambda **kw: sem.suggest_charts(sem.SuggestSpec.model_validate({"dataset": "billing_invoices", **kw}))  # noqa: E731
    assert s(measures=["invoiced"], time={"grain": "month"})["recommended"] == "line"
    assert s(measures=["invoiced"], dimensions=["status"], time={"grain": "month"})["recommended"] == "stacked_column"
    assert s(measures=["invoiced"], dimensions=["plan"])["recommended"] == "bar"                       # medium cardinality ranked
    low = s(measures=["invoiced"], dimensions=["status"])
    assert low["recommended"] == "bar" or low["suggestions"][0]["type"] in ("bar", "donut")
    assert {x["type"] for x in low["suggestions"]} >= {"donut", "column", "table"}
    assert s(measures=["invoiced", "collection_rate"], time={"grain": "month"})["recommended"] == "combo"   # mixed units
    assert s(measures=["collection_rate"], dimensions=["status"])["suggestions"][0]["type"] != "donut"         # ratios are not additive
    assert s(measures=["invoiced", "outstanding"])["recommended"] == "kpi"
    pie_ok = s(measures=["invoiced"], dimensions=["status"], ) ["suggestions"]
    assert all(x["series_mapping"] is not None for x in pie_ok)
    assert s(measures=["invoiced"], dimensions=["status"], row_count=40)["recommended"] == "bar"
    again = s(measures=["invoiced"], dimensions=["plan", "status"])
    assert again == s(measures=["invoiced"], dimensions=["plan", "status"])                                  # deterministic
    with pytest.raises(Exception):
        s(measures=["nope"])


def test_chart_suggestions_endpoints(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            r = resp_json(await e.req("GET", "/chart-suggestions?dataset=billing_invoices&measures=invoiced&grain=month", roles="viewer"))
            assert r["recommended"] == "line" and r["suggestions"][0]["series_mapping"]["x"] == "created_at"
            r = resp_json(await e.req("POST", "/chart-suggestions", json={"dataset": "billing_invoices", "measures": ["invoiced"], "dimensions": ["plan"]}))
            assert r["recommended"] == "bar"
            assert (await e.req("GET", "/chart-suggestions?dataset=zzz&measures=a")).status_code == 422
    run(scenario())
