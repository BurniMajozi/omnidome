import asyncio
import json
import uuid

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from services.agent_orchestrator.routes import memory
from services.common.auth import AuthContext


def admin_context():
    return AuthContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=["org_admin"])


def test_okf_create_still_needs_a_name_description_and_defaults_the_source_agent():
    with pytest.raises(ValidationError):
        memory.SkillCreateRequest(description="Review evidence", guidance_prompt="Inspect sources first")
    assert memory.SkillCreateRequest(name="Review", description="Review evidence").source_agent_type == "shared"


def test_okf_proxy_forwards_source_and_admin_identity(monkeypatch):
    seen = {}

    def handle(request):
        seen["body"] = json.loads(request.content)
        seen["roles"] = request.headers.get("x-roles")
        return httpx.Response(201, json={"skill_name": "Review"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(memory.httpx, "AsyncClient",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    payload = memory.SkillCreateRequest(name="Review", description="Review evidence",
                                        source_agent_type="custom_architect",
                                        target_agent_types=["custom_architect"],
                                        guidance_prompt="Inspect sources first")
    result = asyncio.run(memory.create_skill(payload, admin_context()))
    assert result["skill_name"] == "Review"
    assert seen["body"]["source_agent_type"] == "custom_architect"
    assert seen["roles"] == "org_admin"


def test_okf_list_outage_is_error_not_empty(monkeypatch):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(memory.httpx, "AsyncClient",
                        lambda **kwargs: real_client(
                            transport=httpx.MockTransport(lambda _request: httpx.Response(503)), **kwargs))
    with pytest.raises(HTTPException) as unavailable:
        asyncio.run(memory.list_skills(None, admin_context()))
    assert unavailable.value.status_code == 503
