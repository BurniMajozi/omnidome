"""Memory tool inputs and write acknowledgements use the service contract."""

import asyncio
import json
import uuid

import httpx

from services.agent_orchestrator import tools
from services.agent_orchestrator.routes import protocols
from services.common.auth import AuthContext


def test_memory_metadata_json_is_decoded_before_post(monkeypatch):
    seen = {}

    def handle(request):
        seen.update(json.loads(request.content))
        return httpx.Response(201, json={"id": "entry"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(tools.httpx, "AsyncClient",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    result = asyncio.run(tools.tool_registry.get("memory.write_entry").execute({
        "source_type": "agent_decision", "title": "Decision", "content": "Reviewed",
        "metadata": '{"component":"Sales"}',
    }, tenant_id=str(uuid.uuid4()), user_id=str(uuid.uuid4())))
    assert result["success"] is True
    assert seen["metadata"] == {"component": "Sales"}


def test_memory_recall_limit_is_clamped_to_service_max(monkeypatch):
    seen = {}

    def handle(request):
        seen["limit"] = request.url.params.get("limit")
        return httpx.Response(200, json={"summaries": [], "entries": []})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(tools.httpx, "AsyncClient",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    result = asyncio.run(tools.tool_registry.get("memory.recall").execute(
        {"q": "Sales", "limit": 100}, tenant_id=str(uuid.uuid4())))
    assert result["success"] is True
    assert seen["limit"] == "50"


def test_protocol_memory_write_reports_rejected_response(monkeypatch):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(protocols.httpx, "AsyncClient",
                        lambda **kwargs: real_client(
                            transport=httpx.MockTransport(lambda _request: httpx.Response(422)), **kwargs))
    ctx = AuthContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=[])
    written = asyncio.run(protocols._write_protocol_memory(
        ctx, "AG-UI run", "Content", {}, str(uuid.uuid4())))
    assert written is False
