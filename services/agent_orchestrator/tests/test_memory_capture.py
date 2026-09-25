"""M3 memory-capture (SPEC-orchestrator-memory-hardening.md).

Run with cwd = services/agent_orchestrator:  python -m pytest tests -q
"""

import asyncio
import os
import sys

import httpx
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator import memory_capture as mc  # noqa: E402

T = "00000000-0000-0000-0000-000000000001"


def test_data_changing_tool_call_becomes_one_entry():
    e = mc.tool_entry("support", "api", "support_create_ticket", {"subject": "No internet"},
                      {"success": True, "data": {"id": "t1", "ticket_number": "TK-9"}})
    assert e["source_type"] == "agent_action" and e["module"] == "support"
    assert "support_create_ticket" in e["title"] and "(done)" in e["title"]
    assert "No internet" in e["content"] and "TK-9" in e["content"]
    assert e["metadata"]["success"] is True


def test_failed_tool_call_is_recorded_as_failed_with_the_error():
    e = mc.tool_entry("support", "api", "support_create_ticket", {}, {"success": False, "error": "support timeout"})
    assert "(failed)" in e["title"] and "support timeout" in e["content"] and e["importance"] == "low"


def test_memory_and_consultation_tools_are_not_captured():
    for name in ("memory.write_entry", "memory.upsert_summary", "orchestrator_consult_specialist"):
        assert mc.tool_entry("executive", "api", name, {}, {"success": True}) is None


def test_workflow_entry_carries_lead_and_deal_ids():
    steps = {
        "trigger": {"ok": True, "data": {}},
        "lead": {"ok": True, "body": {"id": "L-uuid", "reference": "LD-000035", "deal_id": "D-uuid"}},
        "draft": {"ok": True, "content": "Hi"},
    }
    e = mc.workflow_entry("Abandoned basket → warm-up", "wf1", "run1", "succeeded", "event", steps, None)
    assert e["source_type"] == "workflow_run" and e["source_id"] == "run1"
    assert e["metadata"]["lead_ids"] == ["L-uuid"] and e["metadata"]["deal_ids"] == ["D-uuid"]
    assert "succeeded" in e["title"] and "lead: ok" in e["content"]


def test_failed_workflow_is_high_importance_and_keeps_the_error():
    e = mc.workflow_entry("Flow", "wf1", "run2", "failed", "manual", {"lead": {"ok": False}}, "sales returned 500")
    assert e["importance"] == "high" and "sales returned 500" in e["content"] and "lead: failed" in e["content"]


def test_long_results_are_clipped():
    e = mc.tool_entry("support", "api", "support_create_ticket", {"x": "y" * 5000}, {"success": True, "data": "z" * 9000})
    assert len(e["content"]) <= mc.MAX_TEXT


class FakeMemory:
    def __init__(self, fail=False):
        self.fail, self.entries = fail, []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.fail:
            return httpx.Response(503, json={"detail": "down"})
        if request.method == "GET":
            sid = request.url.params.get("source_id")
            return httpx.Response(200, json={"items": [e for e in self.entries if e["source_id"] == sid]})
        import json
        self.entries.append(json.loads(request.content))
        return httpx.Response(201, json={"id": "m1"})


@pytest.fixture
def memory(monkeypatch):
    fake = FakeMemory()
    real = httpx.AsyncClient
    monkeypatch.setattr(mc.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(fake.handler), **kw))
    return fake


def event(payload):
    return {"tenant_id": T, "payload": payload}


def test_consumer_writes_the_entry_once_even_when_redelivered(memory):
    entry = {**mc.workflow_entry("Flow", "wf1", "run1", "succeeded", "manual", {}, None)}
    asyncio.run(mc.handle_capture(event(entry)))
    asyncio.run(mc.handle_capture(event(entry)))       # bus retry after a lost response
    assert len(memory.entries) == 1 and memory.entries[0]["title"] == "Workflow 'Flow' succeeded"


def test_consumer_raises_while_memory_is_down_so_the_bus_retries(memory):
    memory.fail = True
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(mc.handle_capture(event(mc.workflow_entry("Flow", "wf1", "run1", "succeeded", "manual", {}, None))))
    memory.fail = False
    asyncio.run(mc.handle_capture(event(mc.workflow_entry("Flow", "wf1", "run1", "succeeded", "manual", {}, None))))
    assert len(memory.entries) == 1


def test_request_never_raises_without_a_database(monkeypatch):
    monkeypatch.setattr(mc, "ENABLED", True)

    async def boom(*_a, **_k):
        raise ConnectionError("db down")
    monkeypatch.setattr(mc, "request_in", boom)
    asyncio.run(mc.request(T, {"source_type": "agent_action", "title": "x"}))   # no exception
