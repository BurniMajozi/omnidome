"""Billing producers -> workflow -> owner bell, against a dedicated PostgreSQL DB."""
import asyncio
import os
import sys
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.pool import NullPool
from services.common import testdb
testdb.use_test_database()
from services.admin.tests.test_iam import client,sb,make_tenant,add_user,q
from services.admin.tests.test_tenant_pricing import save,choice
from services.admin.tests.test_platform_credits import published,purchase,payment
from services.common import platform_billing_events as facts,platform_commerce,platform_usage,event_bus
from services.agent_orchestrator import billing_workflows,workflow_engine,event_triggers
from services.agent_orchestrator.models import Base,Workflow,WorkflowRun,RunStep,AgentApproval


@pytest.fixture
def runtime(monkeypatch,client):
    with testdb.sync_engine().begin() as conn:
        Base.metadata.create_all(conn,tables=[Workflow.__table__,WorkflowRun.__table__,RunStep.__table__,AgentApproval.__table__])
        conn.execute(text("ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS checkpoint jsonb"))
        conn.execute(text("ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS event_id uuid"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_workflow_event ON workflow_runs(workflow_id,event_id)"))
        conn.execute(text(billing_workflows.NOTICE_DDL))
        for statement in billing_workflows.NOTICE_FK_DDL: conn.execute(text(statement))

    @asynccontextmanager
    async def scope():
        engine=create_async_engine(make_url(os.environ["TEST_DATABASE_URL"]).set(drivername="postgresql+asyncpg"),poolclass=NullPool)
        try:
            async with async_sessionmaker(engine,expire_on_commit=False)() as db:
                async with db.begin(): yield db
        finally: await engine.dispose()
    for module in (workflow_engine,event_triggers,billing_workflows):
        monkeypatch.setattr(module,"session_scope",scope)
    async def capture(*args,**kwargs): pass
    monkeypatch.setattr(workflow_engine.memory_capture,"request_in",capture)
    return scope


def event_for(tenant,event_type):
    rows=q("SELECT id,event_type,source,payload FROM domain_events WHERE tenant_id=:t AND event_type=:e ORDER BY created_at DESC LIMIT 1",t=tenant,e=event_type)
    assert rows
    row=rows[0]
    return {"id":str(row[0]),"tenant_id":str(tenant),"type":row[1],"source":row[2],"payload":row[3]}


def test_verified_topup_creates_one_owner_notice_not_a_staff_broadcast(runtime,client,published):
    tenant=make_tenant(client);owner,_=add_user(tenant,["owner"]);staff,_=add_user(tenant,["org_user"])
    assert save(client,tenant,choice()).status_code==200
    asyncio.run(billing_workflows.install(tenant));asyncio.run(billing_workflows.install(tenant))
    assert q("SELECT count(*) FROM workflows WHERE tenant_id=:t",t=tenant)[0][0]==6
    order=purchase(client,tenant,owner).json()
    async def settle():
        async with runtime() as db:
            await platform_commerce.paid(db,order,payment(order))
            await platform_commerce.paid(db,order,payment(order))
    asyncio.run(settle())
    event=event_for(tenant,facts.PREFIX+'credits.topped_up')
    assert q("SELECT count(*) FROM domain_events WHERE tenant_id=:t AND event_type=:e",t=tenant,e=event['type'])[0][0]==1
    asyncio.run(event_triggers.handle_event(event));asyncio.run(event_triggers.handle_event(event))
    notices=q("SELECT recipient_id,body FROM notifications WHERE tenant_id=:t AND source='billing_workflow'",t=tenant)
    assert len(notices)==1 and notices[0][0]==owner and order['reference'] in notices[0][1]
    assert q("SELECT count(*) FROM workflow_runs WHERE tenant_id=:t AND status='succeeded'",t=tenant)[0][0]==1
    run=q("SELECT id FROM workflow_runs WHERE tenant_id=:t",t=tenant)[0][0]
    config=billing_workflows.TEMPLATES[2]['definition']['nodes'][1]['config']
    assert asyncio.run(billing_workflows.send_notice(tenant,run,'owner_notice',config))['notifications_created']==0
    forged={**event,"id":str(uuid.uuid4()),"source":"api"}
    asyncio.run(event_triggers.handle_event(forged))
    assert len(q("SELECT id FROM workflow_runs WHERE tenant_id=:t",t=tenant))==1


def test_credit_alert_bands_are_once_per_period(runtime,client,published):
    tenant=make_tenant(client);add_user(tenant,['owner']);assert save(client,tenant,choice('starter')).status_code==200
    async def consume():
        async with runtime() as db:
            await db.execute(text("UPDATE platform_usage_entitlements SET policy=jsonb_set(policy,'{monthly_credits}','250') WHERE tenant_id=:t"),{"t":str(tenant)})
            for _ in range(5):
                op=uuid.uuid4();policy=await platform_usage.start_operation(db,tenant,op,'research',panel='portal')
                await platform_usage.finish_operation(db,tenant,op,policy,'research',tokens=999999,eligible=True,status='completed')
                await facts.credits_checkpoint(db,tenant)
    asyncio.run(consume())
    exhausted=event_for(tenant,facts.PREFIX+'credits.exhausted')
    assert exhausted['payload']['available']==0
    low=event_for(tenant,facts.PREFIX+'credits.low')
    assert low['payload']['available']==50 and low['payload']['threshold']==50
    assert q("SELECT count(*) FROM domain_events WHERE tenant_id=:t AND event_type=:e",t=tenant,e=exhausted['type'])[0][0]==1


def test_payment_failure_payload_is_sanitised_and_idempotent(runtime,client):
    tenant=make_tenant(client)
    subscription={'tenant_id':tenant,'order_id':uuid.uuid4()}
    provider={'id':1234,'reference':'fake-test-invoice','authorization':{'authorization_code':'SECRET'},'email_token':'SECRET'}
    async def emit():
        async with runtime() as db:
            await facts.payment_failed(db,subscription,provider);await facts.payment_failed(db,subscription,provider)
    asyncio.run(emit())
    row=event_for(tenant,facts.PREFIX+'subscription.payment_failed')
    assert 'SECRET' not in str(row['payload'])
    assert q("SELECT count(*) FROM domain_events WHERE tenant_id=:t",t=tenant)[0][0]==1


def test_concurrent_event_runs_do_not_duplicate_notifications(runtime,client):
    tenant=make_tenant(client);add_user(tenant,['owner']);asyncio.run(billing_workflows.install(tenant))
    item=billing_workflows.TEMPLATES[0]
    event={'id':str(uuid.uuid4()),'tenant_id':str(tenant),'type':item['trigger_event'],'source':facts.SOURCE,'payload':{'available':8}}
    workflow=billing_workflows.workflow_id(tenant,item['key'])
    def run():
        return asyncio.run(workflow_engine.run_workflow(workflow,str(tenant),str(uuid.UUID(int=0)),{'event':event},trigger='event'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:run(),range(2)))
    assert len({r['run_id'] for r in results})==1
    assert len(q("SELECT id FROM notifications WHERE tenant_id=:t AND source='billing_workflow'",t=tenant))==1
    q("DELETE FROM workflows WHERE id=:id",id=workflow)
    assert not q("SELECT run_id FROM workflow_notice_effects WHERE tenant_id=:t",t=tenant)
