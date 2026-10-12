"""Real PostgreSQL thread ordering/idempotence; no external model, messages or charges."""
import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from services.common import testdb
from services.common.auth import AuthContext, get_auth_context
from services.agent_orchestrator.routes import jobs
from services.agent_orchestrator.models import Base, AgentJob, AgentJobActivity, AgentTenantBudget, RegisteredAgent
from services.agent_orchestrator.job_conversations import history_from

@pytest.fixture
def runtime(monkeypatch):
    testdb.use_test_database()
    with testdb.sync_engine().begin() as db:
        Base.metadata.create_all(db, tables=[AgentJob.__table__, AgentJobActivity.__table__, AgentTenantBudget.__table__, RegisteredAgent.__table__])
    @asynccontextmanager
    async def scope(*args):
        engine = create_async_engine(make_url(os.environ['TEST_DATABASE_URL']).set(drivername='postgresql+asyncpg'), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                async with db.begin(): yield db
        finally: await engine.dispose()
    monkeypatch.setattr(jobs, 'session_scope', scope)
    monkeypatch.setattr(jobs, 'tenant_cap_reason', AsyncMock(return_value=None))
    tenant, user, root = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async def seed():
        async with scope() as db:
            db.add(AgentJob(id=root, tenant_id=tenant, agent_type='assistant', status='awaiting_review',
                objective='Make a recovery plan for the test account', goal_label='Recovery review',
                result={'final_output':'Previous draft plan'}, checkpoint={'actor_id':str(user), 'history':[
                    {'role':'user','content':'Make a recovery plan'}, {'role':'assistant','content':'Previous draft plan'}]}))
    asyncio.run(seed())
    ctx = AuthContext(user_id=user, tenant_id=tenant, roles=['owner'])
    app = FastAPI(); app.include_router(jobs.router)
    app.dependency_overrides[get_auth_context] = lambda: ctx
    with TestClient(app) as client: yield client, scope, ctx, root
    async def clean():
        async with scope() as db: await db.execute(delete(AgentJob).where(AgentJob.tenant_id==tenant))
    asyncio.run(clean())

def test_followup_keeps_prior_response_and_does_not_copy_spend_or_tools(runtime):
    client, scope, ctx, root = runtime
    result = client.post(f'/jobs/{root}/messages',json={'message':'No, try a shorter version', 'request_key':str(uuid.uuid4()), 'max_cost_usd':1.5})
    assert result.status_code==201,result.text
    child = result.json()
    assert child['estimated_cost_usd']==0 and child['total_steps']==0
    thread=client.get(f'/jobs/{child["id"]}/thread').json()
    assert thread['id']==str(root)
    assert [r['objective'] for r in thread['turns']]==['Make a recovery plan for the test account','No, try a shorter version']
    assert thread['turns'][0]['result']['final_output']=='Previous draft plan'
    async def check():
        async with scope() as db:
            prior=await db.get(AgentJob,root); new=await db.get(AgentJob,uuid.UUID(child['id']))
            assert history_from(prior)[-1]['content']=='Previous draft plan'
            assert new.checkpoint['follow_up'] is True
            assert 'history' not in new.checkpoint # Worker loads the final preceding output at execution.
            assert 'model_calls' not in new.checkpoint
    asyncio.run(check())

def test_concurrent_duplicate_click_is_one_turn_and_other_tenant_is_denied(runtime):
    client, scope, ctx, root=runtime
    body={'message':'Keep the same account; change the wording', 'request_key':str(uuid.uuid4())}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:client.post(f'/jobs/{root}/messages',json=body),range(2)))
    assert all(r.status_code==201 for r in responses)
    assert responses[0].json()['id']==responses[1].json()['id']
    assert len(client.get(f'/jobs/{root}/thread').json()['turns'])==2
    assert client.post(f'/jobs/{root}/messages',json={**body,'message':'Different message'}).status_code==409
    ctx.tenant_id=uuid.uuid4()
    assert client.get(f'/jobs/{root}/thread').status_code==404
    assert client.post(f'/jobs/{root}/messages',json=body).status_code==404

def test_queued_messages_form_one_serial_thread_while_first_turn_is_running(runtime):
    client, scope, ctx, root=runtime
    async def start():
        async with scope() as db: (await db.get(AgentJob,root)).status='running'
    asyncio.run(start())
    first=client.post(f'/jobs/{root}/messages',json={'message':'First direction', 'request_key':str(uuid.uuid4())}).json()
    second=client.post(f'/jobs/{root}/messages',json={'message':'Second direction', 'request_key':str(uuid.uuid4())}).json()
    assert first['status']==second['status']=='queued'
    assert second['parent_job_id']==first['id']
    assert len(client.get(f'/jobs/{root}/thread').json()['turns'])==3

def test_activity_is_separate_from_checkpoint_and_contains_no_arguments(runtime,monkeypatch):
    from services.agent_orchestrator import job_activity, steps
    client, scope, ctx, root=runtime
    monkeypatch.setattr(job_activity,'session_scope',scope)
    async def record():
        tracker=steps.Steps(str(root),str(ctx.tenant_id),str(ctx.user_id))
        ident=tracker.begin('memory','Recalling team memory')
        tracker.end(ident,summary='Completed')
        await tracker.queue.put(None)
        await job_activity.capture_activity(root,ctx.tenant_id,tracker)
    asyncio.run(record())
    detail=client.get(f'/jobs/{root}').json()
    assert detail['activity']['items'][0]['title']=='Recalling team memory'
    assert detail['activity']['items'][0]['status']=='done'
    assert 'meta' not in detail['activity']['items'][0]
    assert detail['result']['final_output']=='Previous draft plan'

def test_worker_continues_with_preceding_answer_and_persists_progress(runtime,monkeypatch):
    from types import SimpleNamespace
    from services.agent_orchestrator import control_plane, long_horizon, job_activity, steps
    client, scope, ctx, root=runtime
    child=client.post(f'/jobs/{root}/messages',json={'message':'Make that response shorter', 'request_key':str(uuid.uuid4())}).json()
    monkeypatch.setattr(control_plane,'session_scope',scope)
    monkeypatch.setattr(job_activity,'session_scope',scope)
    monkeypatch.setattr(control_plane,'monthly_spend',AsyncMock(return_value=0))
    monkeypatch.setattr(control_plane,'daily_spend',AsyncMock(return_value=0))
    async def model(**kwargs):
        state=kwargs['resume_from_checkpoint']
        assert state['history'][-1]['content']=='Previous draft plan'
        assert kwargs['prompt']=='Make that response shorter'
        assert kwargs['context']['draft_only'] is True
        sid=steps.current.get().begin('reasoning','Preparing a shorter answer')
        steps.current.get().end(sid)
        state={**state,'iterations_completed':1,'total_steps':0,'total_tokens':2,
               'history':[*state['history'],{'role':'user','content':kwargs['prompt']},{'role':'assistant','content':'Short revised plan'}]}
        await kwargs['checkpoint_callback'](state,None)
        return SimpleNamespace(status='awaiting_review',checkpoint=state,to_dict=lambda:{'final_output':'Short revised plan'},
            estimated_cost_usd=0,actual_cost_usd=0,total_steps=0,total_tokens=2,stopped_by=None)
    monkeypatch.setattr(long_horizon,'run_long_horizon_agent',model)
    asyncio.run(control_plane.execute_job(uuid.UUID(child['id'])))
    transcript=client.get(f'/jobs/{root}/thread').json()['turns']
    assert transcript[-1]['result']['final_output']=='Short revised plan'
    assert transcript[-1]['activity']['items'][0]['title']=='Preparing a shorter answer'
    assert transcript[0]['result']['final_output']=='Previous draft plan'

def test_worker_does_not_claim_followup_before_preceding_turn_is_resolved(runtime,monkeypatch):
    from services.agent_orchestrator import control_plane
    client, scope, ctx, root=runtime
    monkeypatch.setattr(control_plane,'session_scope',scope)
    child=client.post(f'/jobs/{root}/messages',json={'message':'Next direction', 'request_key':str(uuid.uuid4())}).json()
    async def check():
        for state in ['running','queued','awaiting_hitl','interrupted']:
            async with scope() as db: (await db.get(AgentJob,root)).status=state
            # A queued root may itself be claimed; the dependent child must never be claimed.
            claimed=await control_plane.claim_next_job()
            assert claimed != uuid.UUID(child['id'])
        async with scope() as db: (await db.get(AgentJob,root)).status='paused'
        assert await control_plane.claim_next_job()==uuid.UUID(child['id'])
    asyncio.run(check())
