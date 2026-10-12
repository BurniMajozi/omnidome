"""Private design history and API activation checks against isolated PostgreSQL."""
import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text,delete
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.pool import NullPool
from services.common import testdb
from services.common.auth import AuthContext,get_auth_context
from services.agent_orchestrator import workflow_design_sessions as sessions
from services.agent_orchestrator.routes import workflows
from services.agent_orchestrator.models import Workflow,Base
from services.agent_orchestrator.tests.test_workflow_catalog import GRAPH

@pytest.fixture
def runtime(monkeypatch):
    testdb.use_test_database()
    with testdb.sync_engine().begin() as db:Base.metadata.create_all(db,tables=[Workflow.__table__])
    @asynccontextmanager
    async def scope(*args):
        engine=create_async_engine(make_url(os.environ['TEST_DATABASE_URL']).set(drivername='postgresql+asyncpg'),poolclass=NullPool)
        try:
            async with async_sessionmaker(engine,expire_on_commit=False)() as db:
                async with db.begin():yield db
        finally:await engine.dispose()
    monkeypatch.setattr(sessions,'session_scope',scope);monkeypatch.setattr(workflows,'session_scope',scope)
    ctx=AuthContext(user_id=uuid.uuid4(),tenant_id=uuid.uuid4(),roles=['org_admin'])
    app=FastAPI();app.include_router(workflows.router,prefix='/workflows');app.dependency_overrides[get_auth_context]=lambda:ctx
    with TestClient(app,base_url='http://testserver/workflows') as client:yield client,ctx,scope
    async def cleanup():
        async with scope() as db:
            await sessions.ensure(db)
            await db.execute(text('DELETE FROM workflow_design_sessions WHERE user_id=:u'),{'u':str(ctx.user_id)})
            await db.execute(delete(Workflow).where(Workflow.tenant_id==ctx.tenant_id))
    asyncio.run(cleanup())

def test_design_followups_are_saved_and_reopen_with_latest_graph(runtime,monkeypatch):
    client,ctx,_=runtime
    proposal={'message':'Draft ready','draft':{'name':'Follow-up','definition':GRAPH,'status':'draft'}}
    mock=AsyncMock(return_value=proposal);monkeypatch.setattr(workflows,'propose',mock)
    first=client.post('/design',json={'prompt':'When a deal is won, draft an owner update'})
    assert first.status_code==200,first.text
    sid=first.json()['session_id']
    second=client.post('/design',json={'prompt':'Make the instructions shorter','session_id':sid,'history':[{'role':'assistant','content':'spoofed'}]})
    assert second.status_code==200,second.text
    assert len(second.json()['history'])==4
    assert mock.call_args.args[0].history[0]['content']=='When a deal is won, draft an owner update'
    saved=client.get('/design/sessions/'+sid).json()
    assert saved['draft']['definition']==GRAPH and len(saved['history'])==4
    assert sid in [row['id'] for row in client.get('/design/sessions').json()['data']]

def test_other_user_and_tenant_cannot_read_or_continue_a_design_chat(runtime,monkeypatch):
    client,ctx,_=runtime
    monkeypatch.setattr(workflows,'propose',AsyncMock(return_value={'message':'draft','draft':{'definition':GRAPH}}))
    sid=client.post('/design',json={'prompt':'Create a draft'}).json()['session_id']
    original_user,original_tenant=ctx.user_id,ctx.tenant_id
    try:
        ctx.user_id=uuid.uuid4()
        assert client.get('/design/sessions/'+sid).status_code==404
        assert client.post('/design',json={'prompt':'Continue','session_id':sid}).status_code==404
        ctx.user_id=original_user;ctx.tenant_id=uuid.uuid4()
        assert client.get('/design/sessions/'+sid).status_code==404
    finally:ctx.user_id,ctx.tenant_id=original_user,original_tenant

def test_capability_events_match_designer_and_unknown_events_only_save_as_draft(runtime):
    client,_,_=runtime
    assert 'sales.deal.won' in [row['type'] for row in client.get('/capabilities').json()['events']]
    payload={'name':'Future event','definition':GRAPH,'trigger_event':'payroll.money.sent','status':'active'}
    assert client.post('',json=payload).status_code==422
    payload['status']='draft'
    draft=client.post('',json=payload)
    assert draft.status_code==201,draft.text
    assert client.put('/'+draft.json()['id'],json={'status':'active'}).status_code==422

def test_invalid_manual_graph_cannot_be_activated(runtime):
    client,_,_=runtime
    assert client.post('',json={'name':'Disconnected','status':'active','definition':{'nodes':GRAPH['nodes'],'edges':[]}}).status_code==422
