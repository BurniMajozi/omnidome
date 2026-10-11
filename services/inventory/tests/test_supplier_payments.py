"""Supplier payments: bank details, paying a purchase order from the funded payout wallet, 402 / unknown-outcome / sync."""
import asyncio
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from services.inventory import database as models, payouts_client as payouts
from services.inventory.routes import supplier_payments as sp
from services.inventory.tests.test_purchasing_phase1 import seeded

D = Decimal


def run(coro):
    return asyncio.run(coro)


async def add_bank(seed, user=None):
    async with seed.factory() as db:
        db.add(models.SupplierBank(tenant_id=seed.tenant, supplier_id=seed.po.supplier_id, bank_code="632005", account_name="Supplier Pty",
                                   account_last4="1234", recipient_code="RCP_sup"))
        await db.commit()


def fake_pay(monkeypatch, *, status="success", raises=None, fee="6.90"):
    sent = []

    async def pay(tenant_id, user_id, source_id, item_ref, recipient_code, amount_zar, reason):
        sent.append({"source": source_id, "item": item_ref, "recipient": recipient_code, "amount": amount_zar, "reason": reason})
        if raises:
            raise raises
        return {"items": [{"item_ref": item_ref, "reference": f"supplier-{item_ref}", "status": status, "fee_zar": fee, "message": None}]}
    monkeypatch.setattr(payouts, "pay", pay)
    return sent


async def pay(seed, body=None, **kw):
    async with seed.factory() as db:
        return await sp.pay_purchase_order(seed.po.id, body or sp.PayIn(**kw), seed.tenant, seed.manager, db)


async def listing(seed):
    async with seed.factory() as db:
        return await sp.list_payments(seed.po.id, seed.tenant, db)


def test_bank_details_keep_only_last_four_digits_and_block_change_mid_payment(monkeypatch):
    async def go():
        async with seeded(monkeypatch, status="approved") as seed:
            sent = {}

            async def recipient(tenant_id, name, number, bank):
                sent.update(number=number)
                return "RCP_new"
            monkeypatch.setattr(payouts, "create_recipient", recipient)
            async with seed.factory() as db:
                out = await sp.set_bank(seed.po.supplier_id, sp.BankIn(bank_code="632005", account_name="Supplier Pty", account_number="62001234567"),
                                        seed.tenant, seed.manager, db)
                await db.commit()
            assert out["account_last4"] == "4567" and sent["number"] == "62001234567" and "62001234567" not in str(out)
            async with seed.factory() as db:
                got = await sp.get_bank(seed.po.supplier_id, seed.tenant, db)
                row = (await db.execute(models.select(models.SupplierBank))).scalar_one()
            assert got["configured"] and row.recipient_code == "RCP_new" and "62001234567" not in repr(row.__dict__)
            async with seed.factory() as db:
                db.add(models.SupplierPayment(tenant_id=seed.tenant, po_id=seed.po.id, supplier_id=seed.po.supplier_id,
                                              amount_zar=D("10.00"), status="processing"))
                await db.commit()
            async with seed.factory() as db:
                with pytest.raises(HTTPException) as e:
                    await sp.set_bank(seed.po.supplier_id, sp.BankIn(bank_code="1", account_name="Other", account_number="99999999"),
                                      seed.tenant, seed.manager, db)
            assert e.value.status_code == 409
    run(go())


def test_only_approved_orders_with_bank_details_can_be_paid(monkeypatch):
    async def go():
        async with seeded(monkeypatch, status="draft") as seed:
            sent = fake_pay(monkeypatch)
            with pytest.raises(HTTPException) as e:
                await pay(seed)
            assert e.value.status_code == 409 and "approved" in e.value.detail and not sent
    run(go())

    async def go2():
        async with seeded(monkeypatch, status="approved") as seed:
            sent = fake_pay(monkeypatch)
            with pytest.raises(HTTPException) as e:
                await pay(seed)
            assert e.value.status_code == 409 and "bank details" in e.value.detail and not sent
    run(go2())


def test_full_payment_goes_out_and_blocks_a_second_full_payment(monkeypatch):
    async def go():
        async with seeded(monkeypatch, status="approved", quantity=10, cost="100.00") as seed:   # total R1,150
            await add_bank(seed)
            sent = fake_pay(monkeypatch)
            out = await pay(seed, supplier_invoice_ref="INV-77")
            assert out["status"] == "paid" and out["amount_zar"] == 1150.0 and out["fee_zar"] == 6.9
            assert sent[0]["source"] == str(seed.po.id) and sent[0]["recipient"] == "RCP_sup" and sent[0]["amount"] == "1150.00"
            assert sent[0]["item"] == out["id"]
            assert (await listing(seed))["outstanding_zar"] == 0.0
            with pytest.raises(HTTPException) as e:
                await pay(seed, amount_zar=D("0.01"))
            assert e.value.status_code == 400 and len(sent) == 1
    run(go())


def test_partial_payments_add_up_to_the_order_total_at_most(monkeypatch):
    async def go():
        async with seeded(monkeypatch, status="approved", quantity=10, cost="100.00") as seed:
            await add_bank(seed)
            fake_pay(monkeypatch)
            await pay(seed, amount_zar=D("500.00"))
            assert (await listing(seed))["outstanding_zar"] == 650.0
            with pytest.raises(HTTPException) as e:
                await pay(seed, amount_zar=D("650.01"))
            assert e.value.status_code == 400 and "R650.00" in e.value.detail
            await pay(seed, amount_zar=D("650.00"))
            assert (await listing(seed))["paid_zar"] == 1150.0
    run(go())


def test_short_wallet_is_402_and_frees_the_amount_for_a_retry(monkeypatch):
    async def go():
        async with seeded(monkeypatch, status="approved") as seed:
            await add_bank(seed)
            fake_pay(monkeypatch, raises=payouts.InsufficientFunding({"required_zar": 1219.0, "balance_zar": 0.0, "shortfall_zar": 1219.0, "fee_zar": 69.0}))
            with pytest.raises(HTTPException) as e:
                await pay(seed)
            assert e.value.status_code == 402 and e.value.detail["shortfall_zar"] == 1219.0
            data = await listing(seed)
            assert data["payments"][0]["status"] == "failed" and data["outstanding_zar"] == 1150.0
            fake_pay(monkeypatch)
            assert (await pay(seed))["status"] == "paid"
    run(go())


def test_unknown_outcome_stays_pending_counts_against_the_order_and_sync_resolves_it(monkeypatch):
    async def go():
        async with seeded(monkeypatch, status="approved") as seed:
            await add_bank(seed)
            fake_pay(monkeypatch, raises=payouts.PayoutError("payout request failed: timeout"))
            with pytest.raises(HTTPException) as e:
                await pay(seed)
            assert e.value.status_code == 502 and "recorded as pending" in e.value.detail
            data = await listing(seed)
            assert data["payments"][0]["status"] == "pending" and data["outstanding_zar"] == 0.0     # blocks a double payment
            pid = data["payments"][0]["id"]

            async def status(tenant_id, source_id, reconcile=True):
                return {"batches": [{"items": [{"item_ref": pid, "reference": "supplier-x", "status": "success", "fee_zar": 69.0}]}]}
            monkeypatch.setattr(payouts, "status", status)
            async with seed.factory() as db:
                out = await sp.sync_payments(seed.po.id, seed.tenant, db)
                await db.commit()
            assert out["payments"][0]["status"] == "paid" and out["paid_zar"] == 1150.0
    run(go())


def test_sync_fails_a_pending_payment_billing_never_saw(monkeypatch):
    async def go():
        async with seeded(monkeypatch, status="approved") as seed:
            await add_bank(seed)
            fake_pay(monkeypatch, raises=payouts.PayoutError("connection reset"))
            with pytest.raises(HTTPException):
                await pay(seed)

            async def status(tenant_id, source_id, reconcile=True):
                return {"batches": []}
            monkeypatch.setattr(payouts, "status", status)
            async with seed.factory() as db:
                out = await sp.sync_payments(seed.po.id, seed.tenant, db)
                await db.commit()
            assert out["payments"][0]["status"] == "failed" and out["paid_zar"] == 0.0
            fake_pay(monkeypatch)
            assert (await pay(seed))["status"] == "paid"                       # the amount is free again
    run(go())


def test_other_tenants_orders_are_not_found(monkeypatch):
    async def go():
        async with seeded(monkeypatch, status="approved") as seed:
            fake_pay(monkeypatch)
            async with seed.factory() as db:
                with pytest.raises(HTTPException) as e:
                    await sp.pay_purchase_order(seed.po.id, sp.PayIn(), uuid.uuid4(), seed.manager, db)
            assert e.value.status_code == 404
    run(go())
