"""Money logic against an in-memory SQLite stand-in: Paystack webhook, payments, credit notes,
idempotent invoice generation and Paystack initialization. Handlers are called directly (role gates
are covered in test_access.py)."""
import asyncio
import hashlib
import hmac
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.common.auth import AuthContext  # noqa: E402
from services.billing import finance_posting as fp  # noqa: E402
from services.billing.models import (  # noqa: E402
    BillingFinanceOutbox, BillingWebhookEvent, CustomerCredit, DunningAction, Invoice, Payment,
    PaystackInitialization, Subscription,
)
from services.billing.routes import invoices as inv_routes, payments as pay_routes, paystack  # noqa: E402
from services.billing.schemas import CreditNoteRequest, InvoiceGenerateRequest, LineItem, PaymentCreate, PaystackInitializeRequest  # noqa: E402
from services.billing.tests import sqlite_harness as h  # noqa: E402

D = Decimal
SECRET = "whsec_test"


@pytest.fixture
def env(monkeypatch):
    db = h.make_session_factory()
    h.patch_sessions(monkeypatch, db)
    monkeypatch.setattr(paystack, "PAYSTACK_WEBHOOK_SECRET", SECRET)
    reinstated = []

    async def reinstate(tenant, customer):
        reinstated.append(customer)
    monkeypatch.setattr(paystack, "_trigger_auto_reinstate", reinstate)
    tenant = uuid.uuid4()
    ctx = AuthContext(user_id=uuid.uuid4(), tenant_id=tenant)
    return type("Env", (), {"db": db, "tenant": tenant, "ctx": ctx, "reinstated": reinstated})


def charge(env, inv_id, *, reference="ref-1", cents=11500, currency="ZAR", event_id=None, tenant=None):
    return {"reference": reference, "amount": cents, "currency": currency, "id": event_id or reference,
            "metadata": {"invoice_id": str(inv_id), "tenant_id": str(tenant or env.tenant)}}


def run_charge(data):
    return asyncio.run(paystack._handle_charge_success(data, paystack.event_key("charge.success", data, b"")))


def inv_state(env, inv_id):
    with env.db() as s:
        i = s.get(Invoice, inv_id)
        return i.status, i.amount_paid_zar


def counts(env):
    with env.db() as s:
        return (s.query(Payment).count(), s.query(CustomerCredit).count(), s.query(BillingFinanceOutbox).count())


# ── webhook ─────────────────────────────────────────────────────────────────

def test_signature_is_still_hmac_sha512_compare_digest(monkeypatch):
    monkeypatch.setattr(paystack, "PAYSTACK_WEBHOOK_SECRET", SECRET)
    body = b'{"event":"x"}'
    sig = hmac.new(SECRET.encode(), body, hashlib.sha512).hexdigest()
    assert paystack._verify_webhook_signature(body, sig)
    assert not paystack._verify_webhook_signature(body, "0" * 128)
    assert not paystack._verify_webhook_signature(body, None)


def test_charge_pays_the_invoice_posts_and_reinstates_after_commit(env):
    with env.db() as s:
        inv = h.make_invoice(s, env.tenant)
        inv_id, cust = inv.id, inv.customer_id
    assert run_charge(charge(env, inv_id)) == "accepted"
    assert inv_state(env, inv_id) == ("paid", D("115.00"))
    assert env.reinstated == [cust]
    with env.db() as s:
        sources = sorted(r.source for r in s.query(BillingFinanceOutbox).all())
        assert sources == ["billing.payment"]                       # invoice was already issued ('sent')
        assert s.query(BillingFinanceOutbox).one().status == "sent"  # delivered after commit


def test_duplicate_event_has_no_side_effects(env):
    with env.db() as s:
        inv_id = h.make_invoice(s, env.tenant).id
    assert run_charge(charge(env, inv_id)) == "accepted"
    before = counts(env)
    for _ in range(3):
        assert run_charge(charge(env, inv_id)) == "duplicate"
    assert counts(env) == before and inv_state(env, inv_id) == ("paid", D("115.00"))
    assert len(env.reinstated) == 1
    with env.db() as s:
        assert s.query(BillingWebhookEvent).count() == 1


def test_wrong_currency_is_rejected_and_records_nothing(env):
    with env.db() as s:
        inv_id = h.make_invoice(s, env.tenant).id
    assert run_charge(charge(env, inv_id, currency="USD")) == "rejected"
    assert inv_state(env, inv_id) == ("sent", D("0.00")) and counts(env) == (0, 0, 0)


def test_amount_over_the_balance_applies_the_balance_and_holds_the_rest(env):
    with env.db() as s:
        inv_id = h.make_invoice(s, env.tenant, paid="100.00").id     # R15 outstanding
    run_charge(charge(env, inv_id, cents=5000))                       # R50 paid
    assert inv_state(env, inv_id) == ("paid", D("115.00"))            # never above the total
    with env.db() as s:
        credit = s.query(CustomerCredit).one()
        assert credit.amount_zar == D("35.00") and credit.kind == "overpayment"
        assert s.query(Payment).one().amount_zar == D("15.00")


@pytest.mark.parametrize("status", ["voided"])
def test_charge_on_a_voided_invoice_is_never_marked_paid(env, status):
    with env.db() as s:
        inv_id = h.make_invoice(s, env.tenant, status=status).id
    run_charge(charge(env, inv_id))
    assert inv_state(env, inv_id) == ("voided", D("0.00"))
    assert env.reinstated == []
    with env.db() as s:
        credit = s.query(CustomerCredit).one()
        assert credit.kind == "unallocated_payment" and credit.amount_zar == D("115.00")
        assert s.query(Payment).count() == 0
        assert s.query(BillingFinanceOutbox).one().source == "billing.payment"   # cash still reaches the ledger


def test_charge_on_an_already_paid_invoice_becomes_credit(env):
    with env.db() as s:
        inv_id = h.make_invoice(s, env.tenant, status="paid", paid="115.00").id
    run_charge(charge(env, inv_id))
    assert inv_state(env, inv_id) == ("paid", D("115.00"))
    with env.db() as s:
        assert s.query(CustomerCredit).one().amount_zar == D("115.00") and s.query(Payment).count() == 0


def test_amount_must_match_the_initialization(env):
    with env.db() as s:
        inv = h.make_invoice(s, env.tenant)
        inv_id = inv.id
        s.add(PaystackInitialization(tenant_id=env.tenant, invoice_id=inv_id, customer_id=inv.customer_id,
                                     reference="OD-1", amount_cents=11500))
    run_charge(charge(env, inv_id, reference="OD-1", cents=5000))     # different from what we initialized
    assert inv_state(env, inv_id) == ("sent", D("0.00"))
    with env.db() as s:
        assert s.query(CustomerCredit).one().kind == "unallocated_payment"


def test_matching_initialization_is_completed_and_trusted_over_metadata(env):
    other = uuid.uuid4()
    with env.db() as s:
        inv = h.make_invoice(s, env.tenant)
        inv_id = inv.id
        s.add(PaystackInitialization(tenant_id=env.tenant, invoice_id=inv_id, customer_id=inv.customer_id,
                                     reference="OD-2", amount_cents=11500))
    run_charge(charge(env, uuid.uuid4(), reference="OD-2", tenant=other))   # forged metadata, our record wins
    assert inv_state(env, inv_id) == ("paid", D("115.00"))
    with env.db() as s:
        assert s.query(PaystackInitialization).one().status == "completed"


def test_draft_invoice_paid_by_card_is_issued_first_in_the_ledger(env):
    with env.db() as s:
        inv_id = h.make_invoice(s, env.tenant, status="draft").id
    run_charge(charge(env, inv_id))
    with env.db() as s:
        assert sorted(r.source for r in s.query(BillingFinanceOutbox).all()) == ["billing.invoice", "billing.payment"]


def test_classify_charge_is_pure():
    inv = Invoice(status="sent", total_zar=D("115.00"), amount_paid_zar=D("0.00"), credit_note_of=None)
    assert paystack.classify_charge(inv, D("115.00"), None, 11500, "ZAR") == ("apply", D("115.00"), D("0"))
    assert paystack.classify_charge(inv, D("200.00"), None, 20000, "zar")[0:2] == ("apply", D("115.00"))
    assert paystack.classify_charge(inv, D("1.00"), None, 100, "NGN")[0] == "reject_currency"


# ── payments ────────────────────────────────────────────────────────────────

def pay(env, inv_id, amount, key=None, method="eft"):
    resp = Response()
    out = asyncio.run(pay_routes.record_payment(
        PaymentCreate(invoice_id=inv_id, amount_zar=D(amount), method=method, idempotency_key=key), resp, env.ctx, None))
    return out, resp.status_code


def test_payment_idempotency_key_returns_the_original(env):
    with env.db() as s:
        inv_id = h.make_invoice(s, env.tenant).id
    first, _ = pay(env, inv_id, "50.00", key="k1")
    again, code = pay(env, inv_id, "50.00", key="k1")
    assert again.id == first.id and code == 200
    assert inv_state(env, inv_id) == ("partially_paid", D("50.00")) and counts(env)[0] == 1


def test_payment_posts_to_the_ledger_and_rejects_overpay(env):
    with env.db() as s:
        inv_id = h.make_invoice(s, env.tenant).id
    pay(env, inv_id, "115.00", method="card")
    with env.db() as s:
        row = s.query(BillingFinanceOutbox).one()
        assert row.payload["lines"][0] == {"account_code": "1010", "debit": "115.00", "credit": "0.00"}
    with pytest.raises(HTTPException) as e:
        pay(env, inv_id, "1.00")
    assert e.value.status_code == 400


# ── credit notes ────────────────────────────────────────────────────────────

def credit(env, inv_id, **body):
    return asyncio.run(inv_routes.create_credit_note(inv_id, CreditNoteRequest(reason="r", **body), env.ctx))


def test_negative_or_zero_quantity_is_rejected_by_the_schema():
    for q in (-1, 0):
        with pytest.raises(ValidationError):
            LineItem(description="x", quantity=q, unit_price_zar=D("10"))
    with pytest.raises(ValidationError):
        LineItem(description="x", quantity=1, unit_price_zar=D("-1"))


def test_over_credit_is_a_409_and_totals_cannot_exceed_the_invoice(env):
    with env.db() as s:
        inv_id = h.make_invoice(s, env.tenant).id                          # R115
    first = credit(env, inv_id, line_items=[LineItem(description="c", quantity=1, unit_price_zar=D("60"))])
    assert first.total_zar == D("-69.00")
    with pytest.raises(HTTPException) as e:
        credit(env, inv_id, line_items=[LineItem(description="c", quantity=1, unit_price_zar=D("60"))])
    assert e.value.status_code == 409


def test_full_credit_on_unpaid_invoice_voids_it_and_posts_the_reversal(env):
    with env.db() as s:
        inv_id = h.make_invoice(s, env.tenant).id
    cn = credit(env, inv_id)
    assert cn.total_zar == D("-115.00") and cn.status == "paid"
    assert inv_state(env, inv_id)[0] == "voided"
    with env.db() as s:
        row = s.query(BillingFinanceOutbox).one()
        assert row.source == "billing.credit_note"
        assert {l["account_code"]: l["debit"] for l in row.payload["lines"] if D(l["debit"])} == {"4000": "100.00", "2200": "15.00"}
        assert s.query(CustomerCredit).count() == 0


def test_credit_note_on_a_paid_invoice_never_voids_it_and_records_a_refund_due(env):
    with env.db() as s:
        inv_id = h.make_invoice(s, env.tenant, status="paid", paid="115.00").id
    cn = credit(env, inv_id)
    assert cn.status == "credit_issued"
    assert inv_state(env, inv_id) == ("paid", D("115.00"))                  # not voided, payment untouched
    with env.db() as s:
        c = s.query(CustomerCredit).one()
        assert c.kind == "refund_required" and c.amount_zar == D("115.00")


def test_credit_note_on_a_draft_or_foreign_invoice_is_refused(env):
    with env.db() as s:
        draft = h.make_invoice(s, env.tenant, status="draft").id
        foreign = h.make_invoice(s, uuid.uuid4()).id
    for inv_id, code in ((draft, 409), (foreign, 404)):
        with pytest.raises(HTTPException) as e:
            credit(env, inv_id)
        assert e.value.status_code == code


def test_void_unpaid_invoice_posts_full_reversal_but_a_draft_posts_nothing(env):
    with env.db() as s:
        sent = h.make_invoice(s, env.tenant).id
        draft = h.make_invoice(s, env.tenant, status="draft").id
        paid = h.make_invoice(s, env.tenant, status="paid", paid="115.00").id
    asyncio.run(inv_routes.void_invoice(sent, env.ctx))
    asyncio.run(inv_routes.void_invoice(draft, env.ctx))
    with env.db() as s:
        assert [r.source for r in s.query(BillingFinanceOutbox).all()] == ["billing.void"]
    with pytest.raises(HTTPException) as e:
        asyncio.run(inv_routes.void_invoice(paid, env.ctx))
    assert e.value.status_code == 409


def test_sending_a_draft_schedules_dunning_and_posts_revenue_once(env):
    from services.billing.schemas import InvoiceSendRequest
    with env.db() as s:
        inv_id = h.make_invoice(s, env.tenant, status="draft").id
    for _ in range(2):
        asyncio.run(inv_routes.send_invoice(inv_id, InvoiceSendRequest(), env.ctx))
    with env.db() as s:
        assert s.query(DunningAction).count() == 4
        row = s.query(BillingFinanceOutbox).one()
        assert row.source == "billing.invoice"
        assert sum(D(l["credit"]) for l in row.payload["lines"]) == D("115.00")


# ── generate idempotency ────────────────────────────────────────────────────

def make_sub(session, tenant, start, **kw):
    sub = Subscription(id=uuid.uuid4(), tenant_id=tenant, customer_id=uuid.uuid4(), plan="Fibre", status="active",
                       billing_interval="monthly", base_price_zar=D("100.00"), billing_anchor=start,
                       current_period_start=start, current_period_end=date(start.year, start.month, 28), **kw)
    session.add(sub)
    session.flush()
    return sub


def generate(env, billing_date):
    resp = Response()
    out = asyncio.run(inv_routes.generate_invoices(InvoiceGenerateRequest(billing_date=billing_date), resp, env.ctx))
    return out, resp.status_code


def test_generate_twice_creates_one_invoice_and_advances_once(env):
    start = date(2026, 3, 1)
    with env.db() as s:
        sub_id = make_sub(s, env.tenant, start).id
    first, code1 = generate(env, start)
    assert len(first) == 1 and first[0].created and code1 == 201
    second, code2 = generate(env, start)                                   # the double-click
    assert [i.created for i in second] == [False] and second[0].id == first[0].id and code2 == 200
    with env.db() as s:
        assert s.query(Invoice).count() == 1
        sub = s.get(Subscription, sub_id)
        assert sub.current_period_start == first[0].billing_period_end    # advanced exactly once


def test_generate_only_bills_periods_due_on_the_billing_date(env):
    with env.db() as s:
        make_sub(s, env.tenant, date(2026, 6, 1))
    out, code = generate(env, date(2026, 5, 31))
    assert out == [] and code == 200
    with env.db() as s:
        assert s.query(Invoice).count() == 0


def test_generate_gets_the_existing_prorated_invoice_instead_of_double_billing(env):
    start = date(2026, 3, 1)
    with env.db() as s:
        sub = make_sub(s, env.tenant, start)
        existing = h.make_invoice(s, env.tenant, status="draft", subscription_id=sub.id, period_start=start)
        existing.billing_period_end = date(2026, 3, 28)
        existing_id = existing.id
    out, _ = generate(env, start)
    assert [(i.id, i.created) for i in out] == [(existing_id, False)]
    with env.db() as s:
        assert s.query(Invoice).count() == 1


def test_generate_does_not_touch_other_tenants(env):
    with env.db() as s:
        make_sub(s, uuid.uuid4(), date(2026, 3, 1))
    assert generate(env, date(2026, 3, 1))[0] == []


# ── Paystack initialize ─────────────────────────────────────────────────────

def test_to_cents_rounds_half_up_instead_of_truncating():
    assert paystack.to_cents(D("19.99")) == 1999        # int(19.99 * 100) is 1998 in floats
    assert paystack.to_cents(D("0.285")) == 29 and paystack.to_cents(D("115.00")) == 11500
    assert paystack.to_cents(D("1.005")) == 101


def test_callback_allow_list(monkeypatch):
    monkeypatch.delenv("BILLING_CALLBACK_ALLOWED_HOSTS", raising=False)
    monkeypatch.setenv("APP_PUBLIC_URL", "https://app.example.co.za")
    assert paystack.callback_allowed("https://app.example.co.za/pay/done")
    assert not paystack.callback_allowed("https://evil.example.com/steal")
    assert not paystack.callback_allowed("https://app.example.co.za.evil.com/x")
    assert not paystack.callback_allowed("javascript:alert(1)")
    monkeypatch.setenv("BILLING_CALLBACK_ALLOWED_HOSTS", "pay.example.com, other.org")
    assert paystack.callback_allowed("https://pay.example.com/x") and not paystack.callback_allowed("https://app.example.co.za/")
    monkeypatch.delenv("BILLING_CALLBACK_ALLOWED_HOSTS")
    monkeypatch.delenv("APP_PUBLIC_URL")
    assert not paystack.callback_allowed("https://app.example.co.za/")      # nothing configured: nothing allowed


def init(env, **body):
    return asyncio.run(paystack.initialize_paystack(PaystackInitializeRequest(**body), env.ctx))


def test_no_key_means_503_unless_mock_is_explicitly_allowed(env, monkeypatch):
    monkeypatch.setattr(paystack, "PAYSTACK_SECRET", "")
    monkeypatch.delenv("BILLING_ALLOW_MOCK_PAYSTACK", raising=False)
    with env.db() as s:
        inv_id = h.make_invoice(s, env.tenant).id
    with pytest.raises(HTTPException) as e:
        init(env, invoice_id=inv_id)
    assert e.value.status_code == 503
    monkeypatch.setenv("BILLING_ALLOW_MOCK_PAYSTACK", "true")
    out = init(env, invoice_id=inv_id)
    assert out.access_code == "MOCK_ACCESS" and out.reference.startswith("OD-")


def test_initialize_validates_amount_callback_and_uses_the_customer_email(env, monkeypatch):
    monkeypatch.setattr(paystack, "PAYSTACK_SECRET", "sk_test_x")
    monkeypatch.setenv("APP_PUBLIC_URL", "https://app.example.co.za")
    sent = {}

    async def email(tenant, customer, account=None):
        return "customer@example.com"
    monkeypatch.setattr(paystack, "resolve_customer_email", email)

    class Resp:
        status_code = 200
        text = ""
        def json(self): return {"data": {"authorization_url": "https://checkout/x", "access_code": "AC", "reference": sent["payload"]["reference"]}}

    class Client:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            sent["payload"] = json
            return Resp()
    monkeypatch.setattr(paystack.httpx, "AsyncClient", Client)

    with env.db() as s:
        inv_id = h.make_invoice(s, env.tenant, paid="15.00").id            # R100 outstanding
    for kwargs, code in (({"amount_zar": D("100.01")}, 400),                                  # over the balance
                         ({"callback_url": "https://evil.example.com/x"}, 400)):             # open redirect
        with pytest.raises(HTTPException) as e:
            init(env, invoice_id=inv_id, **kwargs)
        assert e.value.status_code == code
    out = init(env, invoice_id=inv_id, email="attacker@evil.com", amount_zar=D("19.99"),
               callback_url="https://app.example.co.za/done")
    p = sent["payload"]
    assert p["amount"] == 1999 and p["currency"] == "ZAR" and p["email"] == "customer@example.com"
    assert p["reference"] == out.reference and p["callback_url"] == "https://app.example.co.za/done"
    with env.db() as s:
        rec = s.query(PaystackInitialization).one()
        assert rec.reference == out.reference and rec.amount_cents == 1999
