"""Review regressions against PostgreSQL, with Paystack replaced by a fake."""
import json
import uuid
from datetime import datetime,timedelta,timezone
import pytest
from services.admin.tests.test_iam import client,sb,make_tenant,platform,as_user,add_user,q
from services.admin.tests.test_tenant_pricing import gateway,issue,choice
from services.billing.routes import platform_checkout as broker


def test_supplier_permissions_and_frozen_invoice(client):
    t=make_tenant(client);u,_=add_user(t,["org_admin"])
    order=issue(client,t,u,choice("growth")).json()
    supplier=client.get("/pricing/supplier",headers=platform()).json()
    assert supplier["vat_registered"] is False
    assert "9 Short Road" in supplier["address"]
    assert client.put("/pricing/supplier",json=supplier,headers=as_user(t,u)).status_code==403
    registered={**supplier,"vat_registered":True,"vat_number":"4123456789"}
    try:
        assert client.put("/pricing/supplier",json=registered,headers=platform(t)).status_code==200
        preview=client.post("/pricing/quote",json=choice("growth")).json()
        assert preview["total_zar"]=="599.00" and preview["vat_zar"]=="78.13"
        frozen=q("SELECT quote FROM platform_orders WHERE id=:id",id=order["id"])[0][0]
        assert frozen["vat_zar"]=="0.00" and frozen["invoice_details"]["supplier"]["vat_registered"] is False
        document=client.get(f"/tenants/{t}/pricing/orders/{order['id']}/document",headers=as_user(t,u))
        assert document.status_code==200 and "9 Short Road" in document.text and "Tax invoice" not in document.text
        with pytest.raises(Exception,match="Frozen platform invoice"):
            q("UPDATE platform_orders SET quote='{}'::jsonb WHERE id=:id",id=order["id"])
    finally:
        assert client.put("/pricing/supplier",json=supplier,headers=platform(t)).status_code==200


def test_prorated_subscription_keeps_full_renewal_price(client,gateway,monkeypatch):
    t=make_tenant(client);u,_=add_user(t,["org_admin"])
    old=issue(client,t,u,choice()).json()
    async def pay_old(*args,**kwargs):return {"status":"success","amount":old["quote"]["amount_cents"],"currency":"ZAR","reference":old["reference"]}
    monkeypatch.setattr(broker,"provider",pay_old)
    headers=as_user(t,u)
    assert gateway.post("/platform-checkout/verify",json={"order_id":old["id"]},headers=headers).json()["status"]=="paid"
    settings=q("SELECT settings FROM tenants WHERE id=:t",t=t)[0][0]
    now=datetime.now(timezone.utc)
    settings["platform_pricing"].update(period_start=(now-timedelta(days=15)).isoformat(),period_end=(now+timedelta(days=15)).isoformat())
    q("UPDATE tenants SET settings=CAST(:s AS jsonb) WHERE id=:t",t=t,s=json.dumps(settings))
    changed=issue(client,t,u,choice("enterprise"),intent="subscription")
    assert changed.status_code==201,changed.text
    order=changed.json();calls=[]
    assert order["quote"]["net_zar"]=="7750.00"
    async def provider(method,path,body=None):
        calls.append((method,path,body))
        if path=="/plan":return {"plan_code":"PLN_"+uuid.uuid4().hex}
        if path=="/transaction/initialize":return {"reference":body["reference"],"authorization_url":"https://checkout.paystack.com/review"}
        if path.startswith("/transaction/verify/"):return {"status":"success","amount":order["quote"]["amount_cents"],"currency":"ZAR","reference":order["reference"],"authorization":{"reusable":True,"authorization_code":"AUTH_test"},"customer":{"customer_code":"CUS_test"}}
        if path=="/subscription":return {"subscription_code":"SUB_"+uuid.uuid4().hex,"email_token":"test-token"}
        return {}
    monkeypatch.setattr(broker,"provider",provider)
    body={"order_id":order["id"]}
    assert gateway.post("/platform-checkout/initialize",json=body,headers=headers).status_code==200
    assert calls[0][2]["amount"]==950000 and calls[1][2]["amount"]==775000 and "plan" not in calls[1][2]
    result=gateway.post("/platform-checkout/verify",json=body,headers=headers)
    assert result.status_code==200,result.text
    assert result.json()["subscription_status"]=="active"
    assert any(path=="/subscription" and body.get("start_date") for _,path,body in calls)
    assert q("SELECT quote FROM platform_subscriptions WHERE order_id=:id",id=order["id"])[0][0]["amount_cents"]==950000


def test_invalid_bundle_replay_is_validation_error(client):
    t=make_tenant(client);u,_=add_user(t,["org_admin"]);key=str(uuid.uuid4())
    assert issue(client,t,u,choice(),key=key).status_code==201
    assert issue(client,t,u,choice(modules={"crm":"enterprise"}),key=key).status_code==422


def test_abandoned_usage_sweep_does_not_invent_a_charge(client):
    import asyncio
    from services.admin.tests.test_commercial_usage import transaction
    from services.admin.commercial import sweep_abandoned
    from services.common.platform_usage import start_operation
    t=make_tenant(client)
    async def start(db): return await start_operation(db,t,uuid.uuid4(),"assisted_action")
    asyncio.run(transaction(start))
    q("UPDATE platform_usage_operations SET started_at=now()-interval '3 hours' WHERE tenant_id=:t",t=t)
    asyncio.run(transaction(sweep_abandoned))
    assert q("SELECT status,credits FROM platform_usage_operations WHERE tenant_id=:t",t=t)==[("abandoned",0)]


def test_expired_checkout_gets_fresh_reference_and_old_attempt_stays_verifiable(client,gateway,monkeypatch):
    t=make_tenant(client);u,_=add_user(t,["org_admin"])
    order=issue(client,t,u,choice()).json();attempts=[]
    async def provider(method,path,body=None):
        if path=="/transaction/initialize":
            attempts.append(body["reference"])
            return {"reference":body["reference"],"authorization_url":"https://checkout.paystack.com/review"}
        return {"status":"success","currency":"ZAR","amount":order["quote"]["amount_cents"],"reference":attempts[0]}
    monkeypatch.setattr(broker,"provider",provider)
    headers=as_user(t,u);body={"order_id":order["id"]}
    assert gateway.post("/platform-checkout/initialize",json=body,headers=headers).status_code==200
    assert gateway.post("/platform-checkout/initialize",json=body,headers=headers).status_code==200
    assert len(attempts)==1
    q("UPDATE platform_orders SET checkout_created_at=now()-interval '16 minutes' WHERE id=:id",id=order["id"])
    assert gateway.post("/platform-checkout/initialize",json=body,headers=headers).status_code==200
    assert len(attempts)==2 and attempts[0]!=attempts[1]
    assert gateway.post("/platform-checkout/verify",json=body,headers=headers).json()["status"]=="paid"


def test_owner_repricing_preserves_manual_panel_grants(client):
    from services.admin.tests.test_tenant_pricing import save
    t=make_tenant(client)
    assert save(client,t,choice()).status_code==200
    q("INSERT INTO modules(id,key,name,is_core) VALUES(:id,'custom_reports','Custom reports',false) ON CONFLICT(key) DO NOTHING",id=str(uuid.uuid4()))
    changed=client.put(f"/tenants/{t}/modules",json={"modules":[{"module_name":"custom_reports","enabled":True}]},headers=platform(t))
    assert changed.status_code==200,changed.text
    assert save(client,t,choice("enterprise")).status_code==200
    assert q("SELECT tm.status FROM tenant_modules tm JOIN modules m ON m.id=tm.module_id WHERE tm.tenant_id=:t AND m.key='custom_reports'",t=t)[0][0]=="ENABLED"


def test_credit_funded_downgrade_sets_up_full_price_renewal(client,gateway,monkeypatch):
    import asyncio
    from services.admin.tests.test_commercial_usage import transaction
    from services.common.platform_commerce import create_order
    from services.common.platform_pricing import Selection
    t=make_tenant(client);u,_=add_user(t,["org_admin"])
    old=issue(client,t,u,choice()).json()
    async def provider(method,path,body=None):
        if path=="/plan": return {"plan_code":"PLN_"+uuid.uuid4().hex}
        if path=="/subscription": return {"subscription_code":"SUB_"+uuid.uuid4().hex,"email_token":"token"}
        return {"status":"success","currency":"ZAR","amount":old["quote"]["amount_cents"],"reference":old["reference"],"authorization":{"reusable":True,"authorization_code":"AUTH_test"},"customer":{"customer_code":"CUS_test"}}
    monkeypatch.setattr(broker,"provider",provider)
    headers=as_user(t,u)
    assert gateway.post("/platform-checkout/verify",json={"order_id":old["id"]},headers=headers).json()["status"]=="paid"
    async def issue_credit(db): return await create_order(db,t,u,Selection(bundle="growth"),"subscription",uuid.uuid4())
    order=asyncio.run(transaction(issue_credit))
    assert order["quote"]["amount_cents"]==0
    result=gateway.post("/platform-checkout/settle",json={"order_id":str(order["id"])},headers=headers)
    assert result.status_code==200,result.text
    assert result.json()["subscription_status"]=="active"
    assert q("SELECT quote FROM platform_subscriptions WHERE order_id=:id",id=str(order["id"]))[0][0]["amount_cents"]==59900


def test_owner_paid_plan_edit_is_prorated_and_keeps_paid_deadline(client,gateway,monkeypatch):
    from services.admin.tests.test_tenant_pricing import save
    t=make_tenant(client);u,_=add_user(t,["org_admin"])
    old=issue(client,t,u,choice()).json()
    async def provider(*args,**kwargs):return {"status":"success","currency":"ZAR","amount":old["quote"]["amount_cents"],"reference":old["reference"]}
    monkeypatch.setattr(broker,"provider",provider)
    assert gateway.post("/platform-checkout/verify",json={"order_id":old["id"]},headers=as_user(t,u)).json()["status"]=="paid"
    settings=q("SELECT settings FROM tenants WHERE id=:t",t=t)[0][0];now=datetime.now(timezone.utc)
    settings["platform_pricing"].update(period_start=(now-timedelta(days=15)).isoformat(),period_end=(now+timedelta(days=15)).isoformat())
    q("UPDATE tenants SET settings=CAST(:s AS jsonb) WHERE id=:t",t=t,s=json.dumps(settings))
    changed=save(client,t,choice("enterprise"))
    assert changed.status_code==200,changed.text
    assert changed.json()["order"]["quote"]["net_zar"]=="7750.00"
    active=q("SELECT settings FROM tenants WHERE id=:t",t=t)[0][0]["platform_pricing"]
    assert active["billing_mode"]=="payment" and active["period_end"]==settings["platform_pricing"]["period_end"]
    assert active["active_quote"]["selection"]["bundle"]=="professional"
