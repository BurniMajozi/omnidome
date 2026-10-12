"""Platform trials against isolated PostgreSQL, without contacting payment providers."""
import json
import uuid
import asyncio
from datetime import datetime, timedelta, timezone
from services.admin.tests.test_iam import client, sb, make_tenant, platform, as_user, add_user, q
from services.admin.tests.test_commercial_usage import transaction
from services.common import platform_usage
from fastapi import HTTPException
import pytest


def start(client,t,user):
    return client.post(f"/tenants/{t}/pricing/trial",headers=as_user(t,user))


def test_trial_once_expiry_retains_members_and_free_seat(client):
    t=make_tenant(client); owner,_=add_user(t,["owner"]); member,_=add_user(t,["org_user"])
    response=start(client,t,owner)
    assert response.status_code==200,response.text
    trial=response.json()
    assert trial["credits"]==50 and trial["seats"]==3
    assert datetime.fromisoformat(trial["ends_at"])-datetime.fromisoformat(trial["starts_at"])==timedelta(days=14)
    assert start(client,t,owner).json()==trial
    q("UPDATE tenants SET settings=jsonb_set(settings,'{platform_trial,ends_at}',CAST(:e AS jsonb)) WHERE id=:t",t=t,e=json.dumps((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()))
    # Reading billing expires the trial without a scheduler or payment callback.
    response=client.get(f"/tenants/{t}/pricing",headers=as_user(t,owner))
    assert response.status_code==200,response.text
    state=response.json()["pricing"]
    assert state["billing_mode"]=="free" and state["active_quote"]["amount_cents"]==0
    assert state["active_quote"]["seats"]==1
    assert len(q("SELECT id FROM users WHERE tenant_id=:t AND is_active=true",t=t))==2
    trial=client.get(f"/tenants/{t}/pricing/trial",headers=as_user(t,owner)).json()
    assert trial["status"]=="expired" and trial["free_user_id"]==str(owner)
    response=client.put(f"/tenants/{t}/pricing/trial/seat",json={"user_id":str(member)},headers=as_user(t,owner))
    assert response.status_code==200,response.text
    assert response.json()["free_user_id"]==str(member)
    assert start(client,t,owner).json()["status"]=="expired"
    assert not q("SELECT id FROM platform_orders WHERE tenant_id=:t",t=t)
    from services.common.platform_credits import window
    active=q("SELECT starts_at,expires_at,policy FROM platform_usage_entitlements WHERE tenant_id=:t",t=t)[0]._mapping
    assert window(active,active["starts_at"]+timedelta(days=65))[2]==50


def test_trial_role_scope_and_paid_plan_protection(client):
    t=make_tenant(client); owner,_=add_user(t,["owner"]); member,_=add_user(t,["org_user"])
    assert start(client,t,member).status_code==403
    assert client.post(f"/tenants/{make_tenant(client)}/pricing/trial",headers=as_user(t,owner)).status_code==403
    body={"selection":{"bundle":"growth","modules":{},"period":"monthly"},"idempotency_key":str(uuid.uuid4())}
    response=client.put(f"/tenants/{t}/pricing",json=body,headers=platform(t))
    assert response.status_code==200,response.text
    assert start(client,t,owner).status_code==409


def test_trial_budget_enforced_with_unpublished_credit_rates(client):
    t=make_tenant(client); owner,_=add_user(t,["owner"])
    old=q("SELECT policy FROM platform_credit_policy WHERE singleton=true")
    q("INSERT INTO platform_credit_policy(singleton,policy) VALUES(true,CAST(:p AS jsonb)) ON CONFLICT(singleton) DO UPDATE SET policy=excluded.policy",p=json.dumps({"enabled":False}))
    try:
        assert start(client,t,owner).status_code==200
        async def first(db):
            return await platform_usage.start_operation(db,t,uuid.uuid4(),"research",panel="portal")
        reserved=asyncio.run(transaction(first))
        assert reserved["reserved_credits"]==50
        with pytest.raises(HTTPException) as error:
            asyncio.run(transaction(first))
        assert error.value.status_code==402
        # The normal settings editor cannot reset or extend a trial.
        result=client.put(f"/tenants/{t}",json={"settings":{"platform_trial":{}}},headers=as_user(t,owner))
        assert result.status_code==403
    finally:
        if old:q("UPDATE platform_credit_policy SET policy=CAST(:p AS jsonb) WHERE singleton=true",p=json.dumps(old[0][0]))
