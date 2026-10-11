from datetime import datetime, timezone
import pytest
import httpx
from services.common.platform_usage import add_months, credit_charge, policy_for_quote
from services.common.platform_pricing import quote, Selection
from services.common.autumn_client import AutumnClient, AutumnError


def test_calendar_anchor_and_shared_allowance():
    anchor=datetime(2026,1,31,12,tzinfo=timezone.utc)
    assert add_months(anchor,1).day==28
    assert add_months(anchor,2).day==31
    priced=quote(Selection(bundle="professional"))
    assert priced["usage_policy"]["monthly_credits"]==5000
    assert priced["usage_policy"]["mode"]=="shadow"
    custom=quote(Selection(modules={"crm":"professional","sales":"enterprise"}))
    assert custom["usage_policy"]["monthly_credits"]==10000
    assert quote(Selection(bundle="starter"))["usage_policy"]["monthly_credits"]==50
    assert quote(Selection(bundle="growth"))["usage_policy"]["monthly_credits"]==500


def test_weighted_charge_and_legacy_no_implicit_grant():
    policy=quote(Selection(bundle="professional"))["usage_policy"]
    assert credit_charge(policy,"assisted_action",1001)==2
    assert credit_charge(policy,"research",1001)==50
    assert credit_charge(policy,"research",50000,False)==0
    with pytest.raises(ValueError): credit_charge(policy,"made_up")
    assert policy_for_quote({})["monthly_credits"]==0


def test_adapter_rejects_paid_routes_and_keeps_secret_server_side():
    import asyncio
    asyncio.run(adapter_check())


async def adapter_check():
    calls=[]
    def handle(request):
        calls.append(request)
        return httpx.Response(200,json={"allowed":True})
    client=AutumnClient("http://autumn.local","secret",httpx.MockTransport(handle))
    result=await client.call("check",{"customer_id":"tenant_1","feature_id":"omnidome_ai_credits"})
    assert result["allowed"] and calls[0].headers["authorization"]=="Bearer secret"
    with pytest.raises(ValueError): await client.call("billing.attach",{})
    with pytest.raises(AutumnError,match="http_500"):
        await AutumnClient("http://autumn.local","secret",httpx.MockTransport(lambda r:httpx.Response(500,text="secret token leak"))).call("check",{})
