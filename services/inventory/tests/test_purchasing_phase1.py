"""Focused purchasing behavior tests; SQLite does not validate Postgres row-lock semantics."""
import asyncio
import base64
import copy
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from services.inventory import database as models, finance_outbox, stock
from services.inventory.purchasing_helpers import approval_hash, journal_payload, money, render_purchase_order_pdf
from services.inventory.routes import purchasing as routes


@compiles(JSONB, "sqlite")
def sqlite_jsonb(_type, _compiler, **_kw):
    return "JSON"


PNG = "data:image/png;base64," + base64.b64encode(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)).decode()


def approval_input(**kw):
    return routes.ApprovalInput(signer_name="Manager", signature_data=PNG, **kw)


@asynccontextmanager
async def seeded(monkeypatch, *, limit=0, status="draft", quantity=10, cost="100.00"):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(models.Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(models, "_get_session_factory", lambda: factory)
    async def no_delivery(*args, **kwargs):
        return {"sent": 0, "failed": 0}
    monkeypatch.setattr(finance_outbox, "deliver", no_delivery)
    tenant, creator, manager = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with factory() as db:
        supplier = models.Supplier(tenant_id=tenant, code="SUP", name="Supplier")
        warehouse = models.Warehouse(tenant_id=tenant, code="WH", name="Warehouse")
        product = models.Product(tenant_id=tenant, sku="P1", name="Product")
        db.add_all([supplier, warehouse, product])
        await db.flush()
        value = Decimal(cost) * quantity
        po = models.PurchaseOrder(tenant_id=tenant, supplier_id=supplier.id, warehouse_id=warehouse.id,
            po_number="PO-1", status=status, currency="ZAR", created_by=creator,
            subtotal_zar=value, tax_zar=money(value * Decimal(".15")), total_zar=money(value * Decimal("1.15")))
        db.add(po)
        await db.flush()
        line = models.PurchaseOrderItem(po_id=po.id, product_id=product.id, quantity_ordered=quantity,
                                       quantity_received=0, unit_cost_zar=Decimal(cost), total_cost_zar=value)
        db.add_all([line, models.InventorySettings(tenant_id=tenant, auto_approve_limit=Decimal(limit))])
        await db.flush()
        if status in ("approved", "sent"):
            routes._audit(db, po, [line], "approved", manager, approval_input())
        await db.commit()
        yield SimpleNamespace(db=db, factory=factory, po=po, line=line, tenant=tenant,
                              creator=creator, manager=manager, product=product, warehouse=warehouse)
    await engine.dispose()


def receipt(seed, received=3, rejected=0, ref="delivery-1"):
    return routes.GoodsReceiptCreate(receipt_ref=ref, items=[routes.GRItemInput(
        po_item_id=seed.line.id, quantity_received=received, quantity_rejected=rejected,
        rejection_reason="Damaged" if rejected else None)])


def test_hash_is_stable_but_covers_approved_content():
    po = SimpleNamespace(id=uuid.uuid4(), supplier_id=uuid.uuid4(), warehouse_id=uuid.uuid4(),
                         currency="ZAR", subtotal_zar=Decimal(200), tax_zar=Decimal(30), total_zar=Decimal(230))
    items = [SimpleNamespace(id=uuid.uuid4(), product_id=uuid.uuid4(), quantity_ordered=1,
                             unit_cost_zar=Decimal(100), total_cost_zar=Decimal(100)) for _ in range(2)]
    digest = approval_hash(po, items)
    assert digest == approval_hash(po, list(reversed(items)))
    items[0].quantity_received = 99
    assert digest == approval_hash(po, items)
    items[0].quantity_ordered = 2
    assert digest != approval_hash(po, items)


@pytest.mark.parametrize("bad", ["", "<svg/>", "data:image/png;base64,invalid", "data:image/png;base64,YWJj"])
def test_invalid_signature_is_rejected(bad):
    with pytest.raises(ValidationError):
        routes.ApprovalInput(signer_name="Manager", signature_data=bad)


@pytest.mark.parametrize("value", ["0.01", "0.03", "100.00", "200.05"])
def test_journal_balances_and_uses_real_vat_accounts(value):
    gr = SimpleNamespace(id=uuid.uuid4(), gr_number="GR-1", received_at=datetime.now(timezone.utc))
    payload = journal_payload(gr, Decimal(value))
    assert sum(Decimal(i["debit"]) for i in payload["lines"]) == sum(Decimal(i["credit"]) for i in payload["lines"])
    assert {i["account_code"] for i in payload["lines"]} <= {"1200", "2000", "2210"}
    assert payload["auto_post"] is True
    assert payload["source_id"] == str(gr.id)


@pytest.mark.parametrize("limit,total_status,mode", [("0", "pending_approval", None), ("1149.99", "pending_approval", None),
                                                     ("1150", "approved", "auto")])
def test_submit_respects_tenant_limit_and_audits_auto(monkeypatch, limit, total_status, mode):
    async def scenario():
        async with seeded(monkeypatch, limit=limit) as s:
            po = await routes.submit_purchase_order(s.po.id, s.tenant, s.creator, s.db)
            assert po.status == total_status and po.approval_mode == mode
            audits = (await s.db.execute(select(models.PurchaseOrderApproval))).scalars().all()
            assert len(audits) == (1 if mode else 0)
            if mode:
                assert audits[0].signature_data is None and po.approved_by is None
                assert po.approval_hash == audits[0].po_total_hash
    asyncio.run(scenario())


def test_manual_decision_prevents_creator_and_submitter_and_records_signature(monkeypatch):
    async def scenario():
        async with seeded(monkeypatch) as s:
            await routes.submit_purchase_order(s.po.id, s.tenant, s.creator, s.db)
            for actor in (s.creator,):
                with pytest.raises(HTTPException) as exc:
                    await routes.approve_purchase_order(s.po.id, approval_input(), s.tenant, actor, s.db)
                assert exc.value.status_code == 403
            s.po.submitted_by = uuid.uuid4()
            with pytest.raises(HTTPException) as exc:
                await routes.approve_purchase_order(s.po.id, approval_input(), s.tenant, s.po.submitted_by, s.db)
            assert exc.value.status_code == 403
            result = await routes.approve_purchase_order(s.po.id, approval_input(), s.tenant, s.manager, s.db)
            audit = (await s.db.execute(select(models.PurchaseOrderApproval))).scalar_one()
            assert result.status == "approved" and audit.signature_data == PNG and audit.signer_user_id == s.manager
            records = await routes.list_po_approvals(s.po.id, s.tenant, s.db)
            assert len(records[0]["signature_hash"]) == 64
            assert records[0]["po_total_hash"] == result.approval_hash
            with pytest.raises(HTTPException):
                await routes.approve_purchase_order(s.po.id, approval_input(), s.tenant, s.manager, s.db)
    asyncio.run(scenario())


def test_reject_cancel_and_receive_state_gates(monkeypatch):
    async def scenario():
        async with seeded(monkeypatch) as s:
            await routes.submit_purchase_order(s.po.id, s.tenant, s.creator, s.db)
            body = routes.RejectionInput(signer_name="Manager", signature_data=PNG, comment="Too expensive")
            result = await routes.reject_purchase_order(s.po.id, body, s.tenant, s.manager, s.db)
            assert result.status == "rejected" and result.rejection_reason == "Too expensive"
            with pytest.raises(HTTPException):
                await routes.create_goods_receipt(s.po.id, receipt(s), s.tenant, s.manager, s.db)
            assert (await routes.cancel_purchase_order(s.po.id, s.tenant, s.db)).status == "cancelled"
            with pytest.raises(HTTPException):
                await routes.submit_purchase_order(s.po.id, s.tenant, s.creator, s.db)
    asyncio.run(scenario())


def test_receipt_atomic_accepted_stock_vat_and_idempotent_replay(monkeypatch):
    async def scenario():
        async with seeded(monkeypatch, status="sent") as s:
            observed = []
            async def after_commit(tenant, actor):
                # Separate session sees the durable receipt, stock and outbox before delivery.
                async with s.factory() as other:
                    observed.append((await other.execute(select(func.count()).select_from(models.GoodsReceipt))).scalar())
                    assert (await other.execute(select(models.InventoryLevel.soh))).scalar_one() == 2
                    assert (await other.execute(select(models.InventoryFinanceOutbox))).scalar_one().status == "pending"
                raise RuntimeError("finance unavailable")
            monkeypatch.setattr(finance_outbox, "deliver", after_commit)
            body = receipt(s, received=3, rejected=1)
            gr = await routes.create_goods_receipt(s.po.id, body, s.tenant, s.manager, s.db)
            assert gr.status == "partially_accepted" and gr.value_ex_vat_zar == Decimal(200) and gr.vat_zar == Decimal(30)
            assert s.line.quantity_received == 2 and s.po.status == "partially_received"
            replay = await routes.create_goods_receipt(s.po.id, body, s.tenant, s.manager, s.db)
            assert replay.id == gr.id and observed == [1]
            assert (await s.db.execute(select(models.InventoryLevel.soh))).scalar_one() == 2
            assert (await s.db.execute(select(func.count()).select_from(models.StockMovement))).scalar() == 1
    asyncio.run(scenario())


@pytest.mark.parametrize("invalid", ["over", "duplicate", "foreign", "rejection"])
def test_bad_receipts_leave_stock_and_outbox_untouched(monkeypatch, invalid):
    async def scenario():
        async with seeded(monkeypatch, status="approved") as s:
            body = receipt(s)
            if invalid == "over": body.items[0].quantity_received = 11
            if invalid == "duplicate": body.items.append(copy.copy(body.items[0]))
            if invalid == "foreign": body.items[0].po_item_id = uuid.uuid4()
            if invalid == "rejection": body.items[0].quantity_rejected = 4
            with pytest.raises(HTTPException):
                await routes.create_goods_receipt(s.po.id, body, s.tenant, s.manager, s.db)
            assert s.line.quantity_received == 0
            for model in (models.InventoryLevel, models.GoodsReceipt, models.InventoryFinanceOutbox):
                assert (await s.db.execute(select(func.count()).select_from(model))).scalar() == 0
    asyncio.run(scenario())


def test_all_rejected_remains_outstanding_with_no_stock_or_finance(monkeypatch):
    async def scenario():
        async with seeded(monkeypatch, status="approved") as s:
            gr = await routes.create_goods_receipt(s.po.id, receipt(s, 3, 3), s.tenant, s.manager, s.db)
            assert gr.status == "rejected" and s.line.quantity_received == 0
            assert (await s.db.execute(select(models.InventoryLevel.soh))).scalar_one() == 0
            assert (await s.db.execute(select(func.count()).select_from(models.InventoryFinanceOutbox))).scalar() == 0
    asyncio.run(scenario())


def test_approval_tampering_and_cross_tenant_are_blocked(monkeypatch):
    async def scenario():
        async with seeded(monkeypatch, status="approved") as s:
            with pytest.raises(HTTPException) as exc:
                await routes.get_purchase_order(s.po.id, uuid.uuid4(), s.db)
            assert exc.value.status_code == 404
            s.line.unit_cost_zar += Decimal(1)
            with pytest.raises(HTTPException) as exc:
                await routes.create_goods_receipt(s.po.id, receipt(s), s.tenant, s.manager, s.db)
            assert exc.value.status_code == 409
    asyncio.run(scenario())


def test_send_rejects_missing_supplier_email_and_preserves_approval(monkeypatch):
    async def scenario():
        async with seeded(monkeypatch, status="approved") as s:
            with pytest.raises(HTTPException) as exc:
                await routes.send_purchase_order(s.po.id, s.tenant, s.db)
            assert exc.value.status_code == 422 and "email address" in exc.value.detail
            assert s.po.status == "approved" and s.po.sent_at is None
    asyncio.run(scenario())

def test_send_attaches_real_pdf_and_marks_only_confirmed_delivery(monkeypatch):
    async def scenario():
        async with seeded(monkeypatch, status="approved") as s:
            supplier = (await s.db.execute(select(models.Supplier).where(models.Supplier.id == s.po.supplier_id))).scalar_one()
            supplier.email = "supplier@example.test"
            sent = []
            async def fake_get(service, path, **kwargs):
                assert kwargs["tenant_id"] == s.tenant
                return {"pdf_attachments": True, "configured": True} if path.endswith("send-capabilities") else [{"id": str(uuid.uuid4()), "is_active": True}]
            async def fake_post(service, path, **kwargs):
                assert path == "/api/v1/mail/send" and kwargs["retries"] == 0
                sent.append(kwargs["json"])
                assert base64.b64decode(sent[0]["attachments"][0]["content"]).startswith(b"%PDF-")
                return {"status": "sent", "message_id": "provider-po-test"}
            monkeypatch.setattr(routes, "service_get", fake_get)
            monkeypatch.setattr(routes, "service_post", fake_post)
            result = await routes.send_purchase_order(s.po.id, s.tenant, s.db, s.manager)
            assert result["status"] == "sent" and s.po.status == "sent"
            assert s.po.sent_message_id == "provider-po-test" and s.po.send_claimed_at is None
            assert sent[0]["to"] == [supplier.email]
            with pytest.raises(HTTPException) as exc:
                await routes.send_purchase_order(s.po.id, s.tenant, s.db, s.manager)
            assert exc.value.status_code == 409 and len(sent) == 1
    asyncio.run(scenario())

def test_uncertain_supplier_delivery_preserves_claim_and_blocks_repeat(monkeypatch):
    async def scenario():
        async with seeded(monkeypatch, status="approved") as s:
            supplier = (await s.db.execute(select(models.Supplier).where(models.Supplier.id == s.po.supplier_id))).scalar_one()
            supplier.email = "supplier@example.test"
            async def fake_get(service, path, **kwargs):
                return {"pdf_attachments": True, "configured": True} if path.endswith("send-capabilities") else [{"id": str(uuid.uuid4())}]
            async def uncertain(*args, **kwargs):
                raise TimeoutError()
            monkeypatch.setattr(routes, "service_get", fake_get)
            monkeypatch.setattr(routes, "service_post", uncertain)
            with pytest.raises(HTTPException) as exc:
                await routes.send_purchase_order(s.po.id, s.tenant, s.db, s.manager)
            assert exc.value.status_code == 502 and s.po.status == "approved"
            assert s.po.send_claimed_at is not None and s.po.sent_at is None
            with pytest.raises(HTTPException) as exc:
                await routes.send_purchase_order(s.po.id, s.tenant, s.db, s.manager)
            assert exc.value.status_code == 409
    asyncio.run(scenario())


def test_delivery_failure_backoff_retry_and_sent_skip(monkeypatch):
    original = finance_outbox.deliver
    async def scenario():
        async with seeded(monkeypatch, status="approved") as s:
            await routes.create_goods_receipt(s.po.id, receipt(s), s.tenant, s.manager, s.db)
            calls = []
            async def failing(*args):
                calls.append(args)
                raise RuntimeError("offline")
            monkeypatch.setattr(finance_outbox, "post_entry", failing)
            assert await original(s.tenant, session_factory=s.factory) == {"sent": 0, "failed": 1}
            assert await original(s.tenant, session_factory=s.factory) == {"sent": 0, "failed": 0}
            async def success(*args): calls.append(args)
            monkeypatch.setattr(finance_outbox, "post_entry", success)
            assert await original(s.tenant, force=True, session_factory=s.factory) == {"sent": 1, "failed": 0}
            assert await original(s.tenant, force=True, session_factory=s.factory) == {"sent": 0, "failed": 0}
            assert len(calls) == 2 and calls[0][2]["source_id"] == calls[1][2]["source_id"]
    asyncio.run(scenario())


def test_pdf_returns_real_bytes_or_explicit_renderer_block():
    po = SimpleNamespace(po_number="PO-1", currency="ZAR", warehouse_id=uuid.uuid4(),
                         subtotal_zar=Decimal(100), tax_zar=Decimal(15), total_zar=Decimal(115))
    try:
        pdf = render_purchase_order_pdf(po, [], "Supplier")
    except HTTPException as exc:
        assert exc.status_code == 503 and "renderer unavailable" in exc.detail
    else:
        assert pdf.startswith(b"%PDF-") and b"%%EOF" in pdf


def test_mutations_enforce_role_dependencies(monkeypatch):
    from services.common.auth import AuthContext, get_auth_context
    monkeypatch.setenv("AUTH_ENFORCE_RBAC", "false")
    app = FastAPI()
    app.include_router(routes.router)
    ctx = AuthContext(tenant_id=uuid.uuid4(), user_id=uuid.uuid4(), roles=["viewer"], rbac_loaded=True)
    app.dependency_overrides[get_auth_context] = lambda: ctx
    async def no_db(): yield None
    app.dependency_overrides[models.get_session] = no_db
    with TestClient(app) as client:
        result = client.post("/suppliers", json={"code": "S", "name": "Supplier"})
        assert result.status_code == 403
        result = client.put("/purchasing/settings", json={"auto_approve_limit": "1000"})
        assert result.status_code == 403
        ctx.roles = ["stock_controller"]
        result = client.post(f"/purchase-orders/{uuid.uuid4()}/approve", json={"signer_name": "Manager", "signature_data": PNG})
        assert result.status_code == 403


def test_receipt_completion_replay_and_cancel_protection(monkeypatch):
    async def scenario():
        async with seeded(monkeypatch, status="approved", quantity=3) as s:
            gr = await routes.create_goods_receipt(s.po.id, receipt(s), s.tenant, s.manager, s.db)
            assert s.po.status == "received" and s.po.received_at
            assert (await routes.create_goods_receipt(s.po.id, receipt(s), s.tenant, s.manager, s.db)).id == gr.id
            with pytest.raises(HTTPException) as exc:
                await routes.create_goods_receipt(s.po.id, receipt(s, received=2), s.tenant, s.manager, s.db)
            assert exc.value.status_code == 409
            with pytest.raises(HTTPException):
                await routes.cancel_purchase_order(s.po.id, s.tenant, s.db)
    asyncio.run(scenario())


def test_rollback_after_stock_delta_removes_receipt_movement_and_outbox(monkeypatch):
    async def scenario():
        async with seeded(monkeypatch, status="approved") as s:
            po_id, line_id = s.po.id, s.line.id
            body = receipt(s)
            original_enqueue = finance_outbox.enqueue
            def broken_enqueue(*args):
                original_enqueue(*args)
                raise RuntimeError("transaction interrupted")
            monkeypatch.setattr(finance_outbox, "enqueue", broken_enqueue)
            with pytest.raises(RuntimeError):
                await routes.create_goods_receipt(po_id, body, s.tenant, s.manager, s.db)
            await s.db.rollback()
            async with s.factory() as other:
                assert (await other.execute(select(models.PurchaseOrderItem.quantity_received).where(models.PurchaseOrderItem.id == line_id))).scalar_one() == 0
                for model in (models.InventoryLevel, models.GoodsReceipt, models.StockMovement, models.InventoryFinanceOutbox):
                    assert (await other.execute(select(func.count()).select_from(model))).scalar() == 0
    asyncio.run(scenario())


def test_receipt_locks_shared_products_in_sorted_order(monkeypatch):
    async def scenario():
        async with seeded(monkeypatch, status="approved") as s:
            product = models.Product(tenant_id=s.tenant, sku="P2", name="Product 2")
            s.db.add(product)
            await s.db.flush()
            line = models.PurchaseOrderItem(po_id=s.po.id, product_id=product.id, quantity_ordered=1,
                                           quantity_received=0, unit_cost_zar=Decimal(100), total_cost_zar=Decimal(100))
            s.db.add(line)
            await s.db.flush()
            s.po.subtotal_zar += 100
            s.po.tax_zar += 15
            s.po.total_zar += 115
            s.po.approval_hash = approval_hash(s.po, [s.line, line])
            await s.db.commit()
            calls = []
            original = stock.locked_level
            async def recording(db, tenant, product_id, warehouse_id):
                calls.append(product_id)
                return await original(db, tenant, product_id, warehouse_id)
            monkeypatch.setattr(stock, "locked_level", recording)
            body = receipt(s)
            body.items.insert(0, routes.GRItemInput(po_item_id=line.id, quantity_received=1))
            await routes.create_goods_receipt(s.po.id, body, s.tenant, s.manager, s.db)
            assert calls == sorted([s.product.id, product.id], key=str)
    asyncio.run(scenario())


def test_finance_transport_uses_system_key_and_decimal_payload(monkeypatch):
    async def scenario():
        monkeypatch.setenv("INTERNAL_SERVICE_KEY", "test-internal-key")
        calls = []
        async def fake_request(*args, **kwargs): calls.append((args, kwargs))
        monkeypatch.setattr(finance_outbox, "_request", fake_request)
        tenant, actor = uuid.uuid4(), uuid.uuid4()
        gr = SimpleNamespace(id=uuid.uuid4(), gr_number="GR", received_at=datetime.now(timezone.utc))
        payload = journal_payload(gr, Decimal("100.00"))
        await finance_outbox.post_entry(tenant, actor, payload)
        args, kwargs = calls[0]
        assert args == ("POST", "finance", "/journal-entries")
        assert kwargs["extra_headers"] == {"x-internal-key": "test-internal-key"}
        assert kwargs["tenant_id"] == tenant and kwargs["json"]["auto_post"] is True
    asyncio.run(scenario())


def test_settings_update_persists_and_is_tenant_scoped(monkeypatch):
    async def scenario():
        async with seeded(monkeypatch) as s:
            await routes.update_purchasing_settings(routes.SettingsInput(auto_approve_limit="5000"), s.tenant, s.manager, s.db)
            await s.db.commit()
            assert (await routes.get_purchasing_settings(s.tenant, s.db))["auto_approve_limit"] == "5000.00"
            assert (await routes.get_purchasing_settings(uuid.uuid4(), s.db))["auto_approve_limit"] == "0.00"
    asyncio.run(scenario())
