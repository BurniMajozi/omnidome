"""LLM usage tracing (spec A7 `usage-tracing`).

One `llm_calls` row per model call (who, which model answered, tokens, latency,
outcome) and one `agent_turns` row per agent turn (rounds, tool calls, tokens,
duration, which loop guard ended it). Written off the request path; a failed
write is logged and dropped — tracing must never slow or break an agent.
The Agent Manager reads the aggregates from GET /api/usage/llm.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from typing import Any, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

ENABLED = os.getenv("USAGE_TRACING_ENABLED", "true").lower() == "true"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id UUID PRIMARY KEY,
    tenant_id UUID,
    agent_type VARCHAR(50),
    channel VARCHAR(60),
    model VARCHAR(160),
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    outcome VARCHAR(20) NOT NULL,
    purpose VARCHAR(20) NOT NULL DEFAULT 'round',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_llm_calls_tenant_time ON llm_calls (tenant_id, created_at DESC);
CREATE TABLE IF NOT EXISTS agent_turns (
    id UUID PRIMARY KEY,
    tenant_id UUID,
    agent_type VARCHAR(50),
    channel VARCHAR(60),
    rounds INTEGER NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    stopped_by VARCHAR(20),
    unavailable BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_agent_turns_tenant_time ON agent_turns (tenant_id, created_at DESC)
"""


async def ensure_schema(session) -> None:
    for statement in SCHEMA_SQL.split(";"):
        if re.sub(r"--[^\n]*", "", statement).strip():
            await session.execute(text(statement))


# ── Pure helpers ────────────────────────────────────────────────────────────

def tokens_from(result: Optional[dict]) -> tuple[int, int, int]:
    usage = (result or {}).get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or 0) or prompt + completion
    return prompt, completion, total


def call_outcome(result: Optional[dict]) -> str:
    if not result:
        return "error"
    if result.get("unavailable"):
        return "unavailable"
    if result.get("tool_calls"):
        return "tool_calls"
    if (result.get("content") or "").strip():
        return "answer"
    return "empty"


def _uuid_or_none(value: Any) -> Optional[str]:
    try:
        return str(uuid.UUID(str(value))) if value else None
    except ValueError:
        return None


# ── Recording (fire-and-forget) ─────────────────────────────────────────────

async def _insert(sql: str, params: dict) -> None:
    try:
        from services.common.db import session_scope

        async with session_scope() as s:
            await s.execute(text(sql), params)
    except Exception as exc:  # noqa: BLE001 - tracing must never break an agent
        logger.warning("usage tracing write failed: %s", exc)


def record_llm_call(*, tenant_id: Any, agent_type: str, channel: Optional[str], result: Optional[dict],
                    latency_ms: int, purpose: str = "round") -> None:
    if not ENABLED:
        return
    from services.common.background_tasks import schedule_background

    prompt, completion, total = tokens_from(result)
    schedule_background(_insert(
        """INSERT INTO llm_calls (id, tenant_id, agent_type, channel, model, prompt_tokens, completion_tokens,
                                  total_tokens, latency_ms, outcome, purpose)
           VALUES (:id, :tenant_id, :agent_type, :channel, :model, :p, :c, :t, :latency, :outcome, :purpose)""",
        {"id": str(uuid.uuid4()), "tenant_id": _uuid_or_none(tenant_id), "agent_type": agent_type,
         "channel": channel, "model": (result or {}).get("model"), "p": prompt, "c": completion, "t": total,
         "latency": int(latency_ms), "outcome": call_outcome(result), "purpose": purpose},
    ))


def record_agent_turn(*, tenant_id: Any, agent_type: str, channel: Optional[str], rounds: int, tool_calls: int,
                      total_tokens: int, duration_ms: int, stopped_by: Optional[str], unavailable: bool) -> None:
    if not ENABLED:
        return
    from services.common.background_tasks import schedule_background

    schedule_background(_insert(
        """INSERT INTO agent_turns (id, tenant_id, agent_type, channel, rounds, tool_calls, total_tokens,
                                    duration_ms, stopped_by, unavailable)
           VALUES (:id, :tenant_id, :agent_type, :channel, :rounds, :tool_calls, :tokens, :duration,
                   :stopped_by, :unavailable)""",
        {"id": str(uuid.uuid4()), "tenant_id": _uuid_or_none(tenant_id), "agent_type": agent_type,
         "channel": channel, "rounds": rounds, "tool_calls": tool_calls, "tokens": total_tokens,
         "duration": int(duration_ms), "stopped_by": stopped_by, "unavailable": bool(unavailable)},
    ))
