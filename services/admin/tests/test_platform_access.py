import asyncio
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from services.admin.tests.test_iam import client, sb, make_tenant, platform, as_user, add_user, q
from services.common.entitlements import EntitlementGuard
from services.common import entitlements
from services.common.platform_access import reserve_write

@asynccontextmanager
async def scope():
    engine=create_async_engine(make_url(os.environ["TEST_DATABASE_URL"]).set(drivername="postgresql+asyncpg"),poolclass=NullPool)
    try:
        async with async_sessionmaker(engine)() as db:
            try: yield db; await db.commit()
            except BaseException: await db.rollback(); raise
    finally: await engine.dispose()

def test_guard_enforces_feature_tiers_and_failed_writes_do_not_use_quota(client, monkeypatch):
    monkeypatch.setenv("AUTH_MODE","header")
    monkeypatch.setenv("AUTH_ENFORCE_MODULES","true")
    monkeypatch.setattr(entitlements,"session_scope",scope)
    t=make_tenant(client); user,_=add_user(t,["org_admin"])
    response=client.put(f"/tenants/{t}/pricing",json={"selection":{"modules":{"portal":"starter"}},"idempotency_key":str(uuid.uuid4())},headers=platform(t))
    assert response.status_code==200,response.text
    guard=EntitlementGuard(module_id="portal-builder"); guard.is_licensed=lambda:True
    app=FastAPI(); app.middleware("http")(guard.middleware)
    @app.post("/api/v1/portal/seo/audit")
    async def seo(): return {"ok":True}
    @app.post("/api/v1/portal/pages")
    async def pages(): return {"ok":True}
    @app.post("/fail")
    async def fail():
        from fastapi import HTTPException
        raise HTTPException(422,"Invalid page")
    with TestClient(app) as c:
        headers=as_user(t,user)
        assert c.post("/api/v1/portal/seo/audit",headers=headers).status_code==403
        assert c.post("/api/v1/portal/pages",headers=headers).status_code==200
        assert c.post("/fail",headers=headers).status_code==422
        assert q("SELECT writes FROM platform_panel_usage WHERE tenant_id=:t",t=t)[0][0]==1
        q("UPDATE tenant_modules SET config=jsonb_set(config,'{writes_per_month}','1') WHERE tenant_id=:t AND module_id=(SELECT id FROM modules WHERE key='portal')",t=t)
        assert c.post("/api/v1/portal/pages",headers=headers).status_code==429
        q("""UPDATE tenants SET billing_status='past_due',settings=jsonb_set(settings,'{platform_pricing}',
          jsonb_build_object('billing_mode','payment','active_quote',jsonb_build_object('net_zar','100.00'),
          'period_end',now()-interval '8 days')) WHERE id=:t""",t=t)
        assert c.post("/api/v1/portal/pages",headers=headers).status_code==402

def test_last_available_write_cannot_be_claimed_by_two_requests(client):
    t=make_tenant(client)
    async def reserve():
        async with scope() as db: return bool(await reserve_write(db,t,"crm",1))
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:asyncio.run(reserve()), range(2)))
    assert sorted(results)==[False,True]
    assert q("SELECT writes FROM platform_panel_usage WHERE tenant_id=:t",t=t)[0][0]==1
