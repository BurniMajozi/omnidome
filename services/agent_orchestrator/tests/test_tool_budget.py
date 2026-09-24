"""A3 tool-output-budget (SPEC-orchestrator-memory-hardening.md).

Run with cwd = services/agent_orchestrator:  python -m pytest tests -q
"""

import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator.tool_budget import budget_tool_result, split_budget_fairly  # noqa: E402


def test_fair_split_gives_small_entries_their_size_and_shares_the_rest():
    assert split_budget_fairly(100, [10, 50, 80]) == [10, 45, 45]


def test_fair_split_never_exceeds_sizes_or_total():
    caps = split_budget_fairly(1000, [5, 700, 20, 900])
    assert sum(caps) <= 1000
    assert all(c <= s for c, s in zip(caps, [5, 700, 20, 900]))
    assert split_budget_fairly(10_000, [5, 7]) == [5, 7]


def test_small_results_pass_through_unchanged():
    result = {"success": True, "data": {"balance": 499.0}}
    assert budget_tool_result(result, 8000) == json.dumps(result, default=str)


def test_large_lists_keep_every_record_and_trim_the_largest():
    records = [{"id": f"T-{i:03d}", "subject": "Fibre down", "notes": "x" * (200 + 40 * i)} for i in range(50)]
    out = budget_tool_result({"success": True, "data": records}, 4000)
    assert len(out) <= 4000 + 300                          # budget plus the explanatory header
    assert all(f"T-{i:03d}" in out for i in range(50))     # nothing dropped
    assert "trimmed" in out.lower() and "50 records" in out


def test_lists_nested_under_a_key_are_found():
    rows = [{"id": i, "blob": "y" * 500} for i in range(40)]
    out = budget_tool_result({"success": True, "data": {"total": 40, "items": rows}}, 3000)
    assert "40 records" in out and '"total": 40' in out


def test_large_non_list_output_keeps_head_and_tail():
    text = "HEAD-" + ("m" * 20_000) + "-TAIL"
    out = budget_tool_result({"success": True, "data": text}, 2000)
    assert "HEAD-" in out and "-TAIL" in out and "trimmed" in out.lower()
    assert len(out) <= 2000 + 200
