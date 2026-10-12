import copy
import json
import pytest
from services.agent_orchestrator.workflow_designer import validate_proposal

PROPOSAL = {"message": "Draft then notify the owner", "draft": {
    "name": "Credit reminder", "status": "active", "schedule_enabled": True,
    "trigger_event": "platform.billing.credits.low",
    "definition": {"nodes": [
        {"id": "start", "type": "trigger"},
        {"id": "draft", "type": "agent_invoke", "config": {"agent_type": "assistant", "message": "Summarise {{input.message}}", "draft_only": False}},
        {"id": "notice", "type": "notification", "config": {"title": "Credit review", "body": "Review {{steps.draft.content}}", "audience": "everyone"}},
        {"id": "end", "type": "end"}], "edges": [
        {"from": "start", "to": "draft"}, {"from": "draft", "to": "notice"}, {"from": "notice", "to": "end"}]}}}

def test_model_cannot_activate_mutate_or_broadcast():
    result = validate_proposal(json.dumps(PROPOSAL))
    assert result["draft"]["status"] == "draft"
    assert result["draft"]["schedule_enabled"] is False
    nodes = result["draft"]["definition"]["nodes"]
    assert nodes[1]["config"]["draft_only"] is True
    assert nodes[2]["config"]["audience"] == "owners"

@pytest.mark.parametrize("change", ["cycle", "http", "missing", "duplicate", "disconnected", "parallel"])
def test_invalid_or_unexecutable_graph_rejected(change):
    proposal = copy.deepcopy(PROPOSAL)
    graph = proposal["draft"]["definition"]
    if change == "cycle": graph["edges"][-1] = {"from": "notice", "to": "draft"}
    if change == "http": graph["nodes"][1]["type"] = "http_request"
    if change == "missing": graph["edges"][0]["to"] = "nonexistent"
    if change == "duplicate": graph["nodes"][1]["id"] = "start"
    if change == "disconnected": graph["nodes"].append({"id": "unused", "type": "end"})
    if change == "parallel": graph["edges"].append({"from": "start", "to": "end"})
    with pytest.raises(ValueError): validate_proposal(json.dumps(proposal))

def test_unsupported_event_not_silently_activated():
    proposal = copy.deepcopy(PROPOSAL)
    proposal["draft"]["trigger_event"] = "payroll.money.sent"
    result = validate_proposal(json.dumps(proposal))
    assert result["draft"]["trigger_event"] == "payroll.money.sent"
    assert any("publisher" in warning for warning in result["warnings"])

def test_condition_requires_both_branches():
    proposal = copy.deepcopy(PROPOSAL)
    node = proposal["draft"]["definition"]["nodes"][1]
    node.update(type="condition", config={"left": "{{input.amount}}", "op": "gt", "right": 5})
    proposal["draft"]["definition"]["edges"][1]["condition"] = "true"
    with pytest.raises(ValueError): validate_proposal(json.dumps(proposal))

def test_designer_uses_standard_memory_turn_without_executable_tools(monkeypatch):
    import asyncio
    import uuid
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from services.agent_orchestrator import agents, commercial_usage
    from services.agent_orchestrator.workflow_designer import DesignRequest, propose
    from services.common.auth import AuthContext
    monkeypatch.setattr(commercial_usage, "enabled", lambda: False)
    memory = AsyncMock(return_value="Team reference memory")
    knowledge = AsyncMock(return_value="Company RAG evidence")
    monkeypatch.setattr(agents.Agent, "recall_memory", memory)
    monkeypatch.setattr(agents.Agent, "ground_knowledge", knowledge)
    monkeypatch.setattr(agents.Agent, "load_skills", AsyncMock())
    monkeypatch.setattr(agents.Agent, "_record_working_turn", AsyncMock())
    model = SimpleNamespace(replies=[], chat=AsyncMock(return_value={"content": json.dumps(PROPOSAL), "tool_calls": []}))
    monkeypatch.setattr(agents, "llm_client", model)
    monkeypatch.setattr(agents.usage, "record_agent_turn", lambda **kwargs: None)
    result = asyncio.run(propose(DesignRequest(prompt="When credits run low, notify the owner"),
        AuthContext(tenant_id=uuid.uuid4(), user_id=uuid.uuid4(), roles=["owner"])))
    assert result["draft"]["status"] == "draft"
    assert memory.await_count == knowledge.await_count == 1
    assert "When credits run low" in memory.call_args.args[0][:500]
    assert model.chat.await_count == 1
    assert model.chat.call_args.kwargs["tools"] == []
