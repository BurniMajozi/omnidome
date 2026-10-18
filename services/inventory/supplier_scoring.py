"""Supplier performance from purchasing and receiving facts. Pure functions (no database), so the maths is
unit tested; routes/supplier_perf.py loads the rows.

Measures, per supplier and optionally per product:
  on_time_rate      share of purchase orders whose FIRST receipt arrived on or before the expected delivery date
  avg_days_late     mean days past the expected date across those orders (early counts as 0)
  fill_rate         units accepted / units ordered, over orders that have had at least one receipt
  rejection_rate    units rejected at receiving / units received
  return_rate       units returned to the supplier after receipt / units accepted
  avg_rating        mean of the receiver's 1-5 delivery ratings
  avg_lead_days     order date to first receipt
The composite score needs MIN_DELIVERIES orders with receipts; below that it is None ("not enough data"), never a
made-up number.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any, Iterable, Optional

MIN_DELIVERIES = 3
# Weights of the composite (sum to 100). Rating is optional: when absent its weight moves to on-time and quality.
WEIGHTS = {"on_time": 35, "fill": 25, "quality": 25, "returns": 10, "rating": 5}


def _d(v: Any) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _ratio(num: float, den: float) -> Optional[float]:
    return None if not den else round(num / den, 4)


def grade(score: Optional[float]) -> str:
    if score is None:
        return "Not enough data"
    return "Excellent" if score >= 90 else "Good" if score >= 75 else "Fair" if score >= 60 else "Poor"


def composite(m: dict) -> Optional[float]:
    if (m.get("deliveries") or 0) < MIN_DELIVERIES:
        return None
    parts = {"on_time": m.get("on_time_rate"), "fill": m.get("fill_rate"),
             "quality": None if m.get("rejection_rate") is None else 1 - m["rejection_rate"],
             "returns": None if m.get("return_rate") is None else max(0.0, 1 - m["return_rate"]),
             "rating": None if m.get("avg_rating") is None else (m["avg_rating"] - 1) / 4}
    used = {k: v for k, v in parts.items() if v is not None}
    if not used:
        return None
    total_w = sum(WEIGHTS[k] for k in used)
    return round(sum(WEIGHTS[k] * v for k, v in used.items()) / total_w * 100, 1)


def summarise(pos: Iterable[dict], po_lines: Iterable[dict], receipts: Iterable[dict], receipt_items: Iterable[dict],
              returns: Iterable[dict], evaluations: Iterable[dict], product_id: Optional[str] = None) -> dict:
    """Metrics for ONE supplier's rows (callers group by supplier first).

    pos:           {id, order_date, expected_delivery, status}
    po_lines:      {po_id, product_id, quantity_ordered, unit_cost_zar}
    receipts:      {id, po_id, received_at}
    receipt_items: {gr_id, product_id, quantity_received, quantity_accepted, quantity_rejected, rejection_reason}
    returns:       {product_id, quantity}
    evaluations:   {gr_id, rating, late_reason}
    product_id restricts the lines, receipts and returns to one product (the product-level scorecard)."""
    pos = {str(p["id"]): p for p in pos}
    lines = [l for l in po_lines if str(l["po_id"]) in pos and (product_id is None or str(l["product_id"]) == product_id)]
    po_ids = {str(l["po_id"]) for l in lines} if product_id else set(pos)
    receipts = {str(r["id"]): r for r in receipts if str(r["po_id"]) in po_ids}
    items = [i for i in receipt_items if str(i["gr_id"]) in receipts and (product_id is None or str(i["product_id"]) == product_id)]
    if product_id:   # a receipt only counts for the product if it received that product
        receipts = {k: v for k, v in receipts.items() if any(str(i["gr_id"]) == k for i in items)}

    first_receipt: dict[str, date] = {}
    for r in receipts.values():
        d = _d(r["received_at"])
        if d and (str(r["po_id"]) not in first_receipt or d < first_receipt[str(r["po_id"])]):
            first_receipt[str(r["po_id"])] = d

    expected_known = [(pid, _d(pos[pid]["expected_delivery"])) for pid in first_receipt if _d(pos[pid].get("expected_delivery"))]
    late_days = [max(0, (first_receipt[pid] - exp).days) for pid, exp in expected_known]
    on_time = [x == 0 for x in late_days]
    lead = [(first_receipt[pid] - _d(pos[pid]["order_date"])).days for pid in first_receipt if _d(pos[pid].get("order_date"))]

    ordered = sum(int(l["quantity_ordered"]) for l in lines if str(l["po_id"]) in first_receipt)
    received = sum(int(i["quantity_received"]) for i in items)
    accepted = sum(int(i["quantity_accepted"]) for i in items)
    rejected = sum(int(i["quantity_rejected"]) for i in items)
    returned = sum(int(r["quantity"]) for r in returns if product_id is None or str(r["product_id"]) == product_id)
    reasons: Counter = Counter()
    for i in items:           # units rejected per reason (case-insensitive), not number of receipt lines
        reason = (i.get("rejection_reason") or "").strip().lower()
        if reason and int(i["quantity_rejected"]) > 0:
            reasons[reason] += int(i["quantity_rejected"])
    rated = [int(e["rating"]) for e in evaluations if str(e["gr_id"]) in receipts]
    paid = [float(l["unit_cost_zar"]) for l in lines if str(l["po_id"]) in first_receipt]

    m = {
        "deliveries": len(first_receipt),
        "receipts": len(receipts),
        "orders_open": sum(1 for pid in po_ids if pid not in first_receipt and pos[pid].get("status") in ("approved", "sent", "partially_received")),
        "on_time_rate": _ratio(sum(on_time), len(on_time)),
        "on_time_known": len(on_time),
        "avg_days_late": round(sum(late_days) / len(late_days), 1) if late_days else None,
        "avg_lead_days": round(sum(lead) / len(lead), 1) if lead else None,
        "units_ordered": ordered,
        "units_received": received,
        "units_accepted": accepted,
        "units_rejected": rejected,
        "units_returned": returned,
        "fill_rate": _ratio(min(accepted, ordered) if ordered else 0, ordered),
        "rejection_rate": _ratio(rejected, received),
        "return_rate": _ratio(returned, accepted),
        "avg_rating": round(sum(rated) / len(rated), 2) if rated else None,
        "ratings": len(rated),
        "avg_unit_cost": round(sum(paid) / len(paid), 2) if paid else None,
        "top_rejection_reasons": [{"reason": r, "units": n} for r, n in reasons.most_common(3)],
    }
    m["score"] = composite(m)
    m["grade"] = grade(m["score"])
    return m


def rank_suppliers(rows: list[dict]) -> list[dict]:
    """Best first. Suppliers without enough data are listed after those with a score."""
    return sorted(rows, key=lambda r: (r["metrics"]["score"] is None, -(r["metrics"]["score"] or 0), r["name"].lower()))


def best_for_product(rows: list[dict]) -> Optional[dict]:
    """The supplier to buy this product from: highest score; ties and missing scores fall back to lowest cost."""
    scored = [r for r in rows if r["metrics"]["score"] is not None]
    if scored:
        return max(scored, key=lambda r: (r["metrics"]["score"], -(r.get("unit_cost") or 1e12)))
    costed = [r for r in rows if r.get("unit_cost") is not None]
    return min(costed, key=lambda r: r["unit_cost"]) if costed else None
