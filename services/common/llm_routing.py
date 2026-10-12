"""Platform-owned reasoning profiles. Pending checkout never grants a model tier."""
import json
import re
from contextvars import ContextVar
from sqlalchemy import text
from fastapi import HTTPException
from services.common.db import session_scope, get_tenant_context

SLOTS = ("basic", "balanced", "premium")
route_chain: ContextVar[tuple[str, ...] | None] = ContextVar("llm_route_chain", default=None)
DDL = """CREATE TABLE IF NOT EXISTS platform_llm_routing (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 config jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(), actor_id uuid)"""

def defaults():
    return {"enabled": False, "profiles": {
        "basic": {"model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "fallbacks": [], "enabled": False},
        "balanced": {"model": "", "fallbacks": [], "enabled": False},
        "premium": {"model": "", "fallbacks": [], "enabled": False}},
        "tiers": {"FREE": "basic", "STARTER": "balanced", "PROFESSIONAL": "premium", "ENTERPRISE": "premium"}}

def validate(config):
    if set(config) != {"enabled", "profiles", "tiers"} or not isinstance(config["enabled"], bool):
        raise ValueError("Expected enabled, profiles and tiers")
    if set(config["profiles"]) != set(SLOTS): raise ValueError("Configure exactly three model slots")
    for name, profile in config["profiles"].items():
        if set(profile) != {"model", "fallbacks", "enabled"} or not isinstance(profile["enabled"], bool):
            raise ValueError("Invalid profile")
        if not isinstance(profile["fallbacks"], list) or len(profile["fallbacks"]) > 2:
            raise ValueError("At most two explicit fallbacks")
        for model in [profile["model"], *profile["fallbacks"]]:
            if not isinstance(model, str) or (model and not re.fullmatch(r"[A-Za-z0-9._:/~-]{1,160}", model)):
                raise ValueError("Invalid model identifier")
            if model and name == "basic" and "/" in model and not model.endswith(":free"):
                raise ValueError("Basic cloud models must be explicitly free")
            if model and profile["model"] and ("/" in model) != ("/" in profile["model"]):
                raise ValueError("Use the same provider type for a slot and its fallbacks")
        if profile["enabled"] and not profile["model"]: raise ValueError("Enabled slots need a model")
    if set(config["tiers"]) != {"FREE", "STARTER", "PROFESSIONAL", "ENTERPRISE"}:
        raise ValueError("Configure all pricing tiers")
    if any(value not in SLOTS for value in config["tiers"].values()) or config["tiers"]["FREE"] != "basic":
        raise ValueError("Free tenants must use Basic")
    if config["enabled"] and not config["profiles"]["basic"]["enabled"]:
        raise ValueError("Enable and test Basic before enabling routing")
    return config

def tier_for(settings):
    pricing = (settings or {}).get("platform_pricing") or {}
    active = pricing.get("active_quote") or {}
    if pricing.get("billing_mode") == "trial": return "FREE"
    # Selected quote can be pending payment; only the active provisioned quote counts.
    if not active: return "FREE"
    tier = str(active.get("tier", "FREE")).upper()
    return tier if tier in {"FREE", "STARTER", "PROFESSIONAL", "ENTERPRISE"} else "FREE"

async def read_config():
    async with session_scope() as db:
        exists = (await db.execute(text("SELECT to_regclass('platform_llm_routing')"))).scalar()
        if not exists: return defaults()
        config = (await db.execute(text("SELECT config FROM platform_llm_routing WHERE singleton=true"))).scalar()
        return validate(config or defaults())

async def resolve(tenant_id=None, requested=None):
    config = await read_config()
    if not config["enabled"]: return None
    tenant_id = tenant_id or get_tenant_context()
    async with session_scope() as db:
        settings = (await db.execute(text("SELECT settings FROM tenants WHERE id=:t"), {"t": str(tenant_id)})).scalar() if tenant_id else None
    tier = tier_for(settings)
    slot = config["tiers"][tier]
    profile = config["profiles"][slot]
    if not profile["enabled"]: profile = config["profiles"]["basic"]
    chain = tuple(dict.fromkeys([profile["model"], *profile["fallbacks"]]))
    if requested and requested.removeprefix("openrouter/") not in chain:
        raise HTTPException(403, "This model is not available on your active plan")
    if requested:
        selected = requested.removeprefix("openrouter/")
        chain = (selected, *(model for model in chain if model != selected))
    return chain

async def save(config, actor):
    validate(config)
    async with session_scope() as db:
        await db.execute(text(DDL))
        await db.execute(text("""INSERT INTO platform_llm_routing(singleton,config,actor_id) VALUES(true,CAST(:c AS jsonb),:a)
          ON CONFLICT(singleton) DO UPDATE SET config=excluded.config,actor_id=excluded.actor_id,updated_at=now()"""),
          {"c": json.dumps(config), "a": str(actor)})

async def free_only(tenant_id=None):
    chain = await resolve(tenant_id)
    return chain is not None and all("/" not in model or model.endswith(":free") for model in chain)
