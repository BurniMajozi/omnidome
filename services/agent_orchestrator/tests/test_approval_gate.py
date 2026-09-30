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


def test_decide_approval_approved_records_the_decision_without_running_the_tool(monkeypatch):
    # The decision commits on its own; the tool runs afterwards in
    # execute_approved (a failed commit can no longer follow a real side effect).
    async def _run():
        appr_id = uuid.uuid4()
        appr_row = AgentApproval(
            id=appr_id, tenant_id=uuid.UUID(TENANT), agent_type="support", tool_name="test_execute_tool",
            arguments={"param": "value"}, status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        calls = []

        class MockTool:
            name = "test_execute_tool"
            async def execute(self, tool_input, tenant_id=None, user_id=None):
                calls.append(tool_input)
                return {"success": True}

        tool_registry._tools["test_execute_tool"] = MockTool()

        class QueryMock:
            def scalar_one_or_none(self):
                return appr_row

        class MockSession:
            events = []
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

        monkeypatch.setattr("services.agent_orchestrator.approvals.publish", fake_publish)
        monkeypatch.setattr("services.agent_orchestrator.approvals.notify", fake_notify)
        try:
            result = await decide_approval(session=session, tenant_id=TENANT, approval_id=appr_id,
                                           decision="approved", decided_by="admin-user")
            assert result["status"] == "approved" and result["decided_by"] == "admin-user"
            assert calls == [] and appr_row.executed_at is None
            decided = [e for e in session.events if e["type"] == "agents.approval.decided"]
            assert len(decided) == 1 and decided[0]["payload"]["decision"] == "approved"
        finally:
            tool_registry._tools.pop("test_execute_tool", None)

    asyncio.run(_run())


class ClaimStore:
    """Stands in for the agent_approvals row: claim() succeeds once, like the
    UPDATE ... WHERE execution_started_at IS NULL RETURNING in approvals._claim."""

    def __init__(self, row, fail_record=False):
        self.row, self.claimed, self.fail_record, self.recorded = row, False, fail_record, []

    async def claim(self, tenant_id, approval_id):
        if self.claimed or self.row.status != "approved":
            return None
        self.claimed = True
        return self.row

    async def record(self, row, result):
        if self.fail_record:
            raise RuntimeError("database went away")
        self.recorded.append(result)


def _approved_row(tool_name):
    return AgentApproval(id=uuid.uuid4(), tenant_id=uuid.UUID(TENANT), agent_type="crm", tool_name=tool_name,
                         arguments={"first_name": "TEST"}, status="approved", requested_by="crm",
                         decided_by="11111111-1111-1111-1111-111111111111",
                         expires_at=datetime.now(timezone.utc) + timedelta(hours=24))


def _tool(name, calls, raises=False):
    class T:
        async def execute(self, tool_input, tenant_id=None, user_id=None):
            calls.append((tool_input, user_id))
            if raises:
                raise ConnectionError("crm down")
            return {"success": True, "data": {"id": "c1"}}
    tool_registry._tools[name] = T()


@pytest.mark.parametrize("fail_record", [False, True])
def test_approved_call_runs_at_most_once(monkeypatch, fail_record):
    from services.agent_orchestrator import approvals
    calls, name = [], "test_once_tool"
    _tool(name, calls)
    store = ClaimStore(_approved_row(name), fail_record=fail_record)
    monkeypatch.setattr(approvals, "_claim", store.claim)
    monkeypatch.setattr(approvals, "_record", store.record)
    try:
        for _ in range(3):   # the approve route, the bus consumer, a retry
            try:
                asyncio.run(approvals.execute_approved(TENANT, store.row.id))
            except RuntimeError:
                pass         # recording failed: the claim still stands, so nothing re-runs
        assert len(calls) == 1
        assert calls[0][1] == "11111111-1111-1111-1111-111111111111"   # runs as the approver
    finally:
        tool_registry._tools.pop(name, None)


def test_a_failing_tool_is_recorded_as_failed(monkeypatch):
    from services.agent_orchestrator import approvals
    calls, name = [], "test_failing_tool"
    _tool(name, calls, raises=True)
    store = ClaimStore(_approved_row(name))
    monkeypatch.setattr(approvals, "_claim", store.claim)
    monkeypatch.setattr(approvals, "_record", store.record)
    try:
        out = asyncio.run(approvals.execute_approved(TENANT, store.row.id))
        assert out["success"] is False and "crm down" in out["error"]
        assert store.recorded == [out]
    finally:
        tool_registry._tools.pop(name, None)


def test_nothing_runs_unless_the_approval_is_approved(monkeypatch):
    from services.agent_orchestrator import approvals
    calls, name = [], "test_pending_tool"
    _tool(name, calls)
    row = _approved_row(name)
    row.status = "rejected"
    store = ClaimStore(row)
    monkeypatch.setattr(approvals, "_claim", store.claim)
    monkeypatch.setattr(approvals, "_record", store.record)
    try:
        assert asyncio.run(approvals.execute_approved(TENANT, row.id)) is None and calls == []
    finally:
        tool_registry._tools.pop(name, None)


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


def test_approved_call_runs_as_a_real_user_not_the_agent_name():
    # Live checkpoint 3: an agent-requested approval ran with X-User-Id "crm"
    # and crm answered 401 "Invalid user_id". Run as the requester when that is
    # a user, otherwise as the person who approved it.
    from services.agent_orchestrator.approvals import acting_user_id
    approver = "11111111-1111-1111-1111-111111111111"
    requester = "22222222-2222-2222-2222-222222222222"
    assert acting_user_id(AgentApproval(requested_by=requester, decided_by=approver)) == requester
    assert acting_user_id(AgentApproval(requested_by="crm", decided_by=approver)) == approver
    assert acting_user_id(AgentApproval(requested_by="", decided_by=approver)) == approver
