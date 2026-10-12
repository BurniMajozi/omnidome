import uuid
import asyncio
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from services.admin.tests.test_iam import client, sb, make_tenant, platform, as_user, add_user, q
from services.admin.tests.test_commercial_usage import transaction
from services.common.platform_demo_access import check_calendar_write
from fastapi import HTTPException
import pytest


@pytest.fixture(autouse=True)
def fresh_submission_window():
    from services.admin.platform_onboarding import limiter
    limiter._requests.clear()


def test_public_intake_private_admin_and_demo_collision(client,monkeypatch):
    monkeypatch.setenv("INTERNAL_AUTH_SECRET","platform-demo-test-secret-at-least-32-characters")
    t=make_tenant(client);host,_=add_user(t,["owner"])
    body={"name":"Test visitor","company":"Booking regression","email":f"demo-{uuid.uuid4().hex}@example.com"}
    assert client.post("/public/platform/trial-request",json=body).status_code==200
    assert client.get("/platform/onboarding",headers=as_user(t,host)).status_code==403
    cfg={"enabled":True,"host_id":str(host),"timezone":"Africa/Johannesburg","start_hour":9,"end_hour":16}
    response=client.put("/platform/onboarding/demo",json=cfg,headers=platform(t))
    assert response.status_code==200,response.text
    day=datetime.now(timezone.utc).date()+timedelta(days=4)
    while day.weekday()>4:day+=timedelta(days=1)
    available=client.get(f"/public/platform/demo?day={day.isoformat()}").json()["slots"]
    assert len(available)>1
    body.update(starts_at=available[0],request_key=str(uuid.uuid4()))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda key:client.post("/public/platform/demo/book",json={**body,"request_key":key}),[body["request_key"],str(uuid.uuid4())]))
    assert sorted(r.status_code for r in results)==[200,409]
    booked=next(r.json() for r in results if r.status_code==200)
    async def calendar_conflict(db):
        return await check_calendar_write(db,host,datetime.fromisoformat(booked["starts_at"]),datetime.fromisoformat(booked["starts_at"])+timedelta(minutes=30))
    with pytest.raises(HTTPException) as conflict:
        asyncio.run(transaction(calendar_conflict))
    assert conflict.value.status_code==409
    manage={"id":booked["id"],"token":booked["token"]}
    assert client.post("/public/platform/demo/manage",json={**manage,"token":"x"*64}).status_code==404
    # A failed move keeps the old booking and reminders intact.
    assert client.post("/public/platform/demo/manage",json={**manage,"starts_at":"2020-01-01T12:00:00Z"}).status_code==409
    assert q("SELECT status FROM platform_demo_bookings WHERE id=:i",i=booked["id"])[0][0]=="confirmed"
    moved=client.post("/public/platform/demo/manage",json={**manage,"starts_at":available[-1]})
    assert moved.status_code==200,moved.text
    assert client.post("/public/platform/demo/manage",json=manage).status_code==404
    manage["token"]=moved.json()["token"]
    assert client.post("/public/platform/demo/manage",json=manage).json()["status"]=="cancelled"
    assert client.post("/public/platform/demo/manage",json=manage).json()["status"]=="cancelled"
    # Leave shared test configuration disabled for other tests.
    client.put("/platform/onboarding/demo",json={**cfg,"enabled":False},headers=platform(t))


def test_trial_invitation_starts_clock_after_verified_acceptance(client,sb,monkeypatch):
    from services.admin import iam
    sent=[]
    async def send(to,subject,html):sent.append(to);return "test-message"
    monkeypatch.setattr(iam.agentmail,"is_configured",lambda:True)
    monkeypatch.setattr(iam.agentmail,"send_email",send)
    body={"name":"Invited owner","company":"Trial onboarding","email":f"trial-{uuid.uuid4().hex}@example.com"}
    assert client.post("/public/platform/trial-request",json=body).status_code==200
    ident=q("SELECT id FROM platform_trial_requests WHERE email=:e",e=body["email"])[0][0]
    response=client.post(f"/platform/onboarding/requests/{ident}/provision",headers=platform())
    assert response.status_code==200,response.text
    tenant=response.json()["tenant_id"]
    invite=response.json()["owner_invite"]["invite_id"]
    assert q("SELECT settings->'platform_trial'->>'status' FROM tenants WHERE id=:t",t=tenant)[0][0]=="pending"
    assert client.post(f"/platform/onboarding/requests/{ident}/provision",headers=platform()).json()["duplicate"] is True
    assert sent==[body["email"]]
    claim=client.post("/invites/claim",json={"invite_id":invite,"email":body["email"],"code":"12345678","password":"a-long-test-password"})
    assert claim.status_code==200,claim.text
    trial=q("SELECT settings->'platform_trial' FROM tenants WHERE id=:t",t=tenant)[0][0]
    assert trial["status"]=="active"
    assert datetime.fromisoformat(trial["ends_at"])-datetime.fromisoformat(trial["starts_at"])==timedelta(days=14)


def test_demo_request_works_without_calendar_and_is_private(client):
    body={"name":"Demo visitor","company":"Demo request test","email":f"request-{uuid.uuid4().hex}@example.com"}
    first=client.post("/public/platform/demo/request",json=body)
    assert first.status_code==200,first.text
    assert first.json()["status"]=="requested"
    assert client.post("/public/platform/demo/request",json=body).status_code==200
    assert q("SELECT count(*) FROM platform_demo_requests WHERE email=:e",e=body["email"])[0][0]==1
    t=make_tenant(client);member,_=add_user(t,["org_user"])
    ident=q("SELECT id FROM platform_demo_requests WHERE email=:e",e=body["email"])[0][0]
    assert client.post(f"/platform/onboarding/demo-requests/{ident}/contacted",headers=as_user(t,member)).status_code==403
    response=client.post(f"/platform/onboarding/demo-requests/{ident}/contacted",headers=platform(t))
    assert response.status_code==200,response.text
    assert response.json()["status"]=="contacted"


def test_demo_requests_are_rate_limited(client):
    body={"name":"Rate limit test","company":"Demo request test","email":f"limit-{uuid.uuid4().hex}@example.com"}
    for _ in range(10):
        assert client.post("/public/platform/demo/request",json=body).status_code==200
    assert client.post("/public/platform/demo/request",json=body).status_code==429
