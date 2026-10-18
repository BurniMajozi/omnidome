"""The link between the product catalogue (owned by the product manager) and stock (bought, received, issued).

* Suppliers are one master list (inventory_suppliers). A catalogue product lists the suppliers it can be bought
  from as ``definition.sources`` (supplier, supplier SKU, unit cost, lead time, MOQ, preferred).
* The preferred source's price is kept on the cost sheet as one automatic cost line, so margins always use it.
* A launched physical product with stock tracking becomes a stock item (inventory_products): same number as SKU,
  the catalogue stays the master of name, price, unit and preferred supplier. Purchase orders can only be raised
  for stock items that come from an active catalogue product (see require_catalogue_products).
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select

from services.inventory.database import Product, Supplier

AUTO_COST_NAME = "Purchase cost (preferred supplier)"
UNIT_MAP = {"Each": "EA", "Metre": "M", "Hour": "HR", "Visit": "VISIT"}


def require_catalogue_enabled() -> bool:
    return os.getenv("PURCHASING_REQUIRE_CATALOGUE", "true").strip().lower() not in {"0", "false", "no", "off"}


def is_stockable(nature: str, definition: dict) -> bool:
    """Physical items with a stock tracking mode are held and bought as stock."""
    return nature == "Physical item" and (definition.get("stock") or "None") != "None"


async def supplier_names(db, tenant_id: uuid.UUID, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = (await db.execute(select(Supplier.id, Supplier.name).where(
        Supplier.tenant_id == tenant_id, Supplier.deleted_at.is_(None),
        Supplier.id.in_([uuid.UUID(i) for i in ids])))).all()
    return {str(r[0]): r[1] for r in rows}


def normalise_sources(definition: dict, names: dict[str, str]) -> list[str]:
    """Validate and normalise ``definition['sources']`` in place. Returns problems (empty = fine).

    * every supplier must exist in this tenant's supplier master, and appear once
    * exactly one preferred source when there are any
    * the cost sheet carries exactly one automatic cost line for the preferred source (none when there is none)"""
    problems: list[str] = []
    sources = definition.get("sources") or []
    seen: set[str] = set()
    for s in sources:
        sid = str(s.get("supplier_id"))
        if sid in seen:
            problems.append("A supplier can only be listed once per product")
        seen.add(sid)
        if sid not in names:
            problems.append("A listed supplier does not exist in the supplier list")
    preferred = [s for s in sources if s.get("preferred")]
    for i, s in enumerate(sources):
        s["preferred"] = bool(sources) and (s is (preferred[0] if preferred else sources[0]))
    costs = [c for c in (definition.get("costs") or []) if not c.get("auto")]
    pref = next((s for s in sources if s.get("preferred")), None)
    if pref is not None:
        costs.insert(0, {"name": AUTO_COST_NAME, "supplier": names.get(str(pref["supplier_id"]), ""), "supplier_id": str(pref["supplier_id"]),
                         "amount": str(pref.get("unit_cost") or 0), "cadence": pref.get("cadence") or "Once-off", "auto": True})
    definition["costs"] = costs
    return problems


def preferred_source(definition: dict) -> Optional[dict]:
    return next((s for s in (definition.get("sources") or []) if s.get("preferred")), None)


async def ensure_stock_item(db, tenant_id: uuid.UUID, p) -> Optional[uuid.UUID]:
    """Create or refresh the stock item for a catalogue product and remember the link. Idempotent.

    Returns None (and changes nothing) when the product is not stockable."""
    d = p.definition or {}
    if not is_stockable(p.nature, d):
        return None
    pref = preferred_source(d)
    pref_id = uuid.UUID(str(pref["supplier_id"])) if pref else None
    cost = Decimal(str(pref.get("unit_cost") or 0)) if pref else Decimal("0")
    item = None
    if p.inventory_product_id:
        item = (await db.execute(select(Product).where(Product.id == p.inventory_product_id, Product.tenant_id == tenant_id))).scalar_one_or_none()
    if item is None:
        item = (await db.execute(select(Product).where(Product.tenant_id == tenant_id, Product.sku == p.product_number))).scalar_one_or_none()
        if item is not None and item.id != p.inventory_product_id:
            clash = (await db.execute(select(type(p).id).where(type(p).tenant_id == tenant_id, type(p).inventory_product_id == item.id,
                                                              type(p).id != p.id))).first()
            if clash:
                raise HTTPException(409, f"Stock item with SKU {p.product_number} already belongs to another catalogue product")
    if item is None:
        item = Product(id=uuid.uuid4(), tenant_id=tenant_id, sku=p.product_number, name=p.name)
        db.add(item)
    item.name = p.name
    item.sku = p.product_number
    item.description = (d.get("description") or "")[:2000] or None
    item.unit_of_measure = UNIT_MAP.get(d.get("unit") or "Each", "EA")
    item.rrp = Decimal(str(d.get("price") or 0))
    item.cost_price = cost
    item.preferred_supplier_id = pref_id
    item.is_serialized = (d.get("stock") == "Serial number")
    item.is_active = p.status == "active"
    await db.flush()
    p.inventory_product_id = item.id
    return item.id


async def deactivate_stock_item(db, tenant_id: uuid.UUID, p) -> None:
    if not p.inventory_product_id:
        return
    item = (await db.execute(select(Product).where(Product.id == p.inventory_product_id, Product.tenant_id == tenant_id))).scalar_one_or_none()
    if item is not None:
        item.is_active = False
        await db.flush()


async def require_catalogue_products(db, tenant_id: uuid.UUID, product_ids: list[uuid.UUID]) -> None:
    """Purchase orders may only contain stock items created from an ACTIVE catalogue product."""
    if not require_catalogue_enabled() or not product_ids:
        return
    from services.inventory.catalogue_models import CatalogueProduct
    ok = {r[0] for r in (await db.execute(select(CatalogueProduct.inventory_product_id).where(
        CatalogueProduct.tenant_id == tenant_id, CatalogueProduct.status == "active",
        CatalogueProduct.inventory_product_id.in_(product_ids)))).all()}
    missing = [str(i) for i in dict.fromkeys(product_ids) if i not in ok]
    if missing:
        raise HTTPException(422, {"message": "Only products created and launched in Product Management can be purchased. "
                                             "Create the product there (physical item with stock tracking), then order it.",
                                  "products": missing})
