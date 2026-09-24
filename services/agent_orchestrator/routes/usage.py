"""LLM usage for the Agent Manager (spec A7 `usage-tracing`).

GET /api/usage/llm?days=7 → per-agent turns (with loop-guard stops) and
per-model calls (tokens, failures, latency) for the caller's tenant.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope

router = APIRouter()


@router.get("/llm")
async def llm_usage(days: int = Query(7, ge=1, le=90), ctx: AuthContext = Depends(get_auth_context)):
    params = {"t": str(ctx.tenant_id), "days": days}
    async with session_scope() as s:
        agents = (await s.execute(text("""
            SELECT agent_type,
                   count(*)                                   AS turns,
                   coalesce(sum(tool_calls), 0)               AS tool_calls,
                   coalesce(sum(total_tokens), 0)             AS tokens,
                   round(avg(duration_ms))                    AS avg_duration_ms,
                   count(*) FILTER (WHERE stopped_by = 'step_limit') AS stopped_step_limit,
                   count(*) FILTER (WHERE stopped_by = 'empty')      AS stopped_empty,
                   count(*) FILTER (WHERE stopped_by = 'truncated')  AS stopped_truncated,
                   count(*) FILTER (WHERE unavailable)               AS ai_unavailable
              FROM agent_turns
             WHERE tenant_id = :t AND created_at >= now() - make_interval(days => :days)
             GROUP BY agent_type ORDER BY turns DESC
        """), params)).mappings().all()
        models = (await s.execute(text("""
            SELECT coalesce(model, 'none')                    AS model,
                   count(*)                                   AS calls,
                   coalesce(sum(total_tokens), 0)             AS tokens,
                   count(*) FILTER (WHERE outcome IN ('error', 'unavailable', 'empty')) AS failures,
                   round(avg(latency_ms))                     AS avg_latency_ms
              FROM llm_calls
             WHERE tenant_id = :t AND created_at >= now() - make_interval(days => :days)
             GROUP BY 1 ORDER BY calls DESC
        """), params)).mappings().all()
    as_int = lambda row: {k: (int(v) if hasattr(v, "__int__") and not isinstance(v, str) else v) for k, v in row.items()}  # noqa: E731
    return {"days": days, "agents": [as_int(r) for r in agents], "models": [as_int(r) for r in models]}
