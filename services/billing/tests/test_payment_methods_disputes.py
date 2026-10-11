"""Step 2: cards on file, charging them (with the gateway split), the autopay run, and dispute recording.
SQLite stand-in; Paystack is a fake."""
import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.common.auth import AuthContext  # noqa: E402
from services.billing.models import BillingWebhookEvent, Invoice, Payment, PaystackInitialization  # noqa: E402
from services.billing.models_gateway import GatewayCharge, GatewayDispute, GatewaySettings, PaymentMethod  # noqa: E402
from services.billing.routes import disputes, gateway as gw, payment_methods as pm, paystack  # noqa: E402
from services.billing.tests import sqlite_harness as h  # noqa: E402

CARD = {"authorization_code": "AUTH_secret123", "channel": "card", "reusable": True, "signature": "SIG_1", "brand": "visa",
        "card_type": "visa ", "bank": "TEST BANK", "last4": "4081", "exp_month": "12", "exp_year": "2099"}


@pytest.fixture
def env(monkeypatch):
    db = h.make_session_factory()
    h.patch_sessions(monkeypatch, db)
    monkeypatch.setattr(paystack, "PAYSTACK_SECRET", "sk_test_x")
    monkeypatch.setattr(pm, "_secret", lambda: "sk_test_x")
    calls = []
    mode = {"result": "success", "fail_reason": "Insufficient Funds"}

    async def fake(method, path, body=None):
        calls.append((method, path, body))
        if path == "/transaction/charge_authorization":
            if mode["result"] == "success":
                return {"status": True, "_http_status": 200, "data": {
                    "status": "success", "id": abs(hash(body["reference"])) % 10**9, "reference": body["reference"],
                    "amount": body["amount"], "currency": "ZAR", "fees": 1500, "authorization": CARD}}
            return {"status": True, "_http_status": 200, "data": {"status": "failed", "gateway_response": mode["fail_reason"]}}
        return {"status": True, "_http_status": 200, "data": {}}
    monkeypatch.setattr(pm, "_paystack", fake)

    async def email(*_a, **_k):
        return "cust@example.com"
    monkeypatch.setattr(pm, "resolve_customer_email", email)

    async def no_reinstate(*_a, **_k):
        return None
    monkeypatch.setattr(paystack, "_trigger_auto_reinstate", no_reinstate)
    tenant = uuid.uuid4()
    return type("Env", (), {"db": db, "tenant": tenant, "calls": calls, "mode": mode, "user": uuid.uuid4(),
                            "ctx": AuthContext(user_id=uuid.uuid4(), tenant_id=tenant)})


def make_invoice(env, customer=None, due=date(2026, 1, 31), subtotal="100.00", vat="15.00", status="sent"):
    with env.db() as s:
        return h.make_invoice(s, env.tenant, customer_id=customer or uuid.uuid4(), due=due, subtotal=subtotal, vat=vat, status=status)


def save_card(env, customer, **over):
    row = dict(tenant_id=env.tenant, customer_id=customer, authorization_code="AUTH_x", signature=f"S{uuid.uuid4().hex[:6]}",
               last4="1111", exp_month=12, exp_year=2099, is_default=True, status="active")
    row.update(over)
    with env.db() as s:
        s.add(PaymentMethod(**row))


def gateway(env):
    with env.db() as s:
        s.add(GatewaySettings(tenant_id=env.tenant, status="active", business_name="Acme", settlement_bank_code="1",
                              account_last4="1234", subaccount_code="ACCT_t"))


def charge_event(env, inv, *, save=True, reference="ref-save", auth=None):
    data = {"reference": reference, "amount": 11500, "currency": "ZAR", "id": reference, "fees": 400,
            "authorization": auth or CARD, "customer": {"customer_code": "CUS_abc", "email": "cust@example.com"},
            "metadata": {"invoice_id": str(inv.id), "tenant_id": str(env.tenant), "save_payment_method": save}}
    with env.db() as s:
        s.add(PaystackInitialization(tenant_id=env.tenant, invoice_id=inv.id, customer_id=inv.customer_id, reference=reference,
                                     amount_cents=11500, currency="ZAR", status="pending"))
    return asyncio.run(paystack._handle_charge_success(data, paystack.event_key("charge.success", data, b"")))


# ---- capture ----------------------------------------------------------------

def test_card_saved_only_with_consent_and_reusable_card(env):
    inv = make_invoice(env)
    assert charge_event(env, inv, save=False) == "accepted"
    with env.db() as s:
        assert s.query(PaymentMethod).count() == 0
    inv2 = make_invoice(env)
    charge_event(env, inv2, reference="r2", auth={**CARD, "reusable": False})
    inv3 = make_invoice(env)
    charge_event(env, inv3, reference="r3", auth={**CARD, "channel": "bank"})
    with env.db() as s:
        assert s.query(PaymentMethod).count() == 0
    inv4 = make_invoice(env)
    charge_event(env, inv4, reference="r4")
    with env.db() as s:
        m = s.query(PaymentMethod).one()
        assert m.customer_id == inv4.customer_id and m.is_default and m.last4 == "4081" and m.paystack_customer_code == "CUS_abc"


def test_same_card_is_refreshed_not_duplicated_and_api_hides_the_token(env):
    inv = make_invoice(env)
    charge_event(env, inv)
    inv2 = make_invoice(env, customer=inv.customer_id)
    charge_event(env, inv2, reference="ref-again", auth={**CARD, "authorization_code": "AUTH_new", "exp_year": "2100"})
    with env.db() as s:
        m = s.query(PaymentMethod).one()
        assert m.authorization_code == "AUTH_new" and m.exp_year == 2100
        shown = pm.public(m)
    assert "authorization_code" not in shown and "AUTH_new" not in str(shown) and shown["last4"] == "4081"


def test_expiry_is_through_the_end_of_the_expiry_month():
    m = PaymentMethod(exp_month=6, exp_year=2026)
    assert not pm.is_expired(m, date(2026, 6, 30)) and pm.is_expired(m, date(2026, 7, 1))


# ---- charge saved card -----------------------------------------------------------

def test_charge_saved_success_applies_payment_with_gateway_split(env):
    gateway(env)
    inv = make_invoice(env)
    save_card(env, inv.customer_id, authorization_code="AUTH_live")
    r = asyncio.run(pm.charge_saved_method(env.tenant, env.user, inv.id))
    assert r["status"] == "succeeded" and r["outcome"] == "accepted"
    sent = [c for c in env.calls if c[1] == "/transaction/charge_authorization"][0][2]
    assert sent["authorization_code"] == "AUTH_live" and sent["subaccount"] == "ACCT_t" and sent["transaction_charge"] == 690 \
        and sent["bearer"] == "account" and sent["amount"] == 11500
    with env.db() as s:
        assert s.get(Invoice, inv.id).status == "paid"
        c = s.query(GatewayCharge).one()
        assert c.status == "succeeded" and c.kind == "autopay" and c.payment_method_id is not None and c.paystack_fee_cents == 1500
        assert s.query(Payment).count() == 1


def test_charge_saved_replayed_webhook_is_a_duplicate(env):
    inv = make_invoice(env)
    save_card(env, inv.customer_id)
    asyncio.run(pm.charge_saved_method(env.tenant, env.user, inv.id))
    with env.db() as s:
        key = s.query(BillingWebhookEvent).one().event_key
    assert key.startswith("charge.success:")
    ref = env.calls[0][2]["reference"]
    data = {"reference": ref, "amount": 11500, "currency": "ZAR", "id": key.split(":", 1)[1]}
    assert asyncio.run(paystack._handle_charge_success(data, key)) == "duplicate"
    with env.db() as s:
        assert s.query(Payment).count() == 1


def test_charge_saved_failure_is_recorded_and_invoice_left_unpaid(env):
    gateway(env)
    inv = make_invoice(env)
    save_card(env, inv.customer_id)
    env.mode["result"] = "failed"
    r = asyncio.run(pm.charge_saved_method(env.tenant, env.user, inv.id))
    assert r["status"] == "failed" and r["attempt"] == 1 and r["reason"] == "Insufficient Funds"
    with env.db() as s:
        assert s.get(Invoice, inv.id).amount_paid_zar == 0
        c = s.query(GatewayCharge).one()
        assert c.status == "failed" and c.failure_reason == "Insufficient Funds"
        assert s.query(PaystackInitialization).one().status == "failed"
        assert s.query(Payment).count() == 0


@pytest.mark.parametrize("setup,detail", [
    ("no_card", "No usable saved card"), ("expired", "No usable saved card"), ("removed", "No usable saved card"),
    ("disputed", "open dispute"), ("paid", "already paid")])
def test_charge_saved_refuses_what_it_should(env, setup, detail):
    inv = make_invoice(env, status="paid" if setup == "paid" else "sent")
    if setup == "expired":
        save_card(env, inv.customer_id, exp_month=1, exp_year=2020)
    elif setup == "removed":
        save_card(env, inv.customer_id, status="removed")
    elif setup != "no_card":
        save_card(env, inv.customer_id)
    if setup == "disputed":
        with env.db() as s:
            s.add(GatewayDispute(tenant_id=env.tenant, paystack_dispute_id="d1", invoice_id=inv.id, status="awaiting-merchant-feedback"))
    with pytest.raises(HTTPException) as e:
        asyncio.run(pm.charge_saved_method(env.tenant, env.user, inv.id))
    assert detail in e.value.detail and not env.calls


def test_charge_saved_requires_a_gateway_when_enforced(env, monkeypatch):
    monkeypatch.setenv("GATEWAY_REQUIRE_SUBACCOUNT", "true")
    inv = make_invoice(env)
    save_card(env, inv.customer_id)
    with pytest.raises(HTTPException) as e:
        asyncio.run(pm.charge_saved_method(env.tenant, env.user, inv.id))
    assert e.value.status_code == 409 and not env.calls


def test_methods_api_never_leaks_other_tenants_cards(env):
    mine = uuid.uuid4()
    save_card(env, mine)
    with env.db() as s:
        s.add(PaymentMethod(tenant_id=uuid.uuid4(), customer_id=mine, authorization_code="AUTH_other", signature="o", last4="9999",
                            exp_month=1, exp_year=2099, status="active"))
    out = asyncio.run(pm.list_methods(mine, env.ctx))
    assert [m["last4"] for m in out["methods"]] == ["1111"]


def test_remove_deactivates_at_paystack_and_stops_use(env):
    cust = uuid.uuid4()
    save_card(env, cust, authorization_code="AUTH_gone")
    mid = asyncio.run(pm.list_methods(cust, env.ctx))["methods"][0]["id"]
    asyncio.run(pm.remove_method(uuid.UUID(mid), env.ctx))
    assert ("POST", "/customer/authorization/deactivate", {"authorization_code": "AUTH_gone"}) in env.calls
    assert asyncio.run(pm.list_methods(cust, env.ctx))["methods"] == []


# ---- autopay -------------------------------------------------------------------

NOW = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)
TODAY = date(2026, 3, 1)


def autopay(env):
    return asyncio.run(pm.run_autopay(env.tenant, env.user, today=TODAY, now=NOW))


def test_autopay_charges_only_due_invoices_with_a_card(env):
    due = make_invoice(env, due=date(2026, 2, 20))
    future = make_invoice(env, due=date(2026, 4, 1))
    nocard = make_invoice(env, due=date(2026, 2, 20))
    save_card(env, due.customer_id)
    save_card(env, future.customer_id)
    out = autopay(env)
    assert out["charged"] == 1 and out["skipped"] == 1       # `future` is never selected; `nocard` is skipped
    with env.db() as s:
        assert s.get(Invoice, due.id).status == "paid" and s.get(Invoice, future.id).status == "sent"
        assert s.get(Invoice, nocard.id).status == "sent"


def test_autopay_retry_gap_then_gives_up_after_max_attempts(env):
    inv = make_invoice(env, due=date(2026, 2, 20))
    save_card(env, inv.customer_id)
    env.mode["result"] = "failed"

    def age():
        with env.db() as s:
            s.query(GatewayCharge).update({"created_at": NOW - timedelta(hours=49)})
    # no gateway row, so there is no GatewayCharge ledger: give the run something to count
    gateway(env)
    assert autopay(env)["failed"] == 1
    assert autopay(env)["skipped"] == 1                       # retry gap (48h) has not elapsed
    age()
    assert autopay(env)["failed"] == 1                        # second attempt
    age()
    assert autopay(env)["failed"] == 1                        # third attempt
    age()
    out = autopay(env)
    assert out["failed"] == 0 and out["skipped"] == 1         # exhausted: dunning takes over
    with env.db() as s:
        assert s.query(GatewayCharge).count() == 3


def test_autopay_skips_disputed_invoices(env):
    inv = make_invoice(env, due=date(2026, 2, 20))
    save_card(env, inv.customer_id)
    with env.db() as s:
        s.add(GatewayDispute(tenant_id=env.tenant, paystack_dispute_id="d9", invoice_id=inv.id, status="pending"))
    assert autopay(env)["skipped"] == 1 and not env.calls


# ---- disputes ------------------------------------------------------------------

def dispute_event(ref, **over):
    d = {"id": 777, "status": "awaiting-merchant-feedback", "category": "fraud", "refund_amount": 11500,
         "dueAt": "2026-03-10T12:00:00.000Z", "transaction": {"reference": ref, "amount": 11500},
         "updatedAt": "2026-03-01T10:00:00Z"}
    d.update(over)
    return d


def test_dispute_webhook_matches_tenant_and_invoice_and_freezes(env, monkeypatch):
    alerts = []

    async def alert(subject, html):
        alerts.append(subject)
    monkeypatch.setattr(gw, "_alert_ops", alert)
    inv = make_invoice(env)
    charge_event(env, inv, save=False, reference="ref-d")
    assert asyncio.run(disputes.handle_event("charge.dispute.create", dispute_event("ref-d"))) == "accepted"
    with env.db() as s:
        d = s.query(GatewayDispute).one()
        assert d.tenant_id == env.tenant and d.invoice_id == inv.id and d.amount_cents == 11500 and d.category == "fraud"
        assert d.due_at.year == 2026 and pm.invoice_is_disputed(s, env.tenant, inv.id)
    assert alerts == ["Paystack dispute create: R115.00"]
    # same event again -> duplicate; a later remind (new updatedAt) is processed
    assert asyncio.run(disputes.handle_event("charge.dispute.create", dispute_event("ref-d"))) == "duplicate"
    assert asyncio.run(disputes.handle_event("charge.dispute.remind", dispute_event("ref-d", updatedAt="2026-03-08T10:00:00Z"))) == "accepted"
    out = asyncio.run(disputes.handle_event("charge.dispute.resolve",
                                            dispute_event("ref-d", status="resolved", resolution="merchant-accepted")))
    assert out == "accepted"
    with env.db() as s:
        assert s.query(GatewayDispute).count() == 1 and not pm.invoice_is_disputed(s, env.tenant, inv.id)
        assert s.query(GatewayDispute).one().resolution == "merchant-accepted"
    listed = asyncio.run(disputes.list_disputes(env.ctx))
    assert listed["open"] == 0 and listed["disputes"][0]["status"] == "resolved"


def test_unmatched_dispute_is_kept_for_ops_but_not_shown_to_tenants(env):
    asyncio.run(disputes.handle_event("charge.dispute.create", {"id": 1, "status": "pending",
                                                                 "transaction": {"reference": "unknown", "amount": 5000}}))
    with env.db() as s:
        d = s.query(GatewayDispute).one()
        assert d.tenant_id is None and d.amount_cents == 5000
    assert asyncio.run(disputes.list_disputes(env.ctx))["disputes"] == []
