"""Step 3 backend: refunds (Paystack + manual), refund webhooks, tenant liabilities, dispute evidence / resolve /
loss accounting, the gateway-fee ledger entry, and the retired native-subscription endpoints. SQLite stand-in."""
import asyncio
import os
import sys
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.common.auth import AuthContext  # noqa: E402
from services.billing.models import BillingFinanceOutbox, CustomerCredit, Invoice, Payment  # noqa: E402
from services.billing.models_gateway import (  # noqa: E402
    GatewayCharge, GatewayDispute, GatewayLiability, GatewayRefund, GatewaySettings, PaymentMethod)
from services.billing.routes import (  # noqa: E402
    disputes, gateway as gw, payment_methods as pm, paystack, paystack_recurring as recurring, refunds)
from services.billing.tests import sqlite_harness as h  # noqa: E402


@pytest.fixture
def env(monkeypatch):
    db = h.make_session_factory()
    h.patch_sessions(monkeypatch, db)
    for mod in (refunds, disputes):
        monkeypatch.setattr(mod, "get_session", db)
    monkeypatch.setattr(refunds, "_secret", lambda: "sk_test_x")
    monkeypatch.setattr(disputes, "_secret", lambda: "sk_test_x")
    calls = []
    reply = {"refund": {"status": True, "_http_status": 200, "data": {"id": 555, "status": "pending"}},
             "other": {"status": True, "_http_status": 200, "data": {}}}

    async def fake(method, path, body=None):
        calls.append((method, path, body))
        return reply["refund"] if path == "/refund" else reply["other"]
    monkeypatch.setattr(refunds, "_paystack", fake)
    monkeypatch.setattr(disputes, "_paystack", fake)
    delivered = []

    async def deliver(tenant, entries, **_k):
        delivered.extend(entries)
    monkeypatch.setattr(refunds.fp, "deliver_after_commit", deliver)
    tenant = uuid.uuid4()
    return type("Env", (), {"db": db, "tenant": tenant, "calls": calls, "reply": reply, "delivered": delivered,
                            "ctx": AuthContext(user_id=uuid.uuid4(), tenant_id=tenant)})


def paid_invoice_with_credit(env, *, credit_zar="115.00", paystack_ref="ref-pay", kind="refund_required"):
    with env.db() as s:
        inv = h.make_invoice(s, env.tenant, status="paid", paid="115.00")
        s.add(Payment(tenant_id=env.tenant, invoice_id=inv.id, customer_id=inv.customer_id, amount_zar=Decimal("115.00"),
                      method="card", reference=paystack_ref, paystack_ref=paystack_ref, status="completed"))
        credit = CustomerCredit(tenant_id=env.tenant, customer_id=inv.customer_id, invoice_id=inv.id,
                                amount_zar=Decimal(credit_zar), kind=kind, reference=f"cn:{uuid.uuid4()}", reason="credit note")
        s.add(credit)
        s.flush()
        return inv.id, credit.id


def refund(env, credit_id, **kw):
    kw.setdefault("method", "paystack")
    return asyncio.run(refunds.create_refund(refunds.RefundRequest(credit_id=credit_id, **kw), env.ctx))


# ---- refunds ------------------------------------------------------------------------

def test_credits_list_shows_remaining_and_paystack_capacity(env):
    paid_invoice_with_credit(env)
    out = asyncio.run(refunds.refundable_credits(env.ctx))["credits"]
    assert len(out) == 1 and out[0]["remaining_zar"] == 115.0 and out[0]["paystack_refundable_zar"] == 115.0


def test_paystack_refund_goes_against_the_original_charge_then_webhook_completes_it(env):
    inv_id, credit_id = paid_invoice_with_credit(env)
    out = refund(env, credit_id, amount_zar=Decimal("100.00"), reason="Service cancelled")
    assert out["status"] == "pending" and out["amount_zar"] == 100.0
    method, path, body = env.calls[0]
    assert (method, path) == ("POST", "/refund") and body["transaction"] == "ref-pay" and body["amount"] == 10000
    with env.db() as s:
        assert s.get(CustomerCredit, credit_id).status == "open"
    data = {"id": 555, "status": "processed", "transaction_reference": "ref-pay", "amount": 10000}
    assert asyncio.run(refunds.handle_event("refund.processed", data)) == "accepted"
    assert asyncio.run(refunds.handle_event("refund.processed", data)) == "duplicate"
    with env.db() as s:
        r = s.query(GatewayRefund).one()
        assert r.status == "processed"
        assert s.get(CustomerCredit, credit_id).status == "open"          # R15 still held
        liab = s.query(GatewayLiability).one()
        assert liab.kind == "refund" and liab.amount_cents == 10000 and liab.status == "open"
        assert s.query(BillingFinanceOutbox).filter(BillingFinanceOutbox.source == "billing.refund").count() == 1
    assert [e["source"] for e in env.delivered] == ["billing.refund"]
    assert [(l["account_code"], l["debit"], l["credit"]) for l in env.delivered[0]["lines"]] == [
        ("1100", "100.00", "0.00"), ("1010", "0.00", "100.00")]


def test_full_refund_closes_the_credit(env):
    _, credit_id = paid_invoice_with_credit(env)
    env.reply["refund"] = {"status": True, "_http_status": 200, "data": {"id": 9, "status": "processed"}}
    out = refund(env, credit_id)
    assert out["status"] == "processed"
    with env.db() as s:
        assert s.get(CustomerCredit, credit_id).status == "refunded" and s.query(GatewayLiability).count() == 1


def test_cannot_refund_more_than_the_credit_or_more_than_the_charge_and_pending_counts(env):
    _, credit_id = paid_invoice_with_credit(env, credit_zar="50.00")
    with pytest.raises(HTTPException) as e:
        refund(env, credit_id, amount_zar=Decimal("50.01"))
    assert e.value.status_code == 400 and not env.calls
    refund(env, credit_id, amount_zar=Decimal("30.00"))                      # pending: still counts against the credit
    with pytest.raises(HTTPException) as e:
        refund(env, credit_id, amount_zar=Decimal("30.00"))
    assert e.value.status_code == 400 and "R20.00" in e.value.detail


def test_charge_capacity_is_enforced_across_credits(env):
    # one R115 charge, two credits of R100: the second refund cannot exceed what is left of the charge
    with env.db() as s:
        inv = h.make_invoice(s, env.tenant, status="paid", paid="115.00")
        s.add(Payment(tenant_id=env.tenant, invoice_id=inv.id, customer_id=inv.customer_id, amount_zar=Decimal("115.00"),
                      method="card", reference="one", paystack_ref="one", status="completed"))
        ids = []
        for i in range(2):
            c = CustomerCredit(tenant_id=env.tenant, customer_id=inv.customer_id, invoice_id=inv.id, amount_zar=Decimal("100.00"),
                               kind="refund_required", reference=f"cn:{i}")
            s.add(c)
            s.flush()
            ids.append(c.id)
    refund(env, ids[0], amount_zar=Decimal("100.00"))
    with pytest.raises(HTTPException) as e:
        refund(env, ids[1], amount_zar=Decimal("100.00"))
    assert e.value.status_code == 422 and "No single card payment" in e.value.detail


def test_failed_refund_webhook_releases_the_amount(env):
    _, credit_id = paid_invoice_with_credit(env)
    refund(env, credit_id)
    asyncio.run(refunds.handle_event("refund.failed", {"id": 555, "status": "failed", "transaction_reference": "ref-pay",
                                                          "failure_reason": "Account closed"}))
    with env.db() as s:
        r = s.query(GatewayRefund).one()
        assert r.status == "failed" and r.failure_reason == "Account closed" and s.query(GatewayLiability).count() == 0
        assert s.get(CustomerCredit, credit_id).status == "open"
    again = refund(env, credit_id)                                           # the freed amount can be retried
    assert again["status"] == "pending"


def test_paystack_rejecting_the_refund_marks_it_failed_and_surfaces_the_message(env):
    _, credit_id = paid_invoice_with_credit(env)
    env.reply["refund"] = {"status": False, "_http_status": 400, "message": "Transaction has already been fully reversed"}
    with pytest.raises(HTTPException) as e:
        refund(env, credit_id)
    assert e.value.status_code == 502 and "fully reversed" in e.value.detail
    with env.db() as s:
        assert s.query(GatewayRefund).one().status == "failed"


def test_manual_refund_needs_a_bank_reference_and_creates_no_liability(env):
    _, credit_id = paid_invoice_with_credit(env)
    with pytest.raises(HTTPException) as e:
        refund(env, credit_id, method="manual")
    assert e.value.status_code == 422
    out = refund(env, credit_id, method="manual", manual_reference="EFT-778", reason="Paid by EFT")
    assert out["status"] == "processed" and not env.calls
    with env.db() as s:
        assert s.get(CustomerCredit, credit_id).status == "refunded" and s.query(GatewayLiability).count() == 0
    assert [e["source"] for e in env.delivered] == ["billing.refund"]


def test_overpayment_credit_refunds_against_its_own_paystack_reference(env):
    with env.db() as s:
        c = CustomerCredit(tenant_id=env.tenant, customer_id=uuid.uuid4(), amount_zar=Decimal("40.00"), kind="overpayment", reference="over-ref")
        s.add(c)
        s.flush()
        cid = c.id
    refund(env, cid)
    assert env.calls[0][2]["transaction"] == "over-ref" and env.calls[0][2]["amount"] == 4000


def test_other_tenants_credit_is_not_found(env):
    with env.db() as s:
        c = CustomerCredit(tenant_id=uuid.uuid4(), customer_id=uuid.uuid4(), amount_zar=Decimal("10.00"), kind="overpayment", reference="x")
        s.add(c)
        s.flush()
        cid = c.id
    with pytest.raises(HTTPException) as e:
        refund(env, cid)
    assert e.value.status_code == 404


# ---- gateway fee ledger entry --------------------------------------------------------

def test_commission_is_posted_to_the_tenant_books_on_charge_success(env, monkeypatch):
    monkeypatch.setattr(paystack, "PAYSTACK_SECRET", "sk_test_x")
    async def no_reinstate(*_a, **_k):
        return None
    monkeypatch.setattr(paystack, "_trigger_auto_reinstate", no_reinstate)
    with env.db() as s:
        s.add(GatewaySettings(tenant_id=env.tenant, status="active", business_name="A", settlement_bank_code="1",
                              account_last4="1234", subaccount_code="ACCT_t"))
        inv = h.make_invoice(s, env.tenant)
        invoice_id, customer_id = inv.id, inv.customer_id
    with env.db() as s:
        gw.split_for_charge(s, env.tenant, 11500, "ref-fee", invoice_id=invoice_id)
        from services.billing.models import PaystackInitialization
        s.add(PaystackInitialization(tenant_id=env.tenant, invoice_id=invoice_id, customer_id=customer_id, reference="ref-fee",
                                     amount_cents=11500, currency="ZAR", status="pending"))
    data = {"reference": "ref-fee", "amount": 11500, "currency": "ZAR", "id": "ref-fee", "fees": 300,
            "metadata": {"tenant_id": str(env.tenant), "invoice_id": str(invoice_id)}}
    assert asyncio.run(paystack._handle_charge_success(data, paystack.event_key("charge.success", data, b""))) == "accepted"
    with env.db() as s:
        sources = sorted(r.source for r in s.query(BillingFinanceOutbox))
        assert sources == ["billing.gateway_fee", "billing.payment"]
        fee = [r for r in s.query(BillingFinanceOutbox) if r.source == "billing.gateway_fee"][0].payload
    assert [(l["account_code"], l["debit"], l["credit"]) for l in fee["lines"]] == [("6950", "6.90", "0.00"), ("1010", "0.00", "6.90")]


# ---- disputes ---------------------------------------------------------------------------

def make_dispute(env, **kw):
    inv_id = None
    with env.db() as s:
        inv = h.make_invoice(s, env.tenant, status="paid", paid="115.00")
        inv_id = inv.id
        d = GatewayDispute(tenant_id=env.tenant, paystack_dispute_id="777", reference="ref-d", invoice_id=inv.id, customer_id=inv.customer_id,
                           amount_cents=11500, status="awaiting-merchant-feedback", **kw)
        s.add(d)
        s.flush()
        return d.id, inv_id


def test_evidence_pack_is_assembled_from_our_records(env, monkeypatch):
    async def profile(tenant, customer):
        return {"name": "Thandi Mokoena", "email": "t@example.com", "phone": "0821234567", "address": "1 Main Rd, Soweto"}
    monkeypatch.setattr(disputes, "resolve_customer_profile", profile)
    did, inv_id = make_dispute(env)
    with env.db() as s:
        from services.billing.models import Subscription
        inv = s.get(Invoice, inv_id)
        s.add(Payment(tenant_id=env.tenant, invoice_id=inv_id, customer_id=inv.customer_id, amount_zar=Decimal("115.00"),
                      method="card", reference="ref-d", paystack_ref="ref-d", status="completed"))
        s.add(Subscription(tenant_id=env.tenant, customer_id=inv.customer_id, plan="Fibre 100", status="active",
                           billing_interval="monthly", base_price_zar=Decimal("100.00"), billing_anchor=date(2026, 1, 5)))
    out = asyncio.run(disputes.dispute_detail(did, env.ctx))
    pack = out["evidence_pack"]
    assert pack["customer_name"] == "Thandi Mokoena" and pack["delivery_address"] == "1 Main Rd, Soweto"
    assert pack["delivery_date"] == "2026-01-05" and "Fibre 100" in pack["service_details"]
    assert pack["payments"][0]["reference"] == "ref-d" and len(pack["invoice_numbers"]) == 1 and out["outcome"] is None


def test_submit_evidence_and_resolve_call_paystack_and_enforce_ownership(env):
    did, _ = make_dispute(env)
    body = disputes.EvidenceRequest(customer_email="t@example.com", customer_name="T M", customer_phone="082", service_details="Fibre 100",
                                    delivery_address="1 Main Rd", delivery_date=date(2026, 1, 5))
    assert asyncio.run(disputes.submit_evidence(did, body, env.ctx))["submitted"]
    assert env.calls[0][:2] == ("POST", "/dispute/777/evidence") and env.calls[0][2]["delivery_date"] == "2026-01-05"
    asyncio.run(disputes.resolve_dispute(did, disputes.ResolveRequest(resolution="merchant-accepted", message="We agree"), env.ctx))
    assert env.calls[1][:2] == ("PUT", "/dispute/777/resolve") and env.calls[1][2]["refund_amount"] == 11500
    other = AuthContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4())
    with pytest.raises(HTTPException) as e:
        asyncio.run(disputes.dispute_detail(did, other))
    assert e.value.status_code == 404


def test_lost_dispute_posts_chargeback_and_opens_a_liability_once(env, monkeypatch):
    async def quiet(*_a, **_k): return None
    monkeypatch.setattr(gw, "_alert_ops", quiet)
    monkeypatch.setattr(disputes.fp, "deliver_after_commit", refunds.fp.deliver_after_commit)
    did, _ = make_dispute(env)
    event = {"id": 777, "status": "resolved", "resolution": "merchant-accepted", "refund_amount": 11500,
             "transaction": {"reference": "ref-d", "amount": 11500}, "updatedAt": "2026-03-12T10:00:00Z"}
    assert asyncio.run(disputes.handle_event("charge.dispute.resolve", event)) == "accepted"
    again = {**event, "updatedAt": "2026-03-12T10:05:00Z"}
    asyncio.run(disputes.handle_event("charge.dispute.resolve", again))     # a different delivery of the same outcome
    with env.db() as s:
        assert s.query(GatewayLiability).filter(GatewayLiability.kind == "chargeback").count() == 1
        assert s.query(BillingFinanceOutbox).filter(BillingFinanceOutbox.source == "billing.chargeback").count() == 1
        assert disputes.outcome(s.query(GatewayDispute).one()) == "lost"
    assert [e["source"] for e in env.delivered] == ["billing.chargeback"]
    assert env.delivered[0]["lines"][0]["account_code"] == "6960"


def test_won_or_unrecognised_resolution_posts_nothing(env, monkeypatch):
    async def quiet(*_a, **_k): return None
    monkeypatch.setattr(gw, "_alert_ops", quiet)
    did, _ = make_dispute(env)
    asyncio.run(disputes.handle_event("charge.dispute.resolve", {"id": 777, "status": "resolved", "resolution": "declined",
                                                                  "transaction": {"reference": "ref-d"}, "updatedAt": "a"}))
    asyncio.run(disputes.handle_event("charge.dispute.resolve", {"id": 777, "status": "resolved", "resolution": "something-new",
                                                                  "transaction": {"reference": "ref-d"}, "updatedAt": "b"}))
    with env.db() as s:
        assert s.query(GatewayLiability).count() == 0 and s.query(BillingFinanceOutbox).count() == 0
        assert disputes.outcome(s.query(GatewayDispute).one()) is None


# ---- retired native subscriptions + autopay lock ----------------------------------------------

def test_native_paystack_subscription_creation_is_retired_by_default(env, monkeypatch):
    monkeypatch.delenv("PAYSTACK_NATIVE_SUBSCRIPTIONS_ENABLED", raising=False)
    req = recurring.PaystackSubscribeRequest(customer_code="CUS_x", plan_code="PLN_x")
    with pytest.raises(HTTPException) as e:
        asyncio.run(recurring.create_subscription(req, env.ctx))
    assert e.value.status_code == 410
    with pytest.raises(HTTPException) as e:
        asyncio.run(recurring.sync_plan_to_paystack(uuid.uuid4(), recurring.PaystackPlanSync(), env.ctx))
    assert e.value.status_code == 410


def test_autopay_worker_is_off_by_default_and_pass_visits_tenants_with_cards(env, monkeypatch):
    monkeypatch.delenv("AUTOPAY_WORKER_ENABLED", raising=False)
    assert not pm.worker_enabled()
    seen = []

    async def fake_run(tenant_id, user_id, *, limit=100, **_k):
        seen.append(tenant_id)
        return {"charged": 1, "failed": 0, "pending": 0, "skipped": 2, "details": []}
    monkeypatch.setattr(pm, "run_autopay", fake_run)
    monkeypatch.setattr(pm, "_acquire_pass_lock", lambda: (True, None))
    with env.db() as s:
        s.add(PaymentMethod(tenant_id=env.tenant, customer_id=uuid.uuid4(), authorization_code="A", signature="s", status="active"))
        s.add(PaymentMethod(tenant_id=env.tenant, customer_id=uuid.uuid4(), authorization_code="B", signature="t", status="active"))
        s.add(PaymentMethod(tenant_id=uuid.uuid4(), customer_id=uuid.uuid4(), authorization_code="C", signature="u", status="removed"))
    out = asyncio.run(pm.run_autopay_all())
    assert seen == [env.tenant] and out["tenants"] == 1 and out["charged"] == 1 and out["skipped"] == 2
    monkeypatch.setattr(pm, "_acquire_pass_lock", lambda: (False, None))      # another replica holds the lock
    assert "skipped" in asyncio.run(pm.run_autopay_all()) and seen == [env.tenant]


# ---- evidence attachments ------------------------------------------------------------------

def _upload(env, monkeypatch, data, filename="proof.pdf", *, put_status=200, upload_info=None, signed="https://s3.example.com/up?sig=1"):
    import io
    from fastapi import UploadFile
    from services.common import url_safety
    monkeypatch.setattr(url_safety, "_default_resolver", lambda host, port: ["93.184.216.34"])
    puts = []

    async def paystack(method, path, body=None):
        puts.append((method, path))
        return {"status": True, "_http_status": 200, "data": upload_info if upload_info is not None else {"signedUrl": signed, "fileName": "stored-proof.pdf"}}

    class Resp:
        status_code = put_status

    class Client:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def put(self, url, content=None, headers=None):
            puts.append(("PUT", url, len(content), headers["Content-Type"]))
            return Resp()
    monkeypatch.setattr(disputes, "_paystack", paystack)
    monkeypatch.setattr(disputes.httpx, "AsyncClient", Client)
    did = getattr(env, "_did", None)
    if did is None:
        did, _ = make_dispute(env)
        env._did = did
    up = UploadFile(file=io.BytesIO(data), filename=filename)
    return asyncio.run(disputes.upload_attachment(did, up, env.ctx)), puts


def test_attachment_is_sent_to_the_signed_url_and_returns_the_stored_filename(env, monkeypatch):
    out, calls = _upload(env, monkeypatch, b"%PDF-1.4 evidence", "My proof (1).pdf")
    assert out == {"uploaded_filename": "stored-proof.pdf", "size_bytes": 17}
    assert calls[0] == ("GET", "/dispute/777/upload_url?upload_filename=My_proof__1_.pdf")
    assert calls[1] == ("PUT", "https://s3.example.com/up?sig=1", 17, "application/pdf")


@pytest.mark.parametrize("data,name,code", [
    (b"MZ not a pdf", "proof.pdf", 415),            # content does not match the type
    (b"%PDF-1.4", "proof.exe", 415),                # type not allowed
    (b"", "proof.pdf", 415),
])
def test_attachment_rejects_bad_files_before_calling_paystack(env, monkeypatch, data, name, code):
    with pytest.raises(HTTPException) as e:
        _upload(env, monkeypatch, data, name)
    assert e.value.status_code == code


def test_attachment_over_the_size_cap_is_refused(env, monkeypatch):
    monkeypatch.setenv("DISPUTE_ATTACHMENT_MAX_MB", "0.0001")          # about 100 bytes
    with pytest.raises(HTTPException) as e:
        _upload(env, monkeypatch, b"%PDF" + b"x" * 500, "big.pdf")
    assert e.value.status_code == 413


def test_attachment_refuses_a_non_public_upload_url_and_provider_errors(env, monkeypatch):
    with pytest.raises(HTTPException) as e:
        _upload(env, monkeypatch, b"%PDF-1.4", signed="http://169.254.169.254/latest")
    assert e.value.status_code == 502 and "unusable" in e.value.detail
    with pytest.raises(HTTPException) as e:
        _upload(env, monkeypatch, b"%PDF-1.4", put_status=403)
    assert e.value.status_code == 502 and "HTTP 403" in e.value.detail
    with pytest.raises(HTTPException) as e:
        _upload(env, monkeypatch, b"%PDF-1.4", upload_info={})
    assert e.value.status_code == 502


def test_attachment_needs_an_open_dispute_of_the_callers_tenant(env, monkeypatch):
    import io
    from fastapi import UploadFile
    did, _ = make_dispute(env)
    with env.db() as s:
        s.query(GatewayDispute).update({"status": "resolved"})
    with pytest.raises(HTTPException) as e:
        asyncio.run(disputes.upload_attachment(did, UploadFile(file=io.BytesIO(b"%PDF"), filename="a.pdf"), env.ctx))
    assert e.value.status_code == 409
    other = AuthContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4())
    with pytest.raises(HTTPException) as e:
        asyncio.run(disputes.upload_attachment(did, UploadFile(file=io.BytesIO(b"%PDF"), filename="a.pdf"), other))
    assert e.value.status_code == 404


# ---- disputes on OmniDome's own platform invoices -------------------------------------------

def test_dispute_on_a_platform_invoice_goes_to_platform_ops_not_to_a_tenant(env, monkeypatch):
    from sqlalchemy import text
    alerts = []

    async def alert(subject, html):
        alerts.append(subject)
    monkeypatch.setattr(gw, "_alert_ops", alert)
    tenant = uuid.uuid4()
    with env.db() as s:
        s.execute(text("CREATE TABLE platform_orders (id TEXT, tenant_id TEXT, reference TEXT)"))
        s.execute(text("CREATE TABLE platform_checkout_attempts (reference TEXT, order_id TEXT)"))
        s.execute(text("INSERT INTO platform_orders VALUES ('o1', :t, 'ODP-2026-000012')"), {"t": str(tenant)})
        s.execute(text("INSERT INTO platform_checkout_attempts VALUES ('ODP-2026-000012-retry', 'o1')"))
    for ref in ("ODP-2026-000012", "ODP-2026-000012-retry"):
        asyncio.run(disputes.handle_event("charge.dispute.create", {"id": ref[-5:], "status": "awaiting-merchant-feedback",
                                                                   "transaction": {"reference": ref, "amount": 50_000}}))
    asyncio.run(disputes.handle_event("charge.dispute.create", {"id": "zzz", "status": "pending", "transaction": {"reference": "mystery", "amount": 1}}))
    with env.db() as s:
        rows = {d.paystack_dispute_id: d for d in s.query(GatewayDispute)}
        assert all(d.tenant_id is None for d in rows.values())                     # never visible to a tenant
        assert str(tenant) in rows["00012"].reason and str(tenant) in rows["-retry"[-5:]].reason
        assert rows["zzz"].reason is None
    assert len(alerts) == 3
    assert asyncio.run(disputes.list_disputes(env.ctx))["disputes"] == []
    admin = AuthContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=["platform_admin"])
    out = asyncio.run(disputes.platform_disputes(admin))
    assert out["open"] == 3 and {d["note"] is not None for d in out["disputes"]} == {True, False}
    with pytest.raises(HTTPException) as e:
        asyncio.run(disputes.platform_disputes(env.ctx))
    assert e.value.status_code == 403
