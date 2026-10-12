"""Isolated PostgreSQL configuration and identity tests; provider calls are mocked."""
import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from services.common import testdb, llm_routing as routing
from services.common.auth import AuthContext, get_auth_context
from services.agent_orchestrator.routes import llm_console as console

@pytest.fixture
def runtime(monkeypatch):
    testdb.use_test_database()
    @asynccontextmanager
    async def scope(*args):
        engine = create_async_engine(make_url(os.environ['TEST_DATABASE_URL']).set(drivername='postgresql+asyncpg'),poolclass=NullPool)
        try:
            async with async_sessionmaker(engine,expire_on_commit=False)() as db:
                async with db.begin(): yield db
        finally: await engine.dispose()
    monkeypatch.setattr(routing,'session_scope',scope); monkeypatch.setattr(console,'session_scope',scope)
    async def seed():
        async with scope() as db:
            await db.execute(text(routing.DDL)); await db.execute(text(console.TEST_DDL))
            await db.execute(text('DELETE FROM platform_llm_tests')); await db.execute(text('DELETE FROM platform_llm_routing'))
    asyncio.run(seed())
    ctx=AuthContext(user_id=uuid.uuid4(),tenant_id=uuid.uuid4(),roles=['org_admin'])
    app=FastAPI(); app.include_router(console.router, prefix="/console")
    app.dependency_overrides[get_auth_context]=lambda:ctx
    with TestClient(app, base_url="http://testserver/console") as client: yield client,ctx,scope
    asyncio.run(seed())

def test_tenant_cannot_read_write_or_test_global_configuration(runtime):
    client,ctx,_=runtime
    assert client.get('/capabilities').json()=={'platform_owner':False}
    assert client.get('').status_code==403
    assert client.put('',json={'config':routing.defaults()}).status_code==403
    assert client.post('/playground',json={'slot':'basic','prompt':'test'}).status_code==403
    assert client.get('/analytics').status_code==403

def test_owner_save_is_disabled_and_has_no_credentials(runtime,monkeypatch):
    client,ctx,_=runtime; ctx.is_platform_admin=True
    monkeypatch.setenv('OPENROUTER_API_KEY','never-return-this-secret')
    response=client.put('',json={'config':routing.defaults()})
    assert response.status_code==200,response.text
    state=client.get('').json()
    assert state['config']['enabled'] is False
    assert state['keys'][0]['configured'] is True
    assert 'never-return-this-secret' not in json.dumps(state)

def test_untested_profile_cannot_be_enabled(runtime):
    client,ctx,_=runtime; ctx.is_platform_admin=True
    config=routing.defaults(); config['profiles']['basic']['enabled']=True; config['enabled']=True
    assert client.put('',json={'config':config}).status_code==409

def test_verified_configuration_becomes_stale_after_model_edit(runtime):
    client,ctx,scope=runtime; ctx.is_platform_admin=True
    config=routing.defaults()
    async def verify():
        async with scope() as db:
            await db.execute(text('INSERT INTO platform_llm_tests(fingerprint,actor_id) VALUES(:f,:a)'),{'f':console.fingerprint(config['profiles']['basic']),'a':str(ctx.user_id)})
    asyncio.run(verify())
    config['profiles']['basic']['enabled']=True; config['enabled']=True
    assert client.put('',json={'config':config}).status_code==200
    config['profiles']['basic']['model']='different/model:free'
    assert client.put('',json={'config':config}).status_code==409

def test_unknown_tenant_gets_basic_and_cannot_request_paid_model(runtime):
    _,ctx,_=runtime
    config=routing.defaults(); config['enabled']=True; config['profiles']['basic']['enabled']=True
    asyncio.run(routing.save(config,ctx.user_id))
    assert asyncio.run(routing.resolve(str(ctx.tenant_id))) == (config['profiles']['basic']['model'],)
    with pytest.raises(HTTPException) as error: asyncio.run(routing.resolve(str(ctx.tenant_id),'anthropic/paid'))
    assert error.value.status_code==403

def test_free_route_keeps_human_approval_and_skips_verifier(runtime,monkeypatch):
    from services.agent_orchestrator import jev_gate
    monkeypatch.setattr(routing,'free_only',AsyncMock(return_value=True))
    monkeypatch.setattr(jev_gate,'_get_credentials',lambda:('typesafe','fake-test-key','https://invalid.example'))
    monkeypatch.setattr(jev_gate.settings,'jev_gate_enabled',True)
    class Tool:
        mutates=True
        requires_approval=True
    verdict=asyncio.run(jev_gate.evaluate_tool_call('assistant','test_mutation',{},tool=Tool()))
    assert verdict.action=='require_approval' and not verdict.evaluated_by_jev
    verdict=asyncio.run(jev_gate.verify_agent_response('test','draft'))
    assert not verdict.passed and verdict.action=='flag_for_review'

def test_draft_model_can_be_verified_without_changing_active_route(runtime,monkeypatch):
    client,ctx,_=runtime; ctx.is_platform_admin=True
    from services.agent_orchestrator.llm import LLMClient
    from services.agent_orchestrator import commercial_usage
    monkeypatch.setattr(LLMClient,'_chat',AsyncMock(return_value={'content':'test response','model':'draft/model:free','usage':{}}))
    monkeypatch.setattr(console.usage,'record_llm_call',lambda **kw:None)
    monkeypatch.setattr(commercial_usage,'record_model_cost',AsyncMock())
    config=routing.defaults(); asyncio.run(routing.save(config,ctx.user_id))
    profile={'model':'draft/model:free','fallbacks':[],'enabled':False}
    response=client.post('/playground',json={'slot':'basic','prompt':'test','profile':profile})
    assert response.status_code==200,response.text
    assert client.get('').json()['config']==config
    config['profiles']['basic']={**profile,'enabled':True};config['enabled']=True
    assert client.put('',json={'config':config}).status_code==200
