"""Equipment register and monthly amortisation journals.

Which products are capitalised comes from the catalogue offer model:
  asset  : a company asset, carried as equipment from the day it is received;
  given  : equipment handed to customers, carried as equipment from the day it is issued to them (only when an
           amortisation life is set; otherwise the cost is expensed on dispatch as before).
Both are amortised straight-line, month by month, to their residual value. Units that come back from a customer move
back into stock at net book value (see install_return_hook); units that are lost or scrapped are written off at net book value.

Journals go through the finance outbox (idempotent on source/source_id), so every month posts at most once.
Accounts: 1510 PP&E Equipment, 1600 Accumulated Depreciation, 6400 Depreciation & Amortization, 1200 Inventory, 6900 write-offs.
"""
import calendar
import hashlib
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import select

from services.inventory import finance_outbox
from services.inventory.catalogue_models import CatalogueProduct, InventoryAsset
from services.inventory.purchasing_helpers import _journal

CENT = Decimal("0.01")


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def money(v) -> Decimal:
    return _d(v).quantize(CENT, rounding=ROUND_HALF_UP)


def month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def add_months(y: int, m: int, n: int) -> tuple[int, int]:
    t = y * 12 + (m - 1) + n
    return t // 12, t % 12 + 1


def capitalised_offer(definition: dict, origin: str) -> Optional[dict]:
    """The offer settings when a product of this definition is capitalised at ``origin`` (receipt | issue), else None."""
    o = (definition or {}).get("offer") or {}
    mode, life = o.get("mode") or "sold", int(o.get("life_months") or 0)
    if life <= 0:
        return None
    if (mode == "asset" and origin == "receipt") or (mode == "given" and origin == "issue"):
        return {"life_months": life, "residual": money(o.get("residual_value")), "mode": mode}
    return None


async def catalogue_for(db, tenant_id, inventory_product_id) -> Optional[CatalogueProduct]:
    return (await db.execute(select(CatalogueProduct).where(CatalogueProduct.tenant_id == tenant_id,
                                                           CatalogueProduct.inventory_product_id == inventory_product_id))).scalar_one_or_none()


def _exists(db, tenant_id, source, source_id) -> bool:
    return any(getattr(o, "tenant_id", None) == tenant_id and o.source == source and o.source_id == source_id
               for o in db.new if isinstance(o, finance_outbox.InventoryFinanceOutbox))


async def _already_queued(db, tenant_id, source, source_id) -> bool:
    from services.inventory.database import InventoryFinanceOutbox
    if _exists(db, tenant_id, source, source_id):
        return True
    return (await db.execute(select(InventoryFinanceOutbox.id).where(
        InventoryFinanceOutbox.tenant_id == tenant_id, InventoryFinanceOutbox.source == source,
        InventoryFinanceOutbox.source_id == source_id))).first() is not None


async def capitalise(db, tenant_id, inventory_product_id, quantity: int, unit_cost, day: date, origin: str, reference: str) -> Optional[InventoryAsset]:
    """Register a batch as equipment when the product's offer says so, and queue the reclass journal Dr 1510 / Cr 1200."""
    cat = await catalogue_for(db, tenant_id, inventory_product_id)
    if cat is None or quantity <= 0:
        return None
    cfg = capitalised_offer(cat.definition or {}, origin)
    if cfg is None:
        return None
    cost = money(unit_cost)
    batch = InventoryAsset(tenant_id=tenant_id, product_id=inventory_product_id, catalogue_product_id=cat.id, origin=origin, reference=reference[:100],
                           quantity=quantity, unit_cost=cost, residual=min(cfg["residual"], cost), life_months=cfg["life_months"], in_service=day,
                           depreciated_months=0, accumulated=Decimal(0), status="active")
    db.add(batch)
    await db.flush()
    value = money(cost * quantity)
    journal = _journal("INVENTORY_CAPITALISE", str(batch.id), day, f"Capitalised as equipment: {cat.name} x {quantity}", [
        {"account_code": "1510", "account_name": "PP&E - Equipment", "debit": str(value), "credit": "0.00"},
        {"account_code": "1200", "account_name": "Inventory", "debit": "0.00", "credit": str(value)}])
    finance_outbox.enqueue_payload(db, tenant_id, journal, value)
    return batch


def monthly_charge(b: InventoryAsset) -> Decimal:
    return money(_d(b.quantity) * (_d(b.unit_cost) - _d(b.residual)) / b.life_months)


async def run_depreciation(db, tenant_id, as_of: Optional[date] = None) -> dict:
    """Post every month-end up to ``as_of`` that has not been posted yet (catches up after downtime). Idempotent."""
    as_of = as_of or date.today()
    batches = (await db.execute(select(InventoryAsset).where(InventoryAsset.tenant_id == tenant_id, InventoryAsset.status == "active")
                                .with_for_update(skip_locked=True))).scalars().all()
    posted, amount = 0, Decimal(0)
    for b in batches:
        depreciable = money(_d(b.quantity) * (_d(b.unit_cost) - _d(b.residual)))
        step = monthly_charge(b)
        while b.depreciated_months < b.life_months:
            y, m = add_months(b.in_service.year, b.in_service.month, b.depreciated_months)
            end = month_end(y, m)
            if end > as_of:
                break
            left = money(depreciable - _d(b.accumulated))
            charge = left if b.depreciated_months == b.life_months - 1 else min(step, left)
            b.depreciated_months += 1
            if charge > 0:
                source_id = f"{b.id}:{y}-{m:02d}"
                if not await _already_queued(db, tenant_id, "INVENTORY_DEPRECIATION", source_id):
                    finance_outbox.enqueue_payload(db, tenant_id, _journal("INVENTORY_DEPRECIATION", source_id, end, f"Depreciation {y}-{m:02d}", [
                        {"account_code": "6400", "account_name": "Depreciation & Amortization", "debit": str(charge), "credit": "0.00"},
                        {"account_code": "1600", "account_name": "Accumulated Depreciation", "debit": "0.00", "credit": str(charge)}]), charge)
                b.accumulated = money(_d(b.accumulated) + charge)
                posted += 1
                amount += charge
        if b.depreciated_months >= b.life_months:
            b.status = "fully_depreciated"
    await db.flush()
    return {"journals": posted, "amount": str(amount), "batches": len(batches)}


def _slice(b: InventoryAsset, k: int) -> tuple[Decimal, Decimal, Decimal]:
    cost = money(_d(b.unit_cost) * k)
    acc = money(_d(b.accumulated) * k / b.quantity)
    return cost, acc, money(cost - acc)


def _reduce(b: InventoryAsset, k: int, acc: Decimal, status: str) -> None:
    b.accumulated = money(_d(b.accumulated) - acc)
    b.quantity -= k
    if b.quantity <= 0:
        b.status = status


async def dispose(db, tenant_id, batch_id: uuid.UUID, quantity: int, day: date, reason: str) -> dict:
    """Lost, stolen or scrapped equipment: take it off the register and write off what is left of its value."""
    b = (await db.execute(select(InventoryAsset).where(InventoryAsset.id == batch_id, InventoryAsset.tenant_id == tenant_id).with_for_update())).scalar_one_or_none()
    if b is None or b.quantity <= 0:
        raise LookupError("Asset batch not found or already empty")
    if quantity < 1 or quantity > b.quantity:
        raise ValueError(f"Quantity must be between 1 and {b.quantity}")
    cost, acc, nbv = _slice(b, quantity)
    _reduce(b, quantity, acc, "disposed")
    source_id = hashlib.sha1(f"{b.id}:{b.quantity}:{reason}".encode()).hexdigest()
    lines = [{"account_code": "6900", "account_name": "General & Administrative", "debit": str(nbv), "credit": "0.00"},
             {"account_code": "1600", "account_name": "Accumulated Depreciation", "debit": str(acc), "credit": "0.00"},
             {"account_code": "1510", "account_name": "PP&E - Equipment", "debit": "0.00", "credit": str(cost)}]
    finance_outbox.enqueue_payload(db, tenant_id, _journal("INVENTORY_ASSET_DISPOSAL", source_id, day, f"Equipment written off: {reason}"[:200], lines), cost)
    return {"units": quantity, "cost": str(cost), "accumulated": str(acc), "written_off": str(nbv)}


def install_return_hook() -> None:
    """Customer returns are restocked by the stock-operations flow, which writes a ``customer_return`` movement. Hook the flush so the
    matching equipment is taken back at net book value in the same transaction, without that flow needing to know about assets."""
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    from services.inventory.database import StockMovement
    if getattr(install_return_hook, "_done", False):
        return
    install_return_hook._done = True

    @event.listens_for(Session, "before_flush")
    def _on_flush(session, _ctx, _instances):
        moves = [o for o in session.new if isinstance(o, StockMovement) and o.movement_type == "customer_return"
                 and not getattr(o, "_asset_done", False)]
        for mv in moves:
            mv._asset_done = True
            mv.id = mv.id or uuid.uuid4()
            with session.no_autoflush:
                cat = session.execute(select(CatalogueProduct).where(CatalogueProduct.tenant_id == mv.tenant_id,
                                                                    CatalogueProduct.inventory_product_id == mv.product_id)).scalar_one_or_none()
                if cat is None or ((cat.definition or {}).get("offer") or {}).get("mode") != "given":
                    continue
                rows = session.execute(select(InventoryAsset).where(
                    InventoryAsset.tenant_id == mv.tenant_id, InventoryAsset.product_id == mv.product_id, InventoryAsset.origin == "issue",
                    InventoryAsset.status.in_(("active", "fully_depreciated")), InventoryAsset.quantity > 0).order_by(InventoryAsset.in_service)).scalars().all()
                left, cost, acc, nbv = int(mv.quantity or 0), Decimal(0), Decimal(0), Decimal(0)
                for b in rows:
                    if left <= 0:
                        break
                    k = min(left, b.quantity)
                    left -= k
                    c, a, n = _slice(b, k)
                    cost, acc, nbv = cost + c, acc + a, nbv + n
                    _reduce(b, k, a, "returned")
                if cost > 0:
                    finance_outbox.enqueue_payload(session, mv.tenant_id, _journal(
                        "INVENTORY_ASSET_RETURN", str(mv.id), date.today(), f"Equipment returned {mv.reference or ''}".strip(), [
                            {"account_code": "1200", "account_name": "Inventory", "debit": str(nbv), "credit": "0.00"},
                            {"account_code": "1600", "account_name": "Accumulated Depreciation", "debit": str(acc), "credit": "0.00"},
                            {"account_code": "1510", "account_name": "PP&E - Equipment", "debit": "0.00", "credit": str(cost)}]), cost)


async def depreciation_loop(interval_seconds: int = 6 * 3600):
    """Background: every few hours post any month-end depreciation that is due, for every tenant with equipment on the register."""
    import asyncio
    import logging
    from services.inventory.database import _get_session_factory
    log = logging.getLogger("inventory.assets")
    while True:
        try:
            await asyncio.sleep(60)          # first pass shortly after start-up, then on the interval
            async with _get_session_factory()() as db:
                tenants = (await db.execute(select(InventoryAsset.tenant_id).where(InventoryAsset.status == "active").distinct())).scalars().all()
            for t in tenants:
                async with _get_session_factory()() as db:
                    result = await run_depreciation(db, t)
                    await db.commit()
                if result["journals"]:
                    await finance_outbox.deliver_quietly(t)
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.warning("depreciation loop error", exc_info=True)
            await asyncio.sleep(300)
