"""Record what agents and flows did in tenant memory (SPEC-orchestrator-memory-hardening.md, M3).

Deterministic, not left to the model:
- every executed tool that changes data (policy `mutates`) -> one entry
  (source `agent_action`);
- every finished workflow run -> one entry (source `workflow_run`, with the
  lead/deal ids it touched);
- every decided approval (A8) -> one entry (source `approval`).

Capture publishes `memory.capture.requested` on the Postgres event bus and the
`memory_capture` consumer writes the entry. A stopped memory service therefore
delays the write (bus retries with backoff), it never loses it. The consumer
skips an entry that already exists for the same source, so a retried delivery
cannot write twice.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

import httpx

from services.agent_orchestrator.memory_context import module_for
from services.common.event_bus import EventConsumer, publish

logger = logging.getLogger(__name__)

MEMORY_URL = os.getenv("TENANT_MEMORY_SERVICE_URL", "http://tenant_memory:8025")
ENABLED = os.getenv("MEMORY_CAPTURE_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
CAPTURE_EVENT = "memory.capture.requested"
SKIP_TOOLS = {"memory.write_entry", "memory.upsert_summary",
              "orchestrator_consult_specialist", "orchestrator.consult_specialist"}
MAX_TEXT = 1500


def _brief(value: Any, limit: int = 400) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def find_ids(obj: Any, found: Optional[Dict[str, List[str]]] = None) -> Dict[str, List[str]]:
    """lead/deal ids anywhere in a run's step outputs: explicit lead_id/deal_id
    keys, and the id of a returned lead (reference LD-…) or deal (DL-…)."""
    found = found if found is not None else {"lead_ids": [], "deal_ids": []}

    def add(kind: str, value: Any) -> None:
        if value and str(value) not in found[kind]:
            found[kind].append(str(value))

    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "lead_id":
                add("lead_ids", value)
            elif key == "deal_id":
                add("deal_ids", value)
        ref = str(obj.get("reference") or "")
        if obj.get("id") and ref.startswith("LD-"):
            add("lead_ids", obj["id"])
        elif obj.get("id") and ref.startswith("DL-"):
            add("deal_ids", obj["id"])
        for value in obj.values():
            find_ids(value, found)
    elif isinstance(obj, list):
        for value in obj:
            find_ids(value, found)
    return found


def tool_entry(agent_type: str, channel: str, tool_name: str, arguments: dict, result: Any) -> Optional[dict]:
    """The memory entry for an executed data-changing tool call, or None to skip."""
    if tool_name in SKIP_TOOLS:
        return None
    ok = bool(result.get("success", True)) if isinstance(result, dict) else True
    outcome = "done" if ok else "failed"
    detail = result.get("data") if isinstance(result, dict) and ok else (result.get("error") if isinstance(result, dict) else result)
    return {
        "source_type": "agent_action",
        "module": module_for(agent_type) or tool_name.split("_")[0].split(".")[0],
        "title": f"{agent_type} ran {tool_name} ({outcome})",
        "content": _brief(f"Agent {agent_type} (channel {channel}) called {tool_name} with "
                          f"{_brief(arguments)}. Result: {_brief(detail)}", MAX_TEXT),
        "importance": "normal" if ok else "low",
        "tags": ["agent_action", tool_name, agent_type],
        "metadata": {"tool": tool_name, "agent_type": agent_type, "channel": channel,
                     "success": ok, "arguments": arguments},
    }


def workflow_entry(workflow_name: str, workflow_id: Any, run_id: Any, status: str, trigger: str,
                   steps: Dict[str, Any], error: Optional[str]) -> dict:
    ids = find_ids(steps)
    step_line = ", ".join(f"{k}: {'failed' if isinstance(v, dict) and v.get('ok') is False else 'ok'}"
                          for k, v in steps.items())
    content = f"Workflow '{workflow_name}' ({trigger} run) {status}. Steps: {step_line or 'none'}."
    if error:
        content += f" Error: {_brief(error, 300)}"
    if ids["lead_ids"] or ids["deal_ids"]:
        content += f" Leads: {', '.join(ids['lead_ids']) or '-'}; deals: {', '.join(ids['deal_ids']) or '-'}."
    return {
        "source_type": "workflow_run",
        "source_id": str(run_id),
        "module": "automation",
        "title": f"Workflow '{workflow_name}' {status}",
        "content": content[:MAX_TEXT],
        "importance": "normal" if status == "succeeded" else "high",
        "tags": ["workflow_run", trigger, status],
        "metadata": {"workflow_id": str(workflow_id), "run_id": str(run_id), "trigger": trigger,
                     "status": status, **ids},
    }


def approval_entry(approval: dict, decision: str, decided_by: Optional[str], reason: Optional[str],
                   outcome: Optional[Any] = None) -> dict:
    tool = approval.get("tool_name")
    content = (f"Approval #{approval.get('reference')} for {approval.get('agent_type')} to run {tool} with "
               f"{_brief(approval.get('arguments') or {})} was {decision}"
               + (f" by {decided_by}" if decided_by else "") + (f": {reason}" if reason else "") + ".")
    if outcome is not None:
        content += f" Result: {_brief(outcome)}"
    return {
        "source_type": "approval",
        "source_id": str(approval.get("id")),
        "module": module_for(str(approval.get("agent_type"))) or "approvals",
        "title": f"Approval #{approval.get('reference')} {decision}: {tool}",
        "content": content[:MAX_TEXT],
        "importance": "high",
        "tags": ["approval", decision, str(tool)],
        "metadata": {"approval_id": str(approval.get("id")), "tool": tool, "decision": decision},
    }


# ── Producer ────────────────────────────────────────────────────────────────

async def request_in(session, tenant_id: Any, entry: dict, key: Optional[str] = None) -> None:
    """Queue an entry inside the caller's transaction (commits with its work)."""
    if not ENABLED or not tenant_id or not entry:
        return
    entry = {**entry, "source_id": entry.get("source_id") or str(uuid.uuid4())}
    await publish(session, tenant_id, CAPTURE_EVENT, entry, source="orchestrator",
                  idempotency_key=f"memcap:{key or entry['source_type'] + ':' + entry['source_id']}")


async def request(tenant_id: Any, entry: Optional[dict], key: Optional[str] = None) -> None:
    """Queue an entry in its own transaction. Never raises: capture must not
    break the agent turn that triggered it."""
    if not ENABLED or not tenant_id or not entry:
        return
    try:
        from services.common.db import session_scope
        async with session_scope() as session:
            await request_in(session, tenant_id, entry, key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Memory capture not queued (%s): %s", entry.get("title"), exc)


# ── Consumer ────────────────────────────────────────────────────────────────

async def _post(tenant_id: str, entry: dict) -> None:
    headers = {"X-Tenant-Id": tenant_id, "X-User-Id": tenant_id}
    async with httpx.AsyncClient(timeout=10) as client:
        existing = await client.get(f"{MEMORY_URL}/api/v1/memories", headers=headers, params={
            "source_type": entry["source_type"], "source_id": entry["source_id"], "include_archived": "true",
            "limit": 1})
        existing.raise_for_status()
        if existing.json().get("items"):
            return                                   # a retried delivery already wrote it
        resp = await client.post(f"{MEMORY_URL}/api/v1/memories", headers=headers, json=entry)
        resp.raise_for_status()


async def handle_capture(event: dict) -> None:
    """Write the entry; raising asks the bus to retry later (memory down)."""
    await _post(event["tenant_id"], dict(event["payload"]))


consumer = EventConsumer("memory_capture", {CAPTURE_EVENT: handle_capture})
