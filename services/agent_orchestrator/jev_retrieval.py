"""JEV for retrieval and augmentation (docs/insights-and-jev.md).

What this adds on top of the existing JEV tool gate / answer verifier (jev_gate.py):

  1. RELEVANCE JUDGE   for analytic questions only, the retrieved cards are scored with three JEV propositions
                       (answers_question / is_current / applies_to_this_user), kept above a threshold, re-ordered by the
                       judged score, and dropped when stale or contradicted. Judgements are cached by (question, card).
  2. AUGMENTATION      JEV's confidence decides what happens next: answer, widen retrieval once (graph neighbours + a
                       larger pack), ask ONE clarifying question, or answer with explicit uncertainty.
  3. EVIDENCE          the answer verifier now receives the injected knowledge/memory pack, not only tool outputs, so a
                       correct answer grounded in a card is no longer flagged "ungrounded".
  4. TELEMETRY         one row per turn in `retrieval_log` (which cards were retrieved / kept / used / cited, JEV scores) so the
                       nightly dream-state job can learn relevance from real usage. No query text is stored, only a hash.

Safety properties (all JEV calls here go through `jev_call`):
  * never blocks or fails a turn: short timeout, circuit breaker, every error returns "no judgement";
  * per-tenant daily call budget; global off switch JEV_RETRIEVAL_ENABLED (default on);
  * DATA EGRESS: JEV is an external API. Only scrubbed card excerpts (markup removed, e-mail addresses and long
    digit runs masked, <= 450 chars each) and the question text leave the platform. JEV_DATA_EGRESS=false disables every
    JEV call that carries tenant data (judge, insights verification, answer verification) and the platform falls back to
    its local deterministic checks.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("agent_orchestrator.jev_retrieval")


# ── settings (read at call time) ─────────────────────────────────────────────

def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _num(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)


def enabled() -> bool:
    return _flag("JEV_RETRIEVAL_ENABLED", True)


def egress_allowed() -> bool:
    return _flag("JEV_DATA_EGRESS", True)


def telemetry_enabled() -> bool:
    return _flag("JEV_RETRIEVAL_TELEMETRY", True)


def threshold() -> float:
    return _num("JEV_RETRIEVAL_THRESHOLD", 0.35)


def top_n() -> int:
    return max(2, int(_num("JEV_RETRIEVAL_TOP_N", 8)))


def timeout_s() -> float:
    return _num("JEV_RETRIEVAL_TIMEOUT_S", 6.0)


def daily_cap(purpose: str) -> int:
    return int(_num("JEV_INSIGHTS_DAILY_CALLS", 200)) if purpose == "insights" else int(_num("JEV_RETRIEVAL_DAILY_CALLS", 300))


# ── circuit breaker + budget ─────────────────────────────────────────────────

class Breaker:
    def __init__(self, threshold: int = 3, cooldown_s: float = 60.0):
        self.threshold, self.cooldown_s = threshold, cooldown_s
        self.failures = 0
        self.open_until = 0.0

    def allow(self) -> bool:
        return time.monotonic() >= self.open_until

    def ok(self) -> None:
        self.failures = 0

    def fail(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.open_until = time.monotonic() + self.cooldown_s
            self.failures = 0


breaker = Breaker()
_budget: Dict[tuple, int] = {}


def take_budget(tenant_id: str, purpose: str) -> bool:
    day = time.strftime("%Y-%m-%d", time.gmtime())
    k = (str(tenant_id), day, purpose)
    for old in [x for x in _budget if x[1] != day]:
        _budget.pop(old, None)
    if _budget.get(k, 0) >= daily_cap(purpose):
        return False
    _budget[k] = _budget.get(k, 0) + 1
    return True


def reset_state() -> None:    # tests
    breaker.failures, breaker.open_until = 0, 0.0
    _budget.clear()
    _cache.clear()


# ── scrubbing + transport ────────────────────────────────────────────────────

_TAG = re.compile(r"</?\s*(?:knowledge_reference|evidence|system|assistant|user)[^>]*>", re.IGNORECASE)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LONG_DIGITS = re.compile(r"(?<!\d)(?:\+27|0)?\d{9,}(?!\d)")


def scrub(text: Any, limit: int = 450) -> str:
    t = _TAG.sub("[removed]", str(text or ""))
    t = _EMAIL.sub("[email]", t)
    t = _LONG_DIGITS.sub("[number]", t)
    t = " ".join(t.split())
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


@dataclass
class JevResult:
    ok: bool
    answers: Dict[str, float] = field(default_factory=dict)
    reason: str = ""
    usage: Optional[dict] = None


def _prob(obj: Any) -> float:
    if isinstance(obj, dict):
        val = obj.get("noul", obj.get("probability", 0.5))
    else:
        val = obj
    try:
        return max(0.0, min(1.0, float(val)))
    except (TypeError, ValueError):
        return 0.5


async def jev_call(state: dict, questions: dict, *, tenant_id: str, purpose: str, timeout: Optional[float] = None,
                   transport: Optional[httpx.AsyncBaseTransport] = None) -> JevResult:
    """One JEV evaluation. Uses the same credentials/endpoint as the tool gate (TypeSafe key, else OpenRouter's
    /alpha/decisions with OPENROUTER_API_KEY). Never raises."""
    from services.agent_orchestrator import jev_gate
    from services.agent_orchestrator.config import settings
    if not enabled() or not settings.jev_gate_enabled:
        return JevResult(False, reason="disabled")
    if not egress_allowed():
        return JevResult(False, reason="egress_off")
    provider, api_key, endpoint = jev_gate._get_credentials()
    if not api_key:
        return JevResult(False, reason="no_credentials")
    if not breaker.allow():
        return JevResult(False, reason="breaker_open")
    if not take_budget(tenant_id, purpose):
        return JevResult(False, reason="budget")
    model_name = "typesafe/jev-1.13" if provider == "openrouter" else getattr(settings, "typesafe_model", "jev-latest")
    try:
        async with httpx.AsyncClient(timeout=timeout or timeout_s(), transport=transport) as client:
            resp = await client.post(endpoint, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                                                        "User-Agent": "OmniDome-Agent-Orchestrator/1.0"},
                                     json={"state": state, "model": model_name, "questions": questions})
        if resp.status_code != 200:
            breaker.fail()
            return JevResult(False, reason=f"http_{resp.status_code}")
        data = resp.json()
        breaker.ok()
        answers = {k: _prob(v) for k, v in (data.get("answers") or {}).items()}
        return JevResult(True, answers, usage={"provider": provider, "model": data.get("model") or model_name,
                                               "total_tokens": (data.get("usage") or {}).get("total_tokens"),
                                               "cost_usd": (data.get("usage") or {}).get("cost")})
    except httpx.TimeoutException:
        breaker.fail()
        return JevResult(False, reason="timeout")
    except Exception as exc:  # noqa: BLE001
        breaker.fail()
        logger.warning("JEV call failed (%s)", type(exc).__name__)
        return JevResult(False, reason="error")


# ── relevance judge ──────────────────────────────────────────────────────────

ANALYTIC = re.compile(r"\b(why|trend|compare|comparison|versus|vs\.?|forecast|predict|churn|revenue|margin|growth|decline|"
                      r"analy[sz]e|analysis|breakdown|root cause|drivers?|performance|kpi|report|summar(?:y|ise|ize)|"
                      r"what happened|how (?:is|are|did|has|have)|risk|opportunit(?:y|ies)|pipeline)\b", re.IGNORECASE)


def is_analytic(query: str) -> bool:
    q = " ".join(str(query or "").split())
    return len(q) >= 60 or bool(ANALYTIC.search(q))


@dataclass
class JudgedCard:
    card_id: str
    ref: Optional[int]
    rank: int
    answers: float
    current: float
    applies: float
    score: float
    kept: bool
    reason: str = ""
    cached: bool = False

    def public(self) -> dict:
        return {"card_id": self.card_id, "rank": self.rank, "answers_question": round(self.answers, 3),
                "is_current": round(self.current, 3), "applies_to_user": round(self.applies, 3),
                "score": round(self.score, 3), "kept": self.kept, "reason": self.reason, "cached": self.cached}


@dataclass
class JudgeOutcome:
    status: str                      # judged | skipped:<reason>
    judged: List[JudgedCard] = field(default_factory=list)
    confidence: float = 0.0
    calls: int = 0
    ms: int = 0

    @property
    def kept(self) -> List[JudgedCard]:
        return [j for j in self.judged if j.kept]


_cache: "OrderedDict[str, tuple]" = OrderedDict()
CACHE_MAX = 2048
CACHE_TTL_S = 3600.0


def _norm_query(q: str) -> str:
    return re.sub(r"\s+", " ", str(q or "").strip().lower())


def _cache_key(tenant: str, query: str, card: dict) -> str:
    card_hash = hashlib.sha256(f"{card['card_id']}|{card.get('as_of')}|{card.get('excerpt')}".encode()).hexdigest()[:16]
    return hashlib.sha256(f"{tenant}|{_norm_query(query)}".encode()).hexdigest()[:16] + ":" + card_hash


def _cache_get(key: str) -> Optional[tuple]:
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
        _cache.move_to_end(key)
        return hit[1]
    _cache.pop(key, None)
    return None


def _cache_put(key: str, value: tuple) -> None:
    _cache[key] = (time.monotonic(), value)
    _cache.move_to_end(key)
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)


def combine(answers: float, current: float, applies: float) -> float:
    return answers * (0.5 + 0.5 * current) * (0.6 + 0.4 * applies)


async def judge_cards(query: str, cards: List[dict], *, tenant_id: str, user_roles: Optional[List[str]] = None,
                      transport: Optional[httpx.AsyncBaseTransport] = None) -> JudgeOutcome:
    """cards: [{card_id, ref, title, module, as_of, stale, excerpt}] in retrieval order. Never raises."""
    started = time.perf_counter()
    if not cards:
        return JudgeOutcome("skipped:no_cards")
    cards = cards[: top_n()]
    scores: Dict[str, tuple] = {}
    todo = []
    for c in cards:
        hit = _cache_get(_cache_key(tenant_id, query, c))
        if hit is not None:
            scores[c["card_id"]] = (*hit, True)
        else:
            todo.append(c)
    calls = 0
    if todo:
        state = {"question": scrub(query, 600), "user": {"roles": sorted(set(user_roles or []))[:6]},
                 "cards": {f"c{i}": {"title": scrub(c.get("title"), 140), "module": c.get("module"), "as_of": c.get("as_of"),
                                     "marked_stale": bool(c.get("stale")), "excerpt": scrub(c.get("excerpt"), 450)}
                           for i, c in enumerate(todo)}}
        questions = {}
        for i in range(len(todo)):
            questions[f"c{i}_answers"] = {"type": "noul", "instructions":
                "`cards.c%d` contains information that directly helps answer `question`." % i}
            questions[f"c{i}_current"] = {"type": "noul", "instructions":
                "`cards.c%d` describes the current situation: its as_of date is recent enough for `question` and nothing "
                "in `question` or the other cards contradicts it." % i}
            questions[f"c{i}_applies"] = {"type": "noul", "instructions":
                "`cards.c%d` is about the same area, entity or period that `question` is about, and is the kind of "
                "information someone with `user.roles` would use." % i}
        res = await jev_call(state, questions, tenant_id=tenant_id, purpose="retrieval", transport=transport)
        calls = 1
        if not res.ok:
            return JudgeOutcome(f"skipped:{res.reason}", ms=int((time.perf_counter() - started) * 1000))
        for i, c in enumerate(todo):
            # a proposition JEV did not answer is neutral-positive, so a partial response never drops a card by itself
            a, cur, ap = (res.answers.get(f"c{i}_answers", 0.6), res.answers.get(f"c{i}_current", 0.8),
                          res.answers.get(f"c{i}_applies", 0.8))
            _cache_put(_cache_key(tenant_id, query, c), (a, cur, ap))
            scores[c["card_id"]] = (a, cur, ap, False)

    judged: List[JudgedCard] = []
    thr = threshold()
    for rank, c in enumerate(cards):
        a, cur, ap, was_cached = scores[c["card_id"]]
        score = combine(a, cur, ap)
        reason = ""
        kept = True
        if cur < 0.25:
            kept, reason = False, "stale or contradicted"
        elif score < thr:
            kept, reason = False, "below relevance threshold"
        judged.append(JudgedCard(c["card_id"], c.get("ref"), rank, a, cur, ap, score, kept, reason, was_cached))
    kept_sorted = sorted([j for j in judged if j.kept], key=lambda j: (-j.score, j.rank))
    top = [j.score for j in kept_sorted[:3]]
    confidence = sum(top) / len(top) if top else 0.0
    return JudgeOutcome("judged", judged, confidence, calls, int((time.perf_counter() - started) * 1000))


# ── augmentation policy ──────────────────────────────────────────────────────

@dataclass
class Decision:
    action: str          # answer | widen | clarify | uncertain
    confidence: float
    note: str = ""

    def public(self) -> dict:
        return {"action": self.action, "confidence": round(self.confidence, 3)}


CLARIFY_NOTE = ("Retrieval found nothing that clearly matches this request. Before answering, ask the user ONE short clarifying "
                "question (which customer, module, team or period they mean), unless a governed query tool can answer directly.")
UNCERTAIN_NOTE = ("The retrieved knowledge only weakly matches this question. If you answer from it, say plainly that you are "
                  "uncertain and what is missing; take exact figures from the governed query tools, not from the cards.")


def decide(confidence: float, query: str, widened: bool, n_kept: int) -> Decision:
    q_words = len(str(query or "").split())
    if confidence >= 0.6 and n_kept:
        return Decision("answer", confidence)
    if not widened:
        return Decision("widen", confidence)
    if confidence < 0.3 and q_words <= 5:
        return Decision("clarify", confidence, CLARIFY_NOTE)
    if confidence < 0.6:
        return Decision("uncertain", confidence, UNCERTAIN_NOTE)
    return Decision("answer", confidence)


# ── pack refinement (called from knowledge_client.grounding_block) ───────────

_BLOCK = re.compile(r"(?m)^(?=\[\d+\] )")
_HEAD = re.compile(r"^\[(\d+)\] (.*?)(?: \(([^)]*)\))?\s*$", re.MULTILINE)


def split_blocks(context: str) -> tuple[str, Dict[int, str]]:
    parts = _BLOCK.split(context or "")
    header = parts[0] if parts and not parts[0].startswith("[") else ""
    blocks: Dict[int, str] = {}
    for p in parts:
        m = re.match(r"\[(\d+)\] ", p)
        if m:
            blocks[int(m.group(1))] = p
    return header, blocks


def _body_of(block: str) -> str:
    lines = block.split("\n", 1)
    return lines[1] if len(lines) > 1 else ""


def cards_from_pack(pack: dict) -> List[dict]:
    header, blocks = split_blocks(pack.get("context") or "")
    out = []
    for c in pack.get("citations") or []:
        ref = c.get("ref")
        blk = blocks.get(int(ref)) if ref is not None else None
        if blk is None:
            continue
        out.append({"card_id": c.get("card_id"), "ref": ref, "title": c.get("title"), "module": c.get("module"),
                    "as_of": c.get("as_of"), "stale": bool(c.get("stale")), "excerpt": _body_of(blk)})
    return out


def apply_judgement(pack: dict, outcome: JudgeOutcome) -> dict:
    """Pack re-ordered by judged score with rejected cards removed. Original [n] refs are kept (they are labels)."""
    header, blocks = split_blocks(pack.get("context") or "")
    cits = {int(c["ref"]): c for c in pack.get("citations") or [] if c.get("ref") is not None}
    order = sorted(outcome.kept, key=lambda j: (-j.score, j.rank))
    new_cits, new_blocks = [], []
    for j in order:
        if j.ref is None or int(j.ref) not in blocks:
            continue
        new_blocks.append(blocks[int(j.ref)])
        new_cits.append({**cits[int(j.ref)], "jev_score": round(j.score, 3)})
    out = dict(pack)
    out["citations"] = new_cits
    out["context"] = ((header + "\n".join(new_blocks)).strip() if new_blocks else "")
    out["used_tokens"] = max(1, len(out["context"]) // 4) if new_blocks else 0
    out["dropped_by_judge"] = [j.card_id for j in outcome.judged if not j.kept]
    return out


async def refine_pack(pack: dict, query: str, *, tenant_id: str, roles: Optional[List[str]], widen=None,
                      transport: Optional[httpx.AsyncBaseTransport] = None) -> tuple[dict, dict, str]:
    """(pack, jev_info, trusted_note). `widen` is an async callable returning a wider pack (or None). Never raises; on any
    problem the original pack comes back unchanged with a `skipped:*` status."""
    info: Dict[str, Any] = {"status": "skipped:not_analytic", "widened": False}
    try:
        if not enabled() or not egress_allowed():
            info["status"] = "skipped:" + ("disabled" if not enabled() else "egress_off")
            return pack, info, ""
        if pack.get("status") != "ready" or not is_analytic(query):
            return pack, info, ""
        outcome = await judge_cards(query, cards_from_pack(pack), tenant_id=tenant_id, user_roles=roles, transport=transport)
        if outcome.status != "judged":
            info["status"] = outcome.status
            return pack, info, ""
        decision = decide(outcome.confidence, query, False, len(outcome.kept))
        widened = False
        total_calls = outcome.calls
        if decision.action == "widen":
            if widen is not None:                      # one widening attempt: graph neighbours + a larger pack
                wider = await widen()
                if wider and wider.get("status") == "ready":
                    second = await judge_cards(query, cards_from_pack(wider), tenant_id=tenant_id, user_roles=roles,
                                               transport=transport)
                    total_calls += second.calls
                    if second.status == "judged" and second.confidence >= outcome.confidence:
                        pack, outcome, widened = wider, second, True
            decision = decide(outcome.confidence, query, True, len(outcome.kept))
        outcome.calls = total_calls
        refined = apply_judgement(pack, outcome)
        if not refined["citations"]:
            refined["status"] = "no_matches"
        info.update(status="judged", widened=widened, confidence=round(outcome.confidence, 3), action=decision.action,
                    judged=[j.public() for j in outcome.judged], calls=outcome.calls, ms=outcome.ms,
                    dropped=len(refined.get("dropped_by_judge", [])), dropped_card_ids=list(refined.get("dropped_by_judge", [])))
        return refined, info, decision.note
    except Exception as exc:  # noqa: BLE001 - JEV must never break a turn
        logger.warning("JEV retrieval refinement skipped: %s", type(exc).__name__)
        info["status"] = "skipped:error"
        return pack, info, ""


# ── evidence for the answer verifier ─────────────────────────────────────────

def evidence_from_text(*texts: str, limit: int = 10) -> List[dict]:
    """The injected knowledge / memory blocks as a small, scrubbed evidence list for verify_agent_response."""
    out: List[dict] = []
    for text in texts:
        if not text:
            continue
        _h, blocks = split_blocks(text)
        if blocks:
            for ref, blk in sorted(blocks.items()):
                head = blk.split("\n", 1)[0]
                out.append({"id": f"[{ref}]", "title": scrub(head, 160), "excerpt": scrub(_body_of(blk), 450)})
        else:
            out.append({"id": "memory", "title": "recalled company memory", "excerpt": scrub(text, 700)})
    return out[:limit]


# ── telemetry: retrieval_log ─────────────────────────────────────────────────

RETRIEVAL_LOG_SQL = [
    """CREATE TABLE IF NOT EXISTS retrieval_log (
        id UUID PRIMARY KEY, tenant_id UUID, user_id TEXT, agent_type TEXT, conversation_key TEXT,
        query_hash TEXT NOT NULL, query_chars INTEGER NOT NULL DEFAULT 0, analytic BOOLEAN NOT NULL DEFAULT false,
        cards JSONB NOT NULL DEFAULT '[]'::jsonb, n_retrieved INTEGER NOT NULL DEFAULT 0, n_kept INTEGER NOT NULL DEFAULT 0,
        n_cited INTEGER NOT NULL DEFAULT 0, jev_status TEXT, jev_confidence REAL, action TEXT, widened BOOLEAN NOT NULL DEFAULT false,
        grounded_prob REAL, verdict TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS ix_retrieval_log_tenant_time ON retrieval_log (tenant_id, created_at DESC)",
]
_log_ready = False


def build_log_row(*, tenant_id: str, user_id: Optional[str], agent_type: str, conversation_key: Optional[str], query: str,
                  info: Dict[str, Any], answer: str, verification: Optional[dict]) -> Dict[str, Any]:
    """One telemetry row from a finished turn. `info` is the knowledge info recorded by grounding_block."""
    jev = info.get("jev") or {}
    judged = {j["card_id"]: j for j in jev.get("judged") or []}
    cards = []
    cited_n = 0
    for c in info.get("cards") or []:
        cid = c.get("card_id")
        ref = c.get("ref")
        cited = bool(cid and cid in (answer or "")) or bool(ref is not None and re.search(rf"\[{int(ref)}\]", answer or ""))
        cited_n += int(cited)
        j = judged.get(cid, {})
        cards.append({"card_id": cid, "module": c.get("module"), "rank": len(cards), "retrieval_score": c.get("score"),
                      "judge": ({k: j[k] for k in ("answers_question", "is_current", "applies_to_user", "score")} if j else None),
                      "used": True, "cited": cited})
    for cid in jev.get("dropped_card_ids") or []:
        j = judged.get(cid, {})
        cards.append({"card_id": cid, "module": None, "rank": len(cards), "retrieval_score": None,
                      "judge": ({k: j[k] for k in ("answers_question", "is_current", "applies_to_user", "score")} if j else None),
                      "used": False, "cited": False})
    v = verification or {}
    return {"id": str(uuid.uuid4()), "tenant_id": tenant_id, "user_id": user_id, "agent_type": agent_type,
            "conversation_key": conversation_key, "query_hash": hashlib.sha256(_norm_query(query).encode()).hexdigest()[:32],
            "query_chars": len(query or ""), "analytic": is_analytic(query), "cards": cards,
            "n_retrieved": len(cards), "n_kept": sum(1 for c in cards if c["used"]), "n_cited": cited_n,
            "jev_status": jev.get("status"), "jev_confidence": jev.get("confidence"), "action": jev.get("action"),
            "widened": bool(jev.get("widened")), "grounded_prob": v.get("grounded_in_facts"), "verdict": v.get("action")}


async def write_retrieval_log(row: Dict[str, Any]) -> bool:
    """Insert one row; returns False (and logs) on any failure. Telemetry never affects the turn."""
    global _log_ready
    if not telemetry_enabled() or not row.get("tenant_id"):
        return False
    try:
        import json
        from sqlalchemy import text
        from services.common.db import session_scope
        async with session_scope() as s:
            if not _log_ready:
                for stmt in RETRIEVAL_LOG_SQL:
                    await s.execute(text(stmt))
                _log_ready = True
            await s.execute(text(
                """INSERT INTO retrieval_log (id, tenant_id, user_id, agent_type, conversation_key, query_hash, query_chars,
                       analytic, cards, n_retrieved, n_kept, n_cited, jev_status, jev_confidence, action, widened,
                       grounded_prob, verdict)
                   VALUES (CAST(:id AS uuid), CAST(:tenant_id AS uuid), :user_id, :agent_type, :conversation_key, :query_hash,
                       :query_chars, :analytic, CAST(:cards AS jsonb), :n_retrieved, :n_kept, :n_cited, :jev_status,
                       :jev_confidence, :action, :widened, :grounded_prob, :verdict)"""),
                {**row, "cards": json.dumps(row["cards"], default=str)})
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("retrieval_log write skipped: %s", type(exc).__name__)
        return False


def log_turn_background(**kwargs) -> None:
    """Fire-and-forget telemetry for a finished turn (no-op when disabled or no tenant)."""
    if not telemetry_enabled() or not kwargs.get("tenant_id"):
        return
    try:
        from services.common.background_tasks import schedule_background
        schedule_background(write_retrieval_log(build_log_row(**kwargs)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("retrieval telemetry not scheduled: %s", type(exc).__name__)
