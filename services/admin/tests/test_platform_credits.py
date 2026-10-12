"""PostgreSQL integration: wallet isolation, verified delivery, reservations and preferences."""
import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from services.admin.tests.test_iam import client,sb,make_tenant,platform,as_user,add_user,q
from services.admin.tests.test_tenant_pricing import gateway,save,choice
from services.admin.tests.test_commercial_usage import transaction
from services.common import platform_credits,platform_commerce,platform_usage
from services.billing.routes import platform_checkout as broker


@pytest.fixture
def published(client):
    # Publishing is audited against the Platform Owner's actual tenant.
    headers=platform(make_tenant(client))
    old=client.get('/pricing/credits',headers=headers).json()
    config={"enabled":True,"price_per_credit_zar":"0.25","operation_credit_limit":50}
    assert client.put('/pricing/credits',json=config,headers=headers).status_code==200
    yield config
    assert client.put('/pricing/credits',json={k:old[k] for k in config},headers=headers).status_code==200


def purchase(client,tenant,user,amount="50.00",key=None):
    return client.post(f'/tenants/{tenant}/usage/topups',headers=as_user(tenant,user),json={"amount_zar":amount,"idempotency_key":key or str(uuid.uuid4())})


def payment(order):
    return {"status":"success","currency":"ZAR","amount":order['quote']['amount_cents'],"reference":order['reference'],"id":123}


def test_scopes_amount_and_price_tampering(client,published):
    t=make_tenant(client);owner,_=add_user(t,['owner']);member,_=add_user(t,['org_user'])
    assert purchase(client,t,member).status_code==403
    assert purchase(client,make_tenant(client),owner).status_code==403
    assert purchase(client,t,owner,"49.99").status_code==422
    assert client.put('/pricing/credits',json=published,headers=as_user(t,owner)).status_code==403
    payload={"amount_zar":"50.00","idempotency_key":str(uuid.uuid4()),"credits":999999}
    assert client.post(f'/tenants/{t}/usage/topups',headers=as_user(t,owner),json=payload).status_code==422
    assert client.get(f'/tenants/{t}/usage/logs',headers=as_user(t,member)).status_code==403


def test_topup_is_idempotent_and_does_not_replace_plan(client,published,gateway,monkeypatch):
    t=make_tenant(client);u,_=add_user(t,['org_admin']);save(client,t,choice('growth'))
    before=q('SELECT settings FROM tenants WHERE id=:t',t=t)[0][0]
    key=str(uuid.uuid4());response=purchase(client,t,u,"73.49",key)
    assert response.status_code==201,response.text
    order=response.json()
    assert order['quote']['credit_topup']['credits']==293
    assert purchase(client,t,u,"73.49",key).json()['id']==order['id']
    assert purchase(client,t,u,"50.00",key).status_code==409
    calls=[]
    async def provider(method,path,body=None):
        calls.append(path)
        if path=='/transaction/initialize': return {"authorization_url":"https://checkout.paystack.com/topup","reference":body['reference']}
        return payment(order)
    monkeypatch.setattr(broker,'provider',provider)
    first=gateway.post('/platform-checkout/initialize',headers=as_user(t,u),json={"order_id":order['id']})
    assert first.status_code==200,first.text
    assert calls==['/transaction/initialize']
    result=gateway.post('/platform-checkout/verify',headers=as_user(t,u),json={"order_id":order['id']})
    assert result.status_code==200,result.text
    assert gateway.post('/test-event',json={"event":"charge.success","data":payment(order)}).status_code==200
    assert q('SELECT count(*),sum(credits) FROM platform_credit_entries WHERE tenant_id=:t',t=t)[0]==(1,293)
    assert q('SELECT settings FROM tenants WHERE id=:t',t=t)[0][0]==before
    assert client.get(f'/tenants/{t}/usage',headers=as_user(t,u)).json()['credit_wallet']['purchased_remaining']==293
    document=client.get(f"/tenants/{t}/pricing/orders/{order['id']}/document",headers=as_user(t,u))
    assert document.status_code==200 and 'Quantity' in document.text and 'do not expire' in document.text
    with pytest.raises(Exception): q('UPDATE platform_credit_entries SET credits=99999 WHERE order_id=:o',o=order['id'])


def test_concurrent_work_cannot_reserve_the_same_balance(client,published):
    t=make_tenant(client);save(client,t,choice('starter')) # 50 included
    def start():
        async def run(db): return await platform_usage.start_operation(db,t,uuid.uuid4(),'research',panel='portal')
        try: asyncio.run(transaction(run));return 'reserved'
        except HTTPException as error: return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:start(),range(2)))
    assert sorted(results,key=str)==sorted(['reserved',402],key=str)
    assert q("SELECT sum(reserved_credits) FROM platform_usage_operations WHERE tenant_id=:t AND status='running'",t=t)[0][0]==50


def test_failed_work_releases_reservation_and_logs_are_scoped(client,published):
    t=make_tenant(client);u,_=add_user(t,['owner']);save(client,t,choice('starter'))
    op=uuid.uuid4()
    async def run(db):
        policy=await platform_usage.start_operation(db,t,op,'research',panel='portal')
        await platform_usage.finish_operation(db,t,op,policy,'research',tokens=300000,eligible=False,status='incomplete')
    asyncio.run(transaction(run))
    meter=client.get(f'/tenants/{t}/usage',headers=as_user(t,u)).json()
    assert meter['credit_wallet']['reserved']==0 and meter['credit_wallet']['available']==50
    logs=client.get(f'/tenants/{t}/usage/logs?panel=portal',headers=as_user(t,u)).json()
    assert logs['total']==1 and logs['rows'][0]['credits']==0
    assert client.get(f'/tenants/{make_tenant(client)}/usage/logs',headers=as_user(t,u)).status_code==403


def test_paid_credits_are_spent_once_after_included_allowance(client,published):
    t=make_tenant(client);u,_=add_user(t,['owner']);save(client,t,choice('starter'))
    order=purchase(client,t,u).json()
    async def run(db):
        await platform_commerce.paid(db,order,payment(order))
        for _ in range(2):
            op=uuid.uuid4();policy=await platform_usage.start_operation(db,t,op,'research',panel='portal')
            await platform_usage.finish_operation(db,t,op,policy,'research',tokens=999999,eligible=True,status='completed')
            await platform_usage.finish_operation(db,t,op,policy,'research',tokens=999999,eligible=True,status='completed')
    asyncio.run(transaction(run))
    meter=client.get(f'/tenants/{t}/usage',headers=as_user(t,u)).json()
    assert meter['used']==100 and meter['credit_wallet']['purchased_remaining']==150
    assert meter['credit_wallet']['available']==150 # Do not subtract purchased usage twice.
    assert meter['by_panel'][0]['panel']=='portal' and meter['by_panel'][0]['credits']==100
    assert q('SELECT count(*) FROM platform_credit_entries WHERE tenant_id=:t AND credits<0',t=t)[0][0]==1


def test_delivery_preferences_are_explicitly_pending(client):
    t=make_tenant(client);u,_=add_user(t,['owner'])
    preferences={name:{"mode":"auto_recharge","recharge_zar":100,"monthly_cap_zar":500} for name in ('voice','email')}
    response=client.put(f'/tenants/{t}/usage/delivery-controls',headers=as_user(t,u),json=preferences)
    assert response.status_code==200,response.text
    assert response.json()['preferences']==preferences
    assert all(not c['auto_recharge_active'] and not c['prepaid_enforced'] for c in response.json()['capabilities'].values())
    assert client.put(f'/tenants/{make_tenant(client)}/usage/delivery-controls',headers=as_user(t,u),json=preferences).status_code==403
