"""Backend-owned AG-UI runs.

A run used to live and die with the browser's SSE connection: when the user navigated away the proxy aborted the
upstream request, Starlette cancelled the generator, and `finally: task.cancel()` killed the agent mid-turn.

Now the run executes in a detached task that writes every SSE chunk into a RunRecord. Clients (the original POST,
or a re-attach GET after navigation/reload) just *follow* the record, replaying from any event index. When the run
ends, a notification is written through the platform event bus (services.common.event_bus.notify) so the header
bell, the in-app toast and the browser Notification all come from one source.

In-process state on purpose (single orchestrator process): finished runs are kept for RETENTION_S so a client that
comes back later can replay them; after that the persisted conversation (AgentConversation/AgentMessage) is the
record of truth.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)

RETENTION_S = 3600
MAX_EVENTS = 6000
KEEPALIVE_S = 15
MAX_RECORDS = 200

_AGENT_LABELS = {
    "auto": "OmniDome Orchestrator", "customer_facing": "DomeBot", "executive": "InsightDome",
    "retention": "ChurnGuard", "provisioning": "ProvisionBot", "support": "SupportBot",
    "assistant": "OmniAssist", "orchestrator": "OmniDome Orchestrator",
}


def agent_label(agent_type: str) -> str:
    return _AGENT_LABELS.get(agent_type) or agent_type.replace("_", " ").title()


@dataclass
class RunRecord:
    run_id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: Optional[uuid.UUID]
    conversation_id: uuid.UUID
    agent_type: str
    message: str
    status: str = "running"            # running | finished | error | cancelled
    started: float = field(default_factory=time.time)
    ended: Optional[float] = None
    events: List[str] = field(default_factory=list)   # SSE chunks ("data: {...}\n\n")
    content: str = ""
    error: Optional[str] = None
    task: Optional[asyncio.Task] = None
    cond: asyncio.Condition = field(default_factory=asyncio.Condition)

    @property
    def done(self) -> bool:
        return self.status != "running"

    async def publish(self, chunk: str) -> None:
        try:
            payload = json.loads(chunk[6:]) if chunk.startswith("data: ") else {}
        except ValueError:
            payload = {}
        kind = payload.get("type")
        if kind == "TEXT_MESSAGE_CONTENT":
            self.content += str((payload.get("data") or {}).get("delta") or "")
        elif kind == "RUN_ERROR":
            self.error = str((payload.get("data") or {}).get("error") or "Run failed")
            self.status = "error"
        elif kind == "RUN_FINISHED" and self.status == "running":
            self.status = "finished"
        async with self.cond:
            if len(self.events) < MAX_EVENTS:
                self.events.append(chunk)
            self.cond.notify_all()

    async def close(self, status: Optional[str] = None) -> None:
        if status:
            self.status = status
        elif self.status == "running":
            self.status = "error"
            self.error = self.error or "Run ended unexpectedly"
        self.ended = time.time()
        async with self.cond:
            self.cond.notify_all()

    async def follow(self, start: int = 0) -> AsyncIterator[str]:
        """Yield events from index `start`, then block for new ones until the run is done."""
        i = max(0, start)
        while True:
            async with self.cond:
                while i >= len(self.events) and not self.done:
                    try:
                        await asyncio.wait_for(self.cond.wait(), timeout=KEEPALIVE_S)
                    except asyncio.TimeoutError:
                        break
                batch = self.events[i:]
                finished = self.done and i + len(batch) >= len(self.events)
            if batch:
                for chunk in batch:
                    yield chunk
                i += len(batch)
            elif not finished:
                yield ": keepalive\n\n"
            if finished:
                return

    def summary(self) -> dict:
        return {
            "run_id": str(self.run_id), "conversation_id": str(self.conversation_id),
            "agent_type": self.agent_type, "agent_name": agent_label(self.agent_type),
            "status": self.status, "message": self.message[:200],
            "started_at": self.started, "ended_at": self.ended, "events": len(self.events),
            "preview": (self.content or self.error or "")[:200],
        }


_runs: Dict[uuid.UUID, RunRecord] = {}


def _purge() -> None:
    now = time.time()
    for rid, rec in list(_runs.items()):
        if rec.ended and now - rec.ended > RETENTION_S:
            _runs.pop(rid, None)
    if len(_runs) > MAX_RECORDS:
        for rid, rec in sorted(_runs.items(), key=lambda kv: kv[1].started):
            if rec.done:
                _runs.pop(rid, None)
            if len(_runs) <= MAX_RECORDS:
                break


def create(run_id, tenant_id, user_id, conversation_id, agent_type, message) -> RunRecord:
    _purge()
    rec = RunRecord(run_id=run_id, tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id,
                    agent_type=agent_type, message=message)
    _runs[run_id] = rec
    return rec


def get(run_id: uuid.UUID, tenant_id, user_id) -> Optional[RunRecord]:
    rec = _runs.get(run_id)
    if rec is None or rec.tenant_id != tenant_id:
        return None
    if rec.user_id is not None and user_id is not None and rec.user_id != user_id:
        return None
    return rec


def list_for(tenant_id, user_id, conversation_id: Optional[uuid.UUID] = None) -> List[RunRecord]:
    out = [r for r in _runs.values() if r.tenant_id == tenant_id and (r.user_id == user_id or r.user_id is None)
           and (conversation_id is None or r.conversation_id == conversation_id)]
    return sorted(out, key=lambda r: r.started, reverse=True)


def spawn(rec: RunRecord, chunks: AsyncIterator[str]) -> None:
    """Drain `chunks` into the record in a detached task (survives client disconnects)."""
    async def pump():
        try:
            async for chunk in chunks:
                await rec.publish(chunk)
            await rec.close()
        except asyncio.CancelledError:
            await rec.close("cancelled")
            raise
        except Exception as exc:  # the generator already turns agent errors into RUN_ERROR
            logger.exception("AG-UI run %s crashed", rec.run_id)
            rec.error = rec.error or str(exc)
            await rec.close("error")
        finally:
            try:
                await _notify_done(rec)
            except Exception:
                logger.warning("run-finished notification failed for %s", rec.run_id, exc_info=True)

    rec.task = asyncio.create_task(pump())


async def _notify_done(rec: RunRecord) -> None:
    """One bell entry per finished run, addressed to the user who started it."""
    from services.common.db import session_scope
    from services.common.event_bus import notify

    if rec.status == "cancelled":
        return
    name = agent_label(rec.agent_type)
    ok = rec.status == "finished"
    title = f"{name} finished" if ok else f"{name} stopped: run failed"
    snippet = " ".join((rec.content if ok else (rec.error or "")).split())[:240]
    body = snippet or (rec.message[:160] if rec.message else None)
    link = f"/dashboard?agentRun={rec.run_id}&conversation={rec.conversation_id}"
    async with session_scope() as s:
        await notify(s, rec.tenant_id, title, body=body, category="agent_run",
                     severity="info" if ok else "warning", link=link, recipient_id=rec.user_id,
                     source="orchestrator", subject=("agent_run", rec.run_id))
