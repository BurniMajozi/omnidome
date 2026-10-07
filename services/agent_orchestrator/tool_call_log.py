"""Durable log of side-effect tool calls made inside a job, so a crash-and-resume
never runs the same call twice.

Key: (job_id, step, tool_name, args_hash). step is the job iteration. Before a
state-changing tool runs, its key is claimed (committed). On a replay:
  - finished call  -> the recorded result is returned, the tool is not run again;
  - claimed but no outcome recorded (crash mid-call) -> refused: whether the side
    effect happened is unknown, so a person must check rather than risk a duplicate.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any, Dict, Optional

from sqlalchemy import text

from services.common.db import session_scope

logger = logging.getLogger(__name__)

SCHEMA_SQL = (
    """CREATE TABLE IF NOT EXISTS agent_tool_calls (
        job_id UUID NOT NULL,
        step VARCHAR(40) NOT NULL,
        tool_name VARCHAR(100) NOT NULL,
        args_hash CHAR(64) NOT NULL,
        tenant_id UUID,
        status VARCHAR(12) NOT NULL DEFAULT 'started',
        result JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        finished_at TIMESTAMPTZ,
        PRIMARY KEY (job_id, step, tool_name, args_hash)
    )""",
)
_schema_ready = False


def args_hash(arguments: Dict[str, Any]) -> str:
    canonical = json.dumps(arguments or {}, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _ensure_schema(session) -> None:
    global _schema_ready
    if _schema_ready:
        return
    for statement in SCHEMA_SQL:
        await session.execute(text(statement))
    _schema_ready = True


async def claim(job_id: str | uuid.UUID, step: str, tool_name: str, arguments: Dict[str, Any],
                tenant_id: Optional[str | uuid.UUID] = None) -> Dict[str, Any]:
    """Returns {"state": "run"} (caller owns the call), {"state": "replay", "result": ...}
    or {"state": "unknown"} (a prior attempt never recorded its outcome)."""
    params = {"job": str(job_id), "step": str(step), "tool": tool_name, "hash": args_hash(arguments),
              "tenant": str(tenant_id) if tenant_id else None}
    async with session_scope() as session:
        await _ensure_schema(session)
        inserted = (await session.execute(text(
            """INSERT INTO agent_tool_calls (job_id, step, tool_name, args_hash, tenant_id)
               VALUES (:job, :step, :tool, :hash, :tenant)
               ON CONFLICT DO NOTHING RETURNING job_id"""), params)).first()
        if inserted:
            return {"state": "run"}
        row = (await session.execute(text(
            """SELECT status, result FROM agent_tool_calls
                WHERE job_id = :job AND step = :step AND tool_name = :tool AND args_hash = :hash"""), params)).first()
    if row and row[0] == "done":
        return {"state": "replay", "result": row[1]}
    return {"state": "unknown"}


async def finish(job_id: str | uuid.UUID, step: str, tool_name: str, arguments: Dict[str, Any], result: Any) -> None:
    async with session_scope() as session:
        await session.execute(text(
            """UPDATE agent_tool_calls
                  SET status = 'done', result = CAST(:result AS jsonb), finished_at = now()
                WHERE job_id = :job AND step = :step AND tool_name = :tool AND args_hash = :hash"""),
            {"job": str(job_id), "step": str(step), "tool": tool_name, "hash": args_hash(arguments),
             "result": json.dumps(result, default=str)})
