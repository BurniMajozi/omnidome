import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
import pytest
from services.agent_orchestrator import commercial_usage as meter


@pytest.mark.parametrize("result,eligible", [
    ({"content":"Answer","usage":{"total_tokens":2001}},True),
    ({"content":"Approval required","status":"awaiting_hitl"},False),
    ({"content":"Unavailable","unavailable":True},False),
    ({"content":"Stopped","stopped_by":"budget"},False),
])
def test_shadow_turn_finishes_once_and_records_ineligible_work(monkeypatch,result,eligible):
    records=[]
    @asynccontextmanager
    async def session(): yield object()
    async def start(db,tenant,operation,kind): return {"test":True}
    async def cost(db,**kwargs): records.append(("cost",kwargs))
    async def finish(db,tenant,operation,policy,kind,**kwargs): records.append(("finish",kwargs))
    monkeypatch.setenv("PLATFORM_USAGE_ENABLED","true")
    monkeypatch.setattr(meter,"session_scope",session)
    monkeypatch.setattr(meter.platform_usage,"start_operation",start)
    monkeypatch.setattr(meter.platform_usage,"append_cost",cost)
    monkeypatch.setattr(meter.platform_usage,"finish_operation",finish)
    @meter.metered_turn
    async def turn(self):
        assert meter.current_operation.get()[0]=="tenant"
        return result
    assert asyncio.run(turn(SimpleNamespace(tenant_id="tenant",agent_type="support")))==result
    assert meter.current_operation.get() is None
    assert len([r for r in records if r[0]=="finish"])==1
    assert records[-1][1]["eligible"] is eligible
    assert "amount" not in records[0][1]  # Runtime duration is not a fabricated monetary cost.


def test_research_and_content_receive_their_draft_work_classification():
    assert meter.operation_kind("support",{"tool_calls":[{"name":"web_search"}]})=="research"
    assert meter.operation_kind("portal_builder")=="content_generation"
    assert meter.operation_kind("support",{"tool_calls":[{"name":"knowledge.context"}]})=="assisted_action"
