"""Pure unit tests for the Task 4 (D2) audit taxonomy — no DB involved."""

import audit_actions as aa


def test_agent_invoked():
    assert aa.AGENT_INVOKED == "agent.invoked"


def test_tool_executed():
    assert aa.TOOL_EXECUTED == "tool.executed"


def test_guardrails_input():
    assert aa.GUARDRAILS_INPUT == "guardrails.input"


def test_guardrails_output():
    assert aa.GUARDRAILS_OUTPUT == "guardrails.output"


def test_guardrails_blocked():
    assert aa.GUARDRAILS_BLOCKED == "guardrails.blocked"


def test_pii_masked():
    assert aa.PII_MASKED == "pii.masked"


def test_chat_deployed():
    assert aa.CHAT_DEPLOYED == "chat.deployed"


def test_taxonomy_values_are_unique_dotted_names():
    values = [
        aa.AGENT_INVOKED,
        aa.TOOL_EXECUTED,
        aa.GUARDRAILS_INPUT,
        aa.GUARDRAILS_OUTPUT,
        aa.GUARDRAILS_BLOCKED,
        aa.PII_MASKED,
        aa.CHAT_DEPLOYED,
    ]
    assert len(set(values)) == len(values)
    for v in values:
        assert isinstance(v, str) and v == v.lower() and "." in v
