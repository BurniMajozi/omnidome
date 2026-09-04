"""Task 2: guardrails gate policy tests (strict/standard/audit + require_json)."""

from guardrails.gate import run_gate
from guardrails.validate import validate_json

PII_TEXT = "call me at +27821234567 please"


def test_strict_blocks_on_pii():
    result = run_gate(PII_TEXT, policy="strict")
    assert result["action"] == "block"
    assert result["hits"]


def test_standard_masks():
    result = run_gate(PII_TEXT, policy="standard")
    assert result["action"] == "mask"
    assert "+27821234567" not in result["text"]
    assert "MASKED" in result["text"]


def test_audit_allows_but_returns_hits():
    result = run_gate(PII_TEXT, policy="audit")
    assert result["action"] == "allow"
    assert result["hits"]
    assert result["text"] == PII_TEXT


def test_clean_text_allows_unchanged():
    result = run_gate("hello world, no pii here")
    assert result["action"] == "allow"
    assert result["text"] == "hello world, no pii here"
    assert result["hits"] == []


def test_require_json_blocks_invalid():
    result = run_gate("not json {{{", policy="standard", require_json=True)
    assert result["action"] == "block"
    assert "error" in result


def test_require_json_allows_valid():
    result = run_gate('{"key": "value"}', policy="standard", require_json=True)
    assert result["action"] == "allow"
    assert result["text"] == '{"key": "value"}'


def test_validate_json_helper():
    ok, err = validate_json('{"a": 1}')
    assert ok is True
    assert err is None
    ok, err = validate_json("nope")
    assert ok is False
    assert err
