"""A7 usage-tracing (SPEC-orchestrator-memory-hardening.md) — pure parts.
The inserts and the /api/usage/llm aggregate are verified live.

Run with cwd = services/agent_orchestrator:  python -m pytest tests -q
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator.usage import call_outcome, tokens_from  # noqa: E402


def test_tokens_from_openrouter_usage():
    assert tokens_from({"usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}}) == (120, 30, 150)


def test_tokens_total_is_derived_when_missing():
    assert tokens_from({"usage": {"prompt_tokens": 10, "completion_tokens": 5}}) == (10, 5, 15)


def test_tokens_absent_are_zero():
    assert tokens_from({}) == (0, 0, 0)
    assert tokens_from({"usage": None}) == (0, 0, 0)


def test_call_outcome():
    assert call_outcome({"content": "hi"}) == "answer"
    assert call_outcome({"content": "", "tool_calls": [{"name": "x"}]}) == "tool_calls"
    assert call_outcome({"unavailable": True}) == "unavailable"
    assert call_outcome({"content": "", "tool_calls": []}) == "empty"
    assert call_outcome(None) == "error"
