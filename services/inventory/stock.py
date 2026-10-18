"""Transactional stock operations. Product locks serialize level creation and deltas."""
import hashlib
import json
import uuid
from fastapi import HTTPException
from sqlalchemy import select, text
from datetime import datetime, timezone
from decimal import Decimal
from services.inventory.database import Product, Warehouse, InventoryLevel, StockMovement
from services.inventory import finance_outbox
from services.inventory.purchasing_helpers import dispatch_journal, writeoff_journal

MOVEMENTS = {"PURCHASE": "purchase_receipt", "RETURN_FROM_CUSTOMER": "customer_return",
             "TRANSFER": "warehouse_transfer", "WRITE_OFF": "write_off", "SALE": "customer_dispatch"}

def available(level):
    return level.soh - level.allocated - level.reserved

def stock_delta(level, kind, quantity):
    if quantity <= 0 or kind not in MOVEMENTS:
        raise HTTPException(422, "Invalid stock movement")
    if kind in {"TRANSFER", "WRITE_OFF", "SALE"} and quantity > available(level):
        raise HTTPException(409, "Insufficient available stock")
    if kind in {"PURCHASE", "RETURN_FROM_CUSTOMER"}:
        level.soh += quantity
    elif kind == "SALE":
        level.allocated += quantity
    else:
        level.soh -= quantity

async def lock_operation(db, tenant_id, key):
    if not key or len(key) > 96:
        raise HTTPException(422, "An Idempotency-Key of at most 96 characters is required")
    if db.get_bind().dialect.name == "postgresql":
        lock_id = int.from_bytes(hashlib.sha256(f"{tenant_id}:{key}".encode()).digest()[:8], "big", signed=True)
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})

async def locked_product(db, tenant_id, product_id):
    product = (await db.execute(select(Product).where(Product.id == product_id, Product.tenant_id == tenant_id).with_for_update())).scalar_one_or_none()
    if product is None:
        raise HTTPException(404, "Product not found")
    return product

async def locked_level(db, tenant_id, product_id, warehouse_id):
    await locked_product(db, tenant_id, product_id)
    warehouse = (await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id, Warehouse.tenant_id == tenant_id))).scalar_one_or_none()
    if warehouse is None:
        raise HTTPException(404, "Warehouse not found")
    level = (await db.execute(select(InventoryLevel).where(InventoryLevel.tenant_id == tenant_id,
        InventoryLevel.product_id == product_id, InventoryLevel.warehouse_id == warehouse_id).with_for_update())).scalar_one_or_none()
    if level is None:
        level = InventoryLevel(tenant_id=tenant_id, product_id=product_id, warehouse_id=warehouse_id,
                               soh=0, allocated=0, reserved=0, sit=0)
        db.add(level)
        await db.flush()
    return level

def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

async def replay(db, tenant_id, key, payload_hash):
    move = (await db.execute(select(StockMovement).where(StockMovement.tenant_id == tenant_id, StockMovement.client_ref == key))).scalar_one_or_none()
    if move is None:
        return None
    saved = json.loads(move.notes or "{}")
    if saved.get("fingerprint") != payload_hash:
        raise HTTPException(409, "Idempotency-Key was already used for a different request")
    return saved["response"]

async def post_movement_journal(db, tenant_id, move, key):
    """Stock leaving for a customer (SALE) or written off costs money in finance: queue the journal in the same transaction.

    A return to a supplier is also a WRITE_OFF move, but its own journal (reversing the purchase) is posted by the return."""
    if move.movement_type not in ("WRITE_OFF", "SALE") or (key or "").startswith("supplier-return-"):
        return
    cost = (await db.execute(select(Product.cost_price).where(Product.id == move.product_id, Product.tenant_id == tenant_id))).scalar() or 0
    value = Decimal(str(cost)) * move.quantity
    source_id = hashlib.sha1((key or "").encode()).hexdigest()
    day = datetime.now(timezone.utc).date()
    if move.movement_type == "SALE":
        from services.inventory import asset_register
        if await asset_register.capitalise(db, tenant_id, move.product_id, move.quantity, cost, day, "issue", (key or "")[:100]):
            return          # equipment given to a customer is carried and amortised, not expensed
    journal = writeoff_journal(source_id, value, day) if move.movement_type == "WRITE_OFF" else dispatch_journal(source_id, value, day, "to customer")
    finance_outbox.enqueue_payload(db, tenant_id, journal, value)


async def apply_move(db, tenant_id, user_id, move, key):
    await lock_operation(db, tenant_id, key)
    digest = fingerprint(move.model_dump(mode="json", exclude={"client_ref"}))
    previous = await replay(db, tenant_id, key, digest)
    if previous is not None:
        return previous
    source = await locked_level(db, tenant_id, move.product_id, move.warehouse_id)
    destination = None
    if move.movement_type == "TRANSFER":
        if not move.destination_warehouse_id or move.destination_warehouse_id == move.warehouse_id:
            raise HTTPException(422, "A different destination warehouse is required")
        destination = await locked_level(db, tenant_id, move.product_id, move.destination_warehouse_id)
    before = source.soh
    dest_before = destination.soh if destination else None
    stock_delta(source, move.movement_type, move.quantity)
    if destination:
        destination.soh += move.quantity
    response = {"status": "completed", "available": available(source), "soh": source.soh,
                "destination_soh": destination.soh if destination else None}
    outbound = move.movement_type in {"TRANSFER", "WRITE_OFF", "SALE"}
    db.add(StockMovement(tenant_id=tenant_id, product_id=move.product_id, quantity=move.quantity,
        movement_type=MOVEMENTS[move.movement_type], performed_by=user_id, client_ref=key,
        from_location_type="warehouse" if outbound else None,
        from_location_id=move.warehouse_id if outbound else None,
        to_location_type="warehouse" if destination or not outbound else None,
        to_location_id=move.destination_warehouse_id if destination else (move.warehouse_id if not outbound else None),
        before_soh=before, after_soh=source.soh, dest_before_soh=dest_before,
        dest_after_soh=destination.soh if destination else None,
        notes=json.dumps({"fingerprint": digest, "response": response})))
    await db.flush()
    await post_movement_journal(db, tenant_id, move, key)
    return response

async def checkout(db, tenant_id, user_id, payload, key):
    await lock_operation(db, tenant_id, key)
    digest = fingerprint(payload.model_dump(mode="json", exclude={"client_ref"}))
    marker = f"checkout:{key}"
    previous = await replay(db, tenant_id, marker, digest)
    if previous is not None:
        return previous
    resolved = []
    for item in payload.items:
        try:
            selector = Product.id == uuid.UUID(item.product_id)
        except ValueError:
            selector = Product.sku == item.product_id
        product = (await db.execute(select(Product).where(Product.tenant_id == tenant_id, selector))).scalar_one_or_none()
        if product is None:
            raise HTTPException(404, "Product not found")
        resolved.append((product.id, item))
    # Lock all products in a deterministic order before selecting warehouse levels.
    for product_id in sorted({p for p, _ in resolved}, key=str):
        await locked_product(db, tenant_id, product_id)
    results, movements = [], []
    for product_id, item in resolved:
        warehouse_id = item.warehouse_id or payload.warehouse_id
        if warehouse_id is None:
            levels = (await db.execute(select(InventoryLevel).where(InventoryLevel.tenant_id == tenant_id,
                InventoryLevel.product_id == product_id).with_for_update())).scalars().all()
            if len(levels) != 1:
                raise HTTPException(422, "Specify a warehouse for this product")
            level = levels[0]
            warehouse_id = level.warehouse_id
            level = await locked_level(db, tenant_id, product_id, warehouse_id)
        else:
            level = await locked_level(db, tenant_id, product_id, warehouse_id)
        stock_delta(level, "SALE", item.quantity)
        results.append({"product_id": item.product_id, "warehouse_id": str(warehouse_id),
                        "status": "CHECKED_OUT", "quantity": item.quantity, "remaining": available(level)})
        movements.append(StockMovement(tenant_id=tenant_id, product_id=product_id,
            quantity=item.quantity, movement_type="customer_dispatch", performed_by=user_id,
            from_location_type="warehouse", from_location_id=warehouse_id,
            reference=payload.job_id, before_soh=level.soh, after_soh=level.soh))
    response = {"job_id": payload.job_id, "items": results, "status": "complete"}
    movements[0].client_ref = marker
    movements[0].notes = json.dumps({"fingerprint": digest, "response": response})
    db.add_all(movements)
    await db.flush()
    costs = {pid: Decimal(str(c or 0)) for pid, c in (await db.execute(select(Product.id, Product.cost_price).where(
        Product.tenant_id == tenant_id, Product.id.in_([p for p, _ in resolved])))).all()}
    from services.inventory import asset_register
    day = datetime.now(timezone.utc).date()
    value = Decimal(0)
    for pid, item in resolved:
        if not await asset_register.capitalise(db, tenant_id, pid, item.quantity, costs.get(pid, Decimal(0)), day, "issue", (payload.job_id or marker)[:100]):
            value += costs.get(pid, Decimal(0)) * item.quantity
    finance_outbox.enqueue_payload(db, tenant_id, dispatch_journal(hashlib.sha1(marker.encode()).hexdigest(), value,
                                                                  datetime.now(timezone.utc).date(), payload.job_id or ""), value)
    return response
