"""Deck documents: validation, CRUD, versioning, optimistic concurrency, roles, refresh snapshots, resolve and export."""

import asyncio
import copy
import json

import pytest

from services.fno_intelligence import bi_deck_model as dm
from services.fno_intelligence.tests.bi_harness import TENANT_A, TENANT_B, USER2, env, resp_json, run, seed_billing

REV = {"dataset": "billing_invoices", "measures": ["invoiced", "outstanding"], "time": {"dimension": "created_at", "grain": "month"}}
TOT = {"dataset": "billing_invoices", "measures": ["invoiced", "collected", "outstanding"]}


def doc_basic(title="Q1 Review"):
    return {
        "title": title, "queries": {"rev": REV, "tot": TOT},
        "slides": [
            {"id": "s1", "layout": "title", "title": title},
            {"id": "s2", "layout": "chart_plus_text", "title": "Revenue", "notes": "Total {{tot.invoiced|currency}} this period.", "blocks": [
                {"type": "chart", "id": "c1", "chart_type": "column", "title": "Invoiced by month", "query_ref": "rev",
                 "series": {"x": "created_at", "y": ["invoiced"]}},
                {"type": "text", "id": "t1", "items": [{"text": "Invoiced {{rev.invoiced.last}} in {{rev.invoiced.last.label}}, {{rev.invoiced.delta_pct}} vs prior.", "bullet": True}]}]},
            {"id": "s3", "layout": "kpi_strip", "title": "KPIs", "blocks": [
                {"type": "kpi", "id": "k1", "label": "Outstanding", "value_ref": "tot.outstanding", "delta_ref": "rev.outstanding.delta"},
                {"type": "table", "id": "tb1", "title": "By plan", "query": {"dataset": "billing_invoices", "measures": ["invoiced"], "dimensions": ["plan"]}}]},
        ]}


async def create(e, doc=None, **kw):
    return resp_json(await e.req("POST", "/decks", json={"title": "Q1 Review", "doc": doc if doc is not None else doc_basic(), **kw}), 201)


def put(e, deck, version=None, **body):
    h = {"If-Match": str(version if version is not None else deck["version"])}
    return e.req("PUT", f"/decks/{deck['id']}", headers=h, json=body)


def test_validation_accepts_good_doc_and_fills_defaults():
    doc, warnings, qm = dm.validate_deck_doc(doc_basic())
    assert qm == {"rev": ["invoiced", "outstanding"], "tot": ["invoiced", "collected", "outstanding"], "tb1": ["invoiced"]}
    table = doc.slides[2].blocks[1]
    assert [c.field for c in table.columns] == ["plan", "invoiced"]       # default columns from the query
    assert warnings == []


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d["queries"]["rev"].update(dataset="nope"), "Unknown dataset"),
    (lambda d: d["queries"]["rev"].update(measures=["ghost"]), "Unknown measure"),
    (lambda d: d["slides"][1]["blocks"][0]["series"].update(y=["collected"]), "not a measure of its query"),
    (lambda d: d["slides"][1]["blocks"][0]["series"].update(x="plan"), "not a dimension of its query"),
    (lambda d: d["slides"][1]["blocks"][0].update(query_ref="missing"), "query_ref"),
    (lambda d: d["slides"][1]["blocks"][0].update(chart_type="pie", series={"y": ["invoiced", "outstanding"]}), "exactly one measure"),
    (lambda d: d["slides"][1]["blocks"][1]["items"][0].update(text="{{ghost.total}}"), "unknown query alias"),
    (lambda d: d["slides"][1]["blocks"][1]["items"][0].update(text="{{rev.invoiced|bogus}}"), "unknown format"),
    (lambda d: d["slides"][1].update(notes="{{rev.nothing}}"), "unknown measure or statistic"),
    (lambda d: d["slides"][2]["blocks"][0].update(value_ref="zz.total"), "unknown query alias"),
    (lambda d: d["slides"][2]["blocks"][0].update(value_ref="tot..x;drop"), "invalid reference"),
    (lambda d: d["slides"][2]["blocks"][0].update(id="c1"), "Duplicate block"),
    (lambda d: d["slides"].append(copy.deepcopy(d["slides"][0])), "Duplicate slide id"),
    (lambda d: d["slides"][0].update(layout="weird"), "layout"),
    (lambda d: d["slides"][1]["blocks"][0].update(surprise=1), "surprise"),
    (lambda d: d.update(schema_version=2), "schema_version"),
    (lambda d: d["slides"][2]["blocks"][1].update(columns=[{"field": "collected"}]), "not in its query"),
    (lambda d: d["slides"][1]["blocks"][0].update(colors=["red"]), "#RRGGBB"),
    (lambda d: d["theme"].update(palette={"primary": "blue"}) if "theme" in d else d.update(theme={"palette": {"primary": "blue"}}), "#RRGGBB"),
    (lambda d: d.update(slides=d["slides"] * 40), "at most 60"),
    (lambda d: d["slides"][1]["blocks"][0].update(query={"dataset": "billing_invoices", "measures": ["invoiced"]}), "either query or query_ref"),
    (lambda d: d["slides"][1]["blocks"].append({"type": "image", "id": "im1", "source": {"kind": "url", "url": "http://x.example/a.png"}}), "https"),
    (lambda d: d["slides"][1]["blocks"].append({"type": "image", "id": "im1", "source": {"kind": "brand_logo", "url": "https://x.example/a.png"}}), "brand_logo"),
])
def test_validation_rejects(mutate, needle):
    d = copy.deepcopy(doc_basic())
    mutate(d)
    with pytest.raises(Exception) as ei:
        dm.validate_deck_doc(d)
    assert needle.lower() in str(getattr(ei.value, "detail", ei.value)).lower()


def test_validation_caps():
    d = doc_basic()
    d["slides"] = [{"id": f"x{i}", "layout": "content", "title": "t"} for i in range(dm.MAX_SLIDES + 1)]
    with pytest.raises(Exception):
        dm.validate_deck_doc(d)
    d = doc_basic()
    d["slides"][1]["blocks"] = [{"type": "shape", "id": f"sh{i}"} for i in range(dm.MAX_BLOCKS_PER_SLIDE + 1)]
    with pytest.raises(Exception):
        dm.validate_deck_doc(d)
    d = doc_basic()
    d["slides"][0]["notes"] = "x" * 5000
    with pytest.raises(Exception):
        dm.validate_deck_doc(d)
    d = doc_basic()
    d["slides"][0]["blocks"] = [{"type": "text", "id": "big", "items": [{"text": "y" * 1200} for _ in range(30)] * 1}]
    d["slides"] += [{"id": f"z{i}", "layout": "content", "title": "z", "blocks": [{"type": "text", "id": f"zt{i}", "items": [{"text": "y" * 1200} for _ in range(30)]}]} for i in range(45)]
    with pytest.raises(Exception) as ei:
        dm.validate_deck_doc(d)
    assert "too large" in str(ei.value.detail)


def test_strict_numbers_and_warnings():
    d = doc_basic()
    d["slides"][1]["notes"] = "Revenue grew 15% this year"
    _, warnings, _ = dm.validate_deck_doc(d)
    assert warnings and warnings[0]["literal"] == "15%" and "notes" in warnings[0]["where"]
    d["settings"] = {"strict_numbers": True}
    with pytest.raises(Exception) as ei:
        dm.validate_deck_doc(d)
    assert "strict_numbers" in str(ei.value.detail)


def test_crud_versions_concurrency_and_roles(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            assert (await e.req("POST", "/decks", roles="viewer", json={"title": "x"})).status_code == 403
            d = await create(e)
            assert d["version"] == 1 and d["status"] == "draft" and d["created_by"] and d["slide_count"] == 3
            assert d["doc"]["slides"][2]["blocks"][1]["columns"][0]["field"] == "plan"

            # starter doc when none is given
            s = resp_json(await e.req("POST", "/decks", json={"title": "Blank"}), 201)
            assert s["doc"]["slides"][0]["layout"] == "title" and s["doc"]["title"] == "Blank"
            assert (await e.req("POST", "/decks", json={"title": "Bad", "doc": {"slides": "no"}})).status_code == 422

            # If-Match is mandatory
            assert (await e.req("PUT", f"/decks/{d['id']}", json={"title": "New"})).status_code == 428
            r = await put(e, d, title="Renamed")
            v2 = resp_json(r)
            assert v2["version"] == 2 and v2["title"] == "Renamed" and v2["doc"]["title"] == "Renamed"
            stale = await put(e, d, version=1, title="Stale write")
            assert stale.status_code == 409 and stale.json()["detail"]["current_version"] == 2
            # body base_version works too
            ok = await e.req("PUT", f"/decks/{d['id']}", json={"title": "Via body", "base_version": 2})
            assert resp_json(ok)["version"] == 3

            # concurrent writers: exactly one wins
            cur = resp_json(await e.req("GET", f"/decks/{d['id']}"))
            rs = await asyncio.gather(put(e, cur, title="A"), put(e, cur, title="B"))
            assert sorted(r.status_code for r in rs) == [200, 409]

            # an edit that changes the document, then history
            edited = copy.deepcopy(cur["doc"])
            edited["slides"][0]["title"] = "Edited title slide"
            latest = resp_json(await e.req("GET", f"/decks/{d['id']}"))
            r4 = resp_json(await put(e, latest, doc=edited, note="edit title"))
            versions = resp_json(await e.req("GET", f"/decks/{d['id']}/versions", roles="viewer"))["items"]
            assert [v["version"] for v in versions] == list(range(r4["version"], 0, -1))
            assert versions[0]["note"] == "edit title"
            old = resp_json(await e.req("GET", f"/decks/{d['id']}/versions/1", roles="viewer"))
            assert old["doc"]["slides"][0]["title"] == "Q1 Review"

            # restore creates a NEW version (history is insert-only)
            before = r4["version"]
            rest = resp_json(await e.req("POST", f"/decks/{d['id']}/versions/1/restore", headers={"If-Match": str(before)}))
            assert rest["version"] == before + 1 and rest["doc"]["slides"][0]["title"] == "Q1 Review"
            assert len(resp_json(await e.req("GET", f"/decks/{d['id']}/versions", roles="viewer"))["items"]) == before + 1
            assert (await e.req("POST", f"/decks/{d['id']}/versions/1/restore")).status_code == 428
            assert (await e.req("GET", f"/decks/{d['id']}/versions/99")).status_code == 404

            # invalid edits are rejected and do not bump the version
            bad = copy.deepcopy(rest["doc"])
            bad["slides"][1]["blocks"][0]["series"]["y"] = ["ghost"]
            assert (await put(e, rest, doc=bad)).status_code == 422
            assert resp_json(await e.req("GET", f"/decks/{d['id']}"))["version"] == rest["version"]

            # duplicate
            dup = resp_json(await e.req("POST", f"/decks/{d['id']}/duplicate"), 201)
            assert dup["id"] != d["id"] and dup["title"].startswith("Copy of") and dup["version"] == 1 and dup["doc"]["slides"][1]["id"] == "s2"

            # list / search / tenant isolation
            lst = resp_json(await e.req("GET", "/decks?q=copy", roles="viewer"))
            assert lst["total"] == 1 and "doc" not in lst["items"][0]
            assert resp_json(await e.req("GET", "/decks", roles="viewer", tenant=TENANT_B))["items"] == []
            for m, path in (("GET", ""), ("DELETE", ""), ("GET", "/versions"), ("POST", "/duplicate"), ("POST", "/refresh"), ("GET", "/export/json")):
                r = await e.req(m, f"/decks/{d['id']}{path}", tenant=TENANT_B, roles="admin")
                assert r.status_code == 404, (m, path)
            assert (await e.req("PUT", f"/decks/{d['id']}", tenant=TENANT_B, headers={"If-Match": "1"}, json={"title": "x"})).status_code == 404

            # delete is admin only and removes history
            assert (await e.req("DELETE", f"/decks/{dup['id']}", roles="analyst")).status_code == 403
            assert (await e.req("DELETE", f"/decks/{dup['id']}", roles="admin")).status_code == 204
            assert (await e.req("GET", f"/decks/{dup['id']}")).status_code == 404
    run(scenario())


def test_publish_locks_analyst_edits(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            d = await create(e)
            assert (await e.req("POST", f"/decks/{d['id']}/publish", roles="analyst", json={"published": True})).status_code == 403
            p = resp_json(await e.req("POST", f"/decks/{d['id']}/publish", roles="admin", json={"published": True}))
            assert p["status"] == "published" and p["published_at"] and p["published_by"]
            assert (await put(e, d, title="Sneaky")).status_code == 403
            assert resp_json(await put(e, d, roles="admin", title="Admin edit") if False else await e.req(
                "PUT", f"/decks/{d['id']}", roles="admin", headers={"If-Match": "1"}, json={"title": "Admin edit"}))["title"] == "Admin edit"
            resp_json(await e.req("POST", f"/decks/{d['id']}/publish", roles="admin", json={"published": False}))
            assert resp_json(await e.req("GET", "/decks?status=draft", roles="viewer"))["total"] == 1
    run(scenario())


def test_brand_kit_link_and_cross_tenant_rejected(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            kit = resp_json(await e.req("POST", "/brand-kits", roles="admin", json={"name": "A"}), 201)
            other = resp_json(await e.req("POST", "/brand-kits", tenant=TENANT_B, roles="admin", json={"name": "B"}), 201)
            d = await create(e)
            assert d["brand_kit_id"] == kit["id"] and d["doc"]["brand_kit_id"] == kit["id"]     # default kit applied
            assert (await e.req("POST", "/decks", json={"title": "x", "brand_kit_id": other["id"]})).status_code == 422
            assert (await put(e, d, brand_kit_id=other["id"])).status_code == 422
            cleared = resp_json(await put(e, d, clear_brand_kit=True))
            assert cleared["brand_kit_id"] is None
    run(scenario())


def test_refresh_resolve_export_and_data_snapshots(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            await seed_billing(e)
            await e.req("POST", "/brand-kits", roles="admin", json={"name": "Brand", "company_name": "Acme", "palette": {"primary": "#112233"},
                                                                    "footer_text": "Confidential"})
            d = await create(e)
            run1 = resp_json(await e.req("POST", f"/decks/{d['id']}/refresh"))
            assert run1["as_of"] and set(run1["queries"]) == {"rev", "tot", "tb1"} and run1["errors"] == {}
            assert run1["blocks"] == {"c1": "rev", "tb1": "tb1"}
            assert run1["data"]["tot"]["totals"]["invoiced"] == pytest.approx(3900)
            same = resp_json(await e.req("GET", f"/decks/{d['id']}"))
            assert same["version"] == 1 and same["doc"] == d["doc"]                      # refresh never mutates the document

            res = resp_json(await e.req("POST", f"/decks/{d['id']}/resolve", roles="viewer", json={}))
            assert res["run_id"] == run1["run_id"] and res["as_of"] == run1["as_of"] and res["stale_data"] is False
            s2 = res["slides"][1]
            assert s2["notes"] == "Total R3 900 this period."
            assert s2["blocks"][1]["items"][0]["text"] == "Invoiced R1 800 in 2026-03-01, +63.6% vs prior."
            kpi = res["slides"][2]["blocks"][0]
            assert kpi["value"] == "R1 700" and kpi["delta"] == "+R1 700" and kpi["delta_direction"] == "up"
            assert res["unresolved"] == [] and res["theme"]["palette"]["primary"] == "#112233" and res["theme"]["footer_text"] == "Confidential"

            exp = resp_json(await e.req("GET", f"/decks/{d['id']}/export/json", roles="viewer"))
            assert exp["format"] == "omnidome-deck/1" and exp["deck"]["version"] == 1 and exp["as_of"] == run1["as_of"]
            assert exp["data"]["rev"]["rows"][-1] == ["2026-03-01", 1800.0, 1700.0] and exp["brand_kit"]["company_name"] == "Acme"
            assert exp["doc"]["slides"][1]["blocks"][0]["series"]["y"] == ["invoiced"] and exp["slides"][1]["title"] == "Revenue"

            # data changes after the snapshot: the stored run keeps "as of" numbers until refreshed
            await e.insert("invoices", id=__import__("uuid").uuid4(), tenant_id=TENANT_A, customer_id=__import__("uuid").uuid4(), number="NEW",
                           status="paid", subtotal_zar=1, vat_zar=0, total_zar=5000, amount_paid_zar=5000, due_date="2026-04-30",
                           billing_period_start="2026-04-01", created_at="2026-04-10 08:00:00")
            still = resp_json(await e.req("POST", f"/decks/{d['id']}/resolve", roles="viewer", json={}))
            assert still["slides"][1]["notes"] == "Total R3 900 this period."
            fresh = resp_json(await e.req("POST", f"/decks/{d['id']}/resolve", roles="analyst", json={"refresh": True}))
            assert fresh["slides"][1]["notes"] == "Total R8 900 this period." and fresh["run_id"] != run1["run_id"]
            old = resp_json(await e.req("POST", f"/decks/{d['id']}/resolve", roles="viewer", json={"run_id": run1["run_id"]}))
            assert old["slides"][1]["notes"] == "Total R3 900 this period."
            runs = resp_json(await e.req("GET", f"/decks/{d['id']}/runs", roles="viewer"))["items"]
            assert len(runs) == 2 and "data" not in runs[0]
            assert resp_json(await e.req("GET", f"/decks/{d['id']}/runs/{run1['run_id']}", roles="viewer"))["data"]["tot"]
            assert (await e.req("GET", f"/decks/{d['id']}/runs/{run1['run_id']}", tenant=TENANT_B)).status_code == 404

            # editing the deck marks old data as stale; a viewer cannot force a refresh
            latest = resp_json(await e.req("GET", f"/decks/{d['id']}"))
            resp_json(await put(e, latest, title="Edited"))
            stale = resp_json(await e.req("POST", f"/decks/{d['id']}/resolve", roles="viewer", json={"run_id": fresh["run_id"]}))
            assert stale["stale_data"] is True
            assert (await e.req("POST", f"/decks/{d['id']}/resolve", roles="viewer", json={"refresh": True})).status_code == 403
            assert (await e.req("POST", f"/decks/{d['id']}/refresh", roles="viewer")).status_code == 403
    run(scenario())


def test_unresolvable_tokens_render_dash_and_are_reported(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            await seed_billing(e)
            doc = doc_basic()
            doc["slides"][2]["blocks"][0]["delta_ref"] = "rev.outstanding.delta_pct"    # previous period is 0 -> undefined
            doc["slides"][1]["notes"] = "Placeholder {{?}} stays visible"
            d = await create(e, doc)
            res = resp_json(await e.req("POST", f"/decks/{d['id']}/resolve", roles="analyst", json={"refresh": True}))
            kpi = res["slides"][2]["blocks"][0]
            assert kpi["delta"] is None and kpi["value"] == "R1 700"
            reasons = " ".join(u["reason"] for u in res["unresolved"])
            assert "zero" in reasons and "placeholder" in reasons
            assert res["slides"][1]["notes"] == "Placeholder [add figure] stays visible"
    run(scenario())


def test_failed_query_is_reported_not_fatal(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            d = await create(e)
            await e.sql("DROP TABLE payments")   # unrelated table: fine
            r = resp_json(await e.req("POST", f"/decks/{d['id']}/refresh"))
            assert r["errors"] == {}
            await e.sql("ALTER TABLE invoices RENAME TO invoices_gone")
            r = resp_json(await e.req("POST", f"/decks/{d['id']}/refresh"))
            assert set(r["errors"]) == {"rev", "tot", "tb1"} and r["data"] == {}
            res = resp_json(await e.req("POST", f"/decks/{d['id']}/resolve", json={"run_id": r["run_id"]}))
            assert res["query_errors"] and res["unresolved"]
    run(scenario())


def test_image_url_must_be_safe(tmp_path, monkeypatch):
    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            doc = doc_basic()
            doc["slides"][1]["blocks"].append({"type": "image", "id": "im1", "source": {"kind": "url", "url": "https://cdn.example/a.png"}, "alt": "logo"})
            assert (await e.req("POST", "/decks", json={"title": "x", "doc": doc})).status_code == 201
            doc["slides"][1]["blocks"][-1]["source"]["url"] = "https://127.0.0.1/a.png"
            assert (await e.req("POST", "/decks", json={"title": "x", "doc": doc})).status_code == 422
            doc["slides"][1]["blocks"][-1]["source"]["url"] = "https://localhost/a.png"
            assert (await e.req("POST", "/decks", json={"title": "x", "doc": doc})).status_code == 422
    run(scenario())
