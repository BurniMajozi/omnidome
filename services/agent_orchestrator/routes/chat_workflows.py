"""Conversation-owned attachments. Runs use the existing frozen approval gate."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.agent_orchestrator.conversation.models import AgentConversation, AgentMessage
from services.agent_orchestrator.models import ChatWorkflowAttachment, ChatWorkflowRequest, Workflow, WorkflowRun, AgentApproval
from services.agent_orchestrator.identity import check_conversation_access, OWNER_KEY
from services.agent_orchestrator.approvals import request_approval

router = APIRouter()


async def conversation(session, ident, ctx):
    conv = (await session.execute(select(AgentConversation).where(
        AgentConversation.id == ident, AgentConversation.tenant_id == ctx.tenant_id
    ).with_for_update())).scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "Conversation not found")
    check_conversation_access(conv, ctx)
    return conv


@router.post("/new", status_code=201)
async def new_conversation(ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        conv = AgentConversation(tenant_id=ctx.tenant_id, agent_type="auto", channel="web",
                                 context={OWNER_KEY: str(ctx.user_id), "title": "Workflow chat"})
        session.add(conv)
        await session.flush()
        return {"id": str(conv.id)}


async def attachment_state(session, attachment):
    wf = await session.get(Workflow, attachment.workflow_id)
    approval = await session.get(AgentApproval, attachment.approval_id) if attachment.approval_id else None
    state = {"workflow_id": str(wf.id), "name": wf.name, "status": wf.status,
             "trigger_event": wf.trigger_event, "schedule_enabled": wf.schedule_enabled,
             "steps": len((wf.definition or {}).get("nodes", [])), "execution_status": "attached"}
    if approval:
        state["approval_id"] = str(approval.id)
        state["execution_status"] = "awaiting_approval" if approval.status == "pending" else approval.status
        expires = approval.expires_at
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if approval.status == "pending" and expires and expires <= datetime.now(timezone.utc):
            state["execution_status"] = "expired"
        result = approval.execution_result or {}
        run_id = (result.get("data") or {}).get("run_id")
        if run_id:
            run = await session.get(WorkflowRun, uuid.UUID(run_id))
            if run and run.tenant_id == attachment.tenant_id:
                state.update(execution_status=run.status, run_id=str(run.id), error=run.error,
                             output=run.output or {})
        elif approval.execution_started_at and not approval.executed_at:
            state["execution_status"] = "running"
        elif approval.executed_at and result.get("success") is not True:
            state.update(execution_status="failed", error=result.get("error"))
    return state


@router.get("/{conversation_id}")
async def attached(conversation_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        await conversation(session, conversation_id, ctx)
        rows = (await session.execute(select(ChatWorkflowAttachment).where(
            ChatWorkflowAttachment.conversation_id == conversation_id,
            ChatWorkflowAttachment.tenant_id == ctx.tenant_id))).scalars().all()
        return {"data": [await attachment_state(session, row) for row in rows]}


class Attach(BaseModel):
    workflow_ids: list[uuid.UUID] = Field(max_length=20)


@router.put("/{conversation_id}")
async def attach(conversation_id: uuid.UUID, body: Attach, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        await conversation(session, conversation_id, ctx)
        ids = set(body.workflow_ids)
        workflows = (await session.execute(select(Workflow).where(
            Workflow.id.in_(ids), Workflow.tenant_id == ctx.tenant_id))).scalars().all()
        if len(workflows) != len(ids):
            raise HTTPException(404, "Workflow not found")
        rows = (await session.execute(select(ChatWorkflowAttachment).where(
            ChatWorkflowAttachment.conversation_id == conversation_id))).scalars().all()
        existing = {row.workflow_id for row in rows}
        for row in rows:
            if row.workflow_id not in ids:
                # Detaching never cancels a run or changes the definition's triggers.
                await session.delete(row)
        for ident in ids - existing:
            previous = (await session.execute(select(ChatWorkflowRequest).where(
                ChatWorkflowRequest.conversation_id == conversation_id,
                ChatWorkflowRequest.workflow_id == ident,
                ChatWorkflowRequest.tenant_id == ctx.tenant_id
            ).order_by(ChatWorkflowRequest.created_at.desc()).limit(1))).scalar_one_or_none()
            session.add(ChatWorkflowAttachment(conversation_id=conversation_id, workflow_id=ident,
                tenant_id=ctx.tenant_id, approval_id=previous.approval_id if previous else None))
        return {"attached": len(ids)}


class ChatRun(BaseModel):
    request_key: uuid.UUID
    input: dict = Field(default_factory=dict)


@router.post("/{conversation_id}/{workflow_id}/run")
async def run(conversation_id: uuid.UUID, workflow_id: uuid.UUID, body: ChatRun,
              ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        await conversation(session, conversation_id, ctx)
        attachment = (await session.execute(select(ChatWorkflowAttachment).where(
            ChatWorkflowAttachment.conversation_id == conversation_id,
            ChatWorkflowAttachment.workflow_id == workflow_id,
            ChatWorkflowAttachment.tenant_id == ctx.tenant_id))).scalar_one_or_none()
        if not attachment or attachment.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Attach this workflow first")
        existing = (await session.execute(select(ChatWorkflowRequest).where(
            ChatWorkflowRequest.request_key == body.request_key))).scalar_one_or_none()
        if existing:
            if (existing.tenant_id, existing.conversation_id, existing.workflow_id) != (ctx.tenant_id, conversation_id, workflow_id):
                raise HTTPException(409, "Request key already used")
            return {"approval_id": str(existing.approval_id), "duplicate": True}
        state = await attachment_state(session, attachment)
        if state["execution_status"] in {"awaiting_approval", "approved", "running"}:
            raise HTTPException(409, "This chat already has a pending or running execution of this workflow")
        # Use stored messages, never client-supplied identities or a forged transcript.
        messages = (await session.execute(select(AgentMessage).where(
            AgentMessage.conversation_id == conversation_id,
            AgentMessage.role.in_(["user", "assistant"])
        ).order_by(AgentMessage.created_at.desc()).limit(12))).scalars().all()
        input_data = {**body.input, "chat": {"conversation_id": str(conversation_id),
                      "messages": [{"role": m.role, "content": (m.content or "")[:2000]} for m in reversed(messages)]}}
        if not input_data.get("message"):
            input_data["message"] = next((m.content for m in messages if m.role == "user"), "Run the attached workflow.")
        try:
            approval = await request_approval(session, str(ctx.tenant_id), "assistant", "workflows.run",
                {"workflow_id": str(workflow_id), "input": input_data},
                conversation_id=conversation_id, requested_by=str(ctx.user_id))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        attachment.approval_id = uuid.UUID(approval["id"])
        session.add(ChatWorkflowRequest(request_key=body.request_key, conversation_id=conversation_id,
            workflow_id=workflow_id, tenant_id=ctx.tenant_id, approval_id=attachment.approval_id))
        return {"approval_id": approval["id"], "status": "awaiting_approval"}
