"""A6 tool-policy (SPEC-orchestrator-memory-hardening.md).

Run with cwd = services/agent_orchestrator:  python -m pytest tests -q
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator.tools import TOOL_POLICIES, Tool, policy_for, tool_registry  # noqa: E402


def test_every_registered_tool_has_an_explicit_policy():
    missing = [t.name for t in tool_registry.list_tools() if t.name not in TOOL_POLICIES]
    assert missing == []


def test_policies_are_applied_to_the_registered_tools():
    for tool in tool_registry.list_tools():
        policy = TOOL_POLICIES[tool.name]
        assert (tool.mutates, tool.requires_approval, tool.timeout_s, tool.max_output_chars) == (
            policy.mutates, policy.requires_approval, policy.timeout_s, policy.max_output_chars)


def test_reads_are_not_mutations():
    for name in ("crm_get_customer", "memory.recall", "support_get_tickets",
                 "fno_intelligence.web_intel_competitor_analysis"):
        assert TOOL_POLICIES[name].mutates is False


def test_decided_approval_list():
    # User decision 2026-09-24: create customer, create ticket, provisioning,
    # customer-facing sends, refunds, posting/publishing campaigns.
    assert TOOL_POLICIES["crm_create_customer"].requires_approval
    assert TOOL_POLICIES["support_create_ticket"].requires_approval
    assert not TOOL_POLICIES["memory.write_entry"].requires_approval


def test_unknown_tools_default_to_the_safe_side():
    policy = policy_for("some_new_tool")
    assert policy.mutates and not policy.requires_approval


def test_future_refund_campaign_and_provisioning_tools_need_approval():
    for name in ("billing_issue_refund", "marketing_publish_campaign", "marketing_post_campaign",
                 "network_provision_service", "whatsapp_send_customer_message"):
        assert policy_for(name).requires_approval, name


def test_registering_a_tool_applies_its_policy():
    tool = Tool(name="billing_issue_refund", description="x", service="billing", method="POST",
                endpoint="/refunds", parameters={})
    tool_registry.register(tool)
    try:
        assert tool.mutates and tool.requires_approval
    finally:
        tool_registry._tools.pop("billing_issue_refund", None)
