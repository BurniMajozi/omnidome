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

import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import select

from services.common.db import session_scope
from services.agent_orchestrator.models import Workflow, WorkflowRun, RunStep
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

    if ntype == "agent_invoke":
        agent_type = cfg.get("agent_type", "customer_facing")
        message = _resolve(cfg.get("message", ""), data) or (data.get("input") or {}).get("message", "")
        agent = Agent(
            agent_type=agent_type,
            tenant_id=uuid.UUID(tenant_id) if tenant_id else None,
            context={"user_id": user_id},
        )
        result = await agent.run(message)
        return {"ok": True, "content": result.get("content"), "tool_calls": result.get("tool_calls", [])}

    if ntype == "http_request":
        url = _resolve(cfg.get("url", ""), data)
        method = cfg.get("method", "GET").upper()
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.request(method, url, json=cfg.get("body"))
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:1000]
        return {"ok": resp.status_code < 400, "status": resp.status_code, "body": body}

    if ntype == "condition":
        left = _resolve(str(cfg.get("left", "")), data)
        return {"ok": True, "result": _eval_condition(left, cfg.get("op", "eq"), cfg.get("right"))}

    return {"ok": False, "error": f"unknown node type: {ntype}"}


async def run_workflow(
    workflow_id: uuid.UUID,
    tenant_id: str,
    user_id: str,
    input_data: Optional[dict] = None,
    trigger: str = "manual",
) -> dict:
    """Execute a workflow end-to-end, persisting the run + steps."""
    async with session_scope() as session:
        wf = (
            await session.execute(
                select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == uuid.UUID(tenant_id))
            )
        ).scalar_one_or_none()
        if not wf:
            return {"error": "workflow not found"}

        run = WorkflowRun(
            workflow_id=wf.id, tenant_id=uuid.UUID(tenant_id), trigger=trigger,
            status="running", input=input_data or {},
        )
        session.add(run)
        await session.flush()
        run_id = run.id

        definition = wf.definition or {}
        nodes = {n["id"]: n for n in definition.get("nodes", [])}
        edges = definition.get("edges", [])
        data: dict = {"input": input_data or {}, "steps": {}}

        incoming = {e["to"] for e in edges}
        current = next((nid for nid, n in nodes.items() if n.get("type") == "trigger"), None) \
            or next((nid for nid in nodes if nid not in incoming), None)

        visited = 0
        final_error: Optional[str] = None
        while current and visited < MAX_NODES:
            visited += 1
            node = nodes.get(current)
            if not node:
                break
            step = RunStep(
                run_id=run_id, node_id=current, node_type=node.get("type", "?"),
                status="running", input={"config": node.get("config", {})},
            )
            session.add(step)
            await session.flush()
            try:
                out = await _run_node(node, data, tenant_id, user_id)
                data["steps"][current] = out
                step.output = out
                step.status = "succeeded" if out.get("ok", True) else "failed"
                if not out.get("ok", True):
                    final_error = out.get("error")
            except Exception as exc:  # noqa: BLE001
                logger.exception("workflow node %s failed", current)
                step.status, step.error = "failed", str(exc)
                final_error = str(exc)
            step.finished_at = datetime.now(timezone.utc)
            await session.flush()

            if step.status == "failed" or node.get("type") == "end":
                break

            outgoing = [e for e in edges if e["from"] == current]
            if node.get("type") == "condition":
                want = "true" if data["steps"][current].get("result") else "false"
                current = next((e["to"] for e in outgoing if str(e.get("condition", "")).lower() == want), None) \
                    or next((e["to"] for e in outgoing if not e.get("condition")), None)
            else:
                current = outgoing[0]["to"] if outgoing else None

        run.status = "failed" if final_error else "succeeded"
        run.error = final_error
        run.output = data["steps"]
        run.finished_at = datetime.now(timezone.utc)
        await session.flush()
        return {"run_id": str(run_id), "status": run.status, "steps": data["steps"], "error": final_error}
