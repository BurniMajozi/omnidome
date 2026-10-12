"""Ownership and request deduplication against isolated PostgreSQL; no model or sends."""
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
from services.agent_orchestrator.routes import chat_workflows as routes
from services.agent_orchestrator.models import Base, Workflow, WorkflowRun, AgentApproval, ChatWorkflowAttachment, ChatWorkflowRequest
from services.agent_orchestrator.conversation.models import AgentConversation, AgentMessage, Base as ConversationBase
from services.agent_orchestrator.identity import OWNER_KEY

@pytest.fixture
def runtime(monkeypatch):
    testdb.use_test_database()
    with testdb.sync_engine().begin() as connection:
        ConversationBase.metadata.create_all(connection, tables=[AgentConversation.__table__, AgentMessage.__table__])
        Base.metadata.create_all(connection, tables=[Workflow.__table__, WorkflowRun.__table__, AgentApproval.__table__, ChatWorkflowAttachment.__table__, ChatWorkflowRequest.__table__])
    @asynccontextmanager
    async def scope():
        engine = create_async_engine(make_url(os.environ["TEST_DATABASE_URL"]).set(drivername="postgresql+asyncpg"), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                async with session.begin(): yield session
        finally: await engine.dispose()
    monkeypatch.setattr(routes, "session_scope", scope)
    tenant, other_tenant, user, other_user, conv_id, wf_id, foreign_id = [uuid.uuid4() for _ in range(7)]
    async def setup():
        async with scope() as session:
            session.add(AgentConversation(id=conv_id, tenant_id=tenant, agent_type="auto", context={OWNER_KEY: str(user)}))
            session.add_all([Workflow(id=wf_id, tenant_id=tenant, name="Review", status="active", definition={"nodes": []}),
                             Workflow(id=foreign_id, tenant_id=other_tenant, name="Private", status="active", definition={})])
    asyncio.run(setup())
    ctx = AuthContext(tenant_id=tenant, user_id=user)
    app = FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[get_auth_context] = lambda: ctx
    with TestClient(app) as client:
        yield client, ctx, scope, conv_id, wf_id, foreign_id, other_user
    async def cleanup():
        async with scope() as session:
            await session.execute(delete(AgentConversation).where(AgentConversation.id == conv_id))
            await session.execute(delete(Workflow).where(Workflow.id.in_([wf_id, foreign_id])))
            await session.execute(delete(AgentApproval).where(AgentApproval.tenant_id == tenant))
    asyncio.run(cleanup())

def test_attachment_scope_and_global_activation_unchanged(runtime):
    client, ctx, scope, conv, wf, foreign, other_user = runtime
    assert client.put(f"/{conv}", json={"workflow_ids": [str(foreign)]}).status_code == 404
    assert client.put(f"/{conv}", json={"workflow_ids": [str(wf)]}).status_code == 200
    assert client.get(f"/{conv}").json()["data"][0]["execution_status"] == "attached"
    ctx.user_id = other_user
    assert client.get(f"/{conv}").status_code == 404
    assert client.post(f"/{conv}/{wf}/run", json={"request_key": str(uuid.uuid4())}).status_code == 404
    async def check():
        async with scope() as session:
            assert (await session.get(Workflow, wf)).status == "active"
    asyncio.run(check())

def test_run_request_replay_and_concurrent_clicks_create_one_approval(runtime, monkeypatch):
    client, ctx, scope, conv, wf, _, _ = runtime
    assert client.put(f"/{conv}", json={"workflow_ids": [str(wf)]}).status_code == 200
    async def approval(session, tenant, agent, tool, arguments, **kwargs):
        ident = uuid.uuid4()
        from datetime import datetime, timedelta, timezone
        session.add(AgentApproval(id=ident, tenant_id=ctx.tenant_id, agent_type=agent, tool_name=tool,
            arguments=arguments, conversation_id=conv, requested_by=str(ctx.user_id), status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        await session.flush()
        return {"id": str(ident)}
    mock = AsyncMock(side_effect=approval)
    monkeypatch.setattr(routes, "request_approval", mock)
    key = str(uuid.uuid4())
    def send(): return client.post(f"/{conv}/{wf}/run", json={"request_key": key})
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: send(), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json()["approval_id"] == responses[1].json()["approval_id"]
    assert mock.await_count == 1
    assert client.post(f"/{conv}/{wf}/run", json={"request_key": str(uuid.uuid4())}).status_code == 409
    assert client.get(f"/{conv}").json()["data"][0]["execution_status"] == "awaiting_approval"
    # Detaching does not cancel an approval; reattaching must recover it.
    assert client.put(f"/{conv}", json={"workflow_ids": []}).status_code == 200
    assert client.put(f"/{conv}", json={"workflow_ids": [str(wf)]}).status_code == 200
    assert client.get(f"/{conv}").json()["data"][0]["execution_status"] == "awaiting_approval"
    async def approve_without_claim():
        async with scope() as session:
            row = await session.get(AgentApproval, uuid.UUID(responses[0].json()["approval_id"]))
            row.status = "approved"
    asyncio.run(approve_without_claim())
    assert client.post(f"/{conv}/{wf}/run", json={"request_key": str(uuid.uuid4())}).status_code == 409
