"""Supplier scoring maths, source normalisation, supplier field validation. Pure: no database."""
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from services.inventory import catalogue_stock as stock
from services.inventory import supplier_scoring as sc
from services.inventory.routes.purchasing import SupplierCreate, SupplierUpdate

P1, P2 = "prod-1", "prod-2"


def po(i, order, expected, status="received"):
    return {"id": f"po{i}", "po_number": f"PO-{i}", "order_date": order, "expected_delivery": expected, "status": status}


def line(i, product, qty, cost=100.0):
    return {"po_id": f"po{i}", "product_id": product, "quantity_ordered": qty, "unit_cost_zar": cost}


def gr(i, po_i, day):
    return {"id": f"gr{i}", "po_id": f"po{po_i}", "received_at": datetime(2026, 9, day, 9, 0, tzinfo=timezone.utc)}


def item(gr_i, product, received, rejected=0, reason=""):
    return {"gr_id": f"gr{gr_i}", "product_id": product, "quantity_received": received, "quantity_accepted": received - rejected,
            "quantity_rejected": rejected, "rejection_reason": reason}


def facts_three():
    pos = [po(1, date(2026, 9, 1), date(2026, 9, 8)), po(2, date(2026, 9, 2), date(2026, 9, 9)), po(3, date(2026, 9, 3), date(2026, 9, 10))]
    lines = [line(1, P1, 10), line(2, P1, 10), line(3, P1, 20, 120.0)]
    receipts = [gr(1, 1, 8), gr(2, 2, 12), gr(3, 3, 10)]     # on time, 3 days late, on time
    items = [item(1, P1, 10), item(2, P1, 10, 2, "Damaged boxes"), item(3, P1, 20, 1, "damaged boxes")]
    return pos, lines, receipts, items


def test_on_time_late_days_fill_and_rejection():
    pos, lines, receipts, items = facts_three()
    m = sc.summarise(pos, lines, receipts, items, [], [])
    assert m["deliveries"] == 3
    assert m["on_time_rate"] == pytest.approx(0.6667, abs=1e-3)
    assert m["avg_days_late"] == 1.0                      # (0 + 3 + 0) / 3
    assert m["units_ordered"] == 40 and m["units_received"] == 40 and m["units_rejected"] == 3
    assert m["fill_rate"] == pytest.approx(37 / 40)
    assert m["rejection_rate"] == pytest.approx(3 / 40, abs=1e-3)
    assert m["top_rejection_reasons"] == [{"reason": "damaged boxes", "units": 3}]      # case-insensitive grouping
    assert m["avg_lead_days"] == pytest.approx((7 + 10 + 7) / 3, abs=0.1)
    assert m["score"] is not None and 0 <= m["score"] <= 100


def test_returns_and_ratings_lower_or_raise_the_score():
    pos, lines, receipts, items = facts_three()
    base = sc.summarise(pos, lines, receipts, items, [], [])
    returned = sc.summarise(pos, lines, receipts, items, [{"product_id": P1, "quantity": 10}], [])
    assert returned["units_returned"] == 10 and returned["return_rate"] == pytest.approx(10 / 37, abs=1e-3)
    assert returned["score"] < base["score"]
    rated = sc.summarise(pos, lines, receipts, items, [], [{"gr_id": "gr1", "rating": 5, "late_reason": ""}, {"gr_id": "gr2", "rating": 1, "late_reason": "Truck broke down"}])
    assert rated["avg_rating"] == 3.0 and rated["ratings"] == 2


def test_not_enough_deliveries_gives_no_score_not_a_made_up_one():
    pos, lines, receipts, items = facts_three()
    m = sc.summarise(pos[:2], lines[:2], receipts[:2], items[:2], [], [])
    assert m["deliveries"] == 2 and m["score"] is None and m["grade"] == "Not enough data"


def test_orders_without_a_receipt_do_not_count_as_deliveries_or_fill():
    pos, lines, receipts, items = facts_three()
    pos.append(po(4, date(2026, 9, 20), date(2026, 9, 27), "approved"))
    lines.append(line(4, P1, 100))
    m = sc.summarise(pos, lines, receipts, items, [], [])
    assert m["deliveries"] == 3 and m["units_ordered"] == 40 and m["orders_open"] == 1


def test_product_scorecard_only_counts_that_product():
    pos, lines, receipts, items = facts_three()
    lines.append(line(1, P2, 5))
    items.append(item(1, P2, 5, 5, "Wrong model"))
    only_p1 = sc.summarise(pos, lines, receipts, items, [], [], P1)
    only_p2 = sc.summarise(pos, lines, receipts, items, [{"product_id": P2, "quantity": 1}], [], P2)
    assert only_p1["units_rejected"] == 3
    assert only_p2["units_rejected"] == 5 and only_p2["deliveries"] == 1 and only_p2["units_returned"] == 1
    assert only_p2["score"] is None                       # one delivery is not enough for a product score


def test_missing_expected_date_is_excluded_from_on_time_not_counted_late():
    pos, lines, receipts, items = facts_three()
    pos[0]["expected_delivery"] = None
    m = sc.summarise(pos, lines, receipts, items, [], [])
    assert m["on_time_known"] == 2 and m["on_time_rate"] == 0.5


def test_ranking_and_best_supplier_choice():
    good = {"name": "Good", "metrics": {"score": 92.0}}
    ok = {"name": "Ok", "metrics": {"score": 70.0}}
    new = {"name": "New", "metrics": {"score": None}}
    assert [r["name"] for r in sc.rank_suppliers([new, ok, good])] == ["Good", "Ok", "New"]
    a = {"supplier_id": "a", "unit_cost": 100.0, "metrics": {"score": 80.0}}
    b = {"supplier_id": "b", "unit_cost": 90.0, "metrics": {"score": 95.0}}
    assert sc.best_for_product([a, b])["supplier_id"] == "b"
    cheap = {"supplier_id": "c", "unit_cost": 50.0, "metrics": {"score": None}}
    dear = {"supplier_id": "d", "unit_cost": 70.0, "metrics": {"score": None}}
    assert sc.best_for_product([dear, cheap])["supplier_id"] == "c"      # no history: fall back to cost
    assert sc.best_for_product([]) is None


# ── sources on a product ────────────────────────────────────────────────────

S1, S2 = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"


def test_sources_pick_one_preferred_and_keep_one_automatic_cost_line():
    d = {"sources": [{"supplier_id": S1, "unit_cost": "600", "cadence": "Once-off", "preferred": False},
                     {"supplier_id": S2, "unit_cost": "580", "cadence": "Once-off", "preferred": True}],
         "costs": [{"name": "Freight", "supplier": "DHL", "amount": "20", "cadence": "Once-off"}]}
    assert stock.normalise_sources(d, {S1: "Alpha", S2: "Beta"}) == []
    assert [s["preferred"] for s in d["sources"]] == [False, True]
    auto = [c for c in d["costs"] if c.get("auto")]
    assert len(auto) == 1 and auto[0]["amount"] == "580" and auto[0]["supplier"] == "Beta" and d["costs"][-1]["name"] == "Freight"
    d["sources"][1]["unit_cost"] = "570"
    stock.normalise_sources(d, {S1: "Alpha", S2: "Beta"})
    assert len([c for c in d["costs"] if c.get("auto")]) == 1 and [c for c in d["costs"] if c.get("auto")][0]["amount"] == "570"   # re-synced, not duplicated
    d["sources"] = []
    stock.normalise_sources(d, {})
    assert not [c for c in d["costs"] if c.get("auto")]


def test_first_source_becomes_preferred_and_unknown_or_duplicate_suppliers_are_rejected():
    d = {"sources": [{"supplier_id": S1, "unit_cost": "10"}, {"supplier_id": S2, "unit_cost": "9"}], "costs": []}
    stock.normalise_sources(d, {S1: "A", S2: "B"})
    assert [s["preferred"] for s in d["sources"]] == [True, False]
    bad = {"sources": [{"supplier_id": S1, "unit_cost": "1"}, {"supplier_id": S1, "unit_cost": "2"}, {"supplier_id": S2, "unit_cost": "3"}], "costs": []}
    problems = stock.normalise_sources(bad, {S1: "A"})
    assert any("once" in p for p in problems) and any("does not exist" in p for p in problems)


def test_stockable_and_catalogue_requirement_switch():
    assert stock.is_stockable("Physical item", {"stock": "Serial number"})
    assert not stock.is_stockable("Physical item", {"stock": "None"})
    assert not stock.is_stockable("Digital service", {"stock": "Quantity"})


# ── supplier details ────────────────────────────────────────────────────────

def test_supplier_requires_valid_email_and_vat_and_accepts_the_full_record():
    full = SupplierCreate(code="metro", name="Metro Fibre Wholesale", contact_person="Thandi Mokoena", email="orders@metro.example",
                          phone="+27 11 555 0100", address="1 Main Rd, Sandton", tax_id="4123456789", account_number="ACC-0042",
                          payment_terms="Net 30", lead_time_days=10)
    assert full.account_number == "ACC-0042" and full.tax_id == "4123456789"
    with pytest.raises(ValidationError):
        SupplierCreate(code="x", name="X", email="not-an-email")
    with pytest.raises(ValidationError):
        SupplierCreate(code="x", name="X", tax_id="1")
    with pytest.raises(ValidationError):
        SupplierUpdate(email="bad@")
    assert SupplierUpdate(phone="+27 82 000 0000").model_dump(exclude_unset=True) == {"phone": "+27 82 000 0000"}
