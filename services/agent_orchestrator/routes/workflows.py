"""Workflow / DAG runner API (Phase A).

CRUD for workflow definitions + manual run + run history. Tenant-scoped via the
verified auth context. The visual editor and schedule/webhook triggers are later
phases; this exposes the runnable core.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.agent_orchestrator.models import Workflow, WorkflowRun, RunStep
from services.agent_orchestrator.workflow_engine import run_workflow

router = APIRouter()


class WorkflowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    definition: dict = {}
    status: str = "draft"


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    definition: Optional[dict] = None
    status: Optional[str] = None


class RunRequest(BaseModel):
    input: dict = {}


def _wf_json(w: Workflow) -> dict:
    return {
        "id": str(w.id), "name": w.name, "description": w.description,
        "definition": w.definition, "status": w.status,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "updated_at": w.updated_at.isoformat() if w.updated_at else None,
    }


@router.get("")
async def list_workflows(ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as s:
        rows = (await s.execute(
            select(Workflow).where(Workflow.tenant_id == ctx.tenant_id).order_by(Workflow.updated_at.desc())
        )).scalars().all()
        return {"data": [_wf_json(w) for w in rows]}


@router.post("", status_code=201)
async def create_workflow(body: WorkflowCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as s:
        w = Workflow(tenant_id=ctx.tenant_id, name=body.name, description=body.description,
                     definition=body.definition or {}, status=body.status)
        s.add(w)
        await s.flush()
        return _wf_json(w)


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as s:
        w = (await s.execute(select(Workflow).where(
            Workflow.id == workflow_id, Workflow.tenant_id == ctx.tenant_id))).scalar_one_or_none()
        if not w:
            raise HTTPException(404, "workflow not found")
        return _wf_json(w)


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: uuid.UUID, body: WorkflowUpdate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as s:
        w = (await s.execute(select(Workflow).where(
            Workflow.id == workflow_id, Workflow.tenant_id == ctx.tenant_id))).scalar_one_or_none()
        if not w:
            raise HTTPException(404, "workflow not found")
        if body.name is not None:
            w.name = body.name
        if body.description is not None:
            w.description = body.description
        if body.definition is not None:
            w.definition = body.definition
        if body.status is not None:
            w.status = body.status
        await s.flush()
        return _wf_json(w)


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as s:
        w = (await s.execute(select(Workflow).where(
            Workflow.id == workflow_id, Workflow.tenant_id == ctx.tenant_id))).scalar_one_or_none()
        if w:
            await s.delete(w)


@router.post("/{workflow_id}/run")
async def run(workflow_id: uuid.UUID, body: RunRequest, ctx: AuthContext = Depends(get_auth_context)):
    result = await run_workflow(
        workflow_id=workflow_id, tenant_id=str(ctx.tenant_id),
        user_id=str(ctx.user_id), input_data=body.input, trigger="manual",
    )
    if result.get("error") == "workflow not found":
        raise HTTPException(404, "workflow not found")
    return result


@router.post("/hooks/{workflow_id}")
async def webhook_run(workflow_id: uuid.UUID, body: dict):
    """Public webhook trigger (no user session). Runs the workflow in its own
    tenant. Gated by X-Webhook-Key... enforced at the web proxy layer; here we
    resolve the workflow's tenant from the row and run it."""
    async with session_scope() as s:
        w = (await s.execute(select(Workflow).where(Workflow.id == workflow_id))).scalar_one_or_none()
        if not w or w.status != "active":
            raise HTTPException(404, "workflow not found or inactive")
        tenant_id = str(w.tenant_id)
    result = await run_workflow(
        workflow_id=workflow_id, tenant_id=tenant_id,
        user_id="00000000-0000-0000-0000-000000000000", input_data=body or {}, trigger="webhook",
    )
    return result


@router.get("/{workflow_id}/runs")
async def list_runs(workflow_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as s:
        rows = (await s.execute(
            select(WorkflowRun).where(
                WorkflowRun.workflow_id == workflow_id, WorkflowRun.tenant_id == ctx.tenant_id
            ).order_by(WorkflowRun.started_at.desc()).limit(50)
        )).scalars().all()
        return {"data": [{
            "id": str(r.id), "status": r.status, "trigger": r.trigger,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "error": r.error,
        } for r in rows]}


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as s:
        r = (await s.execute(select(WorkflowRun).where(
            WorkflowRun.id == run_id, WorkflowRun.tenant_id == ctx.tenant_id))).scalar_one_or_none()
        if not r:
            raise HTTPException(404, "run not found")
        steps = (await s.execute(
            select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.started_at.asc())
        )).scalars().all()
        return {
            "id": str(r.id), "status": r.status, "input": r.input, "output": r.output, "error": r.error,
            "steps": [{
                "node_id": st.node_id, "node_type": st.node_type, "status": st.status,
                "output": st.output, "error": st.error,
            } for st in steps],
        }
