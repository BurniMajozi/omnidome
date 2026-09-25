"""Unit tests for Agent Approval Gate (spec A8 `approval-gate`).

Run with cwd = services/agent_orchestrator:
../../.venv/Scripts/python.exe -m pytest tests/test_approval_gate.py -v
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import os
import sys
import uuid
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator.approvals import (
    approval_ref,
    _format_display_metadata,
    request_approval,
    decide_approval,
    list_approvals,
    get_approval,
    _approval_to_dict,
)
from services.agent_orchestrator.models import AgentApproval
from services.agent_orchestrator.tools import Tool, tool_registry, policy_for
from services.agent_orchestrator.agents import Agent

TENANT = "00000000-0000-0000-0000-000000000001"


def test_approval_ref_formatting():
    u = uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert approval_ref(u) == "APP-12345678"


def test_format_display_metadata_categorization():
    meta_refund = _format_display_metadata("billing", "billing_issue_refund", {"amount": 500})
    assert meta_refund["category"] == "Outage Compensation"
    assert meta_refund["impact"] == "critical"
    assert "Refund R500" in meta_refund["title"]

    meta_camp = _format_display_metadata("executive", "marketing_publish_campaign", {"campaign_name": "Summer Boost"})
    assert meta_camp["category"] == "Pricing Strategy"
    assert meta_camp["impact"] == "high"

    meta_prov = _format_display_metadata("provisioning", "network_provision_circuit", {"circuit_id": "CKT-99"})
    assert meta_prov["category"] == "Network Provisioning"
    assert meta_prov["impact"] == "high"

    meta_ticket = _format_display_metadata("support", "support_create_ticket", {"subject": "Fibre down"})
    assert meta_ticket["category"] == "Outage Compensation"
    assert meta_ticket["agentName"] == "SupportBot"


def test_tool_policies_require_approval_correctly():
    assert policy_for("crm_create_customer").requires_approval is True
    assert policy_for("support_create_ticket").requires_approval is True
    assert policy_for("billing_issue_refund").requires_approval is True
    assert policy_for("marketing_publish_campaign").requires_approval is True
    assert policy_for("network_check_coverage").requires_approval is False
    assert policy_for("analytics.query").requires_approval is False


def test_agent_execute_call_intercepts_approval_required(monkeypatch):
    async def _run():
        executed = []

        async def fake_execute(*args, **kwargs):
            executed.append(kwargs)
            return {"success": True, "data": {"ticket_id": "TCK-1"}}

        # Register temporary test tool requiring approval
        test_tool = Tool(
            name="test_approval_tool",
            description="Creates high risk resource",
            service="support",
            method="POST",
            endpoint="/test",
            parameters={},
            mutates=True,
            requires_approval=True,
        )
        tool_registry._tools["test_approval_tool"] = test_tool

        # Mock request_approval_standalone
        recorded_req = []

        async def fake_request_standalone(**kwargs):
            recorded_req.append(kwargs)
            return {
                "id": "11111111-1111-1111-1111-111111111111",
                "reference": "APP-11111111",
                "status": "pending",
                "message": "Submitted for approval (#APP-11111111); tell the user it will run once approved.",
            }

        monkeypatch.setattr(
            "services.agent_orchestrator.approvals.request_approval_standalone",
            fake_request_standalone,
        )

        agent = Agent(agent_type="support", tenant_id=uuid.UUID(TENANT), context={"user_id": "u-123"})
        name, args, result = await agent._execute_call(
            tc={"name": "test_approval_tool", "arguments": {"customer_id": "C-1"}},
            call_counts={},
            tenant=TENANT,
        )

        try:
            assert name == "test_approval_tool"
            assert result["requires_approval"] is True
            assert result["approval_id"] == "11111111-1111-1111-1111-111111111111"
            assert result["reference"] == "APP-11111111"
            assert "Submitted for approval" in result["message"]
            # Crucial: tool execute was NEVER invoked
            assert len(executed) == 0
            # Approval request was recorded
            assert len(recorded_req) == 1
            assert recorded_req[0]["tool_name"] == "test_approval_tool"
            assert recorded_req[0]["requested_by"] == "u-123"
        finally:
            tool_registry._tools.pop("test_approval_tool", None)

    asyncio.run(_run())


class FakeSession:
    """Lightweight in-memory DB session mock for approvals logic."""
    def __init__(self):
        self.rows = {}
        self.events = []
        self.notifications = []

    def add(self, obj):
        self.rows[str(obj.id)] = obj

    async def flush(self):
        pass


def test_request_approval_stores_row_and_emits_event(monkeypatch):
    async def _run():
        session = FakeSession()

        async def fake_publish(s, tenant_id, event_type, payload, **kwargs):
            session.events.append({"type": event_type, "payload": payload})
            return uuid.uuid4()

        async def fake_notify(s, tenant_id, title, **kwargs):
            session.notifications.append({"tenant_id": tenant_id, "title": title, **kwargs})
            return uuid.uuid4()

        monkeypatch.setattr("services.agent_orchestrator.approvals.publish", fake_publish)
        monkeypatch.setattr("services.agent_orchestrator.approvals.notify", fake_notify)

        res = await request_approval(
            session=session,
            tenant_id=TENANT,
            agent_type="support",
            tool_name="support_create_ticket",
            arguments={"subject": "Outage in Area 4"},
            requested_by="u-test",
        )

        assert res["status"] == "pending"
        assert res["reference"].startswith("APP-")
        assert len(session.rows) == 1
        appr_row = next(iter(session.rows.values()))
        assert appr_row.status == "pending"
        assert appr_row.agent_type == "support"
        assert appr_row.arguments == {"subject": "Outage in Area 4"}

        # Event published
        assert len(session.events) == 1
        assert session.events[0]["type"] == "agents.approval.requested"
        assert session.events[0]["payload"]["tool_name"] == "support_create_ticket"

        # Notification sent
        assert len(session.notifications) == 1
        assert "Approval required" in session.notifications[0]["title"]
        assert session.notifications[0]["category"] == "approval"

    asyncio.run(_run())


def test_decide_approval_approved_executes_tool_idempotently(monkeypatch):
    async def _run():
        appr_id = uuid.uuid4()
        appr_row = AgentApproval(
            id=appr_id,
            tenant_id=uuid.UUID(TENANT),
            agent_type="support",
            tool_name="test_execute_tool",
            arguments={"param": "value"},
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        calls = []

        class MockTool:
            name = "test_execute_tool"
            async def execute(self, tool_input, tenant_id=None, user_id=None):
                calls.append({"input": tool_input, "tenant": tenant_id})
                return {"success": True, "data": {"result_id": "RES-1"}}

        tool_registry._tools["test_execute_tool"] = MockTool()

        class QueryMock:
            def where(self, *args, **kwargs):
                return self
            def with_for_update(self):
                return self
            def scalar_one_or_none(self):
                return appr_row

        class MockSession:
            def __init__(self):
                self.events = []
                self.actions = []

            async def execute(self, stmt, *args, **kwargs):
                return QueryMock()

            def add(self, obj):
                self.actions.append(obj)

            async def flush(self):
                pass

        session = MockSession()

        async def fake_publish(s, tenant_id, event_type, payload, **kwargs):
            session.events.append({"type": event_type, "payload": payload})
            return uuid.uuid4()

        async def fake_notify(*args, **kwargs):
            return uuid.uuid4()

        async def fake_request_in(*args, **kwargs):
            pass

        monkeypatch.setattr("services.agent_orchestrator.approvals.publish", fake_publish)
        monkeypatch.setattr("services.agent_orchestrator.approvals.notify", fake_notify)
        monkeypatch.setattr("services.agent_orchestrator.memory_capture.request_in", fake_request_in)

        try:
            result = await decide_approval(
                session=session,
                tenant_id=TENANT,
                approval_id=appr_id,
                decision="approved",
                decided_by="admin-user",
            )

            assert result["status"] == "approved"
            assert result["decided_by"] == "admin-user"
            assert len(calls) == 1
            assert calls[0]["input"] == {"param": "value"}
            assert appr_row.executed_at is not None
            assert appr_row.execution_result == {"success": True, "data": {"result_id": "RES-1"}}

            # Event published
            decided_events = [e for e in session.events if e["type"] == "agents.approval.decided"]
            assert len(decided_events) == 1
            assert decided_events[0]["payload"]["decision"] == "approved"

            # Re-running execution on same row is idempotent
            from services.agent_orchestrator.approvals import _execute_approved_call
            second_res = await _execute_approved_call(session, appr_row)
            assert len(calls) == 1  # Tool NOT called a second time
            assert second_res == {"success": True, "data": {"result_id": "RES-1"}}
        finally:
            tool_registry._tools.pop("test_execute_tool", None)

    asyncio.run(_run())


def test_decide_approval_rejected_does_not_execute(monkeypatch):
    async def _run():
        appr_id = uuid.uuid4()
        appr_row = AgentApproval(
            id=appr_id,
            tenant_id=uuid.UUID(TENANT),
            agent_type="support",
            tool_name="test_rejected_tool",
            arguments={"param": "value"},
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        calls = []

        class MockTool:
            name = "test_rejected_tool"
            async def execute(self, *args, **kwargs):
                calls.append(kwargs)
                return {"success": True}

        tool_registry._tools["test_rejected_tool"] = MockTool()

        class QueryMock:
            def where(self, *args, **kwargs):
                return self
            def with_for_update(self):
                return self
            def scalar_one_or_none(self):
                return appr_row

        class MockSession:
            def __init__(self):
                self.events = []
            async def execute(self, stmt, *args, **kwargs):
                return QueryMock()
            def add(self, obj):
                pass
            async def flush(self):
                pass

        session = MockSession()

        async def fake_publish(s, tenant_id, event_type, payload, **kwargs):
            session.events.append({"type": event_type, "payload": payload})
            return uuid.uuid4()

        async def fake_notify(*args, **kwargs):
            return uuid.uuid4()

        async def fake_request_in(*args, **kwargs):
            pass

        monkeypatch.setattr("services.agent_orchestrator.approvals.publish", fake_publish)
        monkeypatch.setattr("services.agent_orchestrator.approvals.notify", fake_notify)
        monkeypatch.setattr("services.agent_orchestrator.memory_capture.request_in", fake_request_in)

        try:
            result = await decide_approval(
                session=session,
                tenant_id=TENANT,
                approval_id=appr_id,
                decision="rejected",
                decided_by="admin-user",
                reason="Too risky",
            )

            assert result["status"] == "rejected"
            assert result["rejection_reason"] == "Too risky"
            # Crucial: tool execute was NEVER invoked
            assert len(calls) == 0
            assert appr_row.executed_at is None
        finally:
            tool_registry._tools.pop("test_rejected_tool", None)

    asyncio.run(_run())


def test_decide_approval_expired_raises():
    async def _run():
        appr_id = uuid.uuid4()
        appr_row = AgentApproval(
            id=appr_id,
            tenant_id=uuid.UUID(TENANT),
            agent_type="support",
            tool_name="test_tool",
            arguments={},
            status="pending",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # expired!
        )

        class QueryMock:
            def where(self, *args, **kwargs):
                return self
            def with_for_update(self):
                return self
            def scalar_one_or_none(self):
                return appr_row

        class MockSession:
            async def execute(self, stmt, *args, **kwargs):
                return QueryMock()
            async def flush(self):
                pass

        session = MockSession()

        with pytest.raises(ValueError, match="expired"):
            await decide_approval(
                session=session,
                tenant_id=TENANT,
                approval_id=appr_id,
                decision="approved",
                decided_by="admin",
            )

    asyncio.run(_run())
