"""The insights pipeline: access check -> gather evidence -> (cache) -> narrative -> validate -> verify (JEV) -> store.

One code path serves every panel and the executive overview. All inputs come through `Sources` (signed calls with the
caller's identity), the model through `LLMFn`, the verifier through jev_retrieval.jev_call, persistence through the store;
tests replace all four.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Optional

from services.agent_orchestrator import jev_retrieval
from services.agent_orchestrator.insights import config, fallback, narrative
from services.agent_orchestrator.insights.evidence import EvidenceSet, scrub
from services.agent_orchestrator.insights.modules import PANELS, PanelSpec, canonical, spec_for
from services.agent_orchestrator.insights.sources import Caller, HttpSources, Sources, gather
from services.agent_orchestrator.insights.store import StoreError, cache_key, get_store

logger = logging.getLogger(__name__)

VERDICTS = ("helpful", "not_helpful", "dismissed", "acted")


class UnknownModule(Exception):
    def __init__(self, module: str):
        self.module, self.valid = module, sorted(PANELS)
        super().__init__(f"unknown panel '{module}'")


class AccessDenied(Exception):
    def __init__(self, module: str, allowed: list[str]):
        self.module, self.allowed = module, allowed
        super().__init__(f"no access to the {module} panel")


class NotFound(Exception):
    pass


_inflight: dict[str, asyncio.Task] = {}
_forced: dict[tuple, deque] = defaultdict(deque)


def reset_state() -> None:      # tests
    _inflight.clear()
    _forced.clear()


# ── access ───────────────────────────────────────────────────────────────────

async def resolve_access(sources: Sources, caller: Caller) -> list[str]:
    """Panels the caller may open. The memory service decides (module permissions + roles); if it cannot answer we fall back
    to the verified identity: admins get everything, others only the modules their token names, otherwise nothing."""
    allowed = await sources.allowed_modules(caller)
    if allowed is not None:
        return sorted(set(allowed) & set(PANELS))
    if caller.is_admin:
        return sorted(PANELS)
    return sorted({canonical(m) for m in caller.modules} & set(PANELS))


def _check(spec: PanelSpec, allowed: list[str]) -> None:
    if spec.module != "overview" and spec.module not in allowed:
        raise AccessDenied(spec.module, allowed)


# ── generation ───────────────────────────────────────────────────────────────

def _iso(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(ts or time.time(), tz=timezone.utc).isoformat()


def _compact_evidence(ev: EvidenceSet) -> list[dict]:
    out = []
    for e in ev.items[:24]:
        if e.kind == "fact":
            excerpt = f"{e.title}: {e.value_text}" + (f" ({e.delta_text})" if e.delta_text else "") + f"; {e.fact_kind}; as of {(e.as_of or '')[:10]}"
        elif e.kind == "personal":
            excerpt = f"{e.title}; {e.text}"
        else:
            excerpt = e.text
        out.append({"id": e.ref, "title": scrub(e.title, 120), "excerpt": scrub(excerpt, 420)})
    if ev.headline:
        out.append({"id": "P.*", "title": "the person's own counts today", "excerpt": ", ".join(f"{k}={v}" for k, v in sorted(ev.headline.items()))})
    return out


async def verify_narrative(spec: PanelSpec, resolved: dict, ev: EvidenceSet, tenant_id: str) -> dict:
    """JEV groundedness check of the resolved narrative against exactly the evidence supplied. Local checks (citations,
    number stripping) have already run; this is the independent second opinion."""
    if not config.verify_enabled():
        return {"status": "skipped", "reason": "verification disabled"}
    text = narrative.verification_text(resolved)
    if not text.strip():
        return {"status": "skipped", "reason": "nothing to verify"}
    state = {"question": f"A briefing for the {spec.label} panel of an internet service provider", "draft": text[:3000],
             "evidence": _compact_evidence(ev)}
    qs = {
        "grounded": {"type": "noul", "instructions": "Every factual claim, figure and date in `draft` is supported by the items in "
                     "`evidence` (each evidence item states its own values); nothing in `draft` is invented or extrapolated."},
        "consistent": {"type": "noul", "instructions": "No statement in `draft` contradicts any item in `evidence`."},
        "useful": {"type": "noul", "instructions": "`draft` is a useful, specific briefing for the panel named in `question`."},
    }
    res = await jev_retrieval.jev_call(state, qs, tenant_id=tenant_id, purpose="insights", timeout=12.0)
    if not res.ok:
        return {"status": "unavailable", "reason": res.reason}
    grounded, consistent = res.answers.get("grounded", 0.5), res.answers.get("consistent", 0.5)
    prob = min(grounded, consistent)
    status = "verified" if prob >= config.verify_min_grounded() else ("weak" if prob >= config.verify_fail_below() else "failed")
    return {"status": status, "probability": round(prob, 3), "grounded": round(grounded, 3), "consistent": round(consistent, 3),
            "useful": round(res.answers.get("useful", 0.5), 3), "usage": res.usage}


def _critique(v: dict) -> str:
    return (f"grounded={v.get('grounded')}, consistent={v.get('consistent')}: some statements are not supported by the "
            "evidence or contradict it. Keep only claims the evidence states.")


async def _narrate(spec: PanelSpec, caller: Caller, ev: EvidenceSet, allowed: list[str], store: Any, llm: narrative.LLMFn,
                   degraded: list[str]) -> tuple[Optional[dict], dict, Optional[str], dict]:
    """(resolved narrative | None, verification, model, stats). Appends reasons to `degraded`."""
    view = {"roles": sorted(r for r in caller.roles if r), "panels": [m for m in allowed if m != spec.module]}
    stats: dict = {"llm_calls": 0}
    if not await store.take_budget(caller.tenant_id, config.daily_llm_calls()):
        degraded.append("daily AI budget for this workspace is used up")
        return None, {"status": "skipped", "reason": "budget"}, None, stats

    async def attempt(critique: Optional[str], previous: Optional[str]):
        msgs = narrative.build_messages(spec, view, ev, critique, previous)
        stats["llm_calls"] += 1
        got = await llm(msgs, caller.tenant_id)
        if got is None:
            return None, None, None
        text, model = got
        raw = narrative.parse_json(text)
        if raw is None:
            return None, text, model
        resolved, st = narrative.resolve(raw, ev, spec)
        stats.update(st)
        return resolved, text, model

    resolved, text, model = await attempt(None, None)
    if resolved is None:
        degraded.append("language model unavailable" if text is None else "model returned unusable output")
        return None, {"status": "skipped", "reason": "no narrative"}, model, stats
    if not resolved["recommendations"] and not resolved["summary"]:
        degraded.append("model output failed validation")
        return None, {"status": "skipped", "reason": "invalid narrative"}, model, stats

    v = await verify_narrative(spec, resolved, ev, caller.tenant_id)
    if v["status"] in ("weak", "failed") and await store.take_budget(caller.tenant_id, config.daily_llm_calls()):
        stats["retried"] = True
        again, text2, model2 = await attempt(_critique(v), text)
        if again is not None and (again["summary"] or again["recommendations"]):
            v2 = await verify_narrative(spec, again, ev, caller.tenant_id)
            v2["first_attempt"] = {k: v.get(k) for k in ("status", "probability")}
            resolved, v, model = again, v2, model2 or model
    if v["status"] == "failed":
        degraded.append("the model's briefing failed verification against your data")
        return None, v, model, stats
    return resolved, v, model, stats


def _assemble(spec: PanelSpec, scope: str, ev: EvidenceSet, resolved: Optional[dict], verification: dict, model: Optional[str],
              degraded: list[str], stats: dict, dismissed: set) -> dict:
    tmpl = fallback.template(spec, ev)
    source = "llm" if resolved else "template"
    body = resolved or tmpl
    summary = body["summary"] or tmpl["summary"]
    recs = [r for r in body["recommendations"] if r["id"] not in dismissed]
    if resolved and not recs and not body["recommendations"]:
        recs = [r for r in tmpl["recommendations"] if r["id"] not in dismissed]
    doc = {
        "id": str(uuid.uuid4()), "module": spec.module, "label": spec.label, "scope": scope,
        "summary": summary, "recommendations": recs, "kpis": fallback.kpis(ev), "risks": body.get("risks", []),
        "evidence": [e.public() for e in ev.items],
        "generated_at": _iso(), "as_of": ev.as_of(), "stale": ev.mostly_stale(),
        "degraded": "; ".join(degraded) or None, "degraded_reasons": list(degraded),
        "model": model if resolved else None, "source": source, "used_skills": list(ev.used_skills),
        "verified": bool(resolved) and verification.get("status") == "verified",
        "verification": verification, "stats": stats, "empty": False, "cached": False,
    }
    return doc


def _empty_doc(spec: PanelSpec, scope: str, ev: EvidenceSet, degraded: list[str]) -> dict:
    return {"id": str(uuid.uuid4()), "module": spec.module, "label": spec.label, "scope": scope, "summary": "",
            "recommendations": [], "kpis": [], "risks": [], "evidence": [], "generated_at": _iso(), "as_of": None,
            "stale": False, "degraded": "; ".join(degraded) or None, "degraded_reasons": list(degraded), "model": None,
            "source": "none", "used_skills": [], "verified": False, "verification": {"status": "skipped", "reason": "no evidence"},
            "stats": {}, "empty": True, "cached": False,
            "empty_reason": ("The data services behind this panel could not be reached." if degraded
                             else "Not enough data yet: nothing indexed for this panel and no open items for you.")}


async def _generate(caller: Caller, spec: PanelSpec, scope: str, ev: EvidenceSet, allowed: list[str], store: Any,
                    llm: narrative.LLMFn) -> dict:
    degraded = list(ev.degraded)
    if ev.empty():
        return _empty_doc(spec, scope, ev, degraded)
    resolved, verification, model, stats = await _narrate(spec, caller, ev, allowed, store, llm, degraded)
    dismissed = await store.dismissed_rec_ids(caller.tenant_id, caller.user_id, spec.module)
    return _assemble(spec, scope, ev, resolved, verification, model, degraded, stats, dismissed)


async def _without_dismissed(caller: Caller, spec: PanelSpec, cached: Optional[dict], store: Any) -> Optional[dict]:
    """A recommendation the person dismissed (or marked not helpful) stays hidden, also in a cached briefing."""
    if cached is None:
        return None
    dismissed = await store.dismissed_rec_ids(caller.tenant_id, caller.user_id, spec.module)
    if not dismissed:
        return cached
    doc = dict(cached["doc"])
    doc["recommendations"] = [r for r in doc.get("recommendations", []) if r["id"] not in dismissed]
    return {**cached, "doc": doc}


def _served(doc: dict, *, stored_at: float, ttl: float, now: float, cached: bool = True, extra: Optional[dict] = None) -> dict:
    out = dict(doc)
    age = max(0.0, now - stored_at)
    out.update(cached=cached, age_s=int(age), stale=bool(doc.get("stale")) or age >= ttl)
    if extra:
        out.update(extra)
    return out


def _forced_allowed(caller: Caller, now: float) -> bool:
    q = _forced[(caller.tenant_id, caller.user_id)]
    while q and now - q[0] > 600:
        q.popleft()
    if len(q) >= config.forced_refreshes_per_10min():
        return False
    q.append(now)
    return True


async def panel_insights(caller: Caller, module: str, scope: str = "", refresh: Any = False, *, sources: Optional[Sources] = None,
                         store: Any = None, llm: Optional[narrative.LLMFn] = None, now: Optional[float] = None) -> dict:
    """The briefing for one panel. `refresh`: False (use cache), True (force, rate-limited) or "background" (serve cache now,
    regenerate behind it). Raises UnknownModule / AccessDenied."""
    spec = spec_for(module)
    if spec is None:
        raise UnknownModule(module)
    sources, store, llm = sources or HttpSources(), store or get_store(), llm or narrative.default_llm
    now = now or time.time()
    scope = " ".join(str(scope or "").split())[:80]

    allowed = await resolve_access(sources, caller)
    _check(spec, allowed)

    key = cache_key(caller.tenant_id, caller.user_id, spec.module, scope, caller.roles_hash)
    ev = await gather(sources, caller, spec, scope)
    ev.allowed = allowed
    fp = ev.fingerprint(caller.roles_hash)
    ttl = config.cache_ttl_s()
    cached = await _without_dismissed(caller, spec, await store.get(key), store)

    if cached is not None and refresh is not True:
        age = now - cached["generated_at"]
        if age < ttl and cached["evidence_hash"] == fp:
            return _served(cached["doc"], stored_at=cached["generated_at"], ttl=ttl, now=now)
        if age < config.min_regen_s():                       # changed, but too soon to regenerate again
            return _served(cached["doc"], stored_at=cached["generated_at"], ttl=ttl, now=now)
        if refresh == "background":
            _regen_in_background(key, caller, spec, scope, ev, allowed, store, llm, fp)
            return _served(cached["doc"], stored_at=cached["generated_at"], ttl=ttl, now=now,
                           extra={"stale": True, "refreshing": True})
    if refresh is True and cached is not None and not _forced_allowed(caller, now):
        return _served(cached["doc"], stored_at=cached["generated_at"], ttl=ttl, now=now,
                       extra={"notice": "Refresh limit reached; showing the latest briefing."})

    doc = await _single_flight(key, caller, spec, scope, ev, allowed, store, llm, fp)
    return _served(doc, stored_at=time.time(), ttl=ttl, now=time.time(), cached=False)


async def _single_flight(key, caller, spec, scope, ev, allowed, store, llm, fp) -> dict:
    task = _inflight.get(key)
    if task is None:
        async def run() -> dict:
            try:
                doc = await _generate(caller, spec, scope, ev, allowed, store, llm)
                await store.put(key, doc, fp, caller.tenant_id, caller.user_id)
                return doc
            finally:
                _inflight.pop(key, None)
        task = asyncio.ensure_future(run())
        _inflight[key] = task
    return await task


def _regen_in_background(key, caller, spec, scope, ev, allowed, store, llm, fp) -> None:
    if key in _inflight:
        return
    try:
        from services.common.background_tasks import schedule_background
        schedule_background(_single_flight(key, caller, spec, scope, ev, allowed, store, llm, fp))
    except Exception as exc:  # noqa: BLE001
        logger.warning("background insight refresh not scheduled: %s", type(exc).__name__)


async def cached_insights(caller: Caller, module: str, scope: str = "", *, sources: Optional[Sources] = None,
                          store: Any = None, now: Optional[float] = None) -> Optional[dict]:
    """GET: the stored briefing if there is one (no generation, no LLM). Same access rules as POST."""
    spec = spec_for(module)
    if spec is None:
        raise UnknownModule(module)
    sources, store = sources or HttpSources(), store or get_store()
    _check(spec, await resolve_access(sources, caller))
    scope = " ".join(str(scope or "").split())[:80]
    cached = await _without_dismissed(caller, spec, await store.get(
        cache_key(caller.tenant_id, caller.user_id, spec.module, scope, caller.roles_hash)), store)
    if cached is None:
        return None
    return _served(cached["doc"], stored_at=cached["generated_at"], ttl=config.cache_ttl_s(), now=now or time.time())


# ── feedback ─────────────────────────────────────────────────────────────────

_IMPORTANCE = {"acted": "high", "helpful": "normal", "not_helpful": "low", "dismissed": "low"}


async def submit_feedback(caller: Caller, insight_id: str, verdict: str, rec_id: Optional[str] = None, note: Optional[str] = None,
                          *, sources: Optional[Sources] = None, store: Any = None) -> dict:
    """Store the verdict (own insights only) and write a PRIVATE memory entry so retrieval/priorities can learn from it.
    The memory write never leaves the tenant; its failure does not fail the feedback."""
    if verdict not in VERDICTS:
        raise ValueError("verdict must be one of " + ", ".join(VERDICTS))
    sources, store = sources or HttpSources(), store or get_store()
    doc = await store.get_by_id(insight_id, caller.tenant_id, caller.user_id)
    if doc is None:
        raise NotFound("insight not found")
    rec = None
    if rec_id:
        rec = next((r for r in doc.get("recommendations", []) if r["id"] == rec_id), None)
        if rec is None:
            raise NotFound("recommendation not found in that insight")
    note = scrub(note, 500) if note else None
    row = {"id": str(uuid.uuid4()), "tenant_id": caller.tenant_id, "user_id": caller.user_id, "insight_id": insight_id,
           "rec_id": rec_id, "module": doc["module"], "verdict": verdict, "note": note}
    await store.add_feedback(row)
    subject = rec["title"] if rec else f"the {doc['label']} briefing"
    evidence_ids = [e["id"] for e in (rec["evidence"] if rec else doc.get("evidence", [])[:6])]
    entry = {"source_type": "insight_feedback", "source_id": row["id"], "module": doc["module"],
             "title": f"Insight feedback ({verdict}): {subject}"[:240],
             "content": f"{caller.user_id} marked {subject} as {verdict.replace('_', ' ')} on the {doc['label']} panel."
                        + (f" Note: {note}" if note else ""),
             "visibility": "private", "importance": _IMPORTANCE[verdict],
             "tags": ["insight_feedback", doc["module"], verdict],
             "metadata": {"insight_id": insight_id, "rec_id": rec_id, "evidence_ids": evidence_ids, "verdict": verdict}}
    signalled = False
    try:
        signalled = await sources.memory_signal(caller, entry)
    except Exception as exc:  # noqa: BLE001
        logger.info("insight feedback memory signal skipped: %s", type(exc).__name__)
    return {"id": row["id"], "stored": True, "memory_signal": signalled, "verdict": verdict}
