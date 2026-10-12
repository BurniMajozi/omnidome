"""Tenant pricing against PostgreSQL; providers are replaced, no payments are made."""
import uuid
import os
import pytest
from services.admin.tests.test_iam import client, sb, make_tenant, platform, as_user, add_user, q
from services.billing.routes import platform_checkout as broker
from services.common.db import get_async_session
from fastapi import FastAPI
from fastapi.testclient import TestClient


def choice(bundle="professional", **extra): return {"bundle":bundle,"modules":{},"period":"monthly",**extra}
def save(client,t,selection):
    return client.put(f"/tenants/{t}/pricing",json={"selection":selection,"idempotency_key":str(uuid.uuid4())},headers=platform(t))
def issue(client,t,user,selection,intent="invoice",key=None):
    return client.post(f"/tenants/{t}/pricing/orders",json={"selection":selection,"intent":intent,"idempotency_key":key or str(uuid.uuid4())},headers=as_user(t,user))


@pytest.fixture
def gateway(client, monkeypatch):
    app=FastAPI(); app.include_router(broker.router)
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.engine import make_url
    from sqlalchemy.pool import NullPool
    async def isolated_session():
        engine=create_async_engine(make_url(os.environ["TEST_DATABASE_URL"]).set(drivername="postgresql+asyncpg"),poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as db:
                try: yield db; await db.commit()
                except Exception: await db.rollback(); raise
        finally: await engine.dispose()
    app.dependency_overrides[get_async_session]=isolated_session
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def scope(*args,**kwargs):
        async for db in isolated_session(): yield db
    monkeypatch.setattr(broker,"session_scope",scope)
    @app.post("/test-event")
    async def event(body: dict):
        return {"status":await broker.handle_event(body["event"],body["data"])}
    monkeypatch.setenv("AUTH_MODE", "header")
    with TestClient(app) as c: yield c


def test_pricing_provisioning_and_member_inheritance(client):
    t=make_tenant(client); user,_=add_user(t,["org_user"])
    res=save(client,t,choice()); assert res.status_code==200,res.text
    rows=client.get(f"/tenants/{t}/modules",headers=as_user(t,user))
    assert rows.status_code==200,rows.text
    enabled={r["module_name"] for r in rows.json() if r["enabled"]}
    assert {"crm","support","billing","portal"} <= enabled
    assert "network" not in enabled and "inventory" in enabled
    assert client.get(f"/tenants/{make_tenant(client)}/modules",headers=as_user(t,user)).status_code==403
    assert client.put(f"/tenants/{t}/pricing",json={"selection":choice(),"idempotency_key":str(uuid.uuid4())},headers=as_user(t,user)).status_code==403


def test_free_pricing_provisions_all_six_panels_at_enforced_free_limits(client):
    t=make_tenant(client); user,_=add_user(t,["org_user"])
    res=save(client,t,choice("starter")); assert res.status_code==200,res.text
    expected={"crm","support","portal","retention","products","inventory"}
    rows=client.get(f"/tenants/{t}/modules",headers=as_user(t,user))
    assert rows.status_code==200,rows.text
    enabled={r["module_name"] for r in rows.json() if r["enabled"]}
    assert expected <= enabled
    assert "billing" not in enabled and "network" not in enabled
    stored=q("SELECT m.key,tm.config FROM tenant_modules tm JOIN modules m ON m.id=tm.module_id WHERE tm.tenant_id=:t AND m.key=ANY(CAST(:keys AS text[]))",t=t,keys=list(expected))
    assert len(stored)==6
    assert all(row._mapping["config"]["pricing_tier"]=="free" and row._mapping["config"]["writes_per_month"]==100 for row in stored)
    # Removing a basic panel must not keep a bundle that silently adds it back.
    changed=client.put(f"/tenants/{t}/modules",json={"modules":[{"module_name":"inventory","enabled":False}]},headers=platform(t))
    assert changed.status_code==200,changed.text
    pricing=client.get(f"/tenants/{t}/pricing",headers=platform(t)).json()["pricing"]
    assert pricing["selection"]["bundle"] is None
    assert "inventory" not in pricing["selection"]["modules"]
    assert pricing["quote"]["amount_cents"]==0
    changed=client.put(f"/tenants/{t}/modules",json={"modules":[{"module_name":"inventory","enabled":True}]},headers=platform(t))
    assert changed.status_code==200,changed.text
    pricing=client.get(f"/tenants/{t}/pricing",headers=platform(t)).json()["pricing"]
    assert pricing["selection"]["modules"]["inventory"]=="free"
    assert pricing["quote"]["amount_cents"]==0
    assert pricing["quote"]["usage_policy"]["monthly_credits"]==50


def test_admin_cannot_inject_commercial_settings_and_seats_stay_aligned(client):
    t=make_tenant(client); user,_=add_user(t,["org_admin"])
    assert save(client,t,choice()).status_code==200
    assert client.put(f"/tenants/{t}",json={"settings":{"platform_pricing":{}}},headers=as_user(t,user)).status_code==403
    assert client.put(f"/tenants/{t}",json={"settings":{"branding":"x"}},headers=as_user(t,user)).status_code==200
    assert q("SELECT settings FROM tenants WHERE id=:t",t=t)[0][0]["platform_pricing"]
    assert client.put(f"/tenants/{t}/seats",json={"seat_limit":30},headers=platform(t)).status_code==409


def test_order_idempotency_and_checkbox_invoice_revision(client):
    t=make_tenant(client); user,_=add_user(t,["org_admin"])
    assert save(client,t,choice()).status_code==200
    key=str(uuid.uuid4()); first=issue(client,t,user,choice(),key=key)
    assert first.status_code==201,first.text
    assert issue(client,t,user,choice(),key=key).json()["id"]==first.json()["id"]
    assert issue(client,t,user,choice("enterprise"),key=key).status_code==409
    result=client.put(f"/tenants/{t}/modules",json={"modules":[{"module_name":"network","enabled":True}]},headers=platform(t))
    assert result.status_code==200,result.text
    price=client.get(f"/tenants/{t}/pricing",headers=platform(t)).json()
    assert price["pricing"]["quote"]["selection"]["modules"]["network"]=="starter"
    assert price["orders"][0]["quote"]["net_zar"]=="3999.00"
    assert price["orders"][0]["revision"]>first.json()["revision"]


def test_payment_mismatch_stale_selection_duplicate_and_scope(client,gateway,monkeypatch):
    t=make_tenant(client); user,_=add_user(t,["org_admin"])
    order=issue(client,t,user,choice()).json()
    payment={"status":"success","currency":"ZAR","amount":order["quote"]["amount_cents"],"reference":order["reference"],"id":99}
    async def provider(*args,**kwargs): return dict(payment)
    monkeypatch.setattr(broker,"provider",provider)
    path="/platform-checkout/verify"; body={"order_id":order["id"]}
    payment["amount"]-=1
    assert gateway.post(path,json=body,headers=as_user(t,user)).status_code==409
    assert q("SELECT paid_at FROM platform_orders WHERE id=:id",id=order["id"])[0][0] is None
    payment["amount"]+=1
    other=make_tenant(client); otheruser,_=add_user(other,["org_admin"])
    assert gateway.post(path,json=body,headers=as_user(other,otheruser)).status_code==404
    assert save(client,t,choice("enterprise")).status_code==200
    result=gateway.post(path,json=body,headers=as_user(t,user))
    assert result.status_code==200,result.text
    assert result.json()["status"]=="payment_review"
    assert gateway.post(path,json=body,headers=as_user(t,user)).json()["duplicate"] is True
    assert q("SELECT tier FROM tenants WHERE id=:t",t=t)[0][0]=="ENTERPRISE"


def test_verified_payment_enables_only_selected_modules(client,gateway,monkeypatch):
    monkeypatch.setenv("AUTUMN_SYNC_ENABLED","true")
    t=make_tenant(client); user,_=add_user(t,["org_admin"])
    selection={"modules":{"crm":"starter","portal":"professional"},"seats":3,"period":"annually"}
    order=issue(client,t,user,selection).json()
    async def provider(*args,**kwargs): return {"status":"success","currency":"ZAR","amount":order["quote"]["amount_cents"],"reference":order["reference"]}
    monkeypatch.setattr(broker,"provider",provider)
    res=gateway.post("/platform-checkout/verify",json={"order_id":order["id"]},headers=as_user(t,user))
    assert res.status_code==200,res.text
    assert res.json()["status"]=="paid"
    assert q("SELECT count(*) FROM platform_usage_outbox WHERE tenant_id=:t AND action='reconcile'",t=t)[0][0]==1
    assert q("SELECT policy FROM platform_usage_entitlements WHERE tenant_id=:t",t=t)[0][0]["monthly_credits"]==350
    duplicate=gateway.post("/platform-checkout/verify",json={"order_id":order["id"]},headers=as_user(t,user))
    assert duplicate.json()["duplicate"] is True
    assert q("SELECT count(*) FROM platform_usage_outbox WHERE tenant_id=:t AND action='reconcile'",t=t)[0][0]==1
    rows=client.get(f"/tenants/{t}/modules",headers=as_user(t,user)).json()
    enabled={r["module_name"] for r in rows if r["enabled"]}
    assert "crm" in enabled and "portal" in enabled and "billing" not in enabled
    assert client.get(f"/tenants/{t}/pricing/orders/{order['id']}/document",headers=as_user(t,user)).status_code==200
    changed=client.put(f"/tenants/{t}/modules",json={"modules":[{"module_name":"portal","enabled":False}]},headers=platform(t))
    assert changed.status_code==200,changed.text
    assert q("SELECT tier FROM tenants WHERE id=:t",t=t)[0][0]=="STARTER"


def test_creation_uses_pricing_and_seat_downgrade_is_blocked(client):
    domain="price-"+uuid.uuid4().hex[:10]
    res=client.post("/tenants",json={"name":"Pricing test","domain":domain,"pricing_selection":choice("growth")},headers=platform())
    assert res.status_code==201,res.text
    assert res.json()["seat_limit"]==3
    assert res.json()["platform_order"]["quote"]["net_zar"]=="599.00"
    t=uuid.UUID(res.json()["id"])
    add_user(t,["owner"]); add_user(t,["org_user"])
    assert save(client,t,choice("starter")).status_code==409


def test_gateway_bypass_still_requires_authenticated_organisation_admin(client,gateway):
    t=make_tenant(client); user,_=add_user(t,["org_user"])
    for action in ("initialize","verify","cancel"):
        body={"order_id":str(uuid.uuid4())}
        assert gateway.post(f"/platform-checkout/{action}",json=body).status_code==401
        assert gateway.post(f"/platform-checkout/{action}",json=body,headers=as_user(t,user)).status_code==403


def test_subscription_initialize_uses_invoice_amount_and_pending_can_be_cancelled(client,gateway,monkeypatch):
    t=make_tenant(client); user,_=add_user(t,["org_admin"])
    order=issue(client,t,user,choice(),intent="subscription").json()
    calls=[]
    async def provider(method,path,body=None):
        calls.append((method,path,body))
        if path=="/plan": return {"plan_code":"PLN_"+uuid.uuid4().hex}
        if path=="/transaction/initialize": return {"reference":body["reference"],"authorization_url":"https://checkout.paystack.com/test"}
        return {}
    monkeypatch.setattr(broker,"provider",provider)
    body={"order_id":order["id"]}; headers=as_user(t,user)
    result=gateway.post("/platform-checkout/initialize",json=body,headers=headers)
    assert result.status_code==200,result.text
    assert calls[0][2]["amount"]==order["quote"]["amount_cents"]
    assert calls[1][2]["amount"]==order["quote"]["amount_cents"]
    assert calls[1][2]["currency"]=="ZAR"
    assert gateway.post("/platform-checkout/initialize",json=body,headers=headers).status_code==200
    assert len(calls)==2
    second=issue(client,t,user,choice(),intent="subscription").json()
    assert gateway.post("/platform-checkout/initialize",json={"order_id":second["id"]},headers=headers).status_code==200
    assert gateway.post("/platform-checkout/cancel",json=body,headers=headers).status_code==200
    # A new subscription can now be started; the cancelled attempt is retained.
    third=issue(client,t,user,choice(),intent="subscription").json()
    assert gateway.post("/platform-checkout/initialize",json={"order_id":third["id"]},headers=headers).status_code==200
    assert len(q("SELECT order_id FROM platform_subscriptions WHERE tenant_id=:t",t=t))==3


def test_subscription_events_renewal_idempotency_and_cancel(client,gateway,monkeypatch):
    t=make_tenant(client); user,_=add_user(t,["org_admin"])
    order=issue(client,t,user,choice(),intent="subscription").json()
    plan="PLN_"+uuid.uuid4().hex
    payment={"status":"success","currency":"ZAR","amount":order["quote"]["amount_cents"],"reference":order["reference"],"id":1}
    calls=[]
    async def provider(method,path,body=None):
        calls.append(path)
        if path=="/plan": return {"plan_code":plan}
        if path=="/transaction/initialize": return {"reference":body["reference"],"authorization_url":"https://checkout.paystack.com/test"}
        if path.startswith("/transaction/verify/"): return payment
        return {}
    monkeypatch.setattr(broker,"provider",provider)
    headers=as_user(t,user); body={"order_id":order["id"]}
    assert gateway.post("/platform-checkout/initialize",json=body,headers=headers).status_code==200
    assert gateway.post("/platform-checkout/verify",json=body,headers=headers).json()["status"]=="paid"
    code="SUB_"+uuid.uuid4().hex
    created={"event":"subscription.create","data":{"plan":{"plan_code":plan},"subscription_code":code,"email_token":"fake-token"}}
    assert gateway.post("/test-event",json=created).status_code==200
    renewed={"event":"charge.success","data":{**payment,"id":2,"reference":"renewal-"+uuid.uuid4().hex,"plan":{"plan_code":plan}}}
    assert gateway.post("/test-event",json=renewed).json()["status"]=="paid"
    assert gateway.post("/test-event",json=renewed).json()["status"]=="paid"
    assert len(q("SELECT id FROM platform_orders WHERE reference=:r",r=renewed["data"]["reference"]))==1
    assert gateway.post("/platform-checkout/cancel",json=body,headers=headers).status_code==200
    assert "/subscription/disable" in calls
    renewed["data"]["reference"]="late-"+uuid.uuid4().hex
    assert gateway.post("/test-event",json=renewed).json()["status"]=="payment_review"


def test_late_seat_growth_records_payment_for_review(client,gateway,monkeypatch):
    t=make_tenant(client,seat_limit=10); user,_=add_user(t,["org_admin"])
    order=issue(client,t,user,choice("growth")).json()
    for _ in range(3): add_user(t,["org_user"])
    async def provider(*args,**kwargs): return {"status":"success","currency":"ZAR","amount":order["quote"]["amount_cents"],"reference":order["reference"]}
    monkeypatch.setattr(broker,"provider",provider)
    result=gateway.post("/platform-checkout/verify",json={"order_id":order["id"]},headers=as_user(t,user))
    assert result.status_code==200,result.text
    assert result.json()["status"]=="payment_review"
    assert q("SELECT paid_at FROM platform_orders WHERE id=:id",id=order["id"])[0][0] is not None
    assert q("SELECT seat_limit FROM tenants WHERE id=:t",t=t)[0][0]==10


def test_isp_integer_plan_is_not_mistaken_for_platform_subscription(gateway):
    response=gateway.post("/test-event",json={"event":"charge.success","data":{"reference":"ISP-reference","plan":123,"subscription":123}})
    assert response.status_code==200,response.text
    assert response.json()["status"] is None
