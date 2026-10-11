"""OmniDome fees are quoted EXCLUSIVE of VAT: the 6% / 5.5% / 5% commission is the fee, and 15% VAT is added on top when OmniDome is a
VAT vendor (the shipped default). The tenant pays fee + VAT, receives gross - fee - VAT, and a VAT-vendor tenant claims the VAT as input."""
import asyncio
import os
import sys
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.common.auth import AuthContext  # noqa: E402
from services.billing import finance_posting as fp, platform_tax  # noqa: E402
from services.billing.models_gateway import GatewayCharge, GatewaySettings  # noqa: E402
from services.billing.models_payouts import PayoutItem, PayoutWallet, PayoutWalletEntry  # noqa: E402
from services.billing.models_tax import TaxProfileRow  # noqa: E402
from services.billing.routes import gateway as gw, payouts as po, recon  # noqa: E402
from services.billing.tests import sqlite_harness as h  # noqa: E402

D = Decimal


@pytest.fixture
def env(monkeypatch):
    db = h.make_session_factory()
    h.patch_sessions(monkeypatch, db)
    for mod in (po, recon):
        monkeypatch.setattr(mod, "get_session", db)
    # OmniDome is a VAT vendor at 15% (the shipped default), overriding the conftest default of "unregistered"
    monkeypatch.setattr(platform_tax, "position", lambda session: {"registered": True, "rate": D("0.15")})
    monkeypatch.setattr(po, "_secret", lambda: "sk_test_x")
    tenant = uuid.uuid4()
    return SimpleNamespace(db=db, tenant=tenant, ctx=AuthContext(user_id=uuid.uuid4(), tenant_id=tenant))


def gateway(env):
    with env.db() as s:
        s.add(GatewaySettings(tenant_id=env.tenant, status="active", business_name="A", settlement_bank_code="1",
                              account_last4="1234", subaccount_code="ACCT_t"))


def test_vat_is_added_on_top_of_the_fee_and_everything_kept_is_the_transaction_charge(env):
    gateway(env)
    with env.db() as s:
        out = gw.split_for_charge(s, env.tenant, 115_000, "ref-1")                    # R1,150 at 6% = R69.00 + 15% VAT R10.35
    assert out == {"subaccount": "ACCT_t", "transaction_charge": 7_935, "bearer": "account"}
    with env.db() as s:
        c = s.query(GatewayCharge).one()
        assert c.commission_cents == 6_900 and c.commission_vat_cents == 1_035


def test_preview_shows_fee_vat_and_what_the_tenant_receives(env):
    gateway(env)
    prev = asyncio.run(gw.preview(D("1000"), env.ctx))
    assert prev["commission_zar"] == 60.0 and prev["commission_vat_zar"] == 9.0 and prev["commission_total_zar"] == 69.0
    assert prev["tenant_receives_zar"] == 931.0 and prev["fees_exclude_vat"] is True


def test_a_vat_vendor_tenant_claims_the_vat_on_our_fee_as_input_tax(env):
    gateway(env)
    with env.db() as s:
        s.add(TaxProfileRow(tenant_id=env.tenant, country="ZA", vat_registered=True, vat_number="4123456789", rate_percent=D("15"),
                            prices_include_vat=False, legal_name="Acme", address="1 Main Rd"))
        gw.split_for_charge(s, env.tenant, 115_000, "ref-2")
    with env.db() as s:
        entry = gw.mark_charge_succeeded(s, "ref-2", 3_000)
    assert [(l["account_code"], l["debit"], l["credit"]) for l in entry["lines"]] == [
        ("6950", "69.00", "0.00"), ("1210", "10.35", "0.00"), ("1010", "0.00", "79.35")]


def test_a_non_vendor_tenant_cannot_claim_it_so_the_vat_is_part_of_the_expense(env):
    gateway(env)
    with env.db() as s:
        s.add(TaxProfileRow(tenant_id=env.tenant, country="ZA", vat_registered=False, rate_percent=D("0"), prices_include_vat=True))
        gw.split_for_charge(s, env.tenant, 115_000, "ref-3")
    with env.db() as s:
        entry = gw.mark_charge_succeeded(s, "ref-3", 3_000)
    assert [(l["account_code"], l["debit"], l["credit"]) for l in entry["lines"]] == [("6950", "79.35", "0.00"), ("1010", "0.00", "79.35")]


def test_entry_builder_rejects_nonsense():
    with pytest.raises(ValueError):
        fp.gateway_fee_entry("id", "r", fp.sast_today(), "0")
    with pytest.raises(ValueError):
        fp.gateway_fee_entry("id", "r", fp.sast_today(), "10", "-1")


def test_unregistered_omnidome_adds_no_vat(env, monkeypatch):
    monkeypatch.setattr(platform_tax, "position", lambda session: {"registered": False, "rate": D("0.15")})
    gateway(env)
    with env.db() as s:
        assert gw.split_for_charge(s, env.tenant, 115_000, "ref-4")["transaction_charge"] == 6_900


# ---- recon: the tenant must have received gross - fee - VAT ---------------------------------------------------------------

def charge_obj():
    return GatewayCharge(tenant_id=uuid.uuid4(), reference="r", subaccount_code="ACCT_t", period="2026-03", gross_cents=115_000,
                         commission_cents=6_900, commission_vat_cents=1_035, paystack_fee_cents=3_000, status="succeeded")


def verify(tenant, integration):
    return {"status": "success", "amount": 115_000, "fees": 3_000, "subaccount": {"subaccount_code": "ACCT_t"},
            "fees_split": {"paystack": 3_000, "integration": integration, "subaccount": tenant}}


def test_recon_expects_the_vat_to_have_stayed_with_omnidome():
    ok = recon.evaluate_charge(charge_obj(), verify(107_065, 4_935))              # 115,000 - 6,900 - 1,035 ; 7,935 - 3,000
    assert ok[0] == "ok" and ok[2:] == (107_065, 4_935)
    short = recon.evaluate_charge(charge_obj(), verify(108_100, 3_900))           # tenant got the pre-VAT figure: OmniDome under-collected
    assert short[0] == "mismatch" and "should have received 107065" in short[1] and "VAT 1035" in short[1]


# ---- payouts: the wallet is debited fee + VAT ------------------------------------------------------------------------------

def test_payout_quote_reserve_and_reversal_include_the_vat(env, monkeypatch):
    with env.db() as s:
        po.credit_funding(s, env.tenant, "manual_funding", 2_000_000, "eft-1")
    with env.db() as s:
        q = po.quote(s, env.tenant, 1_000_000)                                    # R10,000 payout
    assert (q["fee_zar"], q["vat_zar"], q["fee_total_zar"], q["required_zar"]) == (600.0, 90.0, 690.0, 10_690.0)

    async def fake(method, path, body=None):
        return {"status": True, "_http_status": 200,
                "data": [{"reference": t["reference"], "transfer_code": "T", "status": "pending"} for t in body["transfers"]]}
    monkeypatch.setattr(po, "_paystack", fake)
    body = po.BatchIn(tenant_id=env.tenant, kind="payroll", source_id="r", items=[
        po.PayoutItemIn(item_ref="a", recipient_code="RCP_1", amount_zar=D("6000.00")),
        po.PayoutItemIn(item_ref="b", recipient_code="RCP_2", amount_zar=D("4000.00"))])
    with env.db() as s:
        b, items = po.create_batch(s, body)
        assert (b.fee_cents, b.fee_vat_cents) == (60_000, 9_000)
        assert sum(i.fee_vat_cents for i in items) == 9_000 and sum(i.fee_cents for i in items) == 60_000
        bid = b.id
    asyncio.run(po.execute_batch(bid))
    with env.db() as s:
        assert s.query(PayoutWallet).one().balance_cents == 2_000_000 - 1_000_000 - 69_000
        item = s.query(PayoutItem).filter_by(item_ref="a").one()
        po.settle_item(s, item, "failed", "bounced")                              # R6,000 fails: amount + its fee + its VAT come back
    with env.db() as s:
        w = s.query(PayoutWallet).one()
        assert w.balance_cents == 2_000_000 - 400_000 - (69_000 - 41_400)
        assert sum(e.amount_cents for e in s.query(PayoutWalletEntry)) == w.balance_cents
