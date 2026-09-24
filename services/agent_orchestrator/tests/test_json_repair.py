"""A1 tool-call-repair (SPEC-orchestrator-memory-hardening.md).

Free/cheap models often emit malformed tool-call arguments. Today a parse error
becomes {} and the tool runs with no arguments. Repairable malformations are
fixed; arguments that were cut off are refused so the model re-issues the call.

Run with cwd = services/agent_orchestrator:  python -m pytest tests -q
"""

import json
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator.json_repair import parse_tool_arguments, repair_json  # noqa: E402


def loads(raw):
    repaired, truncated = repair_json(raw)
    return json.loads(repaired), truncated


def test_valid_json_is_unchanged():
    assert loads('{"a": 1, "b": "x"}') == ({"a": 1, "b": "x"}, False)


def test_trailing_commas():
    assert loads('{"a": [1, 2,], "b": 3,}') == ({"a": [1, 2], "b": 3}, False)


def test_single_quotes():
    assert loads("{'query': 'fibre in Sea Point', 'limit': 5}") == ({"query": "fibre in Sea Point", "limit": 5}, False)


def test_double_quote_inside_single_quoted_string():
    assert loads("{'note': 'say \"hi\"'}") == ({"note": 'say "hi"'}, False)


def test_unquoted_keys():
    assert loads('{query: "fibre", limit: 5}') == ({"query": "fibre", "limit": 5}, False)


def test_python_literals():
    assert loads("{'active': True, 'owner': None}") == ({"active": True, "owner": None}, False)


def test_invalid_escapes_become_literal_backslashes():
    value, truncated = loads(r'{"pattern": "\d+\.log$", "ok": "line\nbreak"}')
    assert value == {"pattern": r"\d+\.log$", "ok": "line\nbreak"} and not truncated


def test_extra_tokens_after_the_first_value_are_dropped():
    assert loads('{"a": 1}{"a": 1}') == ({"a": 1}, False)
    assert loads('{"a": 1} trailing text') == ({"a": 1}, False)


def test_raw_newline_inside_string():
    assert loads('{"body": "line one\nline two"}') == ({"body": "line one\nline two"}, False)


def test_cut_off_string_is_flagged_truncated():
    _, truncated = repair_json('{"query": "fibre in Sea')
    assert truncated


def test_missing_closing_brace_is_flagged_truncated():
    _, truncated = repair_json('{"a": 1, "b": [1, 2')
    assert truncated


# ── parse_tool_arguments: what the agent loop uses ─────────────────────────

def test_parse_accepts_dicts_and_empty():
    assert parse_tool_arguments({"a": 1}) == ({"a": 1}, None)
    assert parse_tool_arguments("") == ({}, None)
    assert parse_tool_arguments(None) == ({}, None)


def test_parse_repairs_malformed_arguments():
    assert parse_tool_arguments("{'customer_id': 'C-1',}") == ({"customer_id": "C-1"}, None)


def test_parse_refuses_cut_off_arguments():
    args, error = parse_tool_arguments('{"query": "fibre in Sea')
    assert args is None and "cut off" in error


def test_parse_refuses_non_objects_and_garbage():
    assert parse_tool_arguments("[1, 2]")[0] is None
    assert parse_tool_arguments("not json at all")[0] is None
    assert parse_tool_arguments(42)[0] is None


@pytest.mark.parametrize("raw", ['{"a": 1}', "{'a': 1}", '{a: 1,}'])
def test_repair_is_idempotent(raw):
    once, _ = repair_json(raw)
    twice, _ = repair_json(once)
    assert once == twice
