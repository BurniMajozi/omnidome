import asyncio
from decimal import Decimal
import pytest
from fastapi import HTTPException
from services.common.platform_credits import DEFAULT_POLICY,topup_quote
from services.common import platform_commerce


@pytest.mark.parametrize("amount",["50.00","73.49","500.00","100000.00"])
@pytest.mark.parametrize("registered,inclusive",[(False,True),(True,True),(True,False)])
def test_customer_selects_gross_payment_and_invoice_discloses_whole_credits(amount,registered,inclusive):
    config={**DEFAULT_POLICY,"enabled":True,"price_per_credit_zar":"0.29"}
    quote=topup_quote(amount,config,{"vat_registered":registered,"prices_include_vat":inclusive,"rate":0.15})
    assert quote["total_zar"]==amount
    assert Decimal(quote["net_zar"])+Decimal(quote["vat_zar"])==Decimal(amount)
    assert quote["amount_cents"]==int(Decimal(amount)*100)
    units=quote["credit_topup"]["credits"]
    unit=Decimal(quote["credit_topup"]["unit_total_zar"])
    assert units*unit<=Decimal(amount)<(units+1)*unit
    assert quote["lines"][0]["quantity"]==units
    assert quote["period"]=="one-off" and quote["entitlements"]==[]
    if not registered: assert Decimal(quote["vat_zar"])==0


@pytest.mark.parametrize("amount",["0","49.99","100000.01"])
def test_amount_limits_are_server_enforced(amount):
    with pytest.raises(HTTPException) as error:
        topup_quote(amount,{**DEFAULT_POLICY,"enabled":True,"price_per_credit_zar":"0.25"},{"vat_registered":False,"prices_include_vat":True,"rate":0.15})
    assert error.value.status_code==422


def test_unpublished_rates_cannot_be_purchased():
    with pytest.raises(HTTPException) as error:
        topup_quote("50",DEFAULT_POLICY,{"vat_registered":False,"prices_include_vat":True,"rate":0.15})
    assert error.value.status_code==409


@pytest.mark.parametrize("change",[{"status":"pending"},{"currency":"USD"},{"amount":4999}])
def test_payment_mismatch_never_reaches_wallet(monkeypatch,change):
    from services.common import platform_credits
    async def never(*args): raise AssertionError("Unverified payment reached wallet")
    monkeypatch.setattr(platform_credits,"settle",never)
    order={"intent":"credit_topup","reference":"ODP-2026-000001","quote":{"currency":"ZAR","amount_cents":5000}}
    payment={"status":"success","currency":"ZAR","amount":5000,"reference":order["reference"],**change}
    with pytest.raises(HTTPException) as error: asyncio.run(platform_commerce.paid(None,order,payment))
    assert error.value.status_code==409
