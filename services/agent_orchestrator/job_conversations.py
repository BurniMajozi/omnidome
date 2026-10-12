"""Persistent conversations made of bounded runs, never a replay of prior tools."""
import uuid
from fastapi import HTTPException
from sqlalchemy import select, text
from services.agent_orchestrator.models import AgentJob, AgentJobActivity
from services.agent_orchestrator.control_plane import job_dict

BLOCKING = {"queued", "running", "pause_requested", "awaiting_hitl", "interrupted"}

async def root_job(session, job_id, tenant):
    visited = set()
    while job_id not in visited and len(visited) < 100:
        visited.add(job_id)
        row = (await session.execute(select(AgentJob).where(AgentJob.id == job_id, AgentJob.tenant_id == tenant))).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Conversation not found")
        parent = (row.checkpoint or {}).get("parent_job_id")
        if not parent:
            return row
        try: job_id = uuid.UUID(parent)
        except ValueError: raise HTTPException(409, "Invalid conversation ancestry")
    raise HTTPException(409, "Conversation ancestry is too long or cyclic")

async def thread_jobs(session, root, tenant):
    return (await session.execute(select(AgentJob).from_statement(text("""
        WITH RECURSIVE turns AS (
          SELECT id,0 AS depth FROM agent_jobs WHERE id=:root AND tenant_id=:tenant
          UNION ALL
          SELECT j.id,p.depth+1 FROM agent_jobs j JOIN turns p ON j.checkpoint->>'parent_job_id'=p.id::text
          WHERE j.tenant_id=:tenant AND p.depth<99
        ) SELECT j.* FROM agent_jobs j JOIN turns t ON j.id=t.id
          ORDER BY t.depth,j.created_at,j.id LIMIT 100
    """).bindparams(root=root, tenant=tenant)))).scalars().all()

def history_from(prior):
    history = list((prior.checkpoint or {}).get("history") or [])
    if not history:
        history = [{"role": "user", "content": prior.objective}]
        output = (prior.result or {}).get("final_output") or (prior.checkpoint or {}).get("last_output")
        if output: history.append({"role": "assistant", "content": output})
    # Plain prior messages only. Tool logs, identity, budget and model context are not copied.
    return [{"role": m["role"], "content": str(m.get("content", ""))[:8000]}
            for m in history if isinstance(m, dict) and m.get("role") in {"user", "assistant"}][-20:]

async def full_turn(session, row):
    result = job_dict(row)
    activity = (await session.execute(select(AgentJobActivity).where(
        AgentJobActivity.job_id == row.id, AgentJobActivity.tenant_id == row.tenant_id))).scalar_one_or_none()
    result["activity"] = {"text": activity.status_text, "items": list((activity.items or {}).values()),
                          "updated_at": activity.updated_at.isoformat() if activity.updated_at else None} if activity else None
    return result
