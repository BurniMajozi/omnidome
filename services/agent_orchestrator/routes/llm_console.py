"""Platform Owner model control. Credentials never enter browser responses."""
import hashlib
import json
import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import text
from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.common import llm_routing, openrouter
from services.agent_orchestrator.llm import LLMClient
from services.agent_orchestrator import usage

router = APIRouter()
TEST_DDL = """CREATE TABLE IF NOT EXISTS platform_llm_tests (
 fingerprint text PRIMARY KEY, actor_id uuid NOT NULL, tested_at timestamptz NOT NULL DEFAULT now())"""

def fingerprint(profile):
    return hashlib.sha256(json.dumps({k: profile[k] for k in ("model", "fallbacks")}, sort_keys=True).encode()).hexdigest()

async def owner(ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.is_platform_admin: raise HTTPException(403, "Platform Owner access required")
    return ctx

class ConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: dict

class PlaygroundInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot: str
    prompt: str = Field(min_length=1, max_length=4000)
    profile: dict | None = None

@router.get("/capabilities")
async def capabilities(ctx: AuthContext = Depends(get_auth_context)):
    return {"platform_owner": ctx.is_platform_admin}

@router.get("/choices")
async def choices(ctx: AuthContext = Depends(get_auth_context)):
    chain = await llm_routing.resolve(str(ctx.tenant_id))
    return {"managed": chain is not None, "models": list(chain or [])}

@router.get("")
async def configuration(ctx: AuthContext = Depends(owner)):
    return {"config": await llm_routing.read_config(), "keys": [{"provider": "OpenRouter", "configured": bool(openrouter.api_key()),
        "management": "Server environment", "editable": False}], "scope": "platform"}

@router.put("")
async def update(body: ConfigInput, ctx: AuthContext = Depends(owner)):
    try: llm_routing.validate(body.config)
    except (ValueError, TypeError, KeyError) as error: raise HTTPException(422, str(error)) from error
    async with session_scope() as db:
        await db.execute(text(TEST_DDL))
        for profile in body.config["profiles"].values():
            if body.config["enabled"] and profile["enabled"]:
                tested = (await db.execute(text("SELECT 1 FROM platform_llm_tests WHERE fingerprint=:f AND tested_at>now()-interval '1 day'"), {"f": fingerprint(profile)})).scalar()
                if not tested: raise HTTPException(409, "Test each model and its fallbacks before enabling the slot")
    await llm_routing.save(body.config, ctx.user_id)
    return {"config": body.config}

@router.post("/playground")
async def playground(body: PlaygroundInput, ctx: AuthContext = Depends(owner)):
    config = await llm_routing.read_config()
    if body.slot not in llm_routing.SLOTS: raise HTTPException(422, "Unknown model slot")
    profile = body.profile if body.profile is not None else config["profiles"][body.slot]
    candidate = llm_routing.defaults(); candidate["profiles"][body.slot] = profile
    try: llm_routing.validate(candidate)
    except (ValueError, TypeError, KeyError) as error: raise HTTPException(422, str(error)) from error
    if not profile["model"]: raise HTTPException(422, "Save a model before testing")
    models = tuple(dict.fromkeys([profile["model"], *profile["fallbacks"]]))
    client = LLMClient()
    started = time.perf_counter()
    # Test every fallback, rather than approving a chain when just its primary works.
    for model in models:
        token = llm_routing.route_chain.set((model,))
        try:
            result = await client._chat("assistant", [{"role":"user","content":body.prompt}], None, "none", model, model)
        finally: llm_routing.route_chain.reset(token)
        usage.record_llm_call(tenant_id=str(ctx.tenant_id), agent_type="assistant", channel="owner_playground", result=result,
                              latency_ms=int((time.perf_counter()-started)*1000), purpose="model_test")
        from services.agent_orchestrator.commercial_usage import record_model_cost
        await record_model_cost(result, str(ctx.tenant_id), int((time.perf_counter()-started)*1000), "model_test")
        if result.get("unavailable") or not result.get("content"):
            raise HTTPException(503, "A configured model did not return an answer; slot remains unverified")
    async with session_scope() as db:
        await db.execute(text(TEST_DDL))
        await db.execute(text("INSERT INTO platform_llm_tests(fingerprint,actor_id) VALUES(:f,:a) ON CONFLICT(fingerprint) DO UPDATE SET tested_at=now(),actor_id=excluded.actor_id"), {"f": fingerprint(profile), "a": str(ctx.user_id)})
    return {"content": result["content"], "served_model": result.get("model"), "tokens": result.get("usage", {}),
            "latency_ms":int((time.perf_counter()-started)*1000), "verified":True}

@router.get("/analytics")
async def analytics(ctx: AuthContext = Depends(owner)):
    async with session_scope() as db:
        rows = (await db.execute(text("""SELECT model, count(*) AS calls, coalesce(sum(total_tokens),0) AS tokens,
          count(*) FILTER(WHERE outcome IN ('error','unavailable','empty')) AS failures,
          round(avg(latency_ms)) AS latency_ms FROM llm_calls WHERE created_at>now()-interval '7 days'
          GROUP BY model ORDER BY calls DESC"""))).mappings().all()
    return {"days":7,"scope":"all_tenants","models":[dict(row) for row in rows]}
