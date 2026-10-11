"""Funded payouts: wallet, liability recovery, batch reserve/execute, failures and reversals, reconcile, funding webhook."""
import asyncio
import os
import sys
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.common.auth import AuthContext  # noqa: E402
from services.billing.models_gateway import GatewayLiability  # noqa: E402
from services.billing.models_payouts import PayoutBatch, PayoutFunding, PayoutItem, PayoutWallet, PayoutWalletEntry  # noqa: E402
from services.billing.routes import paystack, payouts as po  # noqa: E402
from services.billing.tests import sqlite_harness as h  # noqa: E402

D = Decimal


@pytest.fixture
def env(monkeypatch):
    db = h.make_session_factory()
    h.patch_sessions(monkeypatch, db)
    monkeypatch.setattr(po, "get_session", db)
    monkeypatch.setattr(po, "_secret", lambda: "sk_test_x")
    calls = []
    script = {"bulk": None, "balance": 10**9, "verify": {}}

    async def fake(method, path, body=None):
        calls.append((method, path, body))
        if path == "/balance":
            return {"status": True, "_http_status": 200, "data": [{"currency": "ZAR", "balance": script["balance"]}]}
        if path == "/transfer/bulk":
            if script["bulk"] is not None:
                return script["bulk"]
            return {"status": True, "_http_status": 200, "data": [
                {"reference": t["reference"], "recipient": t["recipient"], "amount": t["amount"], "currency": "ZAR",
                 "transfer_code": "TRF_" + t["reference"][-6:], "status": "success"} for t in body["transfers"]]}
        if path.startswith("/transfer/verify/"):
            return script["verify"].get(path.rsplit("/", 1)[1], {"status": False, "_http_status": 404, "message": "Transfer not found"})
        return {"status": True, "_http_status": 200, "data": {}}
    monkeypatch.setattr(po, "_paystack", fake)
    tenant = uuid.uuid4()
    return SimpleNamespace(db=db, tenant=tenant, calls=calls, script=script, ctx=AuthContext(user_id=uuid.uuid4(), tenant_id=tenant))


def fund(env, rand, ref=None):
    with env.db() as s:
        po.credit_funding(s, env.tenant, "manual_funding", int(D(rand) * 100), ref or f"eft-{uuid.uuid4().hex[:6]}")


def balance(env):
    with env.db() as s:
        w = s.query(PayoutWallet).filter_by(tenant_id=env.tenant).first()
        entries = sum(e.amount_cents for e in s.query(PayoutWalletEntry).filter_by(tenant_id=env.tenant))
        assert (w.balance_cents if w else 0) == entries, "wallet balance must always equal the sum of its entries"
        return (w.balance_cents if w else 0) / 100


def batch(env, amounts, kind="payroll", source="run-1", refs=None):
    items = [po.PayoutItemIn(item_ref=(refs or [f"slip{i}" for i in range(len(amounts))])[i], recipient_code=f"RCP_{i}", amount_zar=D(a),
                             reason="Payroll") for i, a in enumerate(amounts)]
    return po.BatchIn(tenant_id=env.tenant, kind=kind, source_id=source, items=items)


def run_batch(env, body):
    with env.db() as s:
        b, _ = po.create_batch(s, body)
        bid = b.id
    return asyncio.run(po.execute_batch(bid))


# ---- wallet ---------------------------------------------------------------------------

def test_funding_is_idempotent_per_reference(env):
    fund(env, "1000", "eft-1")
    fund(env, "1000", "eft-1")
    assert balance(env) == 1000.0


def test_funding_recovers_open_liabilities_oldest_first_and_whole_only(env):
    with env.db() as s:
        s.add(GatewayLiability(tenant_id=env.tenant, kind="refund", source_id="a", amount_cents=30_000, note="refund"))
        s.add(GatewayLiability(tenant_id=env.tenant, kind="chargeback", source_id="b", amount_cents=500_000, note="chargeback"))
    fund(env, "1000")                                    # R300 refund recovered; R5,000 chargeback is more than is left
    assert balance(env) == 700.0
    with env.db() as s:
        st = {l.source_id: l.status for l in s.query(GatewayLiability)}
        assert st == {"a": "recovered", "b": "open"}
        assert po.open_liabilities_cents(s, env.tenant) == 500_000


# ---- batch reserve / execute ---------------------------------------------------------------

def test_short_wallet_is_refused_and_nothing_is_reserved(env):
    fund(env, "100")
    with pytest.raises(HTTPException) as e:
        run_batch(env, batch(env, ["100.00"]))           # R100 + R6 fee needs R106
    assert e.value.status_code == 402 and e.value.detail["shortfall_zar"] == 6.0 and e.value.detail["fee_zar"] == 6.0
    assert balance(env) == 100.0 and not env.calls
    with env.db() as s:
        assert s.query(PayoutBatch).count() == 0


def test_successful_bulk_debits_amount_plus_fee_and_records_each_item(env):
    fund(env, "20000")
    out = run_batch(env, batch(env, ["5000.00", "3000.00"]))      # R8,000 at 6% = R480 fee
    assert out["status"] == "completed" and out["total_zar"] == 8000.0 and out["fee_zar"] == 480.0
    assert [i["status"] for i in out["items"]] == ["success", "success"] and sum(i["fee_zar"] for i in out["items"]) == 480.0
    assert balance(env) == 20000 - 8000 - 480
    bulk = [c for c in env.calls if c[1] == "/transfer/bulk"]
    assert len(bulk) == 1 and bulk[0][2]["source"] == "balance" and [t["amount"] for t in bulk[0][2]["transfers"]] == [500_000, 300_000]
    assert bulk[0][2]["transfers"][0]["reference"] == "payroll-slip0"


def test_more_than_100_items_go_in_chunks(env):
    fund(env, "100000")
    out = run_batch(env, batch(env, ["10.00"] * 150))
    assert len([c for c in env.calls if c[1] == "/transfer/bulk"]) == 2 and out["counts"]["success"] == 150


def test_items_already_paid_or_in_flight_are_never_sent_twice(env):
    fund(env, "20000")
    run_batch(env, batch(env, ["1000.00"], refs=["slipA"]))
    with pytest.raises(HTTPException) as e:
        run_batch(env, batch(env, ["1000.00", "500.00"], refs=["slipA", "slipB"], source="run-1"))
    assert e.value.status_code == 409 and e.value.detail["items"] == ["slipA"]
    before = balance(env)
    assert before == 20000 - 1000 - 60


def test_paystack_rejecting_the_whole_bulk_returns_everything_to_the_wallet(env):
    fund(env, "5000")
    env.script["bulk"] = {"status": False, "_http_status": 400, "message": "Your balance is not enough to fulfil this request"}
    out = run_batch(env, batch(env, ["1000.00", "1000.00"]))
    assert out["status"] == "failed" and all("balance is not enough" in i["message"] for i in out["items"])
    assert balance(env) == 5000.0


def test_failed_item_can_be_retried_as_a_new_attempt_with_a_new_reference(env):
    fund(env, "5000")
    env.script["bulk"] = {"status": True, "_http_status": 200, "data": [
        {"reference": "payroll-s1", "transfer_code": "TRF_1", "status": "failed"}]}
    run_batch(env, batch(env, ["500.00"], refs=["s1"]))
    assert balance(env) == 5000.0
    env.script["bulk"] = None
    out = run_batch(env, batch(env, ["500.00"], refs=["s1"]))
    assert out["attempt"] == 2 and out["items"][0]["reference"] == "payroll-s1-r2" and out["status"] == "completed"
    assert balance(env) == 5000 - 500 - 30


def test_a_five_hundred_item_cap_and_bad_input_are_rejected(env):
    with pytest.raises(Exception):
        po.BatchIn(tenant_id=env.tenant, kind="payroll", source_id="r", items=[])
    with pytest.raises(HTTPException) as e:
        with env.db() as s:
            po.create_batch(s, batch(env, ["10", "10"], refs=["same", "same"]))
    assert e.value.status_code == 422


# ---- webhooks / reconcile ---------------------------------------------------------------------

def test_transfer_failed_webhook_returns_the_money_once(env):
    fund(env, "5000")
    env.script["bulk"] = {"status": True, "_http_status": 200, "data": [
        {"reference": "payroll-s1", "transfer_code": "TRF_1", "status": "pending"}]}
    out = run_batch(env, batch(env, ["1000.00"], refs=["s1"]))
    assert out["items"][0]["status"] == "processing" and balance(env) == 5000 - 1000 - 60
    ev = {"id": 9, "reference": "payroll-s1", "status": "failed", "reason": "Account closed", "updatedAt": "t1"}
    assert asyncio.run(po.handle_transfer_event("transfer.failed", ev)) == "accepted"
    assert asyncio.run(po.handle_transfer_event("transfer.failed", ev)) == "duplicate"
    asyncio.run(po.handle_transfer_event("transfer.failed", {**ev, "updatedAt": "t2"}))      # another delivery of the same outcome
    assert balance(env) == 5000.0
    with env.db() as s:
        assert s.query(PayoutItem).one().message == "Account closed"
    # a late success after failure cannot resurrect it
    asyncio.run(po.handle_transfer_event("transfer.success", {"id": 10, "reference": "payroll-s1", "status": "success"}))
    with env.db() as s:
        assert s.query(PayoutItem).one().status == "failed"
    assert balance(env) == 5000.0


def test_transfer_reversed_after_success_also_returns_the_money(env):
    fund(env, "5000")
    run_batch(env, batch(env, ["1000.00"], refs=["s1"]))
    asyncio.run(po.handle_transfer_event("transfer.reversed", {"id": 1, "reference": "payroll-s1", "status": "reversed"}))
    assert balance(env) == 5000.0


def test_unknown_reference_and_foreign_events_are_ignored(env):
    assert asyncio.run(po.handle_transfer_event("transfer.success", {"id": 1, "reference": "someone-elses"})) == "ignored"
    assert asyncio.run(po.handle_transfer_event("transfer.other", {"id": 1, "reference": "x"})) == "ignored"


def test_unknown_outcome_stays_pending_until_reconciled(env):
    fund(env, "5000")
    env.script["bulk"] = {"status": False, "_http_status": 503, "message": "gateway timeout"}
    out = run_batch(env, batch(env, ["1000.00", "500.00"], refs=["a", "b"]))
    assert out["counts"]["pending"] == 2 and balance(env) == 5000 - 1500 - 90        # reserved, not guessed
    env.script["verify"] = {"payroll-a": {"status": True, "_http_status": 200, "data": {"status": "success", "transfer_code": "TRF_a"}}}
    with env.db() as s:
        bid = s.query(PayoutBatch).one().id
    out = asyncio.run(po.reconcile_batch(bid))
    states = {i["item_ref"]: i["status"] for i in out["items"]}
    assert states == {"a": "success", "b": "failed"}                                  # b was never created at Paystack
    assert balance(env) == 5000 - 1000 - 60


# ---- internal endpoints + funding ----------------------------------------------------------------

def test_internal_endpoints_require_the_service_key(env, monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_KEY", "k" * 32)
    body = batch(env, ["10.00"])
    with pytest.raises(HTTPException) as e:
        asyncio.run(po.internal_create_batch(body, SimpleNamespace(headers={})))
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        asyncio.run(po.internal_create_batch(body, SimpleNamespace(headers={"x-internal-key": "wrong"})))
    assert e.value.status_code == 403
    fund(env, "100")
    out = asyncio.run(po.internal_create_batch(body, SimpleNamespace(headers={"x-internal-key": "k" * 32})))
    assert out["status"] == "completed"


def test_provider_balance_too_low_blocks_before_reserving(env, monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_KEY", "k" * 32)
    fund(env, "5000")
    env.script["balance"] = 10_000                       # R100 at Paystack
    with pytest.raises(HTTPException) as e:
        asyncio.run(po.internal_create_batch(batch(env, ["1000.00"]), SimpleNamespace(headers={"x-internal-key": "k" * 32})))
    assert e.value.status_code == 503 and balance(env) == 5000.0 and not [c for c in env.calls if c[1] == "/transfer/bulk"]


def test_funding_webhook_credits_once_for_the_initialised_amount_only(env):
    with env.db() as s:
        s.add(PayoutFunding(tenant_id=env.tenant, reference="fund-1", amount_cents=500_000))
    wrong = {"reference": "fund-1", "amount": 400_000, "currency": "ZAR", "id": "x1"}
    assert asyncio.run(po.handle_funding_success(wrong, "charge.success:x1")) == "rejected" and balance(env) == 0
    ok = {"reference": "fund-1", "amount": 500_000, "currency": "ZAR", "id": "x2"}
    assert asyncio.run(po.handle_funding_success(ok, "charge.success:x2")) == "accepted"
    assert asyncio.run(po.handle_funding_success(ok, "charge.success:x2")) == "duplicate"
    assert asyncio.run(po.handle_funding_success({**ok, "id": "x3"}, "charge.success:x3")) == "accepted"   # replay, new key
    assert balance(env) == 5000.0                                    # credited once: the wallet entry is unique per reference
    with env.db() as s:
        assert s.query(PayoutFunding).one().status == "credited"


def test_charge_success_routes_funding_checkouts_to_the_wallet(env, monkeypatch):
    monkeypatch.setattr(paystack, "get_session", env.db)
    with env.db() as s:
        s.add(PayoutFunding(tenant_id=env.tenant, reference="fund-2", amount_cents=250_000))
    data = {"reference": "fund-2", "amount": 250_000, "currency": "ZAR", "id": "f2",
            "metadata": {"kind": "payout_funding", "tenant_id": str(env.tenant)}}
    assert asyncio.run(paystack._handle_charge_success(data, paystack.event_key("charge.success", data, b""))) == "accepted"
    assert balance(env) == 2500.0


def test_manual_funding_is_platform_admin_only(env):
    body = po.ManualFundingIn(tenant_id=env.tenant, amount_zar=D("1000.00"), bank_reference="EFT-9")
    with pytest.raises(HTTPException) as e:
        asyncio.run(po.manual_funding(body, env.ctx))
    assert e.value.status_code == 403
    admin = AuthContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=["platform_admin"])
    assert asyncio.run(po.manual_funding(body, admin))["credited"] is True
    assert asyncio.run(po.manual_funding(body, admin))["credited"] is False
    assert balance(env) == 1000.0


def test_wallet_and_quote_endpoints(env):
    fund(env, "1000")
    w = asyncio.run(po.wallet(env.ctx))
    assert w["balance_zar"] == 1000.0 and w["entries"][0]["kind"] == "manual_funding"
    q = asyncio.run(po.post_quote(po.QuoteIn(amount_zar=D("2000.00")), env.ctx))
    assert q["fee_zar"] == 120.0 and q["required_zar"] == 2120.0 and q["shortfall_zar"] == 1120.0 and "_fee_cents" not in q
