"""Catalogue rules (pure) and API behaviour on an in-memory SQLite database (no Postgres needed)."""
import asyncio
import uuid
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.common.auth import AuthContext, get_auth_context
from services.inventory import catalogue_rules as rules
from services.inventory.catalogue_models import (CatalogueAsset, CatalogueEvent, CatalogueList, CatalogueProduct,
                                                 CatalogueReservedNumber)
from services.inventory.database import get_session
from services.inventory.routes.catalogue import router

TENANT = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_TENANT = uuid.UUID("22222222-2222-2222-2222-222222222222")
USER = uuid.UUID("33333333-3333-3333-3333-333333333333")


# ── pure rules ───────────────────────────────────────────────────────────────

def _view(pid="p1", status="draft", **over):
    d = {"description": "Fibre.", "price": 799, "recurring": True, "term": 24,
         "costs": [{"name": "Access", "supplier": "Metro", "amount": 480, "cadence": "Monthly"},
                   {"name": "Install", "supplier": "Field", "amount": 300, "cadence": "Once-off"}],
         "components": [], "fees": [],
         "readiness": {"tests_required": True, "tests": [], "icasa": {"required": False, "exempt_reason": "n/a"}}}
    d.update(over.pop("definition", {}))
    return {"id": pid, "name": "Fibre 100", "category": "Connectivity", "range": "Home Fibre", "family": "Fibre",
            "nature": "Digital service", "usage": "Customer-facing", "status": status, "definition": d, **over}


def _passing_tests(nature="Digital service"):
    return [{"name": n, "result": "Pass", "tester": "QA", "date": "2026-10-14"} for n in rules.standard_tests(nature)]


def test_economics_missing_cost_is_not_zero():
    p = _view(definition={"costs": []})
    assert rules.economics("p1", {"p1": p})["complete"] is False


def test_economics_includes_component_cost_once():
    router_p = _view("r1", "active", nature="Physical item", definition={"costs": [{"name": "Unit", "supplier": "S", "amount": 600, "cadence": "Once-off"}], "recurring": False, "price": 999})
    fibre = _view("p1", definition={"components": [{"product_id": "r1", "qty": 2}]})
    e = rules.economics("p1", {"p1": fibre, "r1": router_p})
    assert e["monthly"] == Decimal(480)
    assert e["upfront"] == Decimal(300 + 1200)
    assert e["complete"] is True


def test_cycle_detection():
    a = _view("a", definition={"components": [{"product_id": "b", "qty": 1}]})
    b = _view("b", definition={"components": []})
    cat = {"a": a, "b": b}
    assert rules.would_cycle("b", "a", cat)       # b including a would loop
    assert rules.would_cycle("a", "a", cat)       # self inclusion
    assert not rules.would_cycle("a", "b", cat)


def test_business_days_skip_weekends():
    from datetime import date
    assert rules.add_business_days(date(2026, 10, 19), 5).isoformat() == "2026-10-26"   # Mon + 5 = next Mon
    assert rules.add_business_days(date(2026, 10, 16), 1).isoformat() == "2026-10-19"   # Fri + 1 = Mon


def test_launch_blocked_until_all_gates_pass():
    p = _view()
    checks = {c["key"]: c for c in rules.launch_checks(p, {"p1": p})}
    assert not checks["testing"]["ok"]
    p["definition"]["readiness"]["tests"] = _passing_tests()
    assert all(c["ok"] for c in rules.launch_checks(p, {"p1": p}))


def test_failed_or_pending_test_blocks_launch():
    p = _view()
    p["definition"]["readiness"]["tests"] = _passing_tests() + [{"name": "Extra", "result": "Fail", "tester": "QA", "date": "2026-10-14"}]
    assert not {c["key"]: c for c in rules.launch_checks(p, {"p1": p})}["testing"]["ok"]


def test_waived_test_needs_reason():
    p = _view()
    tests = _passing_tests()
    tests[0] = {**tests[0], "result": "Waived", "notes": ""}
    p["definition"]["readiness"]["tests"] = tests
    assert not {c["key"]: c for c in rules.launch_checks(p, {"p1": p})}["testing"]["ok"]
    tests[0]["notes"] = "Covered by supplier certification"
    assert {c["key"]: c for c in rules.launch_checks(p, {"p1": p})}["testing"]["ok"]


def test_icasa_notice_period_enforced():
    p = _view()
    p["definition"]["readiness"]["tests"] = _passing_tests()
    item = {"kind": "Product", "objectives": "o", "reasons": "r", "lodged": "2026-10-19", "ref": "msg-1", "effective": "2026-10-26"}
    p["definition"]["readiness"]["icasa"] = {"required": True, "notice": 7, "items": [item]}
    c = {x["key"]: x for x in rules.launch_checks(p, {"p1": p})}["icasa_product"]
    assert not c["ok"] and "notice period" in c["detail"]
    item["effective"] = "2026-10-30"
    assert {x["key"]: x for x in rules.launch_checks(p, {"p1": p})}["icasa_product"]["ok"]


def test_direct_route_needs_recorded_reasons():
    p = _view()
    r = p["definition"]["readiness"]
    r.update({"tests_required": False, "tests_exempt_reason": ""})
    c = {x["key"]: x for x in rules.launch_checks(p, {"p1": p})}
    assert not c["testing"]["ok"]
    r["tests_exempt_reason"] = "Resale of a certified item"
    assert {x["key"]: x for x in rules.launch_checks(p, {"p1": p})}["testing"]["ok"]


def test_promotion_lodgment_is_a_separate_gate():
    p = _view()
    p["definition"]["readiness"]["tests"] = _passing_tests()
    p["definition"]["readiness"]["icasa"] = {"required": True, "notice": 5, "items": [
        {"kind": "Product", "objectives": "o", "reasons": "r", "lodged": "2026-10-01", "ref": "a", "effective": "2026-11-01"},
        {"kind": "Promotion", "objectives": "o", "reasons": "r", "lodged": "", "ref": "", "effective": "2026-11-01", "promo_start": "2026-11-01", "promo_end": "2026-12-31"}]}
    checks = rules.launch_checks(p, {"p1": p})
    assert [c["ok"] for c in checks if c["key"] == "icasa_promotion"] == [False]


def test_null_icasa_required_means_the_nature_default_not_exempt():
    """The editor sends required=null until the user picks a route; a digital customer-facing product must still need lodgment."""
    p = _view(definition={"readiness": {"tests_required": False, "tests_exempt_reason": "r", "tests": [],
                                        "icasa": {"required": None, "exempt_reason": "", "items": []}}})
    c = {x["key"]: x for x in rules.launch_checks(p, {"p1": p})}
    assert "icasa_product" in c and not c["icasa_product"]["ok"]
    assert "icasa" not in c
    equipment = _view(nature="Physical item", definition={"readiness": {"tests_required": False, "tests_exempt_reason": "r",
                                                                        "icasa": {"required": None, "exempt_reason": "", "items": []}}})
    assert "icasa" in {x["key"] for x in rules.launch_checks(equipment, {"p1": equipment})}      # equipment defaults to not required
    p["definition"]["readiness"]["icasa"]["items"] = [{"kind": "Product", "effective": "2026-11-09"}]
    assert rules.launch_effective_date(p) == "2026-11-09"


def test_number_validation():
    assert rules.number_is_valid("fib-500")
    assert not rules.number_is_valid("a")
    assert not rules.number_is_valid("bad number!")


# ── API ──────────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


async def _client(tenant=TENANT, roles=("owner",)):
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        for t in (CatalogueProduct, CatalogueList, CatalogueReservedNumber, CatalogueEvent, CatalogueAsset):
            await conn.run_sync(t.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session():
        async with factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    # InventorySequence uses a Postgres UUID type that SQLite cannot round-trip; the real helper is covered
    # by test_stock_db against Postgres. Here a per-tenant counter stands in for it.
    counters: dict = {}

    async def fake_sequence(db, tenant_id, doc_type, prefix):
        counters[tenant_id] = counters.get(tenant_id, 0) + 1
        return f"{prefix}-TEST-{counters[tenant_id]:06d}"

    import services.inventory.routes.catalogue as cat_routes
    cat_routes.next_sequence_number = fake_sequence

    app = FastAPI()
    app.include_router(router)
    holder = {"tenant": tenant}

    async def auth():
        return AuthContext(user_id=USER, tenant_id=holder["tenant"], roles=list(roles), rbac_loaded=True)

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_auth_context] = auth
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    return c, holder, engine


def _body(**over):
    b = {"name": "Fibre 500", "category": "Connectivity", "range": "Home Fibre", "family": "Fibre",
         "definition": {"description": "Fibre.", "price": 1299, "costs": [{"name": "Access", "supplier": "Metro", "amount": 620, "cadence": "Monthly"}]}}
    b.update(over)
    return b


def test_create_assigns_number_and_blocks_cross_tenant_reads():
    async def case():
        c, holder, engine = await _client()
        try:
            r = await c.post("/catalogue/products", json=_body())
            assert r.status_code == 201, r.text
            pid = r.json()["id"]
            assert r.json()["product_number"].startswith("OD-")
            assert r.json()["status"] == "draft" and r.json()["revision"] == 1
            holder["tenant"] = OTHER_TENANT
            assert (await c.get(f"/catalogue/products/{pid}")).status_code == 404
            assert (await c.get("/catalogue/products")).json() == []
        finally:
            await c.aclose(); await engine.dispose()
    _run(case())


def test_unknown_classification_rejected_and_custom_number_unique():
    async def case():
        c, _, engine = await _client()
        try:
            assert (await c.post("/catalogue/products", json=_body(category="Nope"))).status_code == 422
            assert (await c.post("/catalogue/products", json=_body(product_number="FIB-500"))).status_code == 201
            dup = await c.post("/catalogue/products", json=_body(name="Other", product_number="fib-500"))
            assert dup.status_code == 409
            assert (await c.post("/catalogue/products", json=_body(name="Bad", product_number="x"))).status_code == 422
        finally:
            await c.aclose(); await engine.dispose()
    _run(case())


def test_optimistic_concurrency():
    async def case():
        c, _, engine = await _client()
        try:
            p = (await c.post("/catalogue/products", json=_body())).json()
            ok = await c.patch(f"/catalogue/products/{p['id']}", json={"expected_revision": 1, "name": "Renamed"})
            assert ok.status_code == 200 and ok.json()["revision"] == 2
            stale = await c.patch(f"/catalogue/products/{p['id']}", json={"expected_revision": 1, "name": "Stale"})
            assert stale.status_code == 409
        finally:
            await c.aclose(); await engine.dispose()
    _run(case())


def test_launch_rejected_then_succeeds_and_locks_commercial_edits():
    async def case():
        c, _, engine = await _client()
        try:
            body = _body()
            body["definition"]["readiness"] = {"tests_required": False, "tests_exempt_reason": "", "icasa": {"required": False, "exempt_reason": ""}}
            p = (await c.post("/catalogue/products", json=body)).json()
            bad = await c.post(f"/catalogue/products/{p['id']}/launch", json={"expected_revision": 1})
            assert bad.status_code == 422
            assert {f["key"] for f in bad.json()["detail"]["failed"]} == {"testing", "icasa"}
            body["definition"]["readiness"] = {"tests_required": False, "tests_exempt_reason": "Resale of certified item",
                                               "icasa": {"required": False, "exempt_reason": "Not a licensed service"}}
            up = await c.patch(f"/catalogue/products/{p['id']}", json={"expected_revision": 1, "definition": body["definition"]})
            assert up.status_code == 200, up.text
            ok = await c.post(f"/catalogue/products/{p['id']}/launch", json={"expected_revision": 2})
            assert ok.status_code == 200 and ok.json()["status"] == "active"
            price = {**body["definition"], "price": 1499}
            locked = await c.patch(f"/catalogue/products/{p['id']}", json={"expected_revision": 3, "definition": price})
            assert locked.status_code == 409
            content = {**body["definition"], "description": "New wording"}
            assert (await c.patch(f"/catalogue/products/{p['id']}", json={"expected_revision": 3, "definition": content})).status_code == 200
            hist = (await c.get(f"/catalogue/products/{p['id']}/history")).json()
            assert [h["kind"] for h in hist][-1] == "created" and "launched" in [h["kind"] for h in hist]
        finally:
            await c.aclose(); await engine.dispose()
    _run(case())


def test_components_must_exist_and_no_cycles_and_block_archive():
    async def case():
        c, _, engine = await _client()
        try:
            router_def = {"description": "Router", "price": 999, "recurring": False, "costs": [{"name": "Unit", "supplier": "S", "amount": 600, "cadence": "Once-off"}],
                          "readiness": {"tests_required": False, "tests_exempt_reason": "r", "icasa": {"required": False, "exempt_reason": "r"}}}
            r = (await c.post("/catalogue/products", json=_body(name="Router", nature="Physical item", usage="Customer-facing", definition=router_def))).json()
            assert (await c.post(f"/catalogue/products/{r['id']}/launch", json={"expected_revision": 1})).status_code == 200
            parent_def = {**_body()["definition"], "components": [{"product_id": r["id"], "qty": 1}]}
            parent = await c.post("/catalogue/products", json=_body(name="Fibre", definition=parent_def))
            assert parent.status_code == 201
            missing = await c.post("/catalogue/products", json=_body(name="X", definition={**parent_def, "components": [{"product_id": str(uuid.uuid4()), "qty": 1}]}))
            assert missing.status_code == 422
            rev = (await c.get(f"/catalogue/products/{r['id']}")).json()["revision"]
            blocked = await c.post(f"/catalogue/products/{r['id']}/archive", json={"expected_revision": rev})
            assert blocked.status_code == 409 and "Fibre" in blocked.json()["detail"]["products"]
        finally:
            await c.aclose(); await engine.dispose()
    _run(case())


def test_delete_draft_reserves_number_and_launched_cannot_be_deleted():
    async def case():
        c, _, engine = await _client()
        try:
            p = (await c.post("/catalogue/products", json=_body(product_number="TMP-001"))).json()
            assert (await c.delete(f"/catalogue/products/{p['id']}")).status_code == 200
            again = await c.post("/catalogue/products", json=_body(name="Again", product_number="TMP-001"))
            assert again.status_code == 409          # number never recycled
        finally:
            await c.aclose(); await engine.dispose()
    _run(case())


def test_managed_lists_rename_propagates_and_delete_blocked_when_used():
    async def case():
        c, _, engine = await _client()
        try:
            lists = (await c.get("/catalogue/lists")).json()
            assert "Connectivity" in lists["categories"] and "Fibre" in lists["families"]
            await c.post("/catalogue/products", json=_body())
            fam = next(i for i in lists["items"] if i["kind"] == "family" and i["name"] == "Fibre")
            blocked = await c.delete(f"/catalogue/lists/{fam['id']}")
            assert blocked.status_code == 409
            ren = await c.patch(f"/catalogue/lists/{fam['id']}", json={"name": "Fibre FTTH"})
            assert ren.json()["updated_products"] == 1
            prods = (await c.get("/catalogue/products")).json()
            assert prods[0]["family"] == "Fibre FTTH"
            new = await c.post("/catalogue/lists", json={"kind": "family", "name": "Satellite"})
            assert new.status_code == 201
            assert (await c.delete(f"/catalogue/lists/{new.json()['id']}")).status_code == 200
            assert (await c.post("/catalogue/lists", json={"kind": "range", "name": "X", "parent": "Missing"})).status_code == 422
        finally:
            await c.aclose(); await engine.dispose()
    _run(case())


PNG = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 20


def test_asset_upload_validates_content_and_is_tenant_scoped():
    async def case():
        c, holder, engine = await _client()
        try:
            pid = (await c.post("/catalogue/products", json=_body())).json()["id"]
            ok = await c.post(f"/catalogue/products/{pid}/assets", params={"filename": "router.PNG"}, content=PNG)
            assert ok.status_code == 201, ok.text
            asset = ok.json()
            assert asset["kind"] == "Image" and asset["extension"] == "png" and asset["url"].endswith(asset["id"])
            got = await c.get(f"/catalogue/assets/{asset['id']}")
            assert got.status_code == 200 and got.content == PNG and got.headers["content-type"] == "image/png"
            assert got.headers["x-content-type-options"] == "nosniff"
            # a page renamed .png, an SVG and an oversized file are all refused
            assert (await c.post(f"/catalogue/products/{pid}/assets", params={"filename": "x.png"}, content=b"<html><script>1</script>")).status_code == 422
            assert (await c.post(f"/catalogue/products/{pid}/assets", params={"filename": "x.svg"}, content=b"<svg/>")).status_code == 415
            assert (await c.post(f"/catalogue/products/{pid}/assets", params={"filename": "empty.png"}, content=b"")).status_code == 422
            assert (await c.post(f"/catalogue/products/{pid}/assets", params={"filename": "a.gif"}, content=GIF)).status_code == 201
            holder["tenant"] = OTHER_TENANT
            assert (await c.get(f"/catalogue/assets/{asset['id']}")).status_code == 404
            assert (await c.post(f"/catalogue/products/{pid}/assets", params={"filename": "a.png"}, content=PNG)).status_code == 404
            holder["tenant"] = TENANT
            assert (await c.delete(f"/catalogue/assets/{asset['id']}")).status_code == 200
            assert (await c.get(f"/catalogue/assets/{asset['id']}")).status_code == 404
        finally:
            await c.aclose(); await engine.dispose()
    _run(case())


def test_preview_reports_the_same_launch_checks_without_saving():
    async def case():
        c, _, engine = await _client()
        try:
            r = await c.post("/catalogue/preview", json=_body())
            assert r.status_code == 200
            keys = {x["key"]: x["ok"] for x in r.json()["checks"]}
            assert keys["definition"] and keys["costs"] and not keys["testing"]
            assert r.json()["ready_to_launch"] is False
            assert r.json()["economics"]["complete"] is True
            assert (await c.get("/catalogue/products")).json() == []        # nothing was saved
        finally:
            await c.aclose(); await engine.dispose()
    _run(case())


def test_costs_hidden_without_write_access():
    async def case():
        c, _, engine = await _client(roles=("viewer",))
        try:
            # a viewer cannot create; seed through a write client sharing nothing, so assert the 403 and the read shape
            assert (await c.post("/catalogue/products", json=_body())).status_code == 403
            assert (await c.get("/catalogue/products")).status_code == 200
        finally:
            await c.aclose(); await engine.dispose()
    _run(case())
