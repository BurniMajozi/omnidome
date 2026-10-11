"""The single Paystack webhook serves three owners: OmniDome's own platform billing (platform_checkout), tenant-customer
collections (invoices, refunds, disputes) and payouts (transfers, funding). These tests pin the dispatch order so an event
goes to exactly one owner and platform events never reach the tenant paths."""
import asyncio
import hashlib
import hmac
import json
import os
import sys
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.billing.models import CustomerCredit, Payment  # noqa: E402
from services.billing.models_gateway import GatewayDispute, GatewayLiability, GatewayRefund  # noqa: E402
from services.billing.models_payouts import PayoutBatch, PayoutFunding, PayoutItem, PayoutWallet  # noqa: E402
from services.billing.routes import disputes, payouts, paystack, platform_checkout, refunds  # noqa: E402
from services.billing.tests import sqlite_harness as h  # noqa: E402

SECRET = "whsec_dispatch"


@pytest.fixture
def env(monkeypatch):
    db = h.make_session_factory()
    h.patch_sessions(monkeypatch, db)
    for mod in (payouts, refunds, disputes):
        monkeypatch.setattr(mod, "get_session", db)
    monkeypatch.setattr(paystack, "PAYSTACK_WEBHOOK_SECRET", SECRET)
    seen = []

    async def platform(event, data):
        seen.append((event, data.get("reference")))
        return "paid" if str(data.get("reference") or "").startswith("ODP-") else None
    monkeypatch.setattr(platform_checkout, "handle_event", platform)

    async def quiet(*a, **k):
        return None
    monkeypatch.setattr(refunds.fp, "deliver_after_commit", quiet)
    from services.billing.routes import gateway as gw
    monkeypatch.setattr(gw, "_alert_ops", quiet)
    return SimpleNamespace(db=db, platform_seen=seen, tenant=uuid.uuid4())


def deliver(event, data):
    body = json.dumps({"event": event, "data": data}).encode()

    class Req:
        async def body(self):
            return body
    sig = hmac.new(SECRET.encode(), body, hashlib.sha512).hexdigest()
    return asyncio.run(paystack.paystack_webhook(Req(), x_paystack_signature=sig))


def test_platform_invoice_events_stop_at_the_platform_handler(env):
    assert deliver("charge.success", {"reference": "ODP-2026-000001", "amount": 100, "currency": "ZAR", "id": 1}) == {"status": "paid"}
    assert env.platform_seen == [("charge.success", "ODP-2026-000001")]
    with env.db() as s:
        assert s.query(Payment).count() == 0 and s.query(PayoutWallet).count() == 0


def test_every_event_is_offered_to_the_platform_first_and_then_reaches_its_owner(env):
    with env.db() as s:
        s.add(PayoutFunding(tenant_id=env.tenant, reference="fund-abc123", amount_cents=300_000))
    out = deliver("charge.success", {"reference": "fund-abc123", "amount": 300_000, "currency": "ZAR", "id": "c1",
                                     "metadata": {"kind": "payout_funding", "tenant_id": str(env.tenant)}})
    assert out == {"status": "accepted"} and env.platform_seen[-1] == ("charge.success", "fund-abc123")
    with env.db() as s:
        assert s.query(PayoutWallet).one().balance_cents == 300_000


def test_transfer_events_update_payout_items_and_return_the_money(env):
    with env.db() as s:
        s.add(PayoutWallet(tenant_id=env.tenant, balance_cents=0))
        b = PayoutBatch(tenant_id=env.tenant, kind="payroll", source_id="r1", period="2026-03", total_cents=50_000, fee_cents=3_000)
        s.add(b)
        s.flush()
        s.add(PayoutItem(batch_id=b.id, tenant_id=env.tenant, kind="payroll", item_ref="s1", recipient_code="RCP", amount_cents=50_000,
                         fee_cents=3_000, reference="payroll-s1", status="processing"))
    assert deliver("transfer.failed", {"id": 5, "reference": "payroll-s1", "status": "failed", "reason": "Account closed"}) == {"status": "accepted"}
    with env.db() as s:
        assert s.query(PayoutItem).one().status == "failed" and s.query(PayoutWallet).one().balance_cents == 53_000


def test_refund_and_dispute_events_reach_their_handlers(env):
    credit_id = uuid.uuid4()
    with env.db() as s:
        s.add(CustomerCredit(id=credit_id, tenant_id=env.tenant, customer_id=uuid.uuid4(), amount_zar=Decimal("100.00"), kind="overpayment",
                             reference="ref-x"))
        s.add(GatewayRefund(tenant_id=env.tenant, credit_id=credit_id, customer_id=uuid.uuid4(), method="paystack", amount_cents=10_000,
                            transaction_reference="ref-x", status="pending", paystack_refund_id="77"))
    assert deliver("refund.processed", {"id": 77, "status": "processed", "transaction_reference": "ref-x"}) == {"status": "accepted"}
    assert deliver("charge.dispute.create", {"id": 9, "status": "pending", "transaction": {"reference": "ref-x", "amount": 10_000}}) == {"status": "accepted"}
    with env.db() as s:
        assert s.query(GatewayRefund).one().status == "processed" and s.query(GatewayLiability).count() == 1
        assert s.query(GatewayDispute).one().paystack_dispute_id == "9"
    assert [e for e, _ in env.platform_seen] == ["refund.processed", "charge.dispute.create"]


def test_unsigned_or_wrongly_signed_events_are_refused_before_any_handler(env):
    from fastapi import HTTPException

    class Req:
        async def body(self):
            return b'{"event":"transfer.success","data":{"reference":"x"}}'
    with pytest.raises(HTTPException) as e:
        asyncio.run(paystack.paystack_webhook(Req(), x_paystack_signature="deadbeef"))
    assert e.value.status_code == 401 and env.platform_seen == []
