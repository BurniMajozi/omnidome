"""Workflow state-transition regression tests. SQLite does not verify row locks."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import asyncio
from functools import wraps


def run_async(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))
    return wrapped
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from services.agent_orchestrator import workflow_engine as engine
from services.agent_orchestrator import workflow_tools
from services.agent_orchestrator.models import Base, Workflow, WorkflowRun, RunStep, AgentApproval
from services.agent_orchestrator.tools import policy_for, tool_registry


@compiles(JSONB, "sqlite")
def sqlite_json(element, compiler, **kw):
    return "JSON"


TENANT = uuid.uuid4()
USER = uuid.uuid4()
DEFINITION = {
    "nodes": [{"id": "write", "type": "http_request"},
              {"id": "approve", "type": "agent_invoke", "config": {"agent_type": "billing", "message": "Create a draft"}},
              {"id": "save", "type": "http_request"}],
    "edges": [{"from": "write", "to": "approve"}, {"from": "approve", "to": "save"}],
}


@pytest.fixture
def store(monkeypatch):
    async def setup():
        database = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with database.begin() as conn:
            await conn.run_sync(lambda s: Base.metadata.create_all(s, tables=[Workflow.__table__, WorkflowRun.__table__, RunStep.__table__, AgentApproval.__table__]))
        factory = async_sessionmaker(database, expire_on_commit=False)

        @asynccontextmanager
        async def scope():
            async with factory() as session:
                async with session.begin():
                    yield session

        monkeypatch.setattr(engine, "session_scope", scope)
        monkeypatch.setattr(workflow_tools, "session_scope", scope)
        monkeypatch.setattr(engine.memory_capture, "request_in", AsyncMock())
        async with scope() as session:
            wf = Workflow(tenant_id=TENANT, name="Draft recovery", definition=DEFINITION, status="active")
            session.add(wf)
            await session.flush()
            ident = wf.id

        return scope, ident, database
    scope, ident, database = asyncio.run(setup())
    yield scope, ident
    asyncio.run(database.dispose())


def test_workflow_policy_and_customer_exclusion():
    assert not policy_for("workflows.list").mutates
    assert policy_for("workflows.run").mutates
    assert policy_for("workflows.run").requires_approval
    internal = {t.name for t in tool_registry.filter_for_agent("billing")}
    customer = {t.name for t in tool_registry.filter_for_agent("customer_facing")}
    assert {"workflows.list", "workflows.run"} <= internal
    assert not {"workflows.list", "workflows.run"} & customer


@pytest.mark.parametrize("status,executed,result,expected", [
    ("pending", False, None, "pending"),
    ("approved", False, None, "pending"),
    ("approved", True, {"success": True}, "done"),
    ("approved", True, {}, "error"),
    ("approved", True, {"success": False, "error": ""}, "error"),
    ("rejected", False, None, "error"),
    ("expired", False, None, "error"),
])
def test_approval_outcomes(status, executed, result, expected):
    ident = uuid.uuid4()
    row = SimpleNamespace(id=ident, status=status, executed_at=datetime.now(timezone.utc) if executed else None,
                          execution_result=result, expires_at=datetime.now(timezone.utc)+timedelta(days=1))
    error, pending, results = engine.approval_outcomes([row], [str(ident)])
    assert ("error" if error else "pending" if pending else "done") == expected
    if expected == "done": assert results[str(ident)] == result


def test_rejection_wins_over_another_pending_approval():
    rows = [SimpleNamespace(id=uuid.uuid4(), status=status, executed_at=None, execution_result=None, expires_at=None)
            for status in ("pending", "rejected")]
    error, pending, _ = engine.approval_outcomes(rows, [str(r.id) for r in rows])
    assert error and not pending
    assert engine.approval_outcomes(rows, [str(uuid.uuid4())])[0]


def test_branch_and_approval_ids():
    definition = {"edges": [{"from": "check", "to": "yes", "condition": "true"},
                            {"from": "check", "to": "no", "condition": "false"}]}
    assert engine.next_node({"id": "check", "type": "condition"}, definition, {"result": False}) == "no"
    ident = str(uuid.uuid4())
    assert engine.approval_ids({"approval_ids": [ident, ident]}) == [ident]


@run_async
async def test_empty_timeout_fails_run_with_named_step(store, monkeypatch):
    _, ident = store
    node = AsyncMock(side_effect=httpx.ConnectTimeout(""))
    monkeypatch.setattr(engine, "_run_node", node)
    result = await engine.run_workflow(ident, TENANT, USER)
    assert result["status"] == "failed"
    assert result["error"] == "write: ConnectTimeout"
    assert node.await_count == 1


@run_async
async def test_approval_resume_does_not_repeat_writes_and_uses_frozen_definition(store, monkeypatch):
    scope, ident = store
    approval_id = uuid.uuid4()
    calls = []

    async def node(node, data, tenant, user):
        calls.append(node["id"])
        if node["id"] == "approve":
            async with scope() as s:
                s.add(AgentApproval(id=approval_id, tenant_id=TENANT, run_id=uuid.UUID(data["run_id"]),
                    agent_type="billing", tool_name="crm_create_lead", arguments={}, status="pending",
                    expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
            return {"ok": True, "awaiting_approval": True, "approval_ids": [str(approval_id)]}
        return {"ok": True, "value": node["id"]}

    continuation = AsyncMock(return_value={"content": "Draft created", "tool_calls": []})
    contexts = []
    def agent(**kw):
        contexts.append(kw["context"])
        return SimpleNamespace(run=continuation)
    monkeypatch.setattr(engine, "_run_node", node)
    monkeypatch.setattr(engine, "Agent", agent)
    result = await engine.run_workflow(ident, TENANT, USER)
    run_id = uuid.UUID(result["run_id"])
    assert result["status"] == "awaiting_approval"
    assert (await engine.resume_workflow(run_id, uuid.uuid4()))["error"] == "run not found"
    assert (await engine.resume_workflow(run_id, TENANT))["status"] == "awaiting_approval"
    async with scope() as s:
        row = await s.get(AgentApproval, approval_id)
        row.status = "approved"
        row.executed_at = datetime.now(timezone.utc)
        row.execution_result = {"success": True, "data": {"lead_id": "already-created"}}
        wf = await s.get(Workflow, ident)
        wf.definition = {"nodes": [{"id": "changed", "type": "end"}], "edges": []}
    resumed = await engine.resume_workflow(run_id, TENANT)
    assert resumed["status"] == "succeeded"
    assert calls == ["write", "approve", "save"]
    assert contexts[0]["draft_only"] is True
    assert "already-created" in continuation.call_args.args[0]
    assert (await engine.resume_workflow(run_id, TENANT))["status"] == "succeeded"
    assert continuation.await_count == 1
    async with scope() as s:
        steps = (await s.execute(select(RunStep).where(RunStep.run_id == run_id))).scalars().all()
        assert len(steps) == 3
        assert all(step.status == "succeeded" for step in steps)


@run_async
async def test_changed_definition_and_foreign_tenant_cannot_execute(store, monkeypatch):
    scope, ident = store
    async with scope() as s:
        frozen = await workflow_tools.freeze_arguments(s, TENANT, {"workflow_id": str(ident), "input": {}})
        with pytest.raises(ValueError):
            await workflow_tools.freeze_arguments(s, uuid.uuid4(), {"workflow_id": str(ident)})
        wf = await s.get(Workflow, ident)
        wf.definition = {"nodes": [{"id": "changed", "type": "end"}]}
    node = AsyncMock()
    monkeypatch.setattr(engine, "_run_node", node)
    result = await workflow_tools.run_tool("workflows.run", frozen, TENANT, USER)
    assert not result["success"]
    assert "changed after approval" in result["error"]
    assert not node.await_count
    assert not (await workflow_tools.run_tool("workflows.run", {"workflow_id": str(ident)}, TENANT, USER))["success"]


@pytest.mark.parametrize("outcome", ["rejected", "expired", "failed", "foreign", "pending"])
@run_async
async def test_unsuccessful_or_pending_approval_never_advances(store, monkeypatch, outcome):
    scope, ident = store
    approval_id = uuid.uuid4()
    calls = []
    async def node(node, data, tenant, user):
        calls.append(node["id"])
        if node["id"] == "approve":
            async with scope() as s:
                s.add(AgentApproval(id=approval_id, tenant_id=uuid.uuid4() if outcome == "foreign" else TENANT,
                    run_id=uuid.UUID(data["run_id"]), agent_type="billing", tool_name="crm_create_lead", arguments={},
                    status="approved" if outcome in {"failed", "foreign"} else "rejected" if outcome == "rejected" else "pending",
                    executed_at=datetime.now(timezone.utc) if outcome in {"failed", "foreign"} else None,
                    execution_result={"success": False} if outcome == "failed" else {"success": True},
                    expires_at=datetime.now(timezone.utc)+timedelta(days=-1 if outcome == "expired" else 1)))
            return {"ok": True, "awaiting_approval": True, "approval_ids": [str(approval_id)]}
        return {"ok": True}
    monkeypatch.setattr(engine, "_run_node", node)
    continuation = AsyncMock()
    monkeypatch.setattr(engine, "Agent", lambda **kw: SimpleNamespace(run=continuation))
    parked = await engine.run_workflow(ident, TENANT, USER)
    resumed = await engine.resume_workflow(uuid.UUID(parked["run_id"]), TENANT)
    assert resumed["status"] == ("awaiting_approval" if outcome == "pending" else "failed")
    assert calls == ["write", "approve"]
    assert not continuation.await_count


@run_async
async def test_in_flight_step_is_not_automatically_replayed(store, monkeypatch):
    scope, ident = store
    checkpoint = {"in_flight": str(uuid.uuid4()), "data": {"steps": {}}}
    async with scope() as s:
        run = WorkflowRun(workflow_id=ident, tenant_id=TENANT, status="running", checkpoint=checkpoint)
        s.add(run)
        await s.flush()
        run_id = run.id
    node = AsyncMock()
    monkeypatch.setattr(engine, "_run_node", node)
    assert (await engine.drive_run(run_id, TENANT))["status"] == "running"
    assert not node.await_count


@run_async
async def test_loop_stops_at_step_limit(store, monkeypatch):
    scope, ident = store
    async with scope() as s:
        wf = await s.get(Workflow, ident)
        wf.definition = {"nodes": [{"id": "start", "type": "trigger"}], "edges": [{"from": "start", "to": "start"}]}
    node = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(engine, "_run_node", node)
    result = await engine.run_workflow(ident, TENANT, USER)
    assert result["status"] == "failed"
    assert "maximum step count" in result["error"]
    assert node.await_count == engine.MAX_NODES


@pytest.mark.parametrize("recovery_fails", [False, True])
@run_async
async def test_approved_result_is_recorded_before_workflow_resume(monkeypatch, recovery_fails):
    from services.agent_orchestrator import approvals
    row = SimpleNamespace(id=uuid.uuid4(), tenant_id=TENANT, run_id=uuid.uuid4(), tool_name="crm_create_lead",
                          agent_type="billing", arguments={}, conversation_id=None, requested_by=str(USER), decided_by=str(USER))
    order = []
    monkeypatch.setattr(approvals, "_claim", AsyncMock(return_value=row))
    monkeypatch.setattr(approvals.tool_registry, "get", lambda name: SimpleNamespace(execute=AsyncMock(return_value={"success": True})))
    async def record(row, result):
        order.append("record")
    async def resume(tenant, approval):
        order.append("resume")
        if recovery_fails: raise RuntimeError("Database unavailable")
    monkeypatch.setattr(approvals, "_record", record)
    monkeypatch.setattr(engine, "resume_workflow_for_approval", resume)
    assert (await approvals.execute_approved(TENANT, row.id))["success"]
    assert order == ["record", "resume"]
