"""JEV client for the dream state (the calibrated evaluator, used only where deterministic checks cannot decide).

PRIVACY: JEV is an EXTERNAL service (TypeSafe, or OpenRouter's decisions endpoint). Only scrubbed, clipped excerpts of cards
that are not private and not in an excluded module (default hr, finance, billing, compliance) are ever sent; names are
already reduced to initials by the card builders and `scrub` redacts e-mail, phone, ID, card/bank numbers and secrets.
Off by default: needs DREAM_JEV_ENABLED=true (or the tenant setting) AND credentials.

Wire format mirrors services/agent_orchestrator/jev_gate.py: POST {state, model, questions:{name:{type:'noul',instructions}}}
and read answers[name] as a probability. tenant_memory cannot import the orchestrator, so the small client is repeated here.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Optional

import httpx

from services.tenant_memory.knowledge.dream.ports import JevAnswer
from services.tenant_memory.knowledge.textutil import clip, scrub, split_frontmatter

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
EXCERPT_CHARS = 700

QUESTIONS = {
    "still_current": ("The memory card in `card` is still accurate and current. `live_source`, when present, is the card re-rendered from the "
                      "underlying record today: the card is still current when it agrees with `live_source`, or when nothing available "
                      "contradicts it. Reply false when the card states things the live source or its own age make untrue."),
    "contradict": ("`card_a` and `card_b` make statements about the same subject that cannot both be true at the same time "
                   "(different figures, opposite statuses or opposite decisions). Wording differences alone are not a contradiction."),
    "keep_long_term": ("`card` records durable knowledge that will still help staff or agents of a fibre internet provider months from now "
                       "(a decision, a standing preference, a lasting fact), rather than a passing detail or noise."),
}


def excerpt(markdown: str, limit: int = EXCERPT_CHARS) -> str:
    return clip(scrub(split_frontmatter(markdown)[1]), limit)


def card_payload(chunk, now) -> dict:
    age = (now - chunk.as_of).days if chunk.as_of else None
    return {"title": clip(scrub(chunk.title), 120), "kind": chunk.source_type, "excerpt": excerpt(chunk.markdown),
            "as_of": chunk.as_of.date().isoformat() if chunk.as_of else None, "age_days": age}


def eligible_for_jev(chunk, exclude_modules: tuple) -> bool:
    mod = (chunk.module or "general").split(".")[0].lower()
    return chunk.visibility != "private" and mod not in {m.lower() for m in exclude_modules}


def cache_key(kind: str, state: dict) -> str:
    return hashlib.sha256((kind + "\x1f" + json.dumps(state, sort_keys=True, default=str)).encode()).hexdigest()[:40]


def decide(p: float, approve: float, reject: float) -> str:
    """'yes' only at >= approve, 'no' only at <= reject; the middle band is for a human."""
    return "yes" if p >= approve else "no" if p <= reject else "review"


def credentials() -> tuple[str, str, str]:
    key = (os.getenv("TYPESAFE_API_KEY", "") or os.getenv("JEV_API_KEY", "")).strip().strip("'\"")
    if key:
        return "typesafe", key, os.getenv("TYPESAFE_BASE_URL", "").strip() or TYPESAFE_URL
    key = os.getenv("OPENROUTER_API_KEY", "").strip().strip("'\"")
    if key:
        return "openrouter", key, OPENROUTER_DECISIONS_URL
    return "none", "", ""


class HttpJevClient:
    def __init__(self, timeout: float = 30.0, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.timeout, self._transport = timeout, transport

    def configured(self) -> bool:
        return bool(credentials()[1])

    async def ask(self, state: dict, questions: dict) -> JevAnswer:
        provider, key, endpoint = credentials()
        if not key:
            raise RuntimeError("no JEV credentials configured")
        model = "typesafe/jev-1.13" if provider == "openrouter" else os.getenv("TYPESAFE_MODEL", "jev-latest")
        body = {"state": state, "model": model, "questions": {k: {"type": "noul", "instructions": v} for k, v in questions.items()}}
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as c:
            r = await c.post(endpoint, json=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                                           "User-Agent": "OmniDome-Dream/1.0"})
        if r.status_code != 200:
            raise RuntimeError(f"JEV HTTP {r.status_code}")
        data = r.json()
        probs = {}
        for name in questions:
            a = (data.get("answers") or {}).get(name)
            v = (a.get("noul") if "noul" in a else a.get("probability", 0.5)) if isinstance(a, dict) else a
            try:
                probs[name] = max(0.0, min(1.0, float(v)))
            except (TypeError, ValueError):
                probs[name] = 0.5                       # unreadable answer = undecided, i.e. human review
        usage = data.get("usage") or {}
        return JevAnswer(probs=probs, cost_usd=float(usage.get("cost") or 0.0), model=str(data.get("model") or model),
                         tokens=usage.get("total_tokens"))
