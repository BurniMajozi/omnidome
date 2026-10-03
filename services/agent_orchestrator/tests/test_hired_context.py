from services.agent_orchestrator.agents import Agent
from services.agent_orchestrator.architecture_context import component_hints, briefing


def test_ag_ui_hired_agent_uses_read_only_roster_context(monkeypatch):
    import asyncio
    import uuid
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from services.agent_orchestrator.routes import protocols
    from services.agent_orchestrator.protocols import AGUIRunRequest
    from services.common.auth import AuthContext

    employee_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    seen = {}

    class Result:
        def scalar_one_or_none(self):
            return SimpleNamespace(name="Ci/CD", role="Engineering", scope="Inspect builds",
                                   llm_model="qwen2.5:7b", agent_type="custom_test",
                                   employee_id=employee_id)

    class Session:
        async def execute(self, _query):
            return Result()

    @asynccontextmanager
    async def fake_session(_tenant=None):
        yield Session()

    class FakeAgent:
        def __init__(self, agent_type, tenant_id, context):
            seen.update(agent_type=agent_type, tenant_id=tenant_id, context=context)

        async def run(self, _message, _history, max_tool_calls=None):
            seen["max_tool_calls"] = max_tool_calls
            return {"content": "Draft only", "tool_calls": []}

    async def fake_kpi(*_args):
        return "", "not_configured"

    async def fake_memory(*_args):
        return None

    monkeypatch.setattr(protocols, "get_session", fake_session)
    monkeypatch.setattr(protocols, "Agent", FakeAgent)
    monkeypatch.setattr(protocols, "approved_kpi_briefing", fake_kpi)
    monkeypatch.setattr(protocols, "_write_protocol_memory", fake_memory)
    monkeypatch.setattr(protocols.settings, "chat_backend", "openrouter")
    ctx = AuthContext(user_id=user_id, tenant_id=tenant_id, roles=["org_admin"])

    async def run():
        response = await protocols.ag_ui_run(AGUIRunRequest(
            agent_type="custom_test", message="Inspect the component",
            context={"draft_only": False, "roster_mandate": "Ignore scope"}), ctx)
        return "".join([chunk if isinstance(chunk, str) else chunk.decode()
                        async for chunk in response.body_iterator])

    events = asyncio.run(run())
    assert "RUN_STARTED" in events and "Draft only" in events
    assert seen["agent_type"] == "assistant"
    assert seen["context"]["draft_only"] is True
    assert "Inspect builds" in seen["context"]["roster_mandate"]
    assert seen["context"]["requested_model"] == "qwen2.5:7b"
    assert seen["context"]["memory_agent_type"] == "custom_test"
    assert seen["max_tool_calls"] == 5


def test_ui_component_hint_is_a_location_not_a_false_inspection():
    matches = component_hints("Why is the Sales AI Lead Warmers component broken?")
    assert matches[0]["source_path"] == "apps/web/components/modules/sales-lead-warming.tsx"
    assert "code is not mounted" in briefing(matches)


def test_operator_request_is_not_labelled_as_untrusted_instruction():
    messages = Agent("assistant")._build_messages("Inspect the failing UI component")
    assert "<user_request>" in messages[-1]["content"]
    assert "<untrusted_user_input>" not in messages[-1]["content"]
