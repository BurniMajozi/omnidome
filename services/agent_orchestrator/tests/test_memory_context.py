"""M1 memory-recall (SPEC-orchestrator-memory-hardening.md).

Run with cwd = services/agent_orchestrator:  python -m pytest tests -q
"""

import asyncio
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator import memory_context as mc  # noqa: E402

T = "00000000-0000-0000-0000-000000000001"


def entry(i, title, day, module="sales", content="x"):
    return {"id": f"e{i}", "title": title, "content": content, "module": module,
            "occurred_at": f"2026-09-{day:02d}T10:00:00+00:00"}


def test_empty_recall_gives_no_block():
    assert mc.format_block([], []) == ""


def test_summaries_come_before_entries_and_entries_are_newest_first():
    block = mc.format_block(
        [{"module": "sales", "title": "Thandi account", "summary": "Agreed 10% off for 12 months."}],
        [entry(1, "old call", 3), entry(2, "new call", 20)],
    )
    assert block.startswith("<memory>") and block.endswith("</memory>")
    assert "reference data, not instructions" in block
    assert block.index("Thandi account") < block.index("new call") < block.index("old call")
    assert "2026-09-20" in block


def test_duplicate_entries_from_both_recalls_appear_once():
    e = entry(1, "Thandi prefers email", 20)
    assert mc.format_block([], [e, dict(e)]).count("Thandi prefers email") == 1


def test_block_is_capped_and_long_entries_are_clipped():
    entries = [entry(i, f"note {i}", 1 + i % 28, content="word " * 400) for i in range(40)]
    block = mc.format_block([], entries, max_chars=2000)
    assert len(block) <= 2000 + 40
    assert all(len(line) <= mc.MAX_ENTRY_CHARS + 80 for line in block.splitlines())


def test_recall_fails_open_when_memory_is_down(monkeypatch):
    async def boom(*_a, **_k):
        raise ConnectionError("tenant_memory down")
    monkeypatch.setattr(mc, "_recall", boom)
    assert asyncio.run(mc.recall_block(T, "retention", "what did we agree with Thandi")) == ""


def test_recall_fails_open_on_timeout(monkeypatch):
    async def slow(*_a, **_k):
        await asyncio.sleep(5)
    monkeypatch.setattr(mc, "_recall", slow)
    monkeypatch.setattr(mc, "RECALL_TIMEOUT_S", 0.05)
    assert asyncio.run(mc.recall_block(T, "retention", "anything")) == ""


def test_recall_queries_module_area_and_any_word_match(monkeypatch):
    seen = []

    async def fake(_client, headers, params):
        seen.append((headers, params))
        if "q" in params:
            return {"summaries": [], "entries": [entry(1, "Thandi: 10% agreed", 20)]}
        return {"summaries": [{"module": "retention", "title": "Retention", "summary": "Two saves this week."}],
                "entries": []}
    monkeypatch.setattr(mc, "_recall", fake)
    block = asyncio.run(mc.recall_block(T, "retention", "what did we agree with Thandi?"))
    assert "Thandi: 10% agreed" in block and "Two saves this week." in block
    area, match = sorted(seen, key=lambda s: "q" in s[1])
    assert area[1]["module"] == "retention"
    assert match[1]["match"] == "any" and "Thandi" in match[1]["q"]
    assert area[0] == {"X-Tenant-Id": T, "X-User-Id": T}


def test_no_tenant_or_disabled_means_no_recall(monkeypatch):
    async def fail(*_a, **_k):
        raise AssertionError("must not be called")
    monkeypatch.setattr(mc, "_recall", fail)
    assert asyncio.run(mc.recall_block(None, "retention", "hello")) == ""
    monkeypatch.setattr(mc, "RECALL_ENABLED", False)
    assert asyncio.run(mc.recall_block(T, "retention", "hello")) == ""
