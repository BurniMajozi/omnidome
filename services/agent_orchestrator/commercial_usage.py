"""Awaited, tenant-scoped commercial telemetry. Shadow mode never charges customers."""
import functools
import logging
import os
import time
import uuid
from contextvars import ContextVar
from fastapi import HTTPException
from services.common.db import session_scope
from services.common import platform_usage

logger = logging.getLogger(__name__)
current_operation = ContextVar("commercial_operation", default=None)


def enabled():
    return os.getenv("PLATFORM_USAGE_ENABLED", "false").lower() == "true"


def operation_kind(agent_type, result=None):
    names = [str(call.get("tool") or call.get("name") or "") for call in (result or {}).get("tool_calls", [])]
    if any(any(word in name for word in ("web_search", "crawl", "research", "browser")) for name in names):
        return "research"
    if agent_type in {"portal_builder", "content", "website_builder", "marketing_content"}:
        return "content_generation"
    return "assisted_action"


def operation_panel(agent_type):
    from services.common.platform_pricing import catalog
    aliases = {"portal_builder":"portal","website_builder":"portal","marketing_content":"marketing","support":"support","sales":"sales","finance":"finance"}
    name = aliases.get(agent_type,agent_type)
    return name if name in {m["id"] for m in catalog()["modules"]} else "ai"


def metered_turn(fn):
    @functools.wraps(fn)
    async def wrapped(self, *args, **kwargs):
        if not enabled() or not self.tenant_id:
            return await fn(self, *args, **kwargs)
        tenant = str(self.tenant_id)
        operation = uuid.uuid4()
        kind = operation_kind(self.agent_type)
        try:
            async with session_scope() as db:
                policy = await platform_usage.start_operation(db, tenant, operation, kind, panel=operation_panel(self.agent_type))
        except HTTPException:
            raise
        except Exception:
            logger.error("Commercial operation was not started", exc_info=False)
            raise HTTPException(503,"Usage accounting is unavailable; retry before starting billable work")
        token = current_operation.set((tenant, operation))
        started = time.perf_counter()
        result = None
        try:
            result = await fn(self, *args, **kwargs)
            return result
        finally:
            current_operation.reset(token)
            kind = operation_kind(self.agent_type, result)
            eligible = bool(result and result.get("content") and not result.get("unavailable")
                            and not result.get("stopped_by") and result.get("status") != "awaiting_hitl")
            try:
                async with session_scope() as db:
                    await platform_usage.append_cost(db, tenant=tenant, operation=operation,
                        category="runtime", provider="platform", quantity=time.perf_counter()-started,
                        unit="wall_seconds", metadata={"outcome": "completed" if eligible else "incomplete"})
                    await platform_usage.finish_operation(db, tenant, operation, policy, kind,
                        tokens=int((result or {}).get("usage", {}).get("total_tokens") or 0),
                        eligible=eligible, status="completed" if eligible else "incomplete")
            except Exception:
                logger.error("Commercial shadow operation was not finalized", exc_info=False)
    return wrapped


async def record_model_cost(result, tenant=None, latency_ms=0, purpose="round"):
    if not enabled():
        return
    context = current_operation.get()
    if not context and not tenant:
        return  # No orphan/unscoped financial records.
    tenant, operation = context or (tenant, uuid.uuid4())
    usage = (result or {}).get("usage") or {}
    amount = usage.get("cost")
    try:
        if amount is not None and float(amount) < 0:
            amount = None
        async with session_scope() as db:
            await platform_usage.append_cost(db, tenant=tenant, operation=operation,
                category="inference", provider=(result or {}).get("provider") or "model_router",
                quantity=int(usage.get("total_tokens") or int(usage.get("prompt_tokens") or 0)+int(usage.get("completion_tokens") or 0)),
                unit="tokens", amount=amount, source="actual" if amount is not None else "unknown",
                metadata={"model": (result or {}).get("model"), "purpose": purpose,
                          "outcome": "unavailable" if (result or {}).get("unavailable") else "answered"})
    except Exception:
        # Shadow rollout exposes telemetry failures without breaking existing chat.
        # An enforcing rollout must use reservations and fail before costly work.
        logger.error("Commercial model cost was not recorded", exc_info=False)


async def record_tool_cost(name, elapsed, category=None):
    context = current_operation.get()
    if not enabled() or not context:
        return
    tenant, operation = context
    category = category or ("research" if any(x in name for x in ("search", "crawl", "research", "browser")) else "tool")
    try:
        async with session_scope() as db:
            await platform_usage.append_cost(db, tenant=tenant, operation=operation, category=category,
                provider=name, quantity=elapsed, unit="wall_seconds")
    except Exception:
        logger.error("Commercial tool cost was not recorded", exc_info=False)
