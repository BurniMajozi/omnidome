"""M5 memory-housekeeping (SPEC-orchestrator-memory-hardening.md).

Run with cwd = services/agent_orchestrator:  python -m pytest tests/test_memory_housekeeping.py -q
"""

import asyncio
from datetime import datetime, timedelta, timezone
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator import memory_housekeeping as mh

NOW = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
T = "00000000-0000-0000-0000-000000000001"


def make_entry(
    id: str,
    module: str = "sales",
    scope_key: str = "lead_123",
    title: str = "Meeting notes",
    content: str = "Customer agreed to proposal",
    importance: str = "normal",
    days_ago: int = 10,
    archived_at: str | None = None,
):
    return {
        "id": id,
        "tenant_id": T,
        "module": module,
        "scope_key": scope_key,
        "title": title,
        "content": content,
        "importance": importance,
        "occurred_at": NOW - timedelta(days=days_ago),
        "archived_at": archived_at,
    }


def test_find_duplicates_keeps_earliest_and_archives_later_identical_entries():
    e1 = make_entry("e1", days_ago=40)
    e2 = make_entry("e2", days_ago=20)  # duplicate of e1, occurred later
    e3 = make_entry("e3", days_ago=15, content="Different content")

    dup_ids, remaining = mh.find_duplicates([e1, e2, e3])
    assert dup_ids == ["e2"]
    assert [e["id"] for e in remaining] == ["e1", "e3"]


def test_find_low_importance_stale_flags_entries_older_than_threshold():
    e_recent_low = make_entry("e1", importance="low", days_ago=30)
    e_stale_low = make_entry("e2", importance="low", days_ago=95)
    e_stale_normal = make_entry("e3", importance="normal", days_ago=100)

    stale_ids, remaining = mh.find_low_importance_stale([e_recent_low, e_stale_low, e_stale_normal], now=NOW, max_days=90)
    assert stale_ids == ["e2"]
    assert [e["id"] for e in remaining] == ["e1", "e3"]


def test_group_for_rollup_groups_by_module_and_scope_key():
    e1 = make_entry("e1", module="sales", scope_key="lead_1", days_ago=45)
    e2 = make_entry("e2", module="sales", scope_key="lead_1", days_ago=40)
    e3 = make_entry("e3", module="support", scope_key="ticket_5", days_ago=35)
    e_recent = make_entry("e4", module="sales", scope_key="lead_1", days_ago=10)

    groups = mh.group_for_rollup([e1, e2, e3, e_recent], now=NOW, rollup_days=30)
    assert len(groups) == 2
    assert ("sales", "lead_1") in groups
    assert ("support", "ticket_5") in groups
    assert [e["id"] for e in groups[("sales", "lead_1")]] == ["e1", "e2"]
    assert [e["id"] for e in groups[("support", "ticket_5")]] == ["e3"]


def test_plan_housekeeping_does_not_double_count_entries():
    # e_dup is a duplicate of e1
    e1 = make_entry("e1", content="Proposal discussion", days_ago=40)
    e_dup = make_entry("e_dup", content="Proposal discussion", days_ago=35)
    # e_low is low importance and > 90 days with unique content
    e_low = make_entry("e_low", content="Low priority ping", importance="low", days_ago=100)
    # e_recent is active and within 30 days with unique content
    e_recent = make_entry("e_recent", content="Recent check-in", days_ago=5)

    entries = [e1, e_dup, e_low, e_recent]
    plan = mh.plan_housekeeping(entries, now=NOW, rollup_days=30, low_importance_days=90)

    assert plan["duplicates_count"] == 1
    assert plan["duplicate_ids"] == ["e_dup"]
    assert plan["low_importance_count"] == 1
    assert plan["low_importance_ids"] == ["e_low"]
    assert len(plan["rollups"]) == 1
    assert plan["rollups"][0]["entry_ids"] == ["e1"]
    assert plan["total_archived_count"] == 3  # e_dup, e_low, e1 (rolled up)


def test_run_housekeeping_dry_run_calls_no_summariser():
    entries = [make_entry("e1", content="Discussion A", days_ago=40), make_entry("e2", content="Discussion B", days_ago=40)]
    summariser_called = False

    async def fake_summariser(prev, ents):
        nonlocal summariser_called
        summariser_called = True
        return "Summary"

    plan = asyncio.run(mh.execute_housekeeping_plan(
        entries=entries,
        existing_summaries={},
        now=NOW,
        dry_run=True,
        summariser=fake_summariser,
    ))

    assert not summariser_called
    assert plan["dry_run"] is True
    assert plan["entries_rolled_up"] == 2
    assert len(plan["rollups"]) == 1


def test_run_housekeeping_live_generates_summaries_for_groups():
    e1 = make_entry("e1", module="sales", scope_key="lead_A", content="Notes A", days_ago=40)
    e2 = make_entry("e2", module="support", scope_key="ticket_B", content="Notes B", days_ago=50)
    calls = []

    async def fake_summariser(prev, ents):
        calls.append((prev, [e["id"] for e in ents]))
        return f"Rolled up summary for {ents[0]['module']}"

    result = asyncio.run(mh.execute_housekeeping_plan(
        entries=[e1, e2],
        existing_summaries={("sales", "lead_A"): "Old sales summary"},
        now=NOW,
        dry_run=False,
        summariser=fake_summariser,
    ))

    assert result["dry_run"] is False
    assert len(calls) == 2
    sales_call = next(c for c in calls if "e1" in c[1])
    support_call = next(c for c in calls if "e2" in c[1])
    assert sales_call[0] == "Old sales summary"
    assert support_call[0] == ""
    assert len(result["new_summaries"]) == 2
