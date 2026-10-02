"""Run against a dedicated empty *_inventory_test Postgres database, never production."""
import asyncio
import os
import uuid
from types import SimpleNamespace
import pytest
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.engine import make_url
from services.inventory.database import Base, Product, Warehouse, InventoryLevel, StockMovement
from services.inventory.schema import run_reconciliation
from services.inventory.stock import apply_move, checkout
from services.inventory.main import StockUpdate, StockCheckoutRequest

URL = os.getenv("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="Dedicated TEST_DATABASE_URL required")

def run(fn):
    return asyncio.run(fn())


def test_concurrent_first_document_numbers():
    async def case():
        from services.inventory.database import next_sequence_number
        engine, factory = await setup()
        tenant = uuid.uuid4()
        async def allocate():
            async with factory() as db:
                value = await next_sequence_number(db, tenant, "po", "PO")
                await db.commit()
                return value
        try:
            values = await asyncio.gather(*(allocate() for _ in range(8)))
            assert len(set(values)) == 8
            assert sorted(int(value.rsplit("-", 1)[1]) for value in values) == list(range(1, 9))
        finally:
            await engine.dispose()
    run(case)

async def setup():
    engine = create_async_engine(make_url(URL).set(drivername="postgresql+asyncpg"))
    assert engine.url.database.endswith("_inventory_test"), "Refusing non-test database"
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)

async def seed(factory):
    tid, uid, pid, first, second = [uuid.uuid4() for _ in range(5)]
    async with factory.begin() as db:
        db.add(Product(id=pid, tenant_id=tid, sku=f"SKU-{pid}", name="Test item"))
        db.add_all([Warehouse(id=first, tenant_id=tid, code="A", name="A"),
                    Warehouse(id=second, tenant_id=tid, code="B", name="B")])
        await db.flush()
        db.add(InventoryLevel(tenant_id=tid, product_id=pid, warehouse_id=first,
                              soh=10, allocated=2, reserved=1, sit=0))
    return tid, uid, pid, first, second

def test_transfer_retries_once_and_credits_destination():
    async def case():
        engine, factory = await setup()
        try:
            tid, uid, pid, first, second = await seed(factory)
            move = StockUpdate(product_id=pid, warehouse_id=first,
                destination_warehouse_id=second, movement_type="TRANSFER", quantity=4)
            async with factory.begin() as db:
                initial = await apply_move(db, tid, uid, move, "transfer-1")
            async with factory.begin() as db:
                assert await apply_move(db, tid, uid, move, "transfer-1") == initial
                levels = (await db.execute(select(InventoryLevel).where(InventoryLevel.tenant_id == tid))).scalars().all()
                assert {row.warehouse_id: row.soh for row in levels} == {first: 6, second: 4}
                assert all(row.available >= 0 for row in levels)
                assert len((await db.execute(select(StockMovement).where(StockMovement.tenant_id == tid))).scalars().all()) == 1
        finally:
            await engine.dispose()
    run(case)

def test_concurrent_checkout_cannot_overallocate_and_accepts_sku():
    async def case():
        engine, factory = await setup()
        try:
            tid, uid, pid, first, _ = await seed(factory)
            payload = StockCheckoutRequest(job_id="job", warehouse_id=first,
                items=[{"product_id": f"SKU-{pid}", "quantity": 5}])
            async def send(key):
                try:
                    async with factory.begin() as db:
                        await checkout(db, tid, uid, payload, key)
                    return 200
                except Exception as exc:
                    return getattr(exc, "status_code", 500)
            assert sorted(await asyncio.gather(send("a"), send("b"))) == [200, 409]
            async with factory.begin() as db:
                row = (await db.execute(select(InventoryLevel).where(InventoryLevel.tenant_id == tid))).scalar_one()
                assert (row.soh, row.allocated, row.reserved, row.available) == (10, 7, 1, 2)
        finally:
            await engine.dispose()
    run(case)

def test_foreign_product_is_hidden_and_failed_checkout_rolls_back():
    async def case():
        engine, factory = await setup()
        try:
            tid, uid, pid, first, _ = await seed(factory)
            payload = StockCheckoutRequest(warehouse_id=first,
                items=[{"product_id": str(pid), "quantity": 2},
                       {"product_id": str(uuid.uuid4()), "quantity": 1}])
            with pytest.raises(Exception) as exc:
                async with factory.begin() as db:
                    await checkout(db, tid, uid, payload, "bad-batch")
            assert exc.value.status_code == 404
            move = StockUpdate(product_id=pid, warehouse_id=first, quantity=1, movement_type="SALE")
            with pytest.raises(Exception) as exc:
                async with factory.begin() as db:
                    await apply_move(db, uuid.uuid4(), uid, move, "foreign")
            assert exc.value.status_code == 404
            async with factory.begin() as db:
                row = (await db.execute(select(InventoryLevel).where(InventoryLevel.tenant_id == tid))).scalar_one()
                assert row.allocated == 2
        finally:
            await engine.dispose()
    run(case)

def test_schema_reconciliation_is_idempotent():
    async def case():
        engine, _ = await setup()
        try:
            for _ in range(2):
                result = await run_reconciliation(engine)
                assert not result["failed_steps"]
                assert not result["unique_indexes"]["failed"]
        finally:
            await engine.dispose()
    run(case)

def test_legacy_migration_keeps_parent_ids_and_stock():
    async def case():
        engine, _ = await setup()
        tid, category_id, warehouse_id, product_id = [uuid.uuid4() for _ in range(4)]
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.execute(text("CREATE TABLE product_categories (id UUID PRIMARY KEY, tenant_id UUID, name TEXT, description TEXT, created_at TIMESTAMPTZ)"))
                await conn.execute(text("CREATE TABLE warehouses (id UUID PRIMARY KEY, tenant_id UUID, name TEXT, location TEXT, is_external BOOLEAN, partner_name TEXT, created_at TIMESTAMPTZ)"))
                await conn.execute(text("CREATE TABLE inventory_products (id UUID PRIMARY KEY, tenant_id UUID, category_id UUID REFERENCES product_categories(id), sku TEXT UNIQUE NOT NULL, name TEXT NOT NULL, description TEXT, cost_price NUMERIC DEFAULT 0, rrp NUMERIC DEFAULT 0, created_at TIMESTAMPTZ DEFAULT now())"))
                await conn.execute(text("CREATE TABLE inventory_levels (id UUID PRIMARY KEY, tenant_id UUID, warehouse_id UUID REFERENCES warehouses(id), product_id UUID REFERENCES inventory_products(id), soh INTEGER DEFAULT 0, sit INTEGER DEFAULT 0, allocated INTEGER DEFAULT 0, min_threshold INTEGER DEFAULT 10, created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now())"))
                await conn.execute(text("INSERT INTO product_categories (id,tenant_id,name) VALUES (:id,:tid,'Existing category')"), {"id": category_id, "tid": tid})
                await conn.execute(text("INSERT INTO warehouses (id,tenant_id,name) VALUES (:id,:tid,'Existing warehouse')"), {"id": warehouse_id, "tid": tid})
                await conn.execute(text("INSERT INTO inventory_products (id,tenant_id,category_id,sku,name) VALUES (:id,:tid,:cid,'OLD-SKU','Existing product')"), {"id": product_id, "tid": tid, "cid": category_id})
                await conn.execute(text("INSERT INTO inventory_levels (id,tenant_id,warehouse_id,product_id,soh,allocated) VALUES (:id,:tid,:wid,:pid,12,3)"), {"id": uuid.uuid4(), "tid": tid, "wid": warehouse_id, "pid": product_id})
                await conn.run_sync(Base.metadata.create_all)
            result = await run_reconciliation(engine)
            assert not result["failed_steps"]
            async with engine.connect() as conn:
                assert (await conn.execute(text("SELECT soh,allocated,available FROM inventory_levels"))).one() == (12, 3, 9)
                assert (await conn.execute(text("SELECT id FROM inventory_warehouses WHERE id=:id"), {"id": warehouse_id})).scalar() == warehouse_id
                assert (await conn.execute(text("SELECT category_id FROM inventory_products"))).scalar() == category_id
            assert not (await run_reconciliation(engine))["failed_steps"]
        finally:
            await engine.dispose()
    run(case)
