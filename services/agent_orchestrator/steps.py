"""Public activity summaries only: never model reasoning, prompts or raw tool arguments."""
import asyncio
import time
import uuid
import re
from contextvars import ContextVar
from datetime import datetime, timezone

current = ContextVar("agent_public_steps", default=None)


class Steps:
    def __init__(self, run_id, tenant_id, user_id):
        self.run_id, self.tenant_id, self.user_id = run_id, tenant_id, user_id
        self.queue = asyncio.Queue()
        self.started = time.monotonic()
        self.active = {}
        self.last_title = "Starting"

    @staticmethod
    def sanitize(value):
        def safe(v, key=""):
            if isinstance(v, dict): return {k: safe(x, k) for k, x in v.items()}
            if isinstance(v, list): return [safe(x) for x in v]
            if isinstance(v, str) and key not in {"id", "run_id", "question_id", "approval_id", "reference", "started_at", "ended_at", "expires_at", "status", "kind", "tool"}:
                v = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", v)
                v = re.sub(r"(?i)bearer\s+\S+|\b(?:sk-|token=)[A-Za-z0-9_-]+", "[redacted]", v)
                v = re.sub(r"\+?\d[\d ()-]{7,}\d", "[number]", v)
                return v[:700]
            return v
        return safe(value)

    def emit(self, name, value):
        self.queue.put_nowait({"name": name, "value": self.sanitize(value)})

    def begin(self, kind, title):
        sid = "s_" + uuid.uuid4().hex[:10]
        item = {"id": sid, "kind": kind, "title": title, "detail": "", "status": "running", "started_at": datetime.now(timezone.utc).isoformat(), "ended_at": None, "duration_ms": None, "result_summary": None, "meta": {}}
        self.active[sid] = (time.monotonic(), item)
        self.last_title = title
        self.emit("omnidome.step", item.copy())
        self.emit("omnidome.status", {"text": title, "elapsed_ms": round((time.monotonic() - self.started) * 1000)})
        return sid

    def end(self, sid, *, error=False, summary="Completed"):
        started, item = self.active.pop(sid)
        item = {**item, "status": "error" if error else "done", "ended_at": datetime.now(timezone.utc).isoformat(), "duration_ms": round((time.monotonic() - started) * 1000), "result_summary": summary}
        self.emit("omnidome.step", item)

    def heartbeat(self):
        elapsed = round((time.monotonic() - self.started) * 1000)
        self.emit("omnidome.status", {"text": f"Still working: {self.last_title.lower()} ({elapsed // 1000}s)", "elapsed_ms": elapsed})


async def track(kind, title, operation, summary_from=None):
    steps = current.get()
    sid = steps.begin(kind, title) if steps else None
    try:
        result = await operation
        if steps:
            outcome = result[2] if isinstance(result, tuple) and len(result) == 3 else result
            failed = isinstance(outcome, dict) and outcome.get("success") is False
            summary = "Could not complete this step" if failed else "Completed"
            if isinstance(outcome, dict):
                payload = outcome.get("result", outcome)
                if isinstance(payload, dict) and isinstance(payload.get("rows"), list): summary = f"{len(payload['rows'])} rows"
            if summary_from: summary = summary_from(result)
            steps.end(sid, error=failed, summary=summary)
        return result
    except BaseException:
        if steps: steps.end(sid, error=True, summary="Cancelled or unavailable")
        raise
