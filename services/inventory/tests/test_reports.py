"""Run report SQL against real in-memory SQLite tables, including cross-tenant rows."""
import asyncio
import csv
import io
import uuid
from datetime import date
from decimal import Decimal
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from services.inventory.database import Product, Warehouse, InventoryLevel, PurchaseOrder, GoodsReceipt, Supplier
from services.inventory.routes.reports import build_report, csv_cell

@compiles(JSONB, "sqlite")
def sqlite_json(element, compiler, **kwargs):
    return "JSON"

class Session:
    def __init__(self, connection): self.connection = connection
    async def execute(self, query): return self.connection.execute(query)

@pytest.fixture
def records():
    engine = create_engine("sqlite://")
    tables = [Product.__table__, Warehouse.__table__, InventoryLevel.__table__, PurchaseOrder.__table__, GoodsReceipt.__table__, Supplier.__table__]
    for table in tables: table.create(engine)
    with engine.begin() as conn:
        tenant, other, product, warehouse, supplier, po = [uuid.uuid4() for _ in range(6)]
        for tid, pid, wid, name in [(tenant, product, warehouse, "=danger"), (other, uuid.uuid4(), uuid.uuid4(), "Other tenant")]:
            conn.execute(Product.__table__.insert().values(id=pid, tenant_id=tid, sku=str(pid), name=name, cost_price=Decimal("12.50"), rrp=Decimal("20.00")))
            conn.execute(Warehouse.__table__.insert().values(id=wid, tenant_id=tid, name=name, code=str(wid)))
            conn.execute(InventoryLevel.__table__.insert().values(tenant_id=tid, product_id=pid, warehouse_id=wid, soh=10, allocated=3, reserved=2, sit=4, reorder_point=8, max_threshold=20))
        conn.execute(PurchaseOrder.__table__.insert().values(id=po, tenant_id=tenant, supplier_id=supplier, warehouse_id=warehouse, po_number="PO-1", status="approved", total_zar=Decimal("115.00"), order_date=date(2026, 10, 1)))
        for value in [Decimal("20.00"), Decimal("30.00")]:
            conn.execute(GoodsReceipt.__table__.insert().values(tenant_id=tenant, po_id=po, warehouse_id=warehouse, gr_number=str(uuid.uuid4()), status="accepted", value_ex_vat_zar=value, vat_zar=value * Decimal("0.15")))
        yield Session(conn), tenant, other, warehouse
    engine.dispose()

def report(records, kind, **kwargs):
    db, tenant, _, _ = records
    return asyncio.run(build_report(db, kind, tenant, kwargs.get("warehouse"), kwargs.get("start"), kwargs.get("end"), kwargs.get("page", 1), kwargs.get("size", 50), kwargs.get("export", False)))

def test_valuation_tenant_scope_and_complete_totals(records):
    data = report(records, "valuation")
    assert data["total"] == 1
    assert data["totals"]["value_zar"] == "125.00"
    assert data["items"][0]["available"] == 5
    assert report(records, "valuation", page=2, size=1)["totals"] == data["totals"]
    assert report(records, "valuation", warehouse=uuid.uuid4())["total"] == 0

def test_reorder_accounts_for_transit_without_creating_orders(records):
    row = report(records, "reorder")["items"][0]
    assert row["suggested_quantity"] == 11
    assert row["estimated_net_zar"] == "137.50"

def test_spend_receipts_do_not_multiply_committed_order_value(records):
    data = report(records, "spend")
    assert data["totals"] == {"committed_gross_zar": "115.00", "received_net_zar": "50.00", "received_vat_zar": "7.50"}
    assert report(records, "spend", start=date(2026, 10, 2))["total"] == 0

def test_margin_and_zero_price(records):
    assert report(records, "margin")["items"][0]["margin_percent"] == "37.50"
    records[0].connection.execute(Product.__table__.update().values(rrp=0))
    assert report(records, "margin")["items"][0]["margin_percent"] is None

def test_csv_protects_formulas_and_exports_all_pages(records):
    response = report(records, "valuation", size=1, page=2, export=True)
    rows = list(csv.DictReader(io.StringIO(response.body.decode("utf-8-sig"))))
    assert len(rows) == 1
    assert rows[0]["name"] == "'=danger"
    assert csv_cell("  @SUM(1)") == "'  @SUM(1)"
    assert csv_cell(Decimal("-2.00")) == Decimal("-2.00")

def test_invalid_date_range(records):
    with pytest.raises(HTTPException) as exc:
        report(records, "spend", start=date(2026, 10, 5), end=date(2026, 10, 1))
    assert exc.value.status_code == 422
