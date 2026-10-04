"""OKF skills at run time (SPEC-orchestrator-memory-hardening.md, M2).

Skills registered in tenant memory (`/api/v1/skills`) add guidance to an
agent's system prompt when that agent has every tool the skill requires.
They never grant tools or override an agent's assigned tool policy.

Skills are fetched once per tenant and cached for CACHE_TTL_S. Like memory
recall this fails open: no skills service, no extra guidance.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

MEMORY_URL = os.getenv("TENANT_MEMORY_SERVICE_URL", "http://tenant_memory:8025")
CACHE_TTL_S = float(os.getenv("OKF_SKILLS_CACHE_S", "60"))
FETCH_TIMEOUT_S = float(os.getenv("OKF_SKILLS_TIMEOUT_S", "2"))
MAX_SKILLS = 8
MAX_GUIDANCE_CHARS = 1200

_cache: Dict[str, Tuple[float, List[dict]]] = {}


def clear_cache() -> None:
    _cache.clear()


def applies_to(skill: dict, agent_type: str) -> bool:
    targets = skill.get("target_agent_types") or []
    return not targets or agent_type in targets or skill.get("source_agent_type") == agent_type


async def _fetch(tenant_id: str, actor_id: Optional[str]) -> List[dict]:
    headers = {"X-Tenant-Id": tenant_id, "X-User-Id": str(actor_id or tenant_id)}
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_S) as client:
        resp = await client.get(f"{MEMORY_URL}/api/v1/skills", headers=headers)
        resp.raise_for_status()
        return resp.json().get("items", [])


async def tenant_skills(tenant_id: Optional[str], actor_id: Optional[str] = None) -> List[dict]:
    """All active skills of the tenant (cached). [] on any error."""
    if not tenant_id:
        return []
    hit = _cache.get(tenant_id)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    try:
        skills = await _fetch(tenant_id, actor_id)
    except Exception as exc:
        logger.warning("OKF skills unavailable for tenant %s: %s", tenant_id, exc)
        skills = hit[1] if hit else []      # keep serving the last good list
        _cache[tenant_id] = (time.monotonic() + min(CACHE_TTL_S, 10), skills)
        return skills
    _cache[tenant_id] = (time.monotonic() + CACHE_TTL_S, skills)
    return skills


async def skills_for(tenant_id: Optional[str], agent_type: str, actor_id: Optional[str] = None) -> List[dict]:
    return [s for s in await tenant_skills(tenant_id, actor_id) if applies_to(s, agent_type)][:MAX_SKILLS]


def skills_prompt(skills: List[dict]) -> str:
    """The "Skills" section appended to the agent's system prompt; "" if none."""
    if not skills:
        return ""
    parts = ["## Skills (shared with you through OKF — follow them when they apply)"]
    for s in skills:
        guidance = " ".join(str(s.get("guidance_prompt") or "").split())
        if len(guidance) > MAX_GUIDANCE_CHARS:
            guidance = guidance[: MAX_GUIDANCE_CHARS - 1] + "…"
        tools = s.get("tools_required") or []
        parts.append(f"### {s.get('skill_name')}\n{guidance}" + (f"\nTools: {', '.join(tools)}" if tools else ""))
    return "\n\n".join(parts)


def extra_tool_names(skills: List[dict], have: List[str], known: List[str]) -> List[str]:
    """tools_required of the skills that the registry knows and the agent lacks."""
    out: List[str] = []
    for s in skills:
        for name in s.get("tools_required") or []:
            if name in known and name not in have and name not in out:
                out.append(name)
    return out
