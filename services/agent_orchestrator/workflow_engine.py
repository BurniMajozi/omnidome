"""Native workflow / DAG execution engine (Phase A).

Executes a JSON workflow definition against OmniDome. Definition shape:
    {
      "nodes": [{"id","type","name","config"}],
      "edges": [{"from","to","condition"?}]   # condition: "true"/"false" for branch nodes
    }
Node types: trigger, agent_invoke, http_request, transform, condition, end.

In-process async execution. Persists a WorkflowRun + a RunStep per node. No
visual editor / scheduler yet (later phases) — this is the runnable core.
"""
from __future__ import annotations

import os
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import select

from services.common.db import session_scope
from services.agent_orchestrator.models import Workflow, WorkflowRun, RunStep
from services.agent_orchestrator import memory_capture
from services.agent_orchestrator.agents import Agent

logger = logging.getLogger(__name__)
MAX_NODES = 50


def _resolve(template: Any, data: dict) -> Any:
    """Substitute {{path.to.value}} references against the run data dict."""
    if not isinstance(template, str):
        return template

    def repl(m: "re.Match[str]") -> str:
        cur: Any = data
        for part in m.group(1).strip().split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        return str(cur) if cur is not None else ""

    return re.sub(r"\{\{([^}]+)\}\}", repl, template)


_EXACT = re.compile(r"^\{\{([^}]+)\}\}$")


def _lookup(path: str, data: dict) -> Any:
    cur: Any = data
    for part in path.strip().split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def resolve_deep(template: Any, data: dict) -> Any:
    """Resolve {{path}} references inside strings, dicts and lists. A string that
    is exactly one placeholder keeps the raw value (objects, numbers); otherwise
    placeholders are substituted as text."""
    if isinstance(template, dict):
        return {k: resolve_deep(v, data) for k, v in template.items()}
    if isinstance(template, list):
        return [resolve_deep(v, data) for v in template]
    if isinstance(template, str):
        exact = _EXACT.match(template.strip())
        if exact:
            return _lookup(exact.group(1), data)
        return _resolve(template, data)
    return template


def service_request(service: str, path: str, *, tenant_id: Optional[str], user_id: str) -> tuple[str, dict]:
    """URL + auth headers for an internal OmniDome service (http_request `service`).
    Base URL from <SERVICE>_SERVICE_URL, e.g. SALES_SERVICE_URL."""
    base = os.getenv(f"{service.upper()}_SERVICE_URL", f"http://{service}:8000").rstrip("/")
    headers = {"X-Tenant-Id": str(tenant_id or ""), "X-User-Id": str(user_id)}
    return f"{base}/{path.lstrip('/')}", headers


def _eval_condition(left: str, op: str, right: Any) -> bool:
    rs = str(right)
    if op in ("eq", "=="):
        return left == rs
    if op in ("ne", "!="):
        return left != rs
    if op == "contains":
        return rs in left
    try:
        ln, rn = float(left), float(rs)
        if op in ("gt", ">"):
            return ln > rn
        if op in ("lt", "<"):
            return ln < rn
        if op in ("gte", ">="):
            return ln >= rn
        if op in ("lte", "<="):
            return ln <= rn
    except (ValueError, TypeError):
        pass
    return False


async def _run_node(node: dict, data: dict, tenant_id: Optional[str], user_id: str) -> dict:
    ntype = node.get("type")
    cfg = node.get("config", {}) or {}

    if ntype in ("trigger", "end", "transform"):
        return {"ok": True, "data": cfg.get("set", {})}

    if ntype == "notification":
        from services.agent_orchestrator.billing_workflows import send_notice
        resolved=resolve_deep(cfg,data)
        if (data.get("input") or {}).get("verification") is True:
            resolved={**resolved,"title":"[TEST] "+str(resolved.get("title","Workflow verification")),
                      "body":"Verification only; no real balance or payment changed. "+str(resolved.get("body",""))}
        return await send_notice(tenant_id,data["run_id"],node["id"],resolved)

    if ntype == "agent_invoke":
        agent_type = cfg.get("agent_type", "customer_facing")
        message = _resolve(cfg.get("message", ""), data) or (data.get("input") or {}).get("message", "")
        agent = Agent(
            agent_type=agent_type,
            tenant_id=uuid.UUID(tenant_id) if tenant_id else None,
            context={"user_id": user_id, "workflow_id": data.get("workflow_id"), "run_id": data.get("run_id"),
                     "draft_only": bool(cfg.get("draft_only", False))},
        )
        result = await agent.run(message)
        if result.get("unavailable"):
            # Every LLM (and fallback) failed: fail the step instead of passing an
            # apology on as if it were real output.
            return {"ok": False, "error": "AI unavailable: every configured model failed or is rate-limited",
                    "content": None}
        tool_calls = result.get("tool_calls", [])
        pending_appr = next((tc["result"] for tc in tool_calls if isinstance(tc.get("result"), dict) and tc["result"].get("requires_approval")), None)
        if pending_appr:
            return {
                "ok": True,
                "awaiting_approval": True,
                "approval_id": pending_appr.get("approval_id"),
                "approval_ids": [tc["result"]["approval_id"] for tc in tool_calls if isinstance(tc.get("result"),dict) and tc["result"].get("requires_approval") and tc["result"].get("approval_id")],
                "reference": pending_appr.get("reference"),
                "content": result.get("content"),
                "tool_calls": tool_calls,
            }
        return {"ok": True, "content": result.get("content"), "tool_calls": tool_calls}

    if ntype == "http_request":
        method = cfg.get("method", "GET").upper()
        headers = resolve_deep(cfg.get("headers") or {}, data)
        if cfg.get("service"):
            # Internal OmniDome service: base URL from env + this run's tenant headers.
            url, auth = service_request(cfg["service"], _resolve(cfg.get("path", ""), data),
                                        tenant_id=tenant_id, user_id=user_id)
            headers = {**headers, **auth}
        else:
            url = _resolve(cfg.get("url", ""), data)
        body = resolve_deep(cfg.get("body"), data) if cfg.get("body") is not None else None
        async with httpx.AsyncClient(timeout=float(cfg.get("timeout", 20.0))) as client:
            resp = await client.request(method, url, json=body, headers=headers or None)
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:1000]
        ok = resp.status_code < 400
        out = {"ok": ok, "status": resp.status_code, "body": body}
        if not ok:
            out["error"] = f"{method} {url} -> HTTP {resp.status_code}"
        return out

    if ntype == "condition":
        left = _resolve(str(cfg.get("left", "")), data)
        return {"ok": True, "result": _eval_condition(left, cfg.get("op", "eq"), cfg.get("right"))}

    return {"ok": False, "error": f"unknown node type: {ntype}"}



def first_node(definition):
    nodes={n["id"]:n for n in definition.get("nodes",[])}
    incoming={e["to"] for e in definition.get("edges",[])}
    return next((key for key,node in nodes.items() if node.get("type")=="trigger"),None) or next((key for key in nodes if key not in incoming),None)


def next_node(node, definition, output):
    if node.get("type")=="end": return None
    outgoing=[edge for edge in definition.get("edges",[]) if edge["from"]==node["id"]]
    if node.get("type")=="condition":
        wanted="true" if output.get("result") else "false"
        return next((e["to"] for e in outgoing if str(e.get("condition","")).lower()==wanted),None) or next((e["to"] for e in outgoing if not e.get("condition")),None)
    return outgoing[0]["to"] if outgoing else None


def approval_ids(output):
    ids=output.get("approval_ids") or ([output["approval_id"]] if output.get("approval_id") else [])
    return list(dict.fromkeys(str(uuid.UUID(str(ident))) for ident in ids))


def run_result(run):
    return {"run_id":str(run.id),"status":run.status,"steps":run.output or {},"error":run.error}


def approval_outcomes(approvals,expected_ids,now=None):
    now=now or datetime.now(timezone.utc)
    if {str(a.id) for a in approvals}!=set(expected_ids):
        return "Workflow approval association is missing",False,{}
    for approval in approvals:
        expires_at=approval.expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at=expires_at.replace(tzinfo=timezone.utc)
        if approval.status in {"rejected","expired"} or (approval.status=="pending" and expires_at and expires_at<=now):
            return f"Approval {approval.id} was rejected or expired",False,{}
        if approval.status=="approved" and approval.executed_at and (approval.execution_result or {}).get("success") is not True:
            return f"Approved action failed: {(approval.execution_result or {}).get('error') or 'unknown failure'}",False,{}
    if any(a.status!="approved" or not a.executed_at for a in approvals): return None,True,{}
    return None,False,{str(a.id):a.execution_result for a in approvals}


async def finish_run(session,run,checkpoint,status,error=None):
    run.status=status
    run.error=error
    run.checkpoint=checkpoint
    run.output=checkpoint["data"]["steps"]
    run.finished_at=None if status in {"running","awaiting_approval"} else datetime.now(timezone.utc)
    await session.flush()
    if status=="failed":
        from services.agent_orchestrator.failure_events import publish_run_failed
        await publish_run_failed(session,run.tenant_id,agent=str(checkpoint.get("name") or "workflow"),run_id=run.id,
                                 error=str(error or "workflow failed"),kind="workflow_run")
    if status in {"succeeded","failed"}:
        try:
            async with session.begin_nested():
                await memory_capture.request_in(session,run.tenant_id,
                    memory_capture.workflow_entry(checkpoint["name"],run.workflow_id,run.id,status,run.trigger,run.output,error),
                    key=f"workflow_run:{run.id}")
        except Exception as exc:
            logger.warning("Workflow %s memory capture failed: %s",run.id,type(exc).__name__)


async def run_workflow(workflow_id,tenant_id,user_id,input_data=None,trigger="manual",expected_definition_hash=None):
    """Freeze a definition, commit the run, then execute each step once."""
    import copy
    from services.agent_orchestrator.workflow_tools import definition_hash
    async with session_scope() as session:
        wf=(await session.execute(select(Workflow).where(Workflow.id==workflow_id,Workflow.tenant_id==uuid.UUID(str(tenant_id))))).scalar_one_or_none()
        if not wf: return {"status":"failed","error":"workflow not found"}
        if expected_definition_hash and (wf.status!="active" or definition_hash(wf)!=expected_definition_hash):
            return {"status":"failed","error":"Workflow changed after approval; request approval for its current definition"}
        definition=copy.deepcopy(wf.definition or {})
        try:
            current=first_node(definition)
            if not current or len(definition.get("nodes",[]))>MAX_NODES: raise ValueError("Workflow must have a starting node and at most 50 nodes")
            nodes={node["id"]:node for node in definition["nodes"]}
            if len(nodes)!=len(definition["nodes"]): raise ValueError("Workflow node IDs must be unique")
            if any(e["from"] not in nodes or e["to"] not in nodes for e in definition.get("edges",[])): raise ValueError("Workflow edge points to a missing node")
        except (ValueError,TypeError,KeyError) as exc:
            return {"status":"failed","error":str(exc) or "Invalid workflow definition"}
        event_id=None
        if trigger=="event":
            try: event_id=uuid.UUID(str((input_data or {}).get("event",{}).get("id")))
            except (TypeError,ValueError): return {"status":"failed","error":"An event run requires a valid event ID"}
            existing=(await session.execute(select(WorkflowRun).where(WorkflowRun.workflow_id==wf.id,WorkflowRun.event_id==event_id))).scalar_one_or_none()
            if existing: return {**run_result(existing),"duplicate":True}
        run=WorkflowRun(workflow_id=wf.id,tenant_id=uuid.UUID(str(tenant_id)),trigger=trigger,status="running",input=input_data or {},event_id=event_id)
        from sqlalchemy.exc import IntegrityError
        try:
            async with session.begin_nested():
                session.add(run);await session.flush()
        except IntegrityError:
            if not event_id: raise
            existing=(await session.execute(select(WorkflowRun).where(WorkflowRun.workflow_id==wf.id,WorkflowRun.event_id==event_id))).scalar_one_or_none()
            if not existing: raise
            return {**run_result(existing),"duplicate":True}
        checkpoint={"definition":definition,"name":wf.name,"user_id":str(user_id),"next_node":current,"visited":0,
            "waiting_node":None,"waiting_approvals":[],"in_flight":None,
            "data":{"input":input_data or {},"steps":{},"workflow_id":str(wf.id),"run_id":str(run.id)}}
        run.checkpoint=checkpoint
        run_id=run.id
    return await drive_run(run_id,tenant_id)


async def drive_run(run_id,tenant_id):
    """A committed in-flight claim is not replayed after ambiguous side effects."""
    import copy
    while True:
        async with session_scope() as session:
            run=(await session.execute(select(WorkflowRun).where(WorkflowRun.id==run_id,WorkflowRun.tenant_id==uuid.UUID(str(tenant_id))).with_for_update())).scalar_one_or_none()
            if not run: return {"status":"failed","error":"run not found"}
            if run.status!="running": return run_result(run)
            checkpoint=copy.deepcopy(run.checkpoint or {})
            if checkpoint.get("in_flight"): return run_result(run)
            current=checkpoint.get("continuation_node") or checkpoint.get("next_node")
            if not current:
                await finish_run(session,run,checkpoint,"succeeded")
                return run_result(run)
            node=next((n for n in checkpoint["definition"]["nodes"] if n["id"]==current),None)
            continuation=bool(checkpoint.get("continuation_node"))
            if not node or (checkpoint["visited"]>=MAX_NODES and not continuation):
                await finish_run(session,run,checkpoint,"failed","Workflow node missing or maximum step count exceeded")
                return run_result(run)
            if continuation:
                step=(await session.execute(select(RunStep).where(RunStep.run_id==run_id,RunStep.node_id==current,RunStep.status=="awaiting_approval"))).scalar_one()
            else:
                step=RunStep(run_id=run_id,tenant_id=run.tenant_id,node_id=current,node_type=node.get("type","?"),status="running",input={"config":node.get("config",{})})
                session.add(step);await session.flush()
                checkpoint["visited"]+=1
            checkpoint["in_flight"]=str(step.id)
            run.checkpoint=checkpoint
            step_id=step.id
        # No workflow database transaction is held during the HTTP/agent call.
        try:
            if continuation:
                cfg=node.get("config") or {}
                agent=Agent(agent_type=cfg.get("agent_type","customer_facing"),tenant_id=uuid.UUID(str(tenant_id)),
                    context={"user_id":checkpoint["user_id"],"workflow_id":checkpoint["data"]["workflow_id"],"run_id":str(run_id),"draft_only":True})
                original=_resolve(cfg.get("message",""),checkpoint["data"]) or checkpoint["data"]["input"].get("message","")
                import json
                prompt=original+"\nThe following actions have already been approved and executed. Do not repeat them. Complete the requested response using these actual results:\n"+json.dumps(checkpoint["data"]["steps"][current]["approval_results"],default=str)
                answer=await agent.run(prompt)
                if answer.get("unavailable") or answer.get("stopped_by"): raise RuntimeError("Approved action completed, but agent continuation was unavailable")
                out={**checkpoint["data"]["steps"][current],"ok":True,"awaiting_approval":False,"content":answer.get("content"),"continuation_tools":answer.get("tool_calls",[])}
            else:
                out=await _run_node(node,checkpoint["data"],str(tenant_id),checkpoint["user_id"])
            error=None if out.get("ok",True) else out.get("error") or f"step {current} failed"
        except Exception as exc:
            error=f"{current}: {str(exc) or type(exc).__name__}"
            out={"ok":False,"error":error}
        async with session_scope() as session:
            run=(await session.execute(select(WorkflowRun).where(WorkflowRun.id==run_id,WorkflowRun.tenant_id==uuid.UUID(str(tenant_id))).with_for_update())).scalar_one()
            checkpoint=copy.deepcopy(run.checkpoint)
            if checkpoint.get("in_flight")!=str(step_id): return run_result(run)
            step=(await session.execute(select(RunStep).where(RunStep.id==step_id,RunStep.tenant_id==run.tenant_id))).scalar_one()
            checkpoint["in_flight"]=None
            checkpoint["continuation_node"]=None
            checkpoint["data"]["steps"][current]=out
            step.output=out;step.finished_at=datetime.now(timezone.utc);step.error=error
            if error:
                step.status="failed"
                await finish_run(session,run,checkpoint,"failed",error)
                return run_result(run)
            if out.get("awaiting_approval"):
                try: ids=approval_ids(out)
                except (TypeError,ValueError): ids=[]
                if not ids:
                    step.status="failed"
                    await finish_run(session,run,checkpoint,"failed",f"{current}: approval identity missing")
                else:
                    step.status="awaiting_approval"
                    checkpoint["waiting_node"]=current;checkpoint["waiting_approvals"]=ids
                    checkpoint["next_node"]=next_node(node,checkpoint["definition"],out)
                    await finish_run(session,run,checkpoint,"awaiting_approval",f"Waiting for {len(ids)} approval(s)")
                return run_result(run)
            step.status="succeeded"
            checkpoint["waiting_node"]=None;checkpoint["waiting_approvals"]=[]
            checkpoint["next_node"]=next_node(node,checkpoint["definition"],out)
            await finish_run(session,run,checkpoint,"running")


async def resume_workflow(run_id,tenant_id):
    """Claim a parked run only after every associated action has a final outcome."""
    import copy
    from services.agent_orchestrator.models import AgentApproval
    async with session_scope() as session:
        run=(await session.execute(select(WorkflowRun).where(WorkflowRun.id==run_id,WorkflowRun.tenant_id==uuid.UUID(str(tenant_id))).with_for_update())).scalar_one_or_none()
        if not run: return {"status":"failed","error":"run not found"}
        if run.status!="awaiting_approval": return run_result(run)
        checkpoint=copy.deepcopy(run.checkpoint or {})
        if not checkpoint.get("waiting_approvals"):
            return {**run_result(run),"error":"This older run has no safe continuation checkpoint; review it before starting a new run"}
        ids=[uuid.UUID(ident) for ident in checkpoint["waiting_approvals"]]
        approvals=(await session.execute(select(AgentApproval).where(AgentApproval.id.in_(ids),AgentApproval.tenant_id==run.tenant_id,AgentApproval.run_id==run.id))).scalars().all()
        error,pending,results=approval_outcomes(approvals,checkpoint["waiting_approvals"])
        if pending: return run_result(run)
        current=checkpoint["waiting_node"]
        step=(await session.execute(select(RunStep).where(RunStep.run_id==run.id,RunStep.node_id==current,RunStep.status=="awaiting_approval"))).scalar_one_or_none()
        if not step: error=error or "Waiting workflow step is missing"
        if error:
            if step: step.status="failed";step.error=error;step.finished_at=datetime.now(timezone.utc)
            await finish_run(session,run,checkpoint,"failed",error)
            return run_result(run)
        output={**checkpoint["data"]["steps"][current],"approval_results":results,"awaiting_approval":False}
        checkpoint["data"]["steps"][current]=output
        checkpoint["continuation_node"]=current
        checkpoint["waiting_approvals"]=[]
        run.checkpoint=checkpoint;run.status="running";run.error=None;run.finished_at=None
    return await drive_run(run_id,tenant_id)


async def resume_workflow_for_approval(tenant_id,approval_id):
    from services.agent_orchestrator.models import AgentApproval
    async with session_scope() as session:
        row=(await session.execute(select(AgentApproval).where(AgentApproval.id==uuid.UUID(str(approval_id)),AgentApproval.tenant_id==uuid.UUID(str(tenant_id))))).scalar_one_or_none()
        run_id=row.run_id if row else None
    if run_id: return await resume_workflow(run_id,tenant_id)
    return None


async def recover_waiting_runs():
    """Recover a decision/execution committed before its workflow was parked."""
    from sqlalchemy import or_,and_
    from services.agent_orchestrator.models import AgentApproval
    async with session_scope() as session:
        runs=(await session.execute(select(WorkflowRun.id,WorkflowRun.tenant_id).join(AgentApproval,AgentApproval.run_id==WorkflowRun.id).where(
            WorkflowRun.status=="awaiting_approval",WorkflowRun.checkpoint.is_not(None),
            or_(AgentApproval.executed_at.is_not(None),AgentApproval.status.in_(["rejected","expired"]),and_(AgentApproval.status=="pending",AgentApproval.expires_at<=datetime.now(timezone.utc))))
            .order_by(WorkflowRun.started_at).limit(100))).all()
    for run_id,tenant_id in dict.fromkeys(runs):
        try: await resume_workflow(run_id,tenant_id)
        except Exception: logger.exception("Workflow approval recovery failed for %s",run_id)


async def approval_recovery_loop():
    import asyncio
    while True:
        try: await recover_waiting_runs()
        except Exception: logger.exception("Workflow approval recovery scan failed")
        await asyncio.sleep(15)
