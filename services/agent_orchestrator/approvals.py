"""Approval gate runtime and persistence (spec A8 `approval-gate`).

When an agent encounters a tool with `requires_approval=True`, execution is gated:
1. An `agent_approvals` row is stored with status='pending' and 24h expiration.
2. `agents.approval.requested` is published on the event bus.
3. A notification is added to the in-app bell feed.
4. The model receives: "Submitted for approval (#ref); tell the user it will run once approved."
5. When approved: `agents.approval.decided` is published, the tool is executed
   idempotently, results are recorded, and memory capture is triggered.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text

from services.common.db import session_scope
from services.common.event_bus import EventConsumer, notify, publish
from services.agent_orchestrator.models import AgentAction, AgentApproval
from services.agent_orchestrator import memory_capture
from services.agent_orchestrator.tools import tool_registry

logger = logging.getLogger(__name__)

EVENT_APPROVAL_REQUESTED = "agents.approval.requested"
EVENT_APPROVAL_DECIDED = "agents.approval.decided"
DEFAULT_EXPIRATION_HOURS = int(os.getenv("APPROVAL_EXPIRATION_HOURS", "24"))

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_approvals (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    tool_name VARCHAR(100) NOT NULL,
    arguments JSONB NOT NULL DEFAULT '{}'::jsonb,
    conversation_id UUID,
    run_id UUID,
    requested_by VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    rejection_reason TEXT,
    execution_result JSONB,
    executed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    decided_at TIMESTAMPTZ,
    decided_by VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_agent_approvals_tenant_status ON agent_approvals (tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_agent_approvals_agent ON agent_approvals (tenant_id, agent_type, status);
"""


async def ensure_schema(session) -> None:
    """Ensure agent_approvals table exists."""
    for statement in SCHEMA_SQL.split(";"):
        if re.sub(r"--[^\n]*", "", statement).strip():
            await session.execute(text(statement))


def approval_ref(approval_id: uuid.UUID | str) -> str:
    """Format short reference like APP-7A3B9C."""
    return f"APP-{str(approval_id)[:8].upper()}"


def _format_display_metadata(agent_type: str, tool_name: str, arguments: dict) -> dict:
    """Build UI summary, impact and category for Executive Approval Queue."""
    agent_names = {
        "executive": "InsightDome",
        "retention": "ChurnGuard",
        "support": "SupportBot",
        "provisioning": "ProvisionBot",
        "billing": "BillMaster",
        "customer_facing": "DomeBot",
        "analytics": "MetricBot",
        "sales": "SalesDirector",
    }
    agent_icons = {
        "executive": "📊",
        "retention": "🛡️",
        "support": "🔧",
        "provisioning": "⚡",
        "billing": "💳",
        "customer_facing": "🤖",
        "analytics": "📈",
        "sales": "🎯",
    }

    category = "General"
    impact = "medium"
    title = f"{tool_name.replace('_', ' ').title()}"

    if "refund" in tool_name:
        category = "Outage Compensation"
        impact = "critical"
        amt = arguments.get("amount") or arguments.get("total") or ""
        title = f"Issue Customer Refund {f'R{amt}' if amt else ''}".strip()
    elif "campaign" in tool_name or "publish" in tool_name:
        category = "Pricing Strategy"
        impact = "high"
        title = f"Publish Marketing Campaign: {arguments.get('campaign_name', 'OmniDome Promo')}"
    elif "provision" in tool_name:
        category = "Network Provisioning"
        impact = "high"
        title = f"Approve Provisioning: {arguments.get('account_number') or arguments.get('circuit_id') or 'Circuit'}"
    elif "ticket" in tool_name:
        category = "Outage Compensation"
        impact = "medium"
        title = f"Create Support Ticket: {arguments.get('subject', 'Customer Issue')}"
    elif "customer" in tool_name:
        category = "Retention Save"
        impact = "high"
        title = f"Create Customer Record: {arguments.get('first_name', '')} {arguments.get('last_name', '')}".strip()

    args_str = ", ".join(f"{k}={v}" for k, v in arguments.items() if v)
    summary = f"{agent_type} requested execution of {tool_name}. Parameters: {args_str or 'none'}."
    context = f"Requires executive authorization before execution. Target service: {tool_name.split('_')[0]}."

    return {
        "agentName": agent_names.get(agent_type, agent_type.capitalize()),
        "agentIcon": agent_icons.get(agent_type, "🤖"),
        "title": title,
        "impact": impact,
        "category": category,
        "summary": summary,
        "context": context,
    }


async def request_approval(
    session,
    tenant_id: str | uuid.UUID,
    agent_type: str,
    tool_name: str,
    arguments: dict,
    conversation_id: Optional[uuid.UUID | str] = None,
    run_id: Optional[uuid.UUID | str] = None,
    requested_by: Optional[str] = None,
) -> dict:
    """Store approval request in caller's session, publish event and raise notification."""
    approval_id = uuid.uuid4()
    ref = approval_ref(approval_id)
    t_id = uuid.UUID(str(tenant_id))
    conv_uuid = uuid.UUID(str(conversation_id)) if conversation_id else None
    run_uuid = uuid.UUID(str(run_id)) if run_id else None
    expires_at = datetime.now(timezone.utc) + timedelta(hours=DEFAULT_EXPIRATION_HOURS)

    approval = AgentApproval(
        id=approval_id,
        tenant_id=t_id,
        agent_type=agent_type,
        tool_name=tool_name,
        arguments=arguments or {},
        conversation_id=conv_uuid,
        run_id=run_uuid,
        requested_by=requested_by,
        status="pending",
        expires_at=expires_at,
    )
    session.add(approval)
    await session.flush()

    payload = {
        "approval_id": str(approval_id),
        "reference": ref,
        "tenant_id": str(t_id),
        "agent_type": agent_type,
        "tool_name": tool_name,
        "arguments": arguments or {},
        "conversation_id": str(conv_uuid) if conv_uuid else None,
        "run_id": str(run_uuid) if run_uuid else None,
        "requested_by": requested_by,
        "expires_at": expires_at.isoformat(),
    }

    await publish(
        session,
        tenant_id=t_id,
        event_type=EVENT_APPROVAL_REQUESTED,
        payload=payload,
        source="orchestrator",
        idempotency_key=f"appr_req:{approval_id}",
    )

    await notify(
        session,
        tenant_id=t_id,
        title=f"Approval required: {agent_type} wants to run {tool_name}",
        body=f"Action proposal #{ref} requires executive authorization.",
        category="approval",
        severity="warning",
        link="/dashboard/admin/agents",
        source="orchestrator",
        subject=("approval", str(approval_id)),
    )

    return {
        "id": str(approval_id),
        "reference": ref,
        "status": "pending",
        "expires_at": expires_at.isoformat(),
        "message": f"Submitted for approval (#{ref}); tell the user it will run once approved.",
    }


async def request_approval_standalone(
    tenant_id: Optional[str | uuid.UUID],
    agent_type: str,
    tool_name: str,
    arguments: dict,
    conversation_id: Optional[uuid.UUID | str] = None,
    run_id: Optional[uuid.UUID | str] = None,
    requested_by: Optional[str] = None,
) -> dict:
    """Convenience wrapper when not inside a DB transaction."""
    tenant = tenant_id or "00000000-0000-0000-0000-000000000001"
    async with session_scope() as session:
        return await request_approval(
            session=session,
            tenant_id=tenant,
            agent_type=agent_type,
            tool_name=tool_name,
            arguments=arguments,
            conversation_id=conversation_id,
            run_id=run_id,
            requested_by=requested_by,
        )


def _approval_to_dict(a: AgentApproval) -> dict:
    """Format an approval row for API response and UI."""
    ref = approval_ref(a.id)
    ui_meta = _format_display_metadata(a.agent_type, a.tool_name, a.arguments or {})

    # Time format: relative or ISO
    now = datetime.now(timezone.utc)
    if a.created_at:
        created = a.created_at if a.created_at.tzinfo else a.created_at.replace(tzinfo=timezone.utc)
        diff = int((now - created).total_seconds())
        if diff < 60:
            time_str = "just now"
        elif diff < 3600:
            time_str = f"{diff // 60} mins ago"
        elif diff < 86400:
            time_str = f"{diff // 3600} hours ago"
        else:
            time_str = f"{diff // 86400} days ago"
    else:
        time_str = "just now"

    return {
        "id": str(a.id),
        "reference": ref,
        "tenant_id": str(a.tenant_id),
        "agent": a.agent_type,
        "agent_type": a.agent_type,
        "tool_name": a.tool_name,
        "arguments": a.arguments or {},
        "conversation_id": str(a.conversation_id) if a.conversation_id else None,
        "run_id": str(a.run_id) if a.run_id else None,
        "requested_by": a.requested_by,
        "status": a.status,
        "rejection_reason": a.rejection_reason,
        "execution_result": a.execution_result,
        "executed_at": a.executed_at.isoformat() if a.executed_at else None,
        "expires_at": a.expires_at.isoformat() if a.expires_at else None,
        "decided_at": a.decided_at.isoformat() if a.decided_at else None,
        "decided_by": a.decided_by,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "timestamp": time_str,
        # ExecutiveApprovalItem UI fields
        **ui_meta,
    }


async def list_approvals(
    session,
    tenant_id: str | uuid.UUID,
    status: Optional[str] = None,
    agent_type: Optional[str] = None,
    limit: int = 50,
) -> List[dict]:
    """Query approvals for tenant, auto-expiring overdue pending items."""
    t_id = uuid.UUID(str(tenant_id))
    now = datetime.now(timezone.utc)

    # Auto-expire overdue pending items
    await session.execute(
        text("""
            UPDATE agent_approvals
               SET status = 'expired', updated_at = now()
             WHERE tenant_id = :t AND status = 'pending' AND expires_at < :now
        """),
        {"t": t_id, "now": now},
    )

    q = select(AgentApproval).where(AgentApproval.tenant_id == t_id)
    if status:
        q = q.where(AgentApproval.status == status)
    if agent_type:
        q = q.where(AgentApproval.agent_type == agent_type)
    q = q.order_by(AgentApproval.created_at.desc()).limit(limit)

    rows = (await session.execute(q)).scalars().all()
    return [_approval_to_dict(r) for r in rows]


async def get_approval(session, tenant_id: str | uuid.UUID, approval_id: str | uuid.UUID) -> Optional[dict]:
    """Get single approval by id."""
    t_id = uuid.UUID(str(tenant_id))
    a_id = uuid.UUID(str(approval_id))
    row = (await session.execute(
        select(AgentApproval).where(AgentApproval.id == a_id, AgentApproval.tenant_id == t_id)
    )).scalar_one_or_none()
    return _approval_to_dict(row) if row else None


async def decide_approval(
    session,
    tenant_id: str | uuid.UUID,
    approval_id: str | uuid.UUID,
    decision: str,  # "approved" | "rejected"
    decided_by: str,
    reason: Optional[str] = None,
) -> dict:
    """Record approve/reject decision, publish event, and execute if approved."""
    t_id = uuid.UUID(str(tenant_id))
    a_id = uuid.UUID(str(approval_id))
    now = datetime.now(timezone.utc)

    row = (await session.execute(
        select(AgentApproval).where(AgentApproval.id == a_id, AgentApproval.tenant_id == t_id).with_for_update()
    )).scalar_one_or_none()

    if not row:
        raise ValueError("Approval not found")
    if row.status != "pending":
        raise ValueError(f"Approval is already {row.status}")
    if row.expires_at < now:
        row.status = "expired"
        await session.flush()
        raise ValueError("Approval has expired")

    decision = decision.lower()
    if decision not in ("approved", "rejected"):
        raise ValueError("Decision must be 'approved' or 'rejected'")

    row.status = decision
    row.decided_at = now
    row.decided_by = decided_by
    if decision == "rejected":
        row.rejection_reason = reason
    await session.flush()

    ref = approval_ref(row.id)
    payload = {
        "approval_id": str(row.id),
        "reference": ref,
        "tenant_id": str(t_id),
        "agent_type": row.agent_type,
        "tool_name": row.tool_name,
        "decision": decision,
        "decided_by": decided_by,
        "reason": reason,
        "conversation_id": str(row.conversation_id) if row.conversation_id else None,
        "run_id": str(row.run_id) if row.run_id else None,
    }

    await publish(
        session,
        tenant_id=t_id,
        event_type=EVENT_APPROVAL_DECIDED,
        payload=payload,
        source="orchestrator",
        idempotency_key=f"appr_dec:{row.id}:{decision}",
    )

    if decision == "rejected":
        # Memory capture entry for rejection
        approval_dict = _approval_to_dict(row)
        mem_entry = memory_capture.approval_entry(approval_dict, decision="rejected", decided_by=decided_by, reason=reason)
        await memory_capture.request_in(session, t_id, mem_entry)
        await notify(
            session,
            tenant_id=t_id,
            title=f"Proposal #{ref} rejected",
            body=f"Execution of {row.tool_name} was rejected: {reason or 'No reason provided'}",
            category="approval",
            severity="info",
            link="/dashboard/admin/agents",
        )
    elif decision == "approved":
        # Execute immediately to guarantee prompt feedback, and record idempotency
        await _execute_approved_call(session, row)

    return _approval_to_dict(row)


def acting_user_id(row: AgentApproval) -> Optional[str]:
    """Whose identity the approved call runs under. Services need a user id: the
    requester when a person asked, otherwise (an agent, workflow or MCP
    specialist asked — requested_by is then the agent type) the approver."""
    for candidate in (row.requested_by, row.decided_by):
        try:
            return str(uuid.UUID(str(candidate)))
        except (TypeError, ValueError):
            continue
    return None


async def _execute_approved_call(session, row: AgentApproval) -> dict:
    """Execute the tool call idempotently, save result, record action, and capture in memory."""
    if row.executed_at is not None:
        logger.info("Approval %s already executed at %s", row.id, row.executed_at)
        return row.execution_result or {}

    tool = tool_registry.get(row.tool_name)
    if not tool:
        err_res = {"success": False, "error": f"Tool {row.tool_name} not found in registry"}
        row.execution_result = err_res
        row.executed_at = datetime.now(timezone.utc)
        return err_res

    ref = approval_ref(row.id)
    logger.info("Executing approved tool call %s for %s (#%s)", row.tool_name, row.agent_type, ref)
    try:
        result = await tool.execute(
            tool_input=row.arguments or {},
            tenant_id=str(row.tenant_id),
            user_id=acting_user_id(row),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Approved tool call %s execution failed: %s", row.tool_name, exc)
        result = {"success": False, "error": str(exc)}

    row.execution_result = result
    row.executed_at = datetime.now(timezone.utc)
    await session.flush()

    # Record AgentAction if linked to a conversation
    if row.conversation_id:
        action = AgentAction(
            conversation_id=row.conversation_id,
            agent_type=row.agent_type,
            tool_name=row.tool_name,
            tool_input=row.arguments or {},
            tool_output=result,
            success=bool(result.get("success", True)),
            error=result.get("error") if not result.get("success", True) else None,
        )
        session.add(action)

    # Memory capture entry for approval decision + outcome (spec M3)
    approval_dict = _approval_to_dict(row)
    mem_entry = memory_capture.approval_entry(
        approval_dict, decision="approved", decided_by=row.decided_by, reason=None, outcome=result
    )
    await memory_capture.request_in(session, row.tenant_id, mem_entry)

    # Bell notification
    ok = bool(result.get("success", True))
    await notify(
        session,
        tenant_id=row.tenant_id,
        title=f"Action #{ref} executed ({'succeeded' if ok else 'failed'})",
        body=f"Approved tool {row.tool_name} ran with status: {'OK' if ok else result.get('error', 'Error')}",
        category="approval",
        severity="info" if ok else "warning",
        link="/dashboard/admin/agents",
    )

    return result


async def handle_approval_decided(event: dict) -> None:
    """Bus consumer handler for agents.approval.decided events."""
    payload = event.get("payload") or {}
    approval_id = payload.get("approval_id")
    decision = payload.get("decision")
    if not approval_id:
        return

    if decision == "approved":
        async with session_scope() as session:
            row = (await session.execute(
                select(AgentApproval).where(AgentApproval.id == uuid.UUID(str(approval_id))).with_for_update()
            )).scalar_one_or_none()
            if row and row.executed_at is None:
                await _execute_approved_call(session, row)


consumer = EventConsumer("approval_gate", {EVENT_APPROVAL_DECIDED: handle_approval_decided})
