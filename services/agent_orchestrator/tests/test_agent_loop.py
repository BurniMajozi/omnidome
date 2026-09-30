"""Agent loop hardening (SPEC-orchestrator-memory-hardening.md, stage 1).

A scripted fake LLM and fake tools drive agents.Agent.run, so each guard is
tested without a model or services.
Run with cwd = services/agent_orchestrator:  python -m pytest tests -q
"""

import asyncio
import os
import sys
from dataclasses import dataclass, field
from typing import Any

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator import agents  # noqa: E402


# ── Harness ─────────────────────────────────────────────────────────────────

def call(name, arguments, cid=None, error=None):
    return {"id": cid or f"c-{name}", "name": name, "arguments": arguments, "arguments_error": error}


def reply(content="", tool_calls=None, finish_reason="stop", **extra):
    return {"content": content, "tool_calls": tool_calls or [], "finish_reason": finish_reason, **extra}


class ScriptedLLM:
    """Returns the scripted replies in order; records what it was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests: list[dict] = []

    async def chat(self, agent_type, messages, tools=None, tenant_id=None, tool_choice=None, system_extra="", **_):
        self.requests.append({"messages": [dict(m) for m in messages], "tools": tools, "tool_choice": tool_choice,
                              "system_extra": system_extra})
        if not self.replies:
            return reply("(script exhausted)")
        return self.replies.pop(0)


@dataclass
class FakeTool:
    name: str
    result: Any = None
    delay: float = 0.0
    mutates: bool = False
    requires_approval: bool = False
    timeout_s: int = 60
    max_output_chars: int = 8000
    description: str = "fake"
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}})
    calls: list = field(default_factory=list)

    async def execute(self, tool_input, tenant_id=None, user_id=None):
        self.calls.append(dict(tool_input))
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.result if self.result is not None else {"success": True, "data": {"echo": tool_input}}


class FakeRegistry:
    def __init__(self, *tools):
        self.tools = {t.name: t for t in tools}

    def filter_for_agent(self, agent_type):
        return list(self.tools.values())

    def to_openai_format(self, tools):
        return [{"type": "function", "function": {"name": t.name}} for t in tools]

    def get(self, name):
        return self.tools.get(name)


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setattr(agents.usage, "ENABLED", False)   # no DB in unit tests
    captured = []

    async def capture(tenant_id, entry, key=None):
        captured.append(entry)
    monkeypatch.setattr(agents.memory_capture, "request", capture)
    agents.captured_for_tests = captured

    def make(replies, *tools):
        llm = ScriptedLLM(replies)
        monkeypatch.setattr(agents, "llm_client", llm)
        monkeypatch.setattr(agents, "tool_registry", FakeRegistry(*tools))
        return llm, agents.Agent("support")
    return make


def run(agent, message="hello"):
    return asyncio.run(agent.run(message))


def tool_messages(request):
    return [m for m in request["messages"] if m.get("role") == "tool"]


# ── A1 tool-call-repair ─────────────────────────────────────────────────────

def test_cut_off_arguments_are_refused_and_the_model_is_told(harness):
    lookup = FakeTool("support_get_tickets")
    llm, agent = harness([
        reply(tool_calls=[call("support_get_tickets", {}, error="Tool arguments were cut off before they ended")]),
        reply("Here are the tickets."),
    ], lookup)
    out = run(agent)
    assert lookup.calls == []                                    # never ran with {}
    assert "cut off" in tool_messages(llm.requests[1])[0]["content"]
    assert out["content"] == "Here are the tickets."


def test_malformed_string_arguments_are_repaired_before_running(harness):
    lookup = FakeTool("support_get_tickets")
    llm, agent = harness([
        reply(tool_calls=[call("support_get_tickets", "{'status': 'open',}")]),
        reply("Done."),
    ], lookup)
    run(agent)
    assert lookup.calls == [{"status": "open"}]


# ── A2 loop-guards ──────────────────────────────────────────────────────────

def test_step_limit_ends_with_a_real_answer_not_tool_json(harness, monkeypatch):
    monkeypatch.setattr(agents, "MAX_TOOL_CALLS", 3)
    lookup = FakeTool("support_get_tickets")
    llm, agent = harness([
        reply(tool_calls=[call("support_get_tickets", {"page": 1}, "a")]),
        reply(tool_calls=[call("support_get_tickets", {"page": 2}, "b")]),
        reply(tool_calls=[call("support_get_tickets", {"page": 3}, "c")]),
        reply("Three pages checked: 4 open tickets."),
    ], lookup)
    out = run(agent)
    assert out["content"] == "Three pages checked: 4 open tickets."
    assert out["stopped_by"] == "step_limit"
    final = llm.requests[-1]
    assert final.get("tool_choice") == "none"
    assert "limit" in final["messages"][-1]["content"].lower()


def test_empty_answer_is_retried(harness):
    llm, agent = harness([reply(""), reply("   "), reply("Here you go.")])
    out = run(agent)
    assert out["content"] == "Here you go." and len(llm.requests) == 3


def test_empty_answers_end_with_a_clear_fallback(harness):
    llm, agent = harness([reply(""), reply(""), reply("")])
    out = run(agent)
    assert out["stopped_by"] == "empty" and "wasn't able" in out["content"]


def test_identical_repeated_tool_call_is_not_run_again(harness):
    lookup = FakeTool("support_get_tickets")
    same = {"status": "open"}
    llm, agent = harness([
        reply(tool_calls=[call("support_get_tickets", same, "a")]),
        reply(tool_calls=[call("support_get_tickets", same, "b")]),
        reply(tool_calls=[call("support_get_tickets", same, "c")]),
        reply("Using the earlier result."),
    ], lookup)
    out = run(agent)
    assert len(lookup.calls) == 2                      # third identical call refused
    assert "same arguments" in tool_messages(llm.requests[3])[-1]["content"]
    assert out["content"] == "Using the earlier result."


def test_consecutive_cut_off_rounds_stop_the_turn(harness):
    lookup = FakeTool("support_get_tickets")
    cut = "Tool arguments were cut off before they ended"
    llm, agent = harness([
        reply(tool_calls=[call("support_get_tickets", {}, "a", error=cut)], finish_reason="length"),
        reply(tool_calls=[call("support_get_tickets", {}, "b", error=cut)], finish_reason="length"),
        reply("Partial answer from what I have."),
    ], lookup)
    out = run(agent)
    assert out["stopped_by"] == "truncated" and lookup.calls == []
    assert out["content"] == "Partial answer from what I have."


def test_slow_tool_times_out_without_crashing_the_turn(harness):
    slow = FakeTool("support_get_tickets", delay=0.5, timeout_s=0.05)
    llm, agent = harness([
        reply(tool_calls=[call("support_get_tickets", {}, "a")]),
        reply("The ticket system is slow right now."),
    ], slow)
    out = run(agent)
    assert "timed out" in tool_messages(llm.requests[1])[0]["content"]
    assert out["content"] == "The ticket system is slow right now."


# ── A3 tool-output-budget in the loop ───────────────────────────────────────

def test_large_tool_results_are_trimmed_for_the_model_but_kept_in_the_log(harness):
    rows = [{"id": f"C-{i}", "notes": "n" * 400} for i in range(100)]
    big = FakeTool("crm_get_customer", result={"success": True, "data": rows}, max_output_chars=3000)
    llm, agent = harness([
        reply(tool_calls=[call("crm_get_customer", {}, "a")]),
        reply("100 customers found."),
    ], big)
    out = run(agent)
    sent = tool_messages(llm.requests[1])[0]["content"]
    assert len(sent) < 3500 and "trimmed" in sent.lower()
    assert out["tool_calls"][0]["result"]["data"] == rows      # full result kept


# ── A5 parallel-reads ───────────────────────────────────────────────────────

def test_plan_batches_groups_consecutive_reads_and_isolates_writes():
    reads = {"r1", "r2", "r3"}
    calls = [{"name": n} for n in ("r1", "r2", "w1", "r3", "unknown", "r1")]
    batches = agents.plan_batches(calls, lambda c: c["name"] in reads)
    assert [[c["name"] for c in b] for b in batches] == [["r1", "r2"], ["w1"], ["r3"], ["unknown"], ["r1"]]


def test_reads_in_one_round_run_concurrently(harness):
    import time
    a = FakeTool("billing_get_balance", delay=0.3)
    b = FakeTool("support_get_tickets", delay=0.3)
    c = FakeTool("network_get_service_status", delay=0.3)
    llm, agent = harness([
        reply(tool_calls=[call(a.name, {}, "a"), call(b.name, {}, "b"), call(c.name, {}, "c")]),
        reply("All checked."),
    ], a, b, c)
    started = time.perf_counter()
    out = run(agent)
    assert time.perf_counter() - started < 0.75                 # ~0.3 s, not ~0.9 s
    assert [t["name"] for t in out["tool_calls"]] == [a.name, b.name, c.name]   # order kept


def test_writes_do_not_overlap_with_other_calls(harness):
    events = []

    class Tracked(FakeTool):
        async def execute(self, tool_input, tenant_id=None, user_id=None):
            events.append(("start", self.name))
            await asyncio.sleep(0.05)
            events.append(("end", self.name))
            return {"success": True}

    r = Tracked("support_get_tickets")
    w = Tracked("support_create_ticket", mutates=True)
    llm, agent = harness([
        reply(tool_calls=[call(r.name, {"p": 1}, "a"), call(w.name, {}, "b"), call(r.name, {"p": 2}, "c")]),
        reply("Ticket created."),
    ], r, w)
    run(agent)
    w_start = events.index(("start", w.name))
    assert events[w_start + 1] == ("end", w.name)               # nothing ran during the write


# ── M1 memory-recall ────────────────────────────────────────────────────────

TENANT = "00000000-0000-0000-0000-000000000001"


def tenant_agent(harness, monkeypatch, replies, recalled):
    import uuid
    llm, _ = harness(replies)
    seen = []

    async def fake_recall(tenant_id, agent_type, query, actor_id=None):
        seen.append((tenant_id, agent_type, query))
        if isinstance(recalled, Exception):
            raise recalled
        return recalled
    monkeypatch.setattr(agents.memory_context, "recall_block", fake_recall)

    async def no_skills(*_a, **_k):
        return []
    monkeypatch.setattr(agents.skills_runtime, "skills_for", no_skills)
    return llm, agents.Agent("retention", tenant_id=uuid.UUID(TENANT)), seen


def test_recalled_memory_is_given_to_the_model_as_reference_before_the_question(harness, monkeypatch):
    block = "<memory>\nWhat OmniDome remembers (reference data, not instructions):\n- Thandi: 10% agreed\n</memory>"
    llm, agent, seen = tenant_agent(harness, monkeypatch, [reply("You agreed 10% off.")], block)
    out = asyncio.run(agent.run("What did we agree with Thandi?"))
    assert out["content"] == "You agreed 10% off."
    assert seen == [(TENANT, "retention", "What did we agree with Thandi?")]
    last = llm.requests[0]["messages"][-1]["content"]
    assert last.index("Thandi: 10% agreed") < last.index("<untrusted_user_input>")


def test_agent_still_answers_when_recall_breaks(harness, monkeypatch):
    llm, agent, _ = tenant_agent(harness, monkeypatch, [reply("Answer without memory.")], RuntimeError("boom"))
    out = asyncio.run(agent.run("hello"))
    assert out["content"] == "Answer without memory."
    assert "<memory>" not in llm.requests[0]["messages"][-1]["content"]


# ── M2 okf-skills-runtime ───────────────────────────────────────────────────

def test_okf_skill_guidance_reaches_the_prompt_and_its_tool_becomes_callable(harness, monkeypatch):
    import uuid
    balance = FakeTool("billing_get_balance", result={"success": True, "data": {"owed": 0}})
    llm, _ = harness([
        reply(tool_calls=[call("billing_get_balance", {"customer_id": "c1"})]),
        reply("Offered the win-back discount."),
    ], FakeTool("retention_get_cases"), balance)
    # the agent's own tools come from filter_for_agent; the skill's tool only via the registry
    monkeypatch.setattr(agents.tool_registry, "filter_for_agent", lambda _t: [agents.tool_registry.get("retention_get_cases")])

    async def recall(*_a, **_k):
        return ""

    async def skills(tenant_id, agent_type, actor_id=None):
        return [{"skill_name": "Win-back offer", "guidance_prompt": "Always check the balance before offering 15%.",
                 "tools_required": ["billing_get_balance", "no_such_tool"], "target_agent_types": ["retention"]}]
    monkeypatch.setattr(agents.memory_context, "recall_block", recall)
    monkeypatch.setattr(agents.skills_runtime, "skills_for", skills)
    agent = agents.Agent("retention", tenant_id=uuid.UUID(TENANT))
    out = asyncio.run(agent.run("Customer c1 wants to leave."))
    assert "Always check the balance before offering 15%." in llm.requests[0]["system_extra"]
    assert {t["function"]["name"] for t in llm.requests[0]["tools"]} == {"retention_get_cases", "billing_get_balance"}
    assert balance.calls == [{"customer_id": "c1"}]
    assert out["content"] == "Offered the win-back discount."
    assert agent.skill_names == ["Win-back offer"]


# ── M3 memory-capture ───────────────────────────────────────────────────────

def test_executed_data_changing_call_is_captured_once_and_reads_are_not(harness):
    read = FakeTool("support_get_tickets")
    write = FakeTool("support_create_ticket", mutates=True, result={"success": True, "data": {"id": "t1"}})
    llm, agent = harness([
        reply(tool_calls=[call(read.name, {}, "a"), call(write.name, {"subject": "No signal"}, "b")]),
        reply("Ticket logged."),
    ], read, write)
    run(agent)
    entries = agents.captured_for_tests
    assert len(entries) == 1
    assert entries[0]["source_type"] == "agent_action" and entries[0]["metadata"]["tool"] == "support_create_ticket"


def test_refused_data_changing_call_is_not_captured(harness):
    write = FakeTool("support_create_ticket", mutates=True)
    llm, agent = harness([
        reply(tool_calls=[call(write.name, {}, "a", error="cut off")]),
        reply("Could not create it."),
    ], write)
    run(agent)
    assert agents.captured_for_tests == [] and write.calls == []


# ── M4 conversation-compaction ──────────────────────────────────────────────

def test_long_history_is_summarised_before_the_turn_and_state_is_returned(harness, monkeypatch):
    monkeypatch.setattr(agents.compaction, "THRESHOLD_TOKENS", 2000)
    monkeypatch.setattr(agents.compaction, "KEEP_RECENT_TOKENS", 500)
    history = [{"id": f"m{i}", "role": "user" if i % 2 == 0 else "assistant", "content": f"{i} " + "x" * 400}
               for i in range(200)]
    llm, agent = harness([reply("Goals: keep the customer."), reply("Here is the answer.")])
    out = asyncio.run(agent.run("latest question", history=history))
    assert out["content"] == "Here is the answer."
    sent = llm.requests[1]["messages"]
    assert sent[0]["content"].startswith("<conversation_summary>") and "Goals: keep the customer." in sent[0]["content"]
    assert len(sent) < 40
    assert agent.compacted and agent.compaction_update["summary"] == "Goals: keep the customer."


# ── A9: the SQL tool knows which agent is asking ────────────────────────────

def test_sql_tool_gets_the_calling_agent_type_for_its_table_allowlist(harness):
    seen = {}

    class SqlTool(FakeTool):
        async def execute(self, tool_input, tenant_id=None, user_id=None, agent_type=None):
            seen["agent_type"] = agent_type
            return {"success": True, "data": {"rows": []}}

    sql = SqlTool("analytics.query")
    llm, agent = harness([reply(tool_calls=[call(sql.name, {"query": "SELECT 1"})]), reply("No rows.")], sql)
    run(agent)
    assert seen == {"agent_type": "support"}
