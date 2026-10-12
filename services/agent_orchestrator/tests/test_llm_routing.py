import asyncio
import copy
import json
import uuid
import httpx
import pytest
from fastapi import HTTPException
from services.common import llm_routing as routing, openrouter
from services.common.auth import AuthContext
from services.agent_orchestrator.routes import llm_console

def test_basic_rejects_paid_fallback():
    config = routing.defaults()
    config["profiles"]["basic"]["fallbacks"] = ["anthropic/paid"]
    with pytest.raises(ValueError, match="explicitly free"): routing.validate(config)

def test_pending_payment_does_not_unlock_models():
    assert routing.tier_for({"platform_pricing":{"quote":{"tier":"ENTERPRISE"}, "provisioned":False}}) == "FREE"

def test_pending_change_keeps_active_plan():
    assert routing.tier_for({"platform_pricing":{"quote":{"tier":"ENTERPRISE"}, "active_quote":{"tier":"STARTER"}, "provisioned":False}}) == "STARTER"

@pytest.mark.parametrize("tier", ["FREE", "STARTER", "PROFESSIONAL", "ENTERPRISE"])
def test_active_modular_and_bundle_tiers(tier):
    assert routing.tier_for({"platform_pricing":{"active_quote":{"tier":tier}}}) == tier

def test_unknown_plan_fails_to_basic():
    assert routing.tier_for({"platform_pricing":{"active_quote":{"tier":"UNKNOWN"}}}) == "FREE"

def test_trial_uses_basic_even_with_professional_panels():
    assert routing.tier_for({"platform_pricing":{"billing_mode":"trial","active_quote":{"tier":"PROFESSIONAL"}}}) == "FREE"

def test_free_parent_cannot_invoke_paid_server_tools(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    bodies=[]
    def handler(request):
        bodies.append(json.loads(request.content)); return httpx.Response(200,json={"choices":[{"message":{"content":"ok"}}]})
    async def run():
        token=routing.route_chain.set(("a/basic:free",))
        try: await openrouter.chat_completion({"tools":[{"type":"openrouter:subagent"}],"plugins":[{"id":"web"}]},transport=httpx.MockTransport(handler))
        finally: routing.route_chain.reset(token)
    asyncio.run(run())
    assert "tools" not in bodies[0] and "plugins" not in bodies[0]

def test_free_cannot_map_to_premium():
    config = routing.defaults(); config["tiers"]["FREE"] = "premium"
    with pytest.raises(ValueError): routing.validate(config)

def test_three_slots_only():
    config = routing.defaults(); config["profiles"]["other"] = {}
    with pytest.raises(ValueError): routing.validate(config)

def test_local_basic_allowed():
    config = routing.defaults(); config["profiles"]["basic"]["model"] = "qwen2.5:7b"
    routing.validate(config)

def test_enabled_routing_requires_basic():
    config = routing.defaults(); config["enabled"] = True
    with pytest.raises(ValueError): routing.validate(config)

def test_owner_gate_rejects_org_admin():
    ctx = AuthContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=["org_admin"])
    with pytest.raises(HTTPException) as e: asyncio.run(llm_console.owner(ctx))
    assert e.value.status_code == 403
    ctx.is_platform_admin=True
    assert asyncio.run(llm_console.owner(ctx)) is ctx

def test_test_fingerprint_changes_when_fallback_changes():
    profile = routing.defaults()["profiles"]["basic"]
    other = copy.deepcopy(profile); other["fallbacks"] = ["a/b:free"]
    assert llm_console.fingerprint(profile) != llm_console.fingerprint(other)

def test_restricted_chain_never_uses_paid_environment(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/paid")
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "other/paid")
    token = routing.route_chain.set(("a/basic:free",))
    try: assert openrouter.model_chain("attacker/paid") == ["a/basic:free"]
    finally: routing.route_chain.reset(token)

def test_exhausted_free_returns_failure_without_paid_call(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "other/paid")
    tried=[]
    def handler(request):
        tried.append(json.loads(request.content)["model"])
        return httpx.Response(429,json={"error":{"message":"capacity"}})
    async def run():
        token = routing.route_chain.set(("a/basic:free", "b/backup:free"))
        try: return await openrouter.chat_completion({}, transport=httpx.MockTransport(handler))
        finally: routing.route_chain.reset(token)
    assert asyncio.run(run()) is None
    assert tried == ["a/basic:free", "b/backup:free"]
    openrouter.reset_limits()
