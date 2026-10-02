"""Unit tests for Jev System One dynamic tool gating and in-flight HITL resumption."""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
import pytest
from unittest.mock import AsyncMock, patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator.jev_gate import (
    evaluate_tool_call,
    _deterministic_pre_check,
    route_agent_intent,
    triage_inbound_inquiry,
    verify_agent_response,
    JevGateVerdict,
    JevRouteDecision,
    JevTriageDecision,
    JevVerificationVerdict,
    APPROVE_AT,
    BLOCK_AT,
)
from services.agent_orchestrator.approvals import (
    _format_display_metadata,
    request_approval_standalone,
    execute_approved,
    mark_conversation_awaiting_hitl,
    resume_conversation,
)
from services.agent_orchestrator.models import AgentApproval, AgentConversation, AgentMessage
from services.agent_orchestrator.tools import Tool, tool_registry
from services.agent_orchestrator.agents import Agent


class DummyReadTool:
    name = "dummy_read"
    description = "Read diagnostic info"
    mutates = False
    requires_approval = False

    async def execute(self, tool_input, **kwargs):
        return {"status": "ok", "value": 42}


class DummyCreditTool:
    name = "billing_issue_credit"
    description = "Issue a billing credit or refund to customer account"
    mutates = True
    requires_approval = True

    async def execute(self, tool_input, **kwargs):
        return {"credited": True}


def test_jev_gate_read_only_fast_path():
    """Non-mutating read-only tools should immediately auto-approve without external API calls."""
    async def _run():
        tool = DummyReadTool()
        verdict = await evaluate_tool_call(
            agent_type="support",
            tool_name="dummy_read",
            arguments={},
            tool=tool,
        )
        assert verdict.action == "auto_approve"
        assert verdict.risk_score == 1.0
        assert verdict.evaluated_by_jev is False

    asyncio.run(_run())


def test_deterministic_pre_check_blocks_ceiling_and_danger():
    """Cookbook step 3: code checks call first before sending to Jev."""
    # Exceeds platform ceiling
    err1 = _deterministic_pre_check("billing_issue_credit", {"amount": 25000})
    assert err1 is not None and "exceeds platform ceiling" in err1

    # Destructive SQL/wipe statement
    err2 = _deterministic_pre_check("database_query", {"query": "DROP TABLE customers"})
    assert err2 is not None and "Destructive statement" in err2

    # Negative amount
    err3 = _deterministic_pre_check("billing_issue_credit", {"amount": -50})
    assert err3 is not None and "greater than 0" in err3

    # Safe amount passes pre-check
    assert _deterministic_pre_check("billing_issue_credit", {"amount": 75}) is None


def test_jev_gate_fallback_when_disabled():
    """When Jev is disabled or key is missing, safe fallback matches static requires_approval."""
    async def _run():
        with patch("services.agent_orchestrator.jev_gate.settings.jev_gate_enabled", False):
            tool = DummyCreditTool()
            verdict = await evaluate_tool_call(
                agent_type="billing",
                tool_name="billing_issue_credit",
                arguments={"amount": 75},
                tool=tool,
            )
            assert verdict.action == "require_approval"
            assert verdict.evaluated_by_jev is False

    asyncio.run(_run())


def test_jev_gate_live_evaluation_3_noul_propositions():
    """If TYPESAFE_API_KEY is configured in .env, verify live evaluation against TypeSafe System One."""
    async def _run():
        from dotenv import load_dotenv
        load_dotenv(os.path.join(REPO_ROOT, ".env"))

        key = os.getenv("TYPESAFE_API_KEY", "").strip().strip("'\"")
        if not key:
            pytest.skip("TYPESAFE_API_KEY not set in environment")

        tool = DummyCreditTool()
        verdict = await evaluate_tool_call(
            agent_type="billing",
            tool_name="billing_issue_credit",
            arguments={"account_id": "ACC-901", "amount": 150, "reason": "Customer requested compensation for verified outage"},
            tool=tool,
            customer_message="My fiber was down for 6 hours yesterday on account ACC-901. Please credit my account.",
        )
        assert verdict.evaluated_by_jev is True
        assert verdict.checks is not None
        # Verify all 3 cookbook Noul propositions were answered
        assert "customer_asked" in verdict.checks
        assert "right_target" in verdict.checks
        assert "policy_covers" in verdict.checks

        # Probabilities should be valid float numbers in [0.0, 1.0] and lean positive (> 0.50)
        assert 0.0 <= verdict.checks["customer_asked"] <= 1.0
        assert verdict.checks["customer_asked"] > 0.50
        assert 0.0 <= verdict.checks["right_target"] <= 1.0
        assert verdict.checks["right_target"] > 0.50
        assert 0.0 <= verdict.checks["policy_covers"] <= 1.0
        assert verdict.action in ("auto_approve", "require_approval")

    asyncio.run(_run())


def test_format_display_metadata_with_jev_info():
    """Display metadata should incorporate Jev risk rating and reason."""
    meta = _format_display_metadata(
        agent_type="support",
        tool_name="reboot_ont",
        arguments={
            "ont_id": "ONT-99",
            "_jev_gate": {
                "action": "require_approval",
                "risk_score": 4.0,
                "reason": "failed policy_covers=0.08",
                "evaluated_by_jev": True,
            },
        },
    )
    assert meta["impact"] == "high"
    assert "Jev System One (Risk 4.0/5.0" in meta["context"]


def test_execute_approved_with_custom_output_override():
    """Cookbook HITL pattern: human supplies custom tool output (onResponseReceived)."""
    async def _run():
        mock_row = AgentApproval(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            agent_type="billing",
            tool_name="billing_issue_refund",
            arguments={"customer_id": "C-1", "amount": 500},
            status="approved",
            conversation_id=None,
        )

        custom_human_output = {"approved": True, "custom_amount": 250, "reviewer": "Manager"}

        with patch("services.agent_orchestrator.approvals._claim", AsyncMock(return_value=mock_row)), \
             patch("services.agent_orchestrator.approvals._record", AsyncMock()):
            result = await execute_approved(
                tenant_id=mock_row.tenant_id,
                approval_id=mock_row.id,
                custom_output=custom_human_output,
                resume=False,
            )

        assert result is not None
        assert result == custom_human_output

    asyncio.run(_run())


def test_route_agent_intent_fallback_when_disabled():
    """When Jev is disabled, fallback cleanly to keyword classification."""
    async def _run():
        with patch("services.agent_orchestrator.jev_gate.settings.jev_gate_enabled", False):
            res = await route_agent_intent("I need to troubleshoot a fault on my line")
            assert res.target_agent == "support"
            assert res.evaluated_by_jev is False

    asyncio.run(_run())


def test_route_agent_intent_live_evaluation():
    """Live Jev Choice routing test if TYPESAFE_API_KEY is configured."""
    async def _run():
        from dotenv import load_dotenv
        load_dotenv(os.path.join(REPO_ROOT, ".env"))

        key = os.getenv("TYPESAFE_API_KEY", "").strip().strip("'\"")
        if not key:
            pytest.skip("TYPESAFE_API_KEY not configured")

        res = await route_agent_intent("My router has a red flashing LOS optical light and zero internet connection.")
        assert res.evaluated_by_jev is True
        assert res.target_agent == "support"
        assert res.confidence >= 0.70
        assert "support" in res.distribution
        assert res.distribution["support"] >= 0.70

    asyncio.run(_run())


def test_verify_agent_response_live_evaluation():
    """Live Jev output verification test if TYPESAFE_API_KEY is configured."""
    async def _run():
        from dotenv import load_dotenv
        load_dotenv(os.path.join(REPO_ROOT, ".env"))

        key = os.getenv("TYPESAFE_API_KEY", "").strip().strip("'\"")
        if not key:
            pytest.skip("TYPESAFE_API_KEY not configured")

        # Grounded and accurate draft
        v_good = await verify_agent_response(
            customer_message="What is my account balance?",
            draft_response="According to our billing records, your current outstanding balance is R450.00.",
            tool_records=[{"name": "billing_get_balance", "result": {"balance": 450.00, "status": "active"}}],
            agent_type="billing",
        )
        assert v_good.evaluated_by_jev is True
        assert v_good.passed is True
        assert v_good.action == "accept"
        assert v_good.answers_inquiry >= 0.70
        assert v_good.grounded_in_facts >= 0.70

    asyncio.run(_run())


def test_triage_inbound_inquiry_fallback_when_disabled():
    """When Jev is disabled, triage falls back cleanly with 0.0 scores."""
    async def _run():
        with patch("services.agent_orchestrator.jev_gate.settings.jev_gate_enabled", False):
            res = await triage_inbound_inquiry("I need to troubleshoot a fault on my line")
            assert res.target_agent == "support"
            assert res.evaluated_by_jev is False
            assert res.frustration_score == 0.0
            assert res.churn_risk_score == 0.0
            assert res.requires_immediate_escalation is False

    asyncio.run(_run())


def test_triage_inbound_inquiry_live_evaluation():
    """Live Jev triage testing Choice, Score, and Noul unified in one call."""
    async def _run():
        from dotenv import load_dotenv
        load_dotenv(os.path.join(REPO_ROOT, ".env"))

        key = os.getenv("TYPESAFE_API_KEY", "").strip().strip("'\"")
        if not key:
            pytest.skip("TYPESAFE_API_KEY not configured")

        res = await triage_inbound_inquiry(
            "This is the THIRD TIME this week my fiber died! Your service is absolute garbage. Cancel my subscription immediately, I am switching to Vodacom!"
        )
        assert res.evaluated_by_jev is True
        assert res.target_agent in ("retention", "support")
        assert res.frustration_score is not None
        assert res.frustration_score >= 1.0  # Frustrated or extremely angry
        assert res.churn_risk_score is not None
        assert res.churn_risk_score >= 1.0  # Considering alternatives or explicit cancellation
        assert res.requires_immediate_escalation is True

    asyncio.run(_run())
