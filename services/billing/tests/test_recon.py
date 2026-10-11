"""Reconciliation: solvency snapshots, Paystack ledger copy + continuity, charge integrity, payout sweep, settlements,
the run orchestration, the platform-admin endpoints and the tenant statement."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.common.auth import AuthContext  # noqa: E402
from services.billing.models_gateway import GatewayCharge, GatewayLiability, GatewayRefund  # noqa: E402
from services.billing.models_payouts import PayoutBatch, PayoutItem, PayoutWallet  # noqa: E402
from services.billing.models_recon import PaystackBalanceSnapshot, PaystackLedgerEntry, PaystackSettlement, ReconRun  # noqa: E402
from services.billing.routes import gateway as gw, payouts as po, recon  # noqa: E402
from services.billing.tests import sqlite_harness as h  # noqa: E402


@pytest.fixture
def env(monkeypatch):
    db = h.make_session_factory()
    h.patch_sessions(monkeypatch, db)
    for mod in (recon, po):
        monkeypatch.setattr(mod, "get_session", db)
    monkeypatch.setattr(recon, "_secret", lambda: "sk_test_x")
    monkeypatch.setattr(recon, "_lock", lambda: (True, None))
    script = {"balance": 10_000_000, "ledger_pages": {}, "verify": {}, "settlements": {}, "http": {}}
    calls, alerts = [], []

    async def fake(method, path, body=None):
        calls.append((method, path))
        if path.startswith("/balance/ledger"):
            page = int(path.rsplit("page=", 1)[1])
            return {"status": True, "_http_status": 200, "data": script["ledger_pages"].get(page, [])}
        if path.startswith("/settlement"):
            page = int(path.rsplit("page=", 1)[1])
            return {"status": True, "_http_status": 200, "data": script["settlements"].get(page, [])}
        if path.startswith("/transaction/verify/"):
            ref = path.rsplit("/", 1)[1]
            if ref in script["http"]:
                return {"status": False, "_http_status": script["http"][ref], "message": "gateway"}
            return script["verify"].get(ref, {"status": False, "_http_status": 404, "message": "Transaction reference not found"})
        return {"status": True, "_http_status": 200, "data": {}}
    monkeypatch.setattr(recon, "_paystack", fake)

    async def balance():
        return script["balance"]
    monkeypatch.setattr(po, "provider_balance_cents", balance)

    async def alert(subject, html):
        alerts.append(subject)
    monkeypatch.setattr(gw, "_alert_ops", alert)
    tenant = uuid.uuid4()
    admin = AuthContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=["platform_admin"])
    return SimpleNamespace(db=db, tenant=tenant, script=script, calls=calls, alerts=alerts, admin=admin,
                           ctx=AuthContext(user_id=uuid.uuid4(), tenant_id=tenant))


def add_wallet(env, cents, tenant=None):
    with env.db() as s:
        s.add(PayoutWallet(tenant_id=tenant or uuid.uuid4(), balance_cents=cents))


def add_charge(env, ref, gross=115_000, commission=6_900, fee=3_000, period=None, tenant=None, status="succeeded", sub="ACCT_t"):
    with env.db() as s:
        s.add(GatewayCharge(tenant_id=tenant or env.tenant, reference=ref, subaccount_code=sub, period=period or "2026-03",
                            gross_cents=gross, commission_cents=commission, paystack_fee_cents=fee, status=status))


def verify_ok(gross=115_000, commission=6_900, fee=3_000, sub="ACCT_t", **over):
    data = {"status": "success", "amount": gross, "fees": fee, "subaccount": {"subaccount_code": sub},
            "fees_split": {"paystack": fee, "integration": commission - fee, "subaccount": gross - commission}}
    data.update(over)
    return {"status": True, "_http_status": 200, "data": data}


def ledger_row(i, diff, bal, reason="Transfer", at="2026-03-01T10:00:00.000Z"):
    return {"id": i, "balance": bal, "difference": diff, "reason": reason, "currency": "ZAR", "createdAt": at,
            "model_responsible": "transfer", "model_row": i}


# ---- categories ------------------------------------------------------------------

@pytest.mark.parametrize("reason,cat", [("Transfer", "payout"), ("Transfer reversal", "payout_reversal"), ("Refund", "refund"),
                                         ("Settlement", "settlement"), ("Payment", "charge"), ("Chargeback", "dispute"),
                                         ("Transaction fee", "fee"), ("Something odd", "other"), (None, "other")])
def test_categorise(reason, cat):
    assert recon.categorise(reason) == cat


# ---- 1. solvency ------------------------------------------------------------------

def test_snapshot_is_ok_when_balance_covers_the_wallets_and_alerts_only_on_the_flip_to_short(env):
    add_wallet(env, 4_000_000)
    add_wallet(env, 3_000_000)
    with env.db() as s:
        s.add(GatewayLiability(tenant_id=env.tenant, kind="refund", source_id="a", amount_cents=50_000, status="open"))
    out = asyncio.run(recon.take_snapshot())
    assert out["status"] == "ok" and out["balance_zar"] == 100000.0 and out["wallets_zar"] == 70000.0
    assert out["headroom_zar"] == 30000.0 and out["liabilities_open_zar"] == 500.0 and env.alerts == []
    env.script["balance"] = 6_000_000                            # R60k at Paystack, wallets hold R70k
    out = asyncio.run(recon.take_snapshot())
    assert out["status"] == "short" and out["headroom_zar"] == -10000.0
    assert env.alerts == ["Paystack balance is below what tenants' payout wallets hold"]
    asyncio.run(recon.take_snapshot())                           # still short: no second alert
    assert len(env.alerts) == 1
    env.script["balance"] = 9_000_000
    assert asyncio.run(recon.take_snapshot())["status"] == "ok"


def test_unreadable_balance_records_nothing(env, monkeypatch):
    async def none():
        return None
    monkeypatch.setattr(po, "provider_balance_cents", none)
    assert asyncio.run(recon.take_snapshot()) is None
    with env.db() as s:
        assert s.query(PaystackBalanceSnapshot).count() == 0


# ---- 2. ledger copy --------------------------------------------------------------------

def test_ledger_sync_is_idempotent_and_stops_when_a_page_adds_nothing(env):
    env.script["ledger_pages"] = {1: [ledger_row(3, -5000, 95_000), ledger_row(2, 10_000, 100_000, "Payment"), ledger_row(1, 90_000, 90_000, "Top up")],
                                  2: []}
    assert asyncio.run(recon.sync_ledger(max_pages=5)) == {"fetched": 3, "new": 3}
    env.calls.clear()
    assert asyncio.run(recon.sync_ledger(max_pages=5)) == {"fetched": 3, "new": 0}
    assert len([c for c in env.calls if "balance/ledger" in c[1]]) == 1                   # stopped after the page with nothing new
    with env.db() as s:
        cats = {e.paystack_id: e.category for e in s.query(PaystackLedgerEntry)}
        assert cats == {3: "payout", 2: "charge", 1: "topup"} and recon.ledger_breaks(s) == []


def test_ledger_continuity_flags_a_missing_row(env):
    env.script["ledger_pages"] = {1: [ledger_row(4, -1000, 80_000), ledger_row(3, -5000, 81_000), ledger_row(1, 90_000, 90_000)]}
    asyncio.run(recon.sync_ledger(max_pages=1))
    with env.db() as s:
        b = recon.ledger_breaks(s)
    # row 2 (-4000 on 90_000 -> 86_000... ) never arrived: 90_000 - 5_000 != 81_000
    assert len(b) == 1 and b[0]["after_paystack_id"] == 1 and b[0]["paystack_id"] == 3
    assert b[0]["expected_balance_zar"] == 850.0 and b[0]["actual_balance_zar"] == 810.0


# ---- 3. charge integrity -----------------------------------------------------------------

def charge_obj(**kw):
    return GatewayCharge(tenant_id=uuid.uuid4(), reference="r", subaccount_code="ACCT_t", period="2026-03", gross_cents=115_000,
                         commission_cents=6_900, paystack_fee_cents=3_000, status="succeeded", **kw)


def test_evaluate_ok_and_within_rounding_tolerance():
    status, note, tenant, ours = recon.evaluate_charge(charge_obj(), verify_ok()["data"])
    assert (status, note, tenant, ours) == ("ok", "", 108_100, 3_900)
    near = verify_ok()["data"]
    near["fees_split"]["integration"] += 2
    assert recon.evaluate_charge(charge_obj(), near)[0] == "ok"


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d["fees_split"].update(subaccount=100_000), "Tenant received 100000 but should have received 108100"),
    (lambda d: d.update(subaccount={"subaccount_code": "ACCT_other"}), "ACCT_other"),
    (lambda d: d.update(amount=114_999), "differs from ours"),
    (lambda d: d.update(status="failed"), "failed"),
    (lambda d: d["fees_split"].update(integration=9_999), "OmniDome's share"),
])
def test_evaluate_flags_what_paystack_did_differently(mutate, needle):
    data = verify_ok()["data"]
    mutate(data)
    status, note, *_ = recon.evaluate_charge(charge_obj(), data)
    assert status == "mismatch" and needle in note


def test_evaluate_without_split_data_is_not_called_ok():
    data = verify_ok()["data"]
    data.pop("fees_split")
    assert recon.evaluate_charge(charge_obj(), data)[0] == "no_split_data"


def test_reconcile_charges_checks_each_once_retries_outages_and_alerts_on_mismatch(env):
    add_charge(env, "good")
    add_charge(env, "short", gross=100_000, commission=6_000)
    add_charge(env, "down")
    add_charge(env, "ghost")
    add_charge(env, "pending-one", status="initialized")                  # never succeeded: not checked
    env.script["verify"] = {"good": verify_ok(), "short": verify_ok(100_000, 6_000, 3_000, **{})}
    env.script["verify"]["short"]["data"]["fees_split"]["subaccount"] = 90_000
    env.script["http"] = {"down": 502}
    out = asyncio.run(recon.reconcile_charges())
    assert out == {"ok": 1, "mismatch": 2, "no_split_data": 0, "unavailable": 1, "checked": 4}      # ghost: Paystack cannot find it
    with env.db() as s:
        by = {c.reference: c for c in s.query(GatewayCharge)}
        assert by["good"].recon_status == "ok" and by["good"].actual_tenant_cents == 108_100
        assert by["short"].recon_status == "mismatch" and "should have received 94000" in by["short"].recon_note
        assert by["ghost"].recon_status == "mismatch" and "could not verify" in by["ghost"].recon_note
        assert by["down"].recon_at is None and by["pending-one"].recon_at is None
    assert env.alerts == ["2 Paystack charge(s) did not settle as instructed"]
    env.calls.clear()
    env.script["http"] = {}
    env.script["verify"]["down"] = verify_ok()
    out = asyncio.run(recon.reconcile_charges())
    assert out["checked"] == 1 and out["ok"] == 1 and [c[1] for c in env.calls] == ["/transaction/verify/down"]


# ---- 4. payout sweep and settlements --------------------------------------------------------

def test_sweep_reconciles_only_batches_with_stale_in_flight_items(env, monkeypatch):
    seen = []

    async def fake_reconcile(batch_id):
        seen.append(batch_id)
    monkeypatch.setattr(po, "reconcile_batch", fake_reconcile)
    old, fresh = datetime.now(timezone.utc) - timedelta(hours=5), datetime.now(timezone.utc) - timedelta(minutes=5)
    ids = {}
    with env.db() as s:
        for name, created, status in (("stale", old, "processing"), ("fresh", fresh, "processing"), ("done", old, "success")):
            b = PayoutBatch(tenant_id=env.tenant, kind="payroll", source_id=name, period="2026-03", total_cents=100)
            s.add(b)
            s.flush()
            ids[name] = b.id
            s.add(PayoutItem(batch_id=b.id, tenant_id=env.tenant, kind="payroll", item_ref=name, recipient_code="RCP_1", amount_cents=100,
                             reference=f"ref-{name}", status=status, created_at=created))
    assert asyncio.run(recon.sweep_payouts()) == {"batches": 1} and seen == [ids["stale"]]


def test_settlements_are_copied_once(env):
    env.script["settlements"] = {1: [{"id": 11, "status": "success", "total_amount": 500_000, "total_fees": 15_000,
                                      "total_processed": 485_000, "settlement_date": "2026-03-02T00:00:00.000Z"}], 2: []}
    assert asyncio.run(recon.sync_settlements()) == {"new": 1}
    assert asyncio.run(recon.sync_settlements()) == {"new": 0}
    out = asyncio.run(recon.settlements(env.admin))
    assert out["settlements"][0]["paid_zar"] == 4850.0 and out["settlements"][0]["fees_zar"] == 150.0


# ---- orchestration + endpoints ------------------------------------------------------------------

def test_run_recon_does_every_step_records_the_run_and_survives_a_failing_step(env, monkeypatch):
    add_wallet(env, 1_000_000)
    add_charge(env, "good")
    env.script["verify"] = {"good": verify_ok()}
    env.script["ledger_pages"] = {1: [ledger_row(1, 100, 100)]}

    async def boom(*a, **k):
        raise RuntimeError("settlements api down")
    monkeypatch.setattr(recon, "sync_settlements", boom)
    out = asyncio.run(recon.run_recon("user:test"))
    assert out["snapshot"]["status"] == "ok" and out["ledger"]["new"] == 1 and out["charges"]["ok"] == 1
    assert out["settlements"] == {"error": "RuntimeError"} and out["ledger_breaks"] == 0
    with env.db() as s:
        r = s.query(ReconRun).one()
        assert r.finished_at is not None and r.error == "settlements" and r.triggered_by == "user:test"


def test_run_recon_is_skipped_without_a_key_or_when_another_run_holds_the_lock(env, monkeypatch):
    monkeypatch.setattr(recon, "_lock", lambda: (False, None))
    assert "another reconciliation" in asyncio.run(recon.run_recon("worker"))["skipped"]
    monkeypatch.setattr(recon, "_secret", lambda: "")
    assert "not configured" in asyncio.run(recon.run_recon("worker"))["skipped"]
    assert not recon.worker_enabled()


def test_platform_endpoints_refuse_tenant_admins_and_show_the_overview(env):
    for fn, args in ((recon.overview, ()), (recon.run_now, ()), (recon.ledger, (None, 10)), (recon.mismatches, ()),
                     (recon.settlements, ()), (recon.snapshots, (10,))):
        with pytest.raises(HTTPException) as e:
            asyncio.run(fn(*args, env.ctx))
        assert e.value.status_code == 403
    add_wallet(env, 500_000)
    add_charge(env, "m", gross=100_000, commission=6_000)
    env.script["verify"] = {"m": verify_ok(100_000, 6_000, 3_000)}
    env.script["verify"]["m"]["data"]["fees_split"]["subaccount"] = 1
    asyncio.run(recon.run_recon("worker"))
    ov = asyncio.run(recon.overview(env.admin))
    assert ov["snapshot"]["status"] == "ok" and ov["open_mismatches"] == 1 and ov["charges_last_30d"]["mismatch"] in (0, 1)
    assert ov["last_run"]["finished"] and ov["wallets_now_zar"] == 5000.0
    mm = asyncio.run(recon.mismatches(env.admin))["mismatches"]
    assert mm[0]["reference"] == "m" and "should have received" in mm[0]["note"]
    assert asyncio.run(recon.snapshots(10, env.admin))["snapshots"][0]["balance_zar"] == 100000.0


# ---- tenant statement ----------------------------------------------------------------------------

def test_tenant_statement_adds_up_and_is_tenant_scoped(env):
    other = uuid.uuid4()
    add_charge(env, "a", gross=100_000, commission=6_000, period="2026-03")
    add_charge(env, "b", gross=200_000, commission=12_000, period="2026-03")
    add_charge(env, "other-month", gross=999_999, commission=1, period="2026-02")
    add_charge(env, "other-tenant", gross=999_999, commission=1, period="2026-03", tenant=other)
    add_charge(env, "failed", gross=999_999, commission=1, period="2026-03", status="failed")
    mid = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
    with env.db() as s:
        s.add(GatewayRefund(tenant_id=env.tenant, credit_id=uuid.uuid4(), customer_id=uuid.uuid4(), amount_cents=10_000,
                            status="processed", updated_at=mid, method="paystack"))
        s.add(GatewayRefund(tenant_id=env.tenant, credit_id=uuid.uuid4(), customer_id=uuid.uuid4(), amount_cents=77_000,
                            status="processed", updated_at=datetime(2026, 4, 2, tzinfo=timezone.utc), method="paystack"))
        s.add(GatewayLiability(tenant_id=env.tenant, kind="chargeback", source_id="d1", amount_cents=5_000, created_at=mid))
        s.add(PayoutWallet(tenant_id=env.tenant, balance_cents=250_000))
        b = PayoutBatch(tenant_id=env.tenant, kind="payroll", source_id="r", period="2026-03", total_cents=80_000, fee_cents=4_800)
        s.add(b)
        s.flush()
        s.add(PayoutItem(batch_id=b.id, tenant_id=env.tenant, kind="payroll", item_ref="s1", recipient_code="RCP", amount_cents=80_000,
                         fee_cents=4_800, reference="p1", status="success"))
        s.query(GatewayCharge).filter(GatewayCharge.reference == "a").update({"recon_status": "ok"})
    st = asyncio.run(recon.statement("2026-03", env.ctx))
    assert st["collections"] == {"charges": 2, "collected_zar": 3000.0, "commission_zar": 180.0, "you_receive_zar": 2820.0}
    assert st["refunds"] == {"count": 1, "total_zar": 100.0} and st["chargebacks"] == {"count": 1, "total_zar": 50.0}
    assert st["payouts"] == {"count": 1, "total_zar": 800.0, "fees_zar": 48.0} and st["payout_wallet_zar"] == 2500.0
    assert st["open_liabilities_zar"] == 50.0 and st["settlement_checks"] == {"verified": 1, "total": 2}


@pytest.mark.parametrize("bad", ["2026-3", "202603", "2026-13", "abcd-ef", "2026-00"])
def test_statement_rejects_bad_periods(env, bad):
    with pytest.raises(HTTPException) as e:
        asyncio.run(recon.statement(bad, env.ctx))
    assert e.value.status_code == 400


def test_month_bounds_follow_sast():
    start, end = recon._month_bounds("2026-03")
    assert start == datetime(2026, 2, 28, 22, 0, tzinfo=timezone.utc) and end == datetime(2026, 3, 31, 22, 0, tzinfo=timezone.utc)
    assert recon._month_bounds("2026-12")[1] == datetime(2026, 12, 31, 22, 0, tzinfo=timezone.utc)
