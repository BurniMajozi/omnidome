"""Gateway flow against the SQLite stand-in: subaccount settings, split fields on initialize, the commission
ledger, tier progression from succeeded volume, and the webhook marking the ledger row (with Paystack's fee)."""
import asyncio
import os
import sys
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.common.auth import AuthContext  # noqa: E402
from services.billing import gateway  # noqa: E402
from services.billing.models_gateway import GatewayChangeEvent, GatewayCharge, GatewaySettings  # noqa: E402
from services.billing.routes import gateway as gw, paystack  # noqa: E402
from services.billing.schemas import PaystackInitializeRequest  # noqa: E402
from services.billing.tests import sqlite_harness as h  # noqa: E402

D = Decimal


@pytest.fixture
def env(monkeypatch):
    db = h.make_session_factory()
    h.patch_sessions(monkeypatch, db)
    monkeypatch.setattr(paystack, "PAYSTACK_SECRET", "sk_test_x")
    monkeypatch.setattr(paystack, "PAYSTACK_WEBHOOK_SECRET", "whsec")
    monkeypatch.setenv("APP_PUBLIC_URL", "https://app.example.co.za")
    sent = {}

    async def email(*_a, **_k):
        return "customer@example.com"
    monkeypatch.setattr(paystack, "resolve_customer_email", email)

    class Resp:
        status_code = 200
        text = ""
        def json(self): return {"data": {"authorization_url": "https://checkout/x", "access_code": "AC",
                                         "reference": sent["payload"]["reference"]}}

    class Client:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            sent["payload"] = json
            return Resp()
    monkeypatch.setattr(paystack.httpx, "AsyncClient", Client)

    async def no_reinstate(*_a, **_k): return None
    monkeypatch.setattr(paystack, "_trigger_auto_reinstate", no_reinstate)
    tenant = uuid.uuid4()
    return type("Env", (), {"db": db, "tenant": tenant, "sent": sent, "ctx": AuthContext(user_id=uuid.uuid4(), tenant_id=tenant)})


def add_settings(env, **kw):
    with env.db() as s:
        s.add(GatewaySettings(tenant_id=env.tenant, status=kw.pop("status", "active"), business_name="Acme ISP",
                              settlement_bank_code="632005", account_last4="1234", subaccount_code="ACCT_test", **kw))


def init(env, inv_id, **body):
    return asyncio.run(paystack.initialize_paystack(PaystackInitializeRequest(invoice_id=inv_id, **body), env.ctx))


def invoice(env, subtotal="1000.00", vat="150.00"):
    with env.db() as s:
        return h.make_invoice(s, env.tenant, subtotal=subtotal, vat=vat).id


def succeed(env, ref, cents, fees=None):
    data = {"reference": ref, "amount": cents, "currency": "ZAR", "id": ref, "fees": fees,
            "metadata": {"tenant_id": str(env.tenant), "invoice_id": "00000000-0000-0000-0000-000000000000"}}
    # init row exists, so the handler resolves tenant/invoice from it
    return asyncio.run(paystack._handle_charge_success(data, paystack.event_key("charge.success", data, b"")))


def test_no_gateway_means_no_split_fields_and_no_ledger(env):
    out = init(env, invoice(env))
    assert "subaccount" not in env.sent["payload"] and "transaction_charge" not in env.sent["payload"]
    with env.db() as s:
        assert s.query(GatewayCharge).count() == 0
    assert out.reference.startswith("OD-")


def test_initialize_sends_subaccount_commission_and_bearer(env):
    add_settings(env)
    out = init(env, invoice(env))                       # R1,150 -> 6% = R69.00
    p = env.sent["payload"]
    assert p["subaccount"] == "ACCT_test" and p["bearer"] == "account" and p["transaction_charge"] == 6900
    with env.db() as s:
        row = s.query(GatewayCharge).one()
        assert row.reference == out.reference and row.gross_cents == 115000 and row.commission_cents == 6900
        assert row.status == "initialized" and row.volume_before_cents == 0


def test_require_subaccount_blocks_unconfigured_tenant(env, monkeypatch):
    monkeypatch.setenv("GATEWAY_REQUIRE_SUBACCOUNT", "true")
    with pytest.raises(HTTPException) as e:
        init(env, invoice(env))
    assert e.value.status_code == 409
    add_settings(env, status="suspended")
    with pytest.raises(HTTPException):
        init(env, invoice(env))


def test_webhook_marks_ledger_succeeded_and_records_paystack_fee(env):
    add_settings(env)
    out = init(env, invoice(env))
    assert succeed(env, out.reference, 115000, fees=3450) == "accepted"
    with env.db() as s:
        row = s.query(GatewayCharge).one()
        assert row.status == "succeeded" and row.paystack_fee_cents == 3450 and row.settled_at is not None


def test_unpaid_charges_do_not_count_toward_volume_but_paid_ones_do(env):
    add_settings(env)
    first = init(env, invoice(env, "249000.00", "0.00"))       # R249,000 at 6%
    init(env, invoice(env, "1000.00", "0.00"))                 # initialised only: volume still 0
    with env.db() as s:
        assert [r.volume_before_cents for r in s.query(GatewayCharge).order_by(GatewayCharge.created_at)] == [0, 0]
    succeed(env, first.reference, 24_900_000)
    init(env, invoice(env, "2000.00", "0.00"))                 # volume now R249,000: R1,000 at 6% + R1,000 at 5.5%
    with env.db() as s:
        last = s.query(GatewayCharge).filter(GatewayCharge.gross_cents == 200_000).one()
        assert last.volume_before_cents == 24_900_000 and last.commission_cents == 6000 + 5500


def test_custom_tiers_override_the_default(env):
    add_settings(env, commission_tiers=[[None, 400]])
    init(env, invoice(env, "1000.00", "0.00"))
    assert env.sent["payload"]["transaction_charge"] == 4000


def test_failed_gateway_call_discards_the_ledger_row(env, monkeypatch):
    add_settings(env)

    class Bad:
        status_code = 500
        text = ""
        def json(self): return {}

    class Client:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): return Bad()
    monkeypatch.setattr(paystack.httpx, "AsyncClient", Client)
    with pytest.raises(HTTPException) as e:
        init(env, invoice(env))
    assert e.value.status_code == 502
    with env.db() as s:
        assert s.query(GatewayCharge).count() == 0


@pytest.fixture
def paystack_calls(monkeypatch):
    calls = []

    async def fake(method, path, body=None):
        calls.append((method, path, body))
        return {"status": True, "data": {"subaccount_code": f"ACCT_{len(calls)}"}}
    monkeypatch.setattr(gw, "_paystack", fake)
    monkeypatch.setattr(gw, "_secret", lambda: "sk_test_x")
    return calls


def setup_req(number="1234567890", bank="632005"):
    return gw.GatewaySetupRequest(business_name="Acme ISP", settlement_bank_code=bank, account_number=number)


def test_first_setup_is_immediate_and_keeps_only_last4(env, paystack_calls):
    out = asyncio.run(gw.set_settings(setup_req(), env.ctx))
    assert out["subaccount_code"] == "ACCT_1" and out["account_last4"] == "7890" and "account_number" not in out
    assert paystack_calls[0][:2] == ("POST", "/subaccount") and paystack_calls[0][2]["percentage_charge"] == 6.0
    with env.db() as s:
        assert [e.event for e in s.query(GatewayChangeEvent)] == ["setup"]


def test_later_change_is_only_a_request_until_another_platform_admin_approves(env, paystack_calls, monkeypatch):
    asyncio.run(gw.set_settings(setup_req(), env.ctx))
    out = asyncio.run(gw.set_settings(setup_req("9999999999", "058002"), env.ctx))
    # settlements still go to the original account; the new details sit as a pending request
    assert out["subaccount_code"] == "ACCT_1" and out["account_last4"] == "7890"
    assert out["pending_change"]["last4"] == "9999" and paystack_calls[1][:2] == ("POST", "/subaccount")
    add_settings_row = init(env, invoice(env))      # still charges against the active subaccount
    assert env.sent["payload"]["subaccount"] == "ACCT_1"

    # the requester (a tenant admin) cannot approve, and neither can a non-platform admin
    with pytest.raises(HTTPException) as e:
        asyncio.run(gw.approve_change(env.tenant, env.ctx))
    assert e.value.status_code == 403
    same_user_platform = AuthContext(user_id=env.ctx.user_id, tenant_id=uuid.uuid4(), roles=["platform_admin"])
    with pytest.raises(HTTPException) as e:
        asyncio.run(gw.approve_change(env.tenant, same_user_platform))
    assert e.value.status_code == 403 and "different admin" in e.value.detail

    approver = AuthContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=["platform_admin"])
    pending = asyncio.run(gw.pending_changes(approver))
    assert [c["tenant_id"] for c in pending["changes"]] == [str(env.tenant)]
    done = asyncio.run(gw.approve_change(env.tenant, approver))
    assert done["subaccount_code"] == "ACCT_2" and done["account_last4"] == "9999" and done["pending_change"] is None
    init(env, invoice(env))
    assert env.sent["payload"]["subaccount"] == "ACCT_2"
    with env.db() as s:
        assert [e.event for e in s.query(GatewayChangeEvent).order_by(GatewayChangeEvent.created_at)] == [
            "setup", "change_requested", "change_approved"]


def test_rejected_change_leaves_the_active_account(env, paystack_calls):
    asyncio.run(gw.set_settings(setup_req(), env.ctx))
    asyncio.run(gw.set_settings(setup_req("9999999999"), env.ctx))
    approver = AuthContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=["platform_admin"])
    out = asyncio.run(gw.reject_change(env.tenant, approver))
    assert out["subaccount_code"] == "ACCT_1" and out["pending_change"] is None
    with pytest.raises(HTTPException) as e:
        asyncio.run(gw.approve_change(env.tenant, approver))
    assert e.value.status_code == 404


def test_change_request_alerts_ops_when_configured(env, paystack_calls, monkeypatch):
    sent = []

    async def send_email(to, subject, html, **_k):
        sent.append((to, subject))
    import services.common.agentmail as am
    monkeypatch.setattr(am, "send_email", send_email)
    monkeypatch.setenv("GATEWAY_ALERT_EMAIL", "ops@example.com")
    asyncio.run(gw.set_settings(setup_req(), env.ctx))
    assert sent == []                                   # first setup: no alert
    asyncio.run(gw.set_settings(setup_req("9999999999"), env.ctx))
    assert sent == [("ops@example.com", "Settlement account change awaiting approval")]


def test_setup_rejects_non_numeric_account():
    with pytest.raises(Exception):
        gw.GatewaySetupRequest(business_name="Acme", settlement_bank_code="1", account_number="12ab5678")


def test_preview_and_summary_reflect_month_volume(env):
    add_settings(env)
    ref = init(env, invoice(env, "300000.00", "0.00")).reference
    succeed(env, ref, 30_000_000)
    prev = asyncio.run(gw.preview(D("1000"), env.ctx))
    assert prev["commission_zar"] == 55.0 and prev["tenant_receives_zar"] == 945.0
    s = asyncio.run(gw.summary(env.ctx))
    assert s["volume_zar"] == 300000.0 and s["current_rate_percent"] == 5.5 and s["charges"] == 1
    assert s["next_threshold_zar"] == 1_000_000.0 and s["remaining_in_band_zar"] == 700_000.0
