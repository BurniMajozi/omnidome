"""Approval gate runtime and persistence (spec A8 `approval-gate`).

When an agent encounters a tool with `requires_approval=True`, execution is gated:
1. An `agent_approvals` row is stored with status='pending' and 24h expiration.
2. `agents.approval.requested` is published on the event bus.
3. A notification is added to the in-app bell feed.
4. The model receives: "Submitted for approval (#ref); tell the user it will run once approved."
5. When approved: the decision is committed and `agents.approval.decided` is
   published. Execution then happens in its own steps (execute_approved):
   claim the row (committed), run the tool, record the result. A claimed
   approval is never run again, so the call happens at most once even if the
   process dies mid-way or both the approve route and the bus consumer try.
   A claimed-but-unrecorded approval stays visible (execution_started_at set,
   executed_at empty) for a person to check.
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
from services.agent_orchestrator.models import AgentAction, AgentApproval, AgentConversation, AgentMessage
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
    execution_started_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    decided_at TIMESTAMPTZ,
    decided_by VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_agent_approvals_tenant_status ON agent_approvals (tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_agent_approvals_agent ON agent_approvals (tenant_id, agent_type, status);
ALTER TABLE agent_approvals ADD COLUMN IF NOT EXISTS execution_started_at TIMESTAMPTZ;
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

    args_str = ", ".join(f"{k}={v}" for k, v in arguments.items() if v and not k.startswith("_"))
    summary = f"{agent_type} requested execution of {tool_name}. Parameters: {args_str or 'none'}."
    context = f"Requires executive authorization before execution. Target service: {tool_name.split('_')[0]}."

    jev_info = arguments.get("_jev_gate")
    if isinstance(jev_info, dict) and jev_info.get("evaluated_by_jev"):
        risk = float(jev_info.get("risk_score", 3.0))
        act = jev_info.get("action", "require_approval")
        impact = "critical" if risk >= 4.5 else "high" if risk >= 3.5 else "medium" if risk >= 2.0 else "low"
        context = f"Jev System One (Risk {risk:.1f}/5.0 | {act}): {jev_info.get('reason', '')}"

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
    tool_call_id: Optional[str] = None,
    jev_gate: Optional[dict] = None,
) -> dict:
    """Store approval request in caller's session, publish event and raise notification."""
    approval_id = uuid.uuid4()
    ref = approval_ref(approval_id)
    t_id = uuid.UUID(str(tenant_id))
    conv_uuid = uuid.UUID(str(conversation_id)) if conversation_id else None
    run_uuid = uuid.UUID(str(run_id)) if run_id else None
    expires_at = datetime.now(timezone.utc) + timedelta(hours=DEFAULT_EXPIRATION_HOURS)

    stored_arguments = dict(arguments or {})
    if tool_call_id:
        stored_arguments["_tool_call_id"] = tool_call_id
    if jev_gate:
        stored_arguments["_jev_gate"] = jev_gate

    approval = AgentApproval(
        id=approval_id,
        tenant_id=t_id,
        agent_type=agent_type,
        tool_name=tool_name,
        arguments=stored_arguments,
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
        "arguments": stored_arguments,
        "conversation_id": str(conv_uuid) if conv_uuid else None,
        "run_id": str(run_uuid) if run_uuid else None,
        "requested_by": requested_by,
        "tool_call_id": tool_call_id,
        "jev_gate": jev_gate,
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
        "tool_call_id": tool_call_id,
        "jev_gate": jev_gate,
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
    tool_call_id: Optional[str] = None,
    jev_gate: Optional[dict] = None,
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
            tool_call_id=tool_call_id,
            jev_gate=jev_gate,
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
        "execution_started_at": a.execution_started_at.isoformat() if a.execution_started_at else None,
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
    # Approved: the caller runs execute_approved() once this has committed.
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


async def _claim(tenant_id: str | uuid.UUID, approval_id: str | uuid.UUID) -> Optional[AgentApproval]:
    """Atomically take the right to run an approved call, in its own committed
    transaction. Only one caller ever gets the row back."""
    async with session_scope() as session:
        claimed = (await session.execute(
            text("""
                UPDATE agent_approvals
                   SET execution_started_at = now(), updated_at = now()
                 WHERE id = :id AND tenant_id = :t AND status = 'approved'
                   AND execution_started_at IS NULL AND executed_at IS NULL
             RETURNING id
            """),
            {"id": str(approval_id), "t": str(tenant_id)},
        )).first()
        if not claimed:
            return None
        row = (await session.execute(select(AgentApproval).where(AgentApproval.id == claimed[0]))).scalar_one()
        session.expunge(row)
        return row


async def _record(row: AgentApproval, result: dict) -> None:
    """Save the outcome: result on the approval, audit action, memory entry
    (spec M3) and a bell notification, in one transaction."""
    ref = approval_ref(row.id)
    ok = bool(result.get("success", True))
    async with session_scope() as session:
        await session.execute(
            text("""
                UPDATE agent_approvals
                   SET execution_result = CAST(:result AS jsonb), executed_at = now(), updated_at = now()
                 WHERE id = :id
            """),
            {"id": str(row.id), "result": json.dumps(result, default=str)},
        )
        if row.conversation_id:
            session.add(AgentAction(
                conversation_id=row.conversation_id,
                agent_type=row.agent_type,
                tool_name=row.tool_name,
                tool_input=row.arguments or {},
                tool_output=result,
                success=ok,
                error=result.get("error") if not ok else None,
            ))
        row.execution_result = result
        row.executed_at = datetime.now(timezone.utc)
        mem_entry = memory_capture.approval_entry(
            _approval_to_dict(row), decision="approved", decided_by=row.decided_by, reason=None, outcome=result
        )
        await memory_capture.request_in(session, row.tenant_id, mem_entry)
        await notify(
            session,
            tenant_id=row.tenant_id,
            title=f"Action #{ref} executed ({'succeeded' if ok else 'failed'})",
            body=f"Approved tool {row.tool_name} ran with status: {'OK' if ok else result.get('error', 'Error')}",
            category="approval",
            severity="info" if ok else "warning",
            link="/dashboard/admin/agents",
        )


async def mark_conversation_awaiting_hitl(conversation_id: uuid.UUID | str, tenant_id: uuid.UUID | str) -> None:
    """Mark conversation status as awaiting_hitl when a tool call pauses for human input."""
    conv_uuid = uuid.UUID(str(conversation_id))
    t_id = uuid.UUID(str(tenant_id))
    async with session_scope() as session:
        conv = (await session.execute(
            select(AgentConversation).where(
                AgentConversation.id == conv_uuid,
                AgentConversation.tenant_id == t_id,
            )
        )).scalar_one_or_none()
        if conv:
            conv.status = "awaiting_hitl"
            ctx = dict(conv.context or {})
            ctx["hitl_status"] = "awaiting_hitl"
            conv.context = ctx
            await session.flush()


async def resume_conversation(
    tenant_id: str | uuid.UUID,
    conversation_id: uuid.UUID | str,
    tool_name: str,
    tool_args: dict,
    tool_result: dict,
    tool_call_id: Optional[str] = None,
    agent_type: Optional[str] = None,
) -> Optional[str]:
    """Resume an in-flight conversation after human review (OpenRouter HITL pattern)."""
    from services.agent_orchestrator.agents import Agent

    conv_uuid = uuid.UUID(str(conversation_id))
    t_id = uuid.UUID(str(tenant_id))

    async with session_scope() as session:
        conv = (await session.execute(
            select(AgentConversation).where(
                AgentConversation.id == conv_uuid,
                AgentConversation.tenant_id == t_id,
            )
        )).scalar_one_or_none()
        if not conv:
            logger.warning("Cannot resume: conversation %s not found for tenant %s", conv_uuid, t_id)
            return None

        eff_agent = agent_type or conv.agent_type
        msg_res = await session.execute(
            select(AgentMessage)
            .where(AgentMessage.conversation_id == conv_uuid)
            .order_by(AgentMessage.created_at.asc())
        )
        msgs = msg_res.scalars().all()
        history = [
            {"role": m.role, "content": m.content or "", "id": str(m.id)}
            for m in msgs
            if m.role in ("user", "assistant", "tool")
        ]
        conv.status = "active"
        ctx = dict(conv.context or {})
        ctx.pop("hitl_status", None)
        conv.context = ctx
        await session.flush()

    # Outside DB lock, resume agent reasoning turn
    agent = Agent(agent_type=eff_agent, tenant_id=t_id, context=conv.context or {})
    resumed = await agent.resume_with_approved_result(
        history=history,
        tool_name=tool_name,
        tool_args=tool_args,
        tool_result=tool_result,
        tool_call_id=tool_call_id,
        conversation_id=conv_uuid,
    )

    final_content = resumed.get("content", "")
    if not final_content.strip():
        final_content = f"Action on {tool_name} was approved and completed successfully."

    call_id = tool_call_id or f"call_{uuid.uuid4().hex[:8]}"
    async with session_scope() as session:
        tool_msg = AgentMessage(
            conversation_id=conv_uuid,
            role="tool",
            content=json.dumps(tool_result, default=str),
            tool_results=[{"name": tool_name, "call_id": call_id, "result": tool_result}],
        )
        assistant_msg = AgentMessage(
            conversation_id=conv_uuid,
            role="assistant",
            content=final_content,
        )
        session.add(tool_msg)
        session.add(assistant_msg)
        await session.flush()

        await publish(
            session,
            tenant_id=t_id,
            event_type="agents.conversation.resumed",
            payload={
                "conversation_id": str(conv_uuid),
                "message": final_content,
                "tool_name": tool_name,
                "tool_result": tool_result,
            },
            source="orchestrator",
            idempotency_key=f"resumed:{conv_uuid}:{call_id}",
        )

    return final_content


async def execute_approved(
    tenant_id: str | uuid.UUID,
    approval_id: str | uuid.UUID,
    custom_output: Optional[dict] = None,
    resume: bool = True,
) -> Optional[dict]:
    """Run an approved call at most once: claim (committed) -> run -> record -> resume conversation.
    Returns dict with execution_result and optional resumed_response."""
    row = await _claim(tenant_id, approval_id)
    if row is None:
        return None

    clean_args = {k: v for k, v in (row.arguments or {}).items() if not k.startswith("_")}

    if custom_output is not None:
        # HITL onResponseReceived pattern: human supplied custom output
        logger.info("Using human-supplied custom output for %s (#%s)", row.tool_name, approval_ref(row.id))
        result = custom_output
    else:
        tool = tool_registry.get(row.tool_name)
        if not tool:
            result = {"success": False, "error": f"Tool {row.tool_name} not found in registry"}
        else:
            logger.info("Executing approved tool call %s for %s (#%s)", row.tool_name, row.agent_type, approval_ref(row.id))
            try:
                result = await tool.execute(
                    tool_input=clean_args,
                    tenant_id=str(row.tenant_id),
                    user_id=acting_user_id(row),
                )
            except Exception as exc:  # noqa: BLE001 - the failure is the outcome to record
                logger.exception("Approved tool call %s execution failed: %s", row.tool_name, exc)
                result = {"success": False, "error": str(exc)}

    resumed_response = None
    if resume and row.conversation_id:
        try:
            resumed_response = await resume_conversation(
                tenant_id=row.tenant_id,
                conversation_id=row.conversation_id,
                tool_name=row.tool_name,
                tool_args=clean_args,
                tool_result=result,
                tool_call_id=(row.arguments or {}).get("_tool_call_id"),
                agent_type=row.agent_type,
            )
        except Exception as exc:
            logger.error("Failed to resume conversation %s: %s", row.conversation_id, exc)

    if resumed_response and isinstance(result, dict):
        result["resumed_response"] = resumed_response

    await _record(row, result)
    return result


async def handle_approval_decided(event: dict) -> None:
    """Bus consumer for agents.approval.decided: runs the call if the approve
    route did not get to it (e.g. the process died after the decision)."""
    payload = event.get("payload") or {}
    if payload.get("approval_id") and payload.get("decision") == "approved":
        await execute_approved(event["tenant_id"], payload["approval_id"])


consumer = EventConsumer("approval_gate", {EVENT_APPROVAL_DECIDED: handle_approval_decided})
