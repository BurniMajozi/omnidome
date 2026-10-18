"""Two suppliers per product, per-supplier costs and margins, channel commission, barcode, identifiers, fact sheets,
unit register. Pure rules plus the API on SQLite (supplier names and the PG-only stock item are faked)."""
import io
import zipfile
from decimal import Decimal

import pytest
from fastapi import HTTPException

from services.inventory import catalogue_docs as docs
from services.inventory import catalogue_rules as rules
from services.inventory import catalogue_stock as stock
from services.inventory.tests.test_catalogue import _body, _client, _run

S1, S2 = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
NAMES = {S1: "Alpha Supply", S2: "Beta Distribution"}


def camera(**over):
    d = {"price": 1000, "recurring": False, "stock": "Serial number", "term": 24, "fees": [],
         "sources": [{"supplier_id": S1, "unit_cost": "600", "cadence": "Once-off", "preferred": True},
                     {"supplier_id": S2, "unit_cost": "560", "cadence": "Once-off", "preferred": False}],
         "costs": [{"name": "Packaging", "supplier": "Internal", "amount": "20", "cadence": "Once-off"},                                 # shared
                   {"name": "Freight from Alpha", "supplier": "Alpha", "supplier_id": S1, "amount": "15", "cadence": "Once-off"},       # Alpha only
                   {"name": "Import duty on Beta", "supplier": "Beta", "supplier_id": S2, "amount": "70", "cadence": "Once-off"}]}     # Beta only
    d.update(over)
    return {"id": "cam", "name": "Camera", "nature": "Physical item", "status": "active", "definition": d}


# ── per-supplier economics ──────────────────────────────────────────────────

def test_each_supplier_scenario_uses_shared_costs_plus_only_its_own_extras():
    cam = camera()
    cat = {"cam": cam}
    alpha = rules.economics("cam", cat, supplier_id=S1, names=NAMES)
    beta = rules.economics("cam", cat, supplier_id=S2, names=NAMES)
    assert alpha["upfront"] == Decimal(600 + 20 + 15) and alpha["profit"] == Decimal(1000 - 635)
    assert beta["upfront"] == Decimal(560 + 20 + 70) and beta["profit"] == Decimal(1000 - 650)
    assert alpha["complete"] and beta["complete"]


def test_default_economics_follow_the_preferred_supplier_and_ignore_other_suppliers_extras():
    cam = camera()
    default = rules.economics("cam", {"cam": cam})
    assert default["upfront"] == Decimal(635)                      # Alpha (preferred): not 635 + Beta's duty
    cam["definition"]["sources"][0]["preferred"], cam["definition"]["sources"][1]["preferred"] = False, True
    assert rules.economics("cam", {"cam": cam})["upfront"] == Decimal(650)


def test_stored_automatic_line_is_never_double_counted():
    cam = camera()
    cam["definition"]["costs"].insert(0, {"name": "Purchase cost (preferred supplier)", "supplier": "Alpha", "supplier_id": S1, "amount": "600", "cadence": "Once-off", "auto": True})
    assert rules.economics("cam", {"cam": cam})["upfront"] == Decimal(635)


def test_margin_matrix_has_a_row_per_supplier():
    m = rules.margin_matrix("cam", {"cam": camera()}, NAMES)
    rows = {r["supplier_id"]: r for r in m["suppliers"]}
    assert rows[S1]["margin_pct"] == 36.5 and rows[S2]["margin_pct"] == 35.0
    assert rows[S1]["preferred"] and not rows[S2]["preferred"]
    assert rows[S1]["name"] == "Alpha Supply"


def test_product_without_suppliers_still_has_one_row():
    cam = camera(sources=[], costs=[{"name": "Unit", "supplier": "Internal", "amount": "600", "cadence": "Once-off"}])
    rows = rules.margin_matrix("cam", {"cam": cam}, {})["suppliers"]
    assert len(rows) == 1 and rows[0]["supplier_id"] is None and rows[0]["margin_pct"] == 40.0


# ── commission by channel ───────────────────────────────────────────────────

def test_channel_commission_percent_fixed_and_bases():
    cam = camera(channels=[{"channel": "Field sales", "commission_type": "percent", "value": "10", "basis": "contract"},
                           {"channel": "Call centre", "commission_type": "fixed", "value": "50"},
                           {"channel": "Online storefront", "commission_type": "none"}])
    row = rules.margin_matrix("cam", {"cam": cam}, NAMES)["suppliers"][0]
    assert row["channels"]["Field sales"]["commission"] == 100.0 and row["channels"]["Field sales"]["margin_pct"] == 26.5
    assert row["channels"]["Call centre"]["commission"] == 50.0 and row["channels"]["Call centre"]["profit"] == 315.0
    assert row["channels"]["Online storefront"]["commission"] == 0.0 and row["channels"]["Online storefront"]["margin_pct"] == 36.5


def test_percent_commission_on_a_monthly_service_uses_the_chosen_basis():
    svc = {"id": "s", "name": "Fibre", "nature": "Digital service", "status": "active",
           "definition": {"price": 800, "recurring": True, "term": 24, "costs": [{"name": "Access", "supplier": "W", "amount": "500", "cadence": "Monthly"}],
                          "fees": [{"name": "Installation", "enabled": True, "mode": "Charge", "cadence": "Once-off", "amount": "950"}],
                          "channels": [{"channel": "Field sales", "commission_type": "percent", "value": "10", "basis": "first_month"},
                                       {"channel": "Partner / reseller", "commission_type": "percent", "value": "10", "basis": "contract"},
                                       {"channel": "Retail store", "commission_type": "percent", "value": "10", "basis": "once_off"}]}}
    ch = rules.margin_matrix("s", {"s": svc})["suppliers"][0]["channels"]
    assert ch["Field sales"]["commission"] == 175.0            # 10% of (800 + 950)
    assert ch["Partner / reseller"]["commission"] == 2015.0    # 10% of 800*24 + 950
    assert ch["Retail store"]["commission"] == 95.0            # 10% of the once-off fee


# ── EAN-13 and tolerant test names ──────────────────────────────────────────

def test_ean13_check_digit():
    assert rules.ean13_valid("4006381333931") and not rules.ean13_valid("4006381333932") and not rules.ean13_valid("12345")
    first12 = "200000000001"
    assert rules.ean13_valid(first12 + str(rules.ean13_check_digit(first12)))


def test_test_names_match_without_case_spaces_or_punctuation():
    p = {"id": "p", "name": "Cam", "nature": "Physical item", "usage": "Customer-facing", "category": "E", "range": "R", "family": "F",
         "definition": {"description": "d", "price": 1, "recurring": False, "stock": "None",
                        "costs": [{"name": "u", "supplier": "s", "amount": 1, "cadence": "Once-off"}],
                        "readiness": {"tests_required": True, "icasa": {"required": False, "exempt_reason": "x"},
                                      "tests": [{"name": "Fulfilment & stock reservation,", "result": "Pass", "tester": "Q", "date": "2026-10-17"},
                                                {"name": "serial & WARRANTY record", "result": "Pass", "tester": "Q", "date": "2026-10-17"},
                                                {"name": "Billing & invoice line", "result": "Pass", "tester": "Q", "date": "2026-10-17"}]}}}
    c = {x["key"]: x for x in rules.launch_checks(p, {"p": p})}
    assert c["testing"]["ok"], c["testing"]


# ── API ─────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def fake_suppliers(monkeypatch):
    async def names(db, tenant_id, ids):
        return {i: NAMES[i] for i in ids if i in NAMES}
    monkeypatch.setattr(stock, "supplier_names", names)


def _prod(**definition):
    b = _body(nature="Physical item", category="Equipment", range="Wi-Fi Routers", family="Equipment")
    b["definition"].update({"stock": "Serial number", "recurring": False, "price": 1000})
    b["definition"]["costs"] = []
    b["definition"].update(definition)
    return b


def test_blank_numbers_save_as_zero_instead_of_blocking_the_product():
    async def case():
        c, _, engine = await _client()
        try:
            b = _prod(price="", costs=[{"name": "Freight", "supplier": "Internal", "amount": "", "cadence": "Once-off"}],
                      fees=[{"id": "f", "name": "Delivery", "enabled": True, "amount": "", "cadence": "Once-off", "mode": "Charge"}])
            r = await c.post("/catalogue/products", json=b)
            assert r.status_code == 201, r.text
            assert r.json()["definition"]["costs"][0]["amount"] == "0"
        finally:
            await c.aclose(); await engine.dispose()
    _run(case())


def test_two_suppliers_with_own_costs_give_a_margin_each_and_reject_unlisted_supplier_costs():
    async def case():
        c, _, engine = await _client()
        try:
            b = _prod(sources=[{"supplier_id": S1, "unit_cost": 600, "preferred": True}, {"supplier_id": S2, "unit_cost": 560}],
                      costs=[{"name": "Packaging", "supplier": "Internal", "amount": 20, "cadence": "Once-off"},
                             {"name": "Freight from Alpha", "supplier": "Alpha", "supplier_id": S1, "amount": 15, "cadence": "Once-off"},
                             {"name": "Duty on Beta", "supplier": "Beta", "supplier_id": S2, "amount": 70, "cadence": "Once-off"}],
                      channels=[{"channel": "Field sales", "commission_type": "percent", "value": 10}])
            r = await c.post("/catalogue/products", json=b)
            assert r.status_code == 201, r.text
            rows = {m["supplier_id"]: m for m in r.json()["margin_matrix"]["suppliers"]}
            assert rows[S1]["margin_pct"] == 36.5 and rows[S2]["margin_pct"] == 35.0
            assert rows[S1]["channels"]["Field sales"]["margin_pct"] == 26.5
            assert r.json()["economics"]["upfront"] == "635"                       # preferred supplier only
            bad = _prod(sources=[{"supplier_id": S1, "unit_cost": 600}],
                        costs=[{"name": "Duty", "supplier": "Beta", "supplier_id": S2, "amount": 70, "cadence": "Once-off"}])
            assert (await c.post("/catalogue/products", json=bad)).status_code == 422
            dup = _prod(channels=[{"channel": "Field sales"}, {"channel": "Field sales"}])
            assert (await c.post("/catalogue/products", json=dup)).status_code == 422
            over = _prod(channels=[{"channel": "Field sales", "commission_type": "percent", "value": 150}])
            assert (await c.post("/catalogue/products", json=over)).status_code == 422
        finally:
            await c.aclose(); await engine.dispose()
    _run(case())


def test_serial_tracking_implies_the_serial_identifier():
    async def case():
        c, _, engine = await _client()
        try:
            r = await c.post("/catalogue/products", json=_prod(identifiers=["MAC address"]))
            assert r.json()["definition"]["identifiers"] == ["Serial number", "MAC address"]
        finally:
            await c.aclose(); await engine.dispose()
    _run(case())


def test_barcode_generate_manufacturer_duplicates_and_physical_only():
    async def case():
        c, _, engine = await _client()
        try:
            a = (await c.post("/catalogue/products", json=_prod())).json()
            g = await c.post(f"/catalogue/products/{a['id']}/barcode", json={"mode": "generate"})
            code = g.json()["definition"]["barcode"]
            assert g.status_code == 200 and code["format"] == "EAN-13" and code["value"].startswith("2") and rules.ean13_valid(code["value"])
            again = await c.post(f"/catalogue/products/{a['id']}/barcode", json={"mode": "generate"})
            assert again.json()["definition"]["barcode"]["value"] != code["value"]          # a regenerated code is a new one
            b = (await c.post("/catalogue/products", json={**_prod(), "name": "Second"})).json()
            ok = await c.post(f"/catalogue/products/{b['id']}/barcode", json={"mode": "manufacturer", "value": "4006381333931"})
            assert ok.status_code == 200 and ok.json()["definition"]["barcode"]["source"] == "manufacturer"
            assert (await c.post(f"/catalogue/products/{a['id']}/barcode", json={"mode": "manufacturer", "value": "4006381333931"})).status_code == 409
            assert (await c.post(f"/catalogue/products/{a['id']}/barcode", json={"mode": "manufacturer", "value": "4006381333932"})).status_code == 422
            digital = (await c.post("/catalogue/products", json=_body())).json()
            assert (await c.post(f"/catalogue/products/{digital['id']}/barcode", json={"mode": "generate"})).status_code == 409
            cleared = await c.post(f"/catalogue/products/{b['id']}/barcode", json={"mode": "clear"})
            assert cleared.json()["definition"]["barcode"]["value"] == ""
        finally:
            await c.aclose(); await engine.dispose()
    _run(case())


# ── fact sheets ─────────────────────────────────────────────────────────────

def _docx(paragraphs):
    xml = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs) + "</w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
        z.writestr("[Content_Types].xml", "<Types/>")
    return buf.getvalue()


def test_text_extraction_txt_docx_and_refusals():
    assert docs.extract_text("txt", b"The AX1800 router supports Wi-Fi 6 on two bands.") .startswith("The AX1800")
    assert "Wi-Fi 6" in docs.extract_text("docx", _docx(["The AX1800 router supports Wi-Fi 6.", "Four gigabit LAN ports."]))
    with pytest.raises(ValueError):
        docs.extract_text("txt", b"  ")
    with pytest.raises(ValueError):
        docs.extract_text("docx", b"not a zip")
    with pytest.raises(ValueError):
        docs.extract_text("png", b"x" * 100)


def test_extractive_draft_keeps_the_sheets_own_facts_and_respects_the_style():
    sheet = "Welcome to our catalogue. The AX1800 delivers 1800 Mbps over dual bands. It has four gigabit LAN ports. Ships in a recyclable box. Warranty is 12 months."
    short = docs.extractive_draft("AX1800 router", sheet, "Short portal description")
    long = docs.extractive_draft("AX1800 router", sheet, "Technical summary")
    assert short.startswith("AX1800 router") and "1800 Mbps" in short
    assert len(long) > len(short)


def test_fact_sheet_upload_draft_and_refusals(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    async def case():
        c, _, engine = await _client()
        try:
            p = (await c.post("/catalogue/products", json=_prod())).json()
            body = {"style": "Customer-friendly", "product": _prod()}
            none_yet = await c.post(f"/catalogue/products/{p['id']}/description-suggestions", json=body)
            assert none_yet.status_code == 409
            sheet = b"The AX1800 router delivers 1800 Mbps over dual bands with four gigabit LAN ports and a 12 month warranty."
            up = await c.post(f"/catalogue/products/{p['id']}/assets", params={"filename": "fact.txt", "purpose": "fact_sheet"}, content=sheet)
            assert up.status_code == 201 and up.json()["text_chars"] > 40
            png = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 32
            assert (await c.post(f"/catalogue/products/{p['id']}/assets", params={"filename": "x.png", "purpose": "fact_sheet"}, content=png)).status_code == 415
            blank = await c.post(f"/catalogue/products/{p['id']}/assets", params={"filename": "empty.txt", "purpose": "fact_sheet"}, content=b"   ")
            assert blank.status_code in (422,)
            d = await c.post(f"/catalogue/products/{p['id']}/description-suggestions", json=body)
            assert d.status_code == 200 and d.json()["method"] == "extract" and "1800 Mbps" in d.json()["text"] and d.json()["sheets"] == ["fact.txt"]
        finally:
            await c.aclose(); await engine.dispose()
    _run(case())


def test_draft_uses_the_model_when_one_answers(monkeypatch):
    async def fake(facts, sheet, style):
        assert "AX1800" in sheet and "Name:" in facts
        return "A fast dual-band router for the home.", "test/model"
    monkeypatch.setattr(docs, "llm_draft", fake)

    async def case():
        c, _, engine = await _client()
        try:
            p = (await c.post("/catalogue/products", json=_prod())).json()
            await c.post(f"/catalogue/products/{p['id']}/assets", params={"filename": "f.txt", "purpose": "fact_sheet"}, content=b"The AX1800 router has dual bands and Wi-Fi 6.")
            d = (await c.post(f"/catalogue/products/{p['id']}/description-suggestions", json={"style": "Customer-friendly", "product": _prod()})).json()
            assert d["method"] == "ai" and d["model"] == "test/model" and d["text"].startswith("A fast")
        finally:
            await c.aclose(); await engine.dispose()
    _run(case())


# ── unit register ───────────────────────────────────────────────────────────

def test_unit_validation_serial_mac_counts_and_duplicates():
    import uuid
    from sqlalchemy import StaticPool
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from services.inventory.catalogue_models import CatalogueProduct, InventoryUnit

    async def case():
        engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
        async with engine.begin() as conn:
            for t in (CatalogueProduct, InventoryUnit):
                await conn.run_sync(t.__table__.create)
        tenant, inv = uuid.uuid4(), uuid.uuid4()
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            s.add(CatalogueProduct(tenant_id=tenant, product_number="OD-1", name="ONT", status="active", nature="Physical item", inventory_product_id=inv,
                                   definition={"stock": "Serial number", "identifiers": ["Serial number", "MAC address"]}))
            await s.commit()
            ok = await stock.validate_units(s, tenant, inv, 2, [{"serial": "SN1", "mac": "aa-bb-cc-dd-ee-01"}, {"serial": "SN2", "mac": "AABBCCDDEE02"}])
            assert [u["mac"] for u in ok] == ["AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"]
            for bad, code in (([{"serial": "SN1", "mac": "AA:BB:CC:DD:EE:01"}], 422),                       # one line for two units
                              ([{"serial": "SN1", "mac": "zz"}, {"serial": "SN2", "mac": "AA:BB:CC:DD:EE:02"}], 422),   # bad MAC
                              ([{"serial": "", "mac": "AA:BB:CC:DD:EE:01"}, {"serial": "SN2", "mac": "AA:BB:CC:DD:EE:02"}], 422),   # no serial
                              ([{"serial": "SN1", "mac": "AA:BB:CC:DD:EE:01"}, {"serial": "SN1", "mac": "AA:BB:CC:DD:EE:02"}], 422)):   # repeated serial
                with pytest.raises(HTTPException) as e:
                    await stock.validate_units(s, tenant, inv, 2, bad)
                assert e.value.status_code == code
            s.add(InventoryUnit(tenant_id=tenant, product_id=inv, serial="SN1", mac="AA:BB:CC:DD:EE:01"))
            await s.commit()
            with pytest.raises(HTTPException) as e:
                await stock.validate_units(s, tenant, inv, 1, [{"serial": "SN9", "mac": "aa:bb:cc:dd:ee:01"}])
            assert e.value.status_code == 409 and "register" in e.value.detail
            # an untracked, non-catalogue product accepts no units without complaint
            assert await stock.validate_units(s, tenant, uuid.uuid4(), 3, []) == []
        await engine.dispose()
    _run(case())


# ── products that are not sold: giveaways, company assets, rented-in kit ────────

def _view(pid, d, usage="Company-owned asset", status="active"):
    return {"id": pid, "name": "x", "category": "c", "range": "r", "family": "f", "nature": "Physical item", "usage": usage,
            "status": status, "definition": d}


def _asset(offer, cost=1200):
    return {"description": "d", "price": 0, "recurring": False, "stock": "Quantity", "offer": offer,
            "costs": [{"name": "Purchase", "supplier": "ACME", "amount": cost, "cadence": "Once-off"}]}


def test_company_asset_is_amortised_and_never_has_revenue():
    from decimal import Decimal
    from services.inventory import catalogue_rules as rules
    cat = {"a": _view("a", _asset({"mode": "asset", "life_months": 36, "residual_value": 120}))}
    e = rules.economics("a", cat)
    assert e["revenue"] == 0 and e["margin_pct"] is None
    assert e["monthly"] == Decimal(1080) / 36 == Decimal(30) and e["upfront"] == 0
    assert e["amortisation_yearly"] == Decimal(360)


def test_given_router_cost_lands_on_the_service_that_includes_it():
    from decimal import Decimal
    from services.inventory import catalogue_rules as rules
    router = _view("r", _asset({"mode": "given", "life_months": 36, "residual_value": 0, "returnable": True}, cost=900))
    svc = _view("s", {"description": "d", "price": 500, "recurring": True, "term": 24, "components": [{"product_id": "r", "qty": 1}],
                      "costs": [{"name": "Wholesale", "supplier": "W", "amount": 200, "cadence": "Monthly"}]}, usage="Customer-facing")
    e = rules.economics("s", {"r": router, "s": svc})
    assert e["monthly"] == Decimal(200) + Decimal(25)                 # 900 over 36 months = 25 a month on top of the wholesale cost
    assert e["profit"] == (500 - 225) * 24
    plain = rules.economics("s", {"r": _view("r", {**router["definition"], "offer": {"mode": "given"}}), "s": svc})
    assert plain["upfront"] == 900                                    # given away with no life: the whole cost hits the service


def test_returnable_giveaway_without_life_recovers_its_residual():
    from services.inventory import catalogue_rules as rules
    e = rules.economics("a", {"a": _view("a", _asset({"mode": "given", "returnable": True, "residual_value": 200}))})
    assert e["upfront"] == 1000


def test_rented_in_uses_monthly_rent_and_launch_gate_does_not_ask_for_a_price():
    from services.inventory import catalogue_rules as rules
    d = _asset({"mode": "rented_in", "rental_monthly": 150}, cost=0)
    d["costs"] = [{"name": "Deposit", "supplier": "Lessor", "amount": 300, "cadence": "Once-off"}]
    e = rules.economics("a", {"a": _view("a", d)})
    assert e["monthly"] == 150 and e["upfront"] == 300
    checks = {c["key"]: c for c in rules.launch_checks(_view("a", {**d, "readiness": {"tests_required": False}}, status="draft"), {})}
    assert checks["price"]["ok"] and checks["testing"]["ok"] and checks["icasa"]["ok"]
    no_rent = rules.launch_checks(_view("a", _asset({"mode": "rented_in"}), status="draft"), {})
    assert not next(c for c in no_rent if c["key"] == "price")["ok"]


def test_a_plain_chair_can_launch_without_price_tests_or_icasa():
    from services.inventory import catalogue_rules as rules
    d = {**_asset({"mode": "asset"}, cost=450), "readiness": {"tests_required": False}}
    d["description"] = "Office chair"
    p = {**_view("c", d, status="draft"), "name": "Office chair", "category": "Office", "range": "Furniture", "family": "Assets"}
    p["definition"]["costs"][0]["supplier"] = "Makro"
    failing = [c["key"] for c in rules.launch_checks(p, {}) if not c["ok"]]
    assert failing == [], failing


def test_sold_products_are_unchanged():
    from services.inventory import catalogue_rules as rules
    d = {"description": "d", "price": 100, "recurring": False, "costs": [{"name": "c", "supplier": "s", "amount": 40, "cadence": "Once-off"}]}
    e = rules.economics("a", {"a": _view("a", d, usage="Customer-facing")})
    assert e["profit"] == 60 and "amortisation_monthly" not in e
