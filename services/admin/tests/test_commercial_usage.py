import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
import pytest
from services.admin.tests.test_iam import client,sb,make_tenant,platform,as_user,add_user,q
from services.admin.tests.test_tenant_pricing import save,choice
from services.common.platform_usage import append_cost, start_operation, finish_operation
from services.common.autumn_worker import reconcile
from services.common.autumn_client import AutumnError


async def transaction(fn):
    engine=create_async_engine(make_url(os.environ["TEST_DATABASE_URL"]).set(drivername="postgresql+asyncpg"),poolclass=NullPool)
    try:
        async with async_sessionmaker(engine)() as db:
            value=await fn(db)
            await db.commit()
            return value
    finally: await engine.dispose()


def test_member_scope_owner_only_costs_and_frozen_policy(client):
    tenant=make_tenant(client);member,_=add_user(tenant,["org_user"])
    assert save(client,tenant,choice()).status_code==200
    response=client.get(f"/tenants/{tenant}/usage",headers=as_user(tenant,member))
    assert response.status_code==200,response.text
    assert response.json()["policy"]["monthly_credits"]==5000
    assert response.json()["charges_enabled"] is False
    assert client.get(f"/tenants/{make_tenant(client)}/usage",headers=as_user(tenant,member)).status_code==403
    assert client.get(f"/tenants/{tenant}/usage/costs",headers=as_user(tenant,member)).status_code==403
    override={"monthly_credits":1000,"reason":"Controlled pilot allowance","expires_at":(datetime.now(timezone.utc)+timedelta(days=5)).isoformat()}
    assert client.put(f"/tenants/{tenant}/usage/policy",json=override,headers=as_user(tenant,member)).status_code==403
    changed=client.put(f"/tenants/{tenant}/usage/policy",json=override,headers=platform(tenant))
    assert changed.status_code==200
    with pytest.raises(Exception):
        q("UPDATE platform_usage_policy_versions SET reason='changed' WHERE id=:id",id=changed.json()["version"])
    assert q("SELECT quote FROM platform_orders WHERE tenant_id=:t",t=tenant)[0][0]["usage_policy"]["monthly_credits"]==5000
    assert client.get(f"/tenants/{tenant}/usage",headers=platform(tenant)).json()["policy"]["monthly_credits"]==1000


def test_cost_events_immutable_unknown_not_zero_and_completion_dedup(client):
    tenant=make_tenant(client);save(client,tenant,choice())
    operation=uuid.uuid4();event=uuid.uuid4()
    async def run(db):
        policy=await start_operation(db,tenant,operation,"research")
        await append_cost(db,tenant=tenant,operation=operation,category="research",provider="search",quantity=1,unit="calls",event_id=event,metadata={"secret":"hidden","model":"test"})
        await append_cost(db,tenant=tenant,operation=operation,category="research",provider="search",quantity=1,unit="calls",event_id=event)
        await finish_operation(db,tenant,operation,policy,"research",tokens=1000,eligible=True,status="completed")
        await finish_operation(db,tenant,operation,policy,"research",tokens=1000,eligible=True,status="completed")
    asyncio.run(transaction(run))
    rows=q("SELECT amount,source,metadata FROM platform_cost_events WHERE id=:id",id=str(event))
    assert len(rows)==1 and rows[0][0] is None and rows[0][1]=="unknown" and "secret" not in rows[0][2]
    with pytest.raises(Exception): q("UPDATE platform_cost_events SET amount=0 WHERE id=:id",id=str(event))
    assert q("SELECT credits FROM platform_usage_operations WHERE id=:id",id=str(operation))[0][0]==50
    costs=client.get(f"/tenants/{tenant}/usage/costs",headers=platform(tenant)).json()
    assert costs["margin_available"] is False and costs["costs"][0]["amount"] is None


def test_grant_retry_and_duplicate_do_not_repeat_remote_success(client):
    tenant=make_tenant(client);save(client,tenant,choice())
    class Fake:
        def __init__(self): self.calls=[];self.fail=True
        async def ensure_feature(self): pass
        async def call(self,action,payload):
            self.calls.append((action,payload))
            if action=="balances.create" and self.fail: raise AutumnError("unavailable")
            return {"success":True}
    fake=Fake()
    async def sync(db):
        active=(await db.execute(text("SELECT * FROM platform_usage_entitlements WHERE tenant_id=:t"),{"t":tenant})).mappings().one()
        return await reconcile(db,active,fake)
    with pytest.raises(AutumnError): asyncio.run(transaction(sync))
    fake.fail=False
    assert asyncio.run(transaction(sync))=="synced"
    count=len([c for c in fake.calls if c[0]=="balances.create"])
    assert asyncio.run(transaction(sync))=="synced"
    assert len([c for c in fake.calls if c[0]=="balances.create"])==count
    old=[c[1] for c in fake.calls if c[0]=="balances.create"][-1]
    assert old["included_grant"]==5000 and old["expires_at"]>datetime.now(timezone.utc).timestamp()*1000
    assert save(client,tenant,choice("enterprise")).status_code==200
    assert asyncio.run(transaction(sync))=="synced"
    assert any(c[0]=="balances.delete" for c in fake.calls)


def test_override_expiry_and_payment_outbox_are_not_client_controlled(client):
    tenant=make_tenant(client);save(client,tenant,choice())
    bad={"monthly_credits":0,"reason":"Test expired override","expires_at":"2020-01-01T00:00:00Z"}
    assert client.put(f"/tenants/{tenant}/usage/policy",json=bad,headers=platform(tenant)).status_code==422
    bad["expires_at"]=(datetime.now(timezone.utc)+timedelta(days=5)).isoformat();bad["mode"]="enforce"
    assert client.put(f"/tenants/{tenant}/usage/policy",json=bad,headers=platform(tenant)).status_code==422
    assert q("SELECT count(*) FROM platform_usage_outbox WHERE tenant_id=:t",t=tenant)[0][0]==1


def test_remote_conflict_requires_matching_paginated_receipt(client):
    tenant=make_tenant(client);save(client,tenant,choice())
    class Remote:
        def __init__(self): self.payload=None;self.wrong=False;self.pages=[]
        async def ensure_feature(self): pass
        async def call(self,action,payload):
            if action=="balances.create":
                self.payload=payload
                raise AutumnError("http_409")
            if action=="balances.list":
                self.pages.append(payload.get("start_cursor"))
                if not payload.get("start_cursor"):
                    return {"list":[],"has_more":True,"next_cursor":"second"}
                return {"list":[{"id":self.payload["balance_id"],
                    "included_grant":1 if self.wrong else self.payload["included_grant"],
                    "expires_at":self.payload["expires_at"]}],"has_more":False}
            return {}
    remote=Remote()
    async def sync(db):
        active=(await db.execute(text("SELECT * FROM platform_usage_entitlements WHERE tenant_id=:t"),{"t":tenant})).mappings().one()
        return await reconcile(db,active,remote)
    remote.wrong=True
    with pytest.raises(AutumnError,match="grant_conflict"): asyncio.run(transaction(sync))
    remote.wrong=False
    assert asyncio.run(transaction(sync))=="synced"
    assert remote.pages[-2:]==[None,"second"]
