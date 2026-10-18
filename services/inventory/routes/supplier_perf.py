"""Supplier performance, delivery evaluations, returns to supplier, and the profitability mix.

The facts live in stock (purchase orders, receiving, returns) so the stock panel records them; the product panel
reads the same numbers per product, so a buyer can see how each supplier performs on each product.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from services.common.auth import get_current_tenant_id, get_current_user_id
from services.inventory import catalogue_rules as rules
from services.inventory import supplier_scoring as scoring
from services.inventory.access import require_tier
from services.inventory.catalogue_models import CatalogueProduct, SupplierEvaluation, SupplierReturn
from services.inventory.database import (GoodsReceipt, GoodsReceiptItem, Product, PurchaseOrder, PurchaseOrderItem,
                                         StockMovement, Supplier, get_session)
from services.inventory import finance_outbox
from services.inventory.purchasing_helpers import return_journal
from services.inventory.stock import apply_move

router = APIRouter(tags=["Supplier performance"])
COUNTED_PO_STATUSES = ("approved", "sent", "partially_received", "received")


# ── data loading ─────────────────────────────────────────────────────────────

async def load_facts(db, tenant_id: uuid.UUID, months: int, supplier_id: Optional[uuid.UUID] = None) -> dict:
    """All purchasing and receiving rows of the window, grouped by supplier id (string)."""
    since = date.today() - timedelta(days=30 * months)
    q = select(PurchaseOrder).where(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.deleted_at.is_(None),
                                    PurchaseOrder.status.in_(COUNTED_PO_STATUSES), PurchaseOrder.order_date >= since)
    if supplier_id:
        q = q.where(PurchaseOrder.supplier_id == supplier_id)
    pos = list((await db.execute(q)).scalars())
    po_ids = [p.id for p in pos]
    by_po_supplier = {str(p.id): str(p.supplier_id) for p in pos}
    lines = list((await db.execute(select(PurchaseOrderItem).where(PurchaseOrderItem.po_id.in_(po_ids)))).scalars()) if po_ids else []
    grs = list((await db.execute(select(GoodsReceipt).where(GoodsReceipt.tenant_id == tenant_id, GoodsReceipt.po_id.in_(po_ids)))).scalars()) if po_ids else []
    gr_ids = [g.id for g in grs]
    items = list((await db.execute(select(GoodsReceiptItem).where(GoodsReceiptItem.gr_id.in_(gr_ids)))).scalars()) if gr_ids else []
    rq = select(SupplierReturn).where(SupplierReturn.tenant_id == tenant_id, SupplierReturn.returned_at >= datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc))
    eq = select(SupplierEvaluation).where(SupplierEvaluation.tenant_id == tenant_id)
    if supplier_id:
        rq, eq = rq.where(SupplierReturn.supplier_id == supplier_id), eq.where(SupplierEvaluation.supplier_id == supplier_id)
    returns = list((await db.execute(rq)).scalars())
    evals = list((await db.execute(eq)).scalars())

    facts: dict[str, dict] = defaultdict(lambda: {"pos": [], "lines": [], "receipts": [], "items": [], "returns": [], "evals": []})
    for p in pos:
        facts[str(p.supplier_id)]["pos"].append({"id": str(p.id), "po_number": p.po_number, "order_date": p.order_date,
                                                 "expected_delivery": p.expected_delivery, "status": p.status})
    for l in lines:
        facts[by_po_supplier[str(l.po_id)]]["lines"].append({"po_id": str(l.po_id), "product_id": str(l.product_id),
                                                             "quantity_ordered": l.quantity_ordered, "unit_cost_zar": float(l.unit_cost_zar)})
    gr_supplier = {}
    for g in grs:
        s = by_po_supplier.get(str(g.po_id))
        if s:
            gr_supplier[str(g.id)] = s
            facts[s]["receipts"].append({"id": str(g.id), "po_id": str(g.po_id), "received_at": g.received_at})
    for i in items:
        s = gr_supplier.get(str(i.gr_id))
        if s:
            facts[s]["items"].append({"gr_id": str(i.gr_id), "product_id": str(i.product_id), "quantity_received": i.quantity_received,
                                      "quantity_accepted": i.quantity_accepted, "quantity_rejected": i.quantity_rejected,
                                      "rejection_reason": i.rejection_reason})
    for r in returns:
        facts[str(r.supplier_id)]["returns"].append({"product_id": str(r.product_id), "quantity": r.quantity})
    for e in evals:
        facts[str(e.supplier_id)]["evals"].append({"gr_id": str(e.gr_id), "rating": e.rating, "late_reason": e.late_reason})
    return facts


def metrics_for(facts: dict, supplier_id: str, product_id: Optional[str] = None) -> dict:
    f = facts.get(supplier_id) or {"pos": [], "lines": [], "receipts": [], "items": [], "returns": [], "evals": []}
    return scoring.summarise(f["pos"], f["lines"], f["receipts"], f["items"], f["returns"], f["evals"], product_id)


async def _suppliers(db, tenant_id: uuid.UUID, active_only: bool = False) -> list[Supplier]:
    q = select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.deleted_at.is_(None))
    if active_only:
        q = q.where(Supplier.is_active.is_(True))
    return list((await db.execute(q.order_by(Supplier.name))).scalars())


def _sup(s: Supplier) -> dict:
    return {"id": str(s.id), "name": s.name, "code": s.code, "is_active": s.is_active, "lead_time_days": s.lead_time_days,
            "payment_terms": s.payment_terms}


# ── scorecards ───────────────────────────────────────────────────────────────

@router.get("/supplier-performance")
async def supplier_scorecards(months: int = Query(12, ge=1, le=36), tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                              db=Depends(get_session)):
    facts = await load_facts(db, tenant_id, months)
    rows = [{**_sup(s), "name": s.name, "metrics": metrics_for(facts, str(s.id))} for s in await _suppliers(db, tenant_id)]
    return {"months": months, "min_deliveries": scoring.MIN_DELIVERIES, "weights": scoring.WEIGHTS,
            "suppliers": scoring.rank_suppliers(rows)}


@router.get("/supplier-performance/{supplier_id}")
async def supplier_scorecard(supplier_id: uuid.UUID, months: int = Query(12, ge=1, le=36),
                             tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    sup = (await db.execute(select(Supplier).where(Supplier.id == supplier_id, Supplier.tenant_id == tenant_id,
                                                   Supplier.deleted_at.is_(None)))).scalar_one_or_none()
    if sup is None:
        raise HTTPException(404, "Supplier not found")
    facts = await load_facts(db, tenant_id, months, supplier_id)
    sid = str(supplier_id)
    f = facts.get(sid) or {"pos": [], "lines": [], "receipts": [], "items": [], "returns": [], "evals": []}
    product_ids = {l["product_id"] for l in f["lines"]}
    names = {str(p.id): (p.sku, p.name) for p in (await db.execute(select(Product).where(
        Product.tenant_id == tenant_id, Product.id.in_([uuid.UUID(x) for x in product_ids])))).scalars()} if product_ids else {}
    cat = {str(c.inventory_product_id): c for c in (await db.execute(select(CatalogueProduct).where(
        CatalogueProduct.tenant_id == tenant_id, CatalogueProduct.inventory_product_id.in_([uuid.UUID(x) for x in product_ids])))).scalars()} if product_ids else {}
    by_product = []
    for pid in sorted(product_ids):
        sku, name = names.get(pid, ("", "Unknown product"))
        c = cat.get(pid)
        by_product.append({"product_id": pid, "catalogue_product_id": str(c.id) if c else None, "product_number": c.product_number if c else sku,
                           "name": c.name if c else name, "metrics": scoring.summarise(f["pos"], f["lines"], f["receipts"], f["items"], f["returns"], f["evals"], pid)})
    receipts_by_po: dict[str, list] = defaultdict(list)
    for r in f["receipts"]:
        receipts_by_po[r["po_id"]].append(r)
    deliveries = []
    for p in sorted(f["pos"], key=lambda x: x["order_date"], reverse=True)[:25]:
        got = [scoring._d(r["received_at"]) for r in receipts_by_po.get(p["id"], []) if r["received_at"]]
        first = min(got) if got else None
        exp = scoring._d(p["expected_delivery"])
        deliveries.append({"po_number": p["po_number"], "order_date": p["order_date"], "expected_delivery": exp, "first_received": first,
                           "days_late": (max(0, (first - exp).days) if first and exp else None), "status": p["status"]})
    returns = list((await db.execute(select(SupplierReturn).where(SupplierReturn.tenant_id == tenant_id, SupplierReturn.supplier_id == supplier_id)
                                     .order_by(SupplierReturn.returned_at.desc()).limit(25))).scalars())
    return {"supplier": _sup(sup), "months": months, "metrics": metrics_for(facts, sid), "by_product": by_product,
            "deliveries": deliveries,
            "returns": [{"id": str(r.id), "product_id": str(r.product_id), "quantity": r.quantity, "reason": r.reason, "status": r.status,
                         "credit_note_ref": r.credit_note_ref, "returned_at": r.returned_at} for r in returns]}


@router.get("/catalogue/products/{product_id}/supplier-performance", dependencies=[Depends(require_tier("write"))])
async def product_supplier_performance(product_id: uuid.UUID, months: int = Query(12, ge=1, le=36),
                                       tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    """For one catalogue product: each listed supplier's quoted terms next to how they actually perform on it."""
    p = (await db.execute(select(CatalogueProduct).where(CatalogueProduct.id == product_id, CatalogueProduct.tenant_id == tenant_id))).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "Product not found")
    sources = (p.definition or {}).get("sources") or []
    suppliers = {str(s.id): s for s in await _suppliers(db, tenant_id)}
    facts = await load_facts(db, tenant_id, months)
    inv = str(p.inventory_product_id) if p.inventory_product_id else None
    rows = []
    for s in sources:
        sid = str(s["supplier_id"])
        sup = suppliers.get(sid)
        rows.append({"supplier_id": sid, "name": sup.name if sup else "Unknown supplier", "preferred": bool(s.get("preferred")),
                     "supplier_sku": s.get("supplier_sku", ""), "unit_cost": float(s.get("unit_cost") or 0), "cadence": s.get("cadence", "Once-off"),
                     "quoted_lead_days": s.get("lead_time_days") if s.get("lead_time_days") is not None else (sup.lead_time_days if sup else None),
                     "moq": s.get("moq"),
                     "metrics": metrics_for(facts, sid, inv) if inv else scoring.summarise([], [], [], [], [], [], None)})
    best = scoring.best_for_product(rows)
    return {"product_id": str(p.id), "product_number": p.product_number, "stock_linked": inv is not None, "months": months,
            "suppliers": rows, "best_supplier_id": best["supplier_id"] if best else None,
            "best_reason": None if not best else ("Highest performance score" if best["metrics"]["score"] is not None else "Lowest quoted cost (not enough delivery history yet)")}


# ── delivery evaluation and returns ──────────────────────────────────────────

class EvaluationIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    late_reason: str = Field("", max_length=300)
    comment: str = Field("", max_length=1000)


@router.post("/goods-receipts/{gr_id}/evaluation", status_code=201, dependencies=[Depends(require_tier("write"))])
async def evaluate_delivery(gr_id: uuid.UUID, body: EvaluationIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                            user_id: uuid.UUID = Depends(get_current_user_id), db=Depends(get_session)):
    gr = (await db.execute(select(GoodsReceipt).where(GoodsReceipt.id == gr_id, GoodsReceipt.tenant_id == tenant_id))).scalar_one_or_none()
    if gr is None or gr.po_id is None:
        raise HTTPException(404, "Receipt not found")
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == gr.po_id, PurchaseOrder.tenant_id == tenant_id))).scalar_one()
    ev = (await db.execute(select(SupplierEvaluation).where(SupplierEvaluation.tenant_id == tenant_id, SupplierEvaluation.gr_id == gr_id))).scalar_one_or_none()
    if ev is None:
        ev = SupplierEvaluation(tenant_id=tenant_id, supplier_id=po.supplier_id, gr_id=gr_id, po_id=po.id, rating=body.rating)
        db.add(ev)
    ev.rating, ev.late_reason, ev.comment, ev.evaluated_by = body.rating, body.late_reason.strip(), body.comment.strip(), user_id
    await db.flush()
    return {"gr_id": str(gr_id), "supplier_id": str(po.supplier_id), "rating": ev.rating}


class _WriteOff(BaseModel):
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: int
    movement_type: Literal["WRITE_OFF"] = "WRITE_OFF"
    destination_warehouse_id: Optional[uuid.UUID] = None
    client_ref: Optional[str] = None


class ReturnIn(BaseModel):
    supplier_id: uuid.UUID
    product_id: uuid.UUID                         # stock item (inventory product)
    quantity: int = Field(gt=0, le=1_000_000)
    reason: str = Field(min_length=3, max_length=300)
    warehouse_id: Optional[uuid.UUID] = None
    po_id: Optional[uuid.UUID] = None
    gr_id: Optional[uuid.UUID] = None
    credit_note_ref: Optional[str] = Field(None, max_length=100)
    adjust_stock: bool = True                     # take the units out of the warehouse now


@router.post("/supplier-returns", status_code=201, dependencies=[Depends(require_tier("write"))])
async def return_to_supplier(body: ReturnIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                             user_id: uuid.UUID = Depends(get_current_user_id), db=Depends(get_session)):
    sup = (await db.execute(select(Supplier).where(Supplier.id == body.supplier_id, Supplier.tenant_id == tenant_id, Supplier.deleted_at.is_(None)))).scalar_one_or_none()
    if sup is None:
        raise HTTPException(404, "Supplier not found")
    prod = (await db.execute(select(Product).where(Product.id == body.product_id, Product.tenant_id == tenant_id))).scalar_one_or_none()
    if prod is None:
        raise HTTPException(404, "Product not found")
    if body.adjust_stock and body.warehouse_id is None:
        raise HTTPException(422, "Choose the warehouse the units are returned from, or untick 'take out of stock'")
    ret = SupplierReturn(tenant_id=tenant_id, supplier_id=body.supplier_id, product_id=body.product_id, warehouse_id=body.warehouse_id,
                         po_id=body.po_id, gr_id=body.gr_id, quantity=body.quantity, reason=body.reason.strip(),
                         credit_note_ref=(body.credit_note_ref or None), status="credited" if body.credit_note_ref else "returned",
                         created_by=user_id)
    db.add(ret)
    await db.flush()
    if body.adjust_stock:
        await apply_move(db, tenant_id, user_id, _WriteOff(product_id=body.product_id, warehouse_id=body.warehouse_id, quantity=body.quantity),
                         f"supplier-return-{ret.id}")
        ret.stock_adjusted = True
        await db.flush()
        # Finance: reverse the purchase at what we paid (latest receipt from this supplier, else the stock item's cost).
        paid = (await db.execute(select(GoodsReceiptItem.unit_cost_zar).join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptItem.gr_id)
                                 .join(PurchaseOrder, PurchaseOrder.id == GoodsReceipt.po_id)
                                 .where(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.supplier_id == body.supplier_id,
                                        GoodsReceiptItem.product_id == body.product_id)
                                 .order_by(GoodsReceipt.received_at.desc()).limit(1))).scalar()
        unit = Decimal(str(paid if paid is not None else prod.cost_price or 0))
        finance_posted = finance_outbox.enqueue_payload(db, tenant_id, return_journal(ret.id, unit * body.quantity, date.today(), sup.name), unit * body.quantity)
    else:
        finance_posted = False
    await db.commit()
    if finance_posted:
        await finance_outbox.deliver_quietly(tenant_id, user_id)
    return {"id": str(ret.id), "supplier_id": str(ret.supplier_id), "quantity": ret.quantity, "stock_adjusted": ret.stock_adjusted,
            "finance_posted": finance_posted, "status": ret.status}


@router.get("/supplier-returns")
async def list_supplier_returns(supplier_id: Optional[uuid.UUID] = None, limit: int = Query(50, ge=1, le=200),
                                tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    q = select(SupplierReturn).where(SupplierReturn.tenant_id == tenant_id)
    if supplier_id:
        q = q.where(SupplierReturn.supplier_id == supplier_id)
    rows = (await db.execute(q.order_by(SupplierReturn.returned_at.desc()).limit(limit))).scalars()
    return [{"id": str(r.id), "supplier_id": str(r.supplier_id), "product_id": str(r.product_id), "quantity": r.quantity, "reason": r.reason,
             "status": r.status, "credit_note_ref": r.credit_note_ref, "stock_adjusted": r.stock_adjusted, "returned_at": r.returned_at} for r in rows]


# ── profitability of the product mix ─────────────────────────────────────────

@router.get("/catalogue/profitability", dependencies=[Depends(require_tier("write"))])
async def profitability(months: int = Query(12, ge=1, le=36), tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    """Unit economics of every launched product (price, direct cost, margin) and the best supplier for each.

    Weights for the mix come from real units dispatched in the last 90 days when the product is a stock item; products
    without a volume signal are shown unweighted and the response says so."""
    rows = list((await db.execute(select(CatalogueProduct).where(CatalogueProduct.tenant_id == tenant_id, CatalogueProduct.status == "active"))).scalars())
    everything = list((await db.execute(select(CatalogueProduct).where(CatalogueProduct.tenant_id == tenant_id))).scalars())
    catalogue = {str(r.id): {"id": str(r.id), "name": r.name, "status": r.status, "definition": r.definition or {}} for r in everything}
    suppliers = {str(s.id): s for s in await _suppliers(db, tenant_id)}
    facts = await load_facts(db, tenant_id, months)
    since = datetime.now(timezone.utc) - timedelta(days=90)
    volume = {str(pid): int(q or 0) for pid, q in (await db.execute(
        select(StockMovement.product_id, func.sum(StockMovement.quantity)).where(
            StockMovement.tenant_id == tenant_id, StockMovement.movement_type == "customer_dispatch", StockMovement.created_at >= since)
        .group_by(StockMovement.product_id))).all()}
    products = []
    for r in sorted(rows, key=lambda x: x.product_number):
        e = rules.economics(str(r.id), catalogue)
        d = r.definition or {}
        inv = str(r.inventory_product_id) if r.inventory_product_id else None
        src_rows = []
        for s in d.get("sources") or []:
            sid = str(s["supplier_id"])
            sup = suppliers.get(sid)
            src_rows.append({"supplier_id": sid, "name": sup.name if sup else "Unknown", "preferred": bool(s.get("preferred")),
                             "unit_cost": float(s.get("unit_cost") or 0), "metrics": metrics_for(facts, sid, inv) if inv else scoring.summarise([], [], [], [], [], [], None)})
        matrix = {m["supplier_id"]: m for m in rules.margin_matrix(str(r.id), catalogue, {k: v.name for k, v in suppliers.items()})["suppliers"]}
        for sr in src_rows:
            sr["margin_pct"] = (matrix.get(sr["supplier_id"]) or {}).get("margin_pct")
        best = scoring.best_for_product(src_rows)
        pref = next((s for s in src_rows if s["preferred"]), None)
        revenue, cost = float(e.get("revenue", 0)), float(e.get("cost", 0))
        products.append({
            "id": str(r.id), "product_number": r.product_number, "name": r.name, "category": r.category, "range": r.range, "nature": r.nature,
            "price": float(Decimal(str(d.get("price") or 0))), "recurring": bool(d.get("recurring", True)),
            "horizon_months": e.get("horizon"), "revenue": revenue, "cost": cost, "profit": float(e.get("profit", 0)),
            "margin_pct": e.get("margin_pct"), "cost_complete": e["complete"],
            "recurring_cost": float(e["monthly"]), "upfront_cost": float(e["upfront"]),
            "volume_90d": volume.get(inv) if inv else None,
            "preferred_supplier": pref["name"] if pref else None,
            "best_supplier": ({"supplier_id": best["supplier_id"], "name": best["name"], "unit_cost": best["unit_cost"], "score": best["metrics"]["score"]} if best else None),
            "suppliers": len(src_rows),
            "supplier_margins": [{"supplier_id": s["supplier_id"], "name": s["name"], "unit_cost": s["unit_cost"], "margin_pct": s["margin_pct"],
                                  "preferred": s["preferred"], "score": s["metrics"]["score"]} for s in src_rows],
        })
    complete = [x for x in products if x["cost_complete"] and x["revenue"] > 0]
    weighted = [x for x in complete if x["volume_90d"]]
    mix = {"products": len(products), "costed": len(complete),
           "unweighted_margin_pct": round(sum(x["profit"] for x in complete) / sum(x["revenue"] for x in complete) * 100, 2) if complete else None,
           "weighted_margin_pct": (round(sum(x["profit"] * x["volume_90d"] for x in weighted) / sum(x["revenue"] * x["volume_90d"] for x in weighted) * 100, 2)
                                   if weighted else None),
           "weighted_products": len(weighted),
           "note": "Weighted by units dispatched in the last 90 days where stock shows them; otherwise unweighted. Margins use direct costs only."}
    return {"months": months, "products": products, "mix": mix}
