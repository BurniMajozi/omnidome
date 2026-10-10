"""M2 okf-skills-runtime (SPEC-orchestrator-memory-hardening.md).

Run with cwd = services/agent_orchestrator:  python -m pytest tests -q
"""

import asyncio
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator import skills_runtime as sr  # noqa: E402

T = "00000000-0000-0000-0000-000000000001"


def skill(name, targets=(), source="support", tools=(), guidance="Do the thing."):
    return {"skill_name": name, "target_agent_types": list(targets), "source_agent_type": source,
            "tools_required": list(tools), "guidance_prompt": guidance}


@pytest.fixture(autouse=True)
def fresh_cache():
    sr.clear_cache()
    yield
    sr.clear_cache()


def test_skill_applies_to_targets_source_and_untargeted():
    assert sr.applies_to(skill("a", targets=["retention"]), "retention")
    assert sr.applies_to(skill("b", targets=["executive"], source="retention"), "retention")
    assert sr.applies_to(skill("c"), "retention")
    assert not sr.applies_to(skill("d", targets=["executive"], source="support"), "retention")


def test_prompt_lists_each_skill_with_guidance_and_tools():
    text = sr.skills_prompt([skill("Win-back offer", tools=["billing_get_balance"], guidance="Offer 15% first.")])
    assert "## Skills" in text and "### Win-back offer" in text
    assert "Offer 15% first." in text and "Tools: billing_get_balance" in text
    assert sr.skills_prompt([]) == ""


def test_long_guidance_is_clipped():
    text = sr.skills_prompt([skill("x", guidance="w " * 2000)])
    assert len(text) < sr.MAX_GUIDANCE_CHARS + 200


def test_only_known_missing_tools_are_added():
    skills = [skill("a", tools=["billing_get_balance", "not_a_tool", "crm_get_customer"])]
    assert sr.extra_tool_names(skills, have=["crm_get_customer"],
                               known=["billing_get_balance", "crm_get_customer"]) == ["billing_get_balance"]


def test_skills_are_cached_per_tenant_and_user(monkeypatch):
    calls = []

    async def fake(tenant_id, actor_id, roles):
        calls.append(tenant_id)
        return [skill("a", targets=["retention"])]
    monkeypatch.setattr(sr, "_fetch", fake)
    for _ in range(3):
        assert [s["skill_name"] for s in asyncio.run(sr.skills_for(T, "retention"))] == ["a"]
    assert asyncio.run(sr.skills_for(T, "executive")) == []
    assert calls == [T]


def test_skills_fail_open_and_keep_the_last_good_list(monkeypatch):
    async def ok(*_):  # (tenant, actor, roles)
        return [skill("a")]

    async def down(*_):
        raise ConnectionError("tenant_memory down")
    monkeypatch.setattr(sr, "_fetch", down)
    assert asyncio.run(sr.skills_for(T, "retention")) == []
    sr.clear_cache()
    monkeypatch.setattr(sr, "_fetch", ok)
    asyncio.run(sr.skills_for(T, "retention"))
    key = (T, "")
    sr._cache[key] = (0, sr._cache[key][1])          # expire
    monkeypatch.setattr(sr, "_fetch", down)
    assert [s["skill_name"] for s in asyncio.run(sr.skills_for(T, "retention"))] == ["a"]
