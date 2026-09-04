"""Dotted audit-taxonomy constants for AgentAction.tool_name rows.

Task 4 (D2): single source of truth so writers (_persist_messages gate
verdicts) and readers (GET /api/agents/actions) agree on names.
Simple constants module — no logic.
"""

AGENT_INVOKED = "agent.invoked"
TOOL_EXECUTED = "tool.executed"
GUARDRAILS_INPUT = "guardrails.input"
GUARDRAILS_OUTPUT = "guardrails.output"
GUARDRAILS_BLOCKED = "guardrails.blocked"
PII_MASKED = "pii.masked"
CHAT_DEPLOYED = "chat.deployed"
