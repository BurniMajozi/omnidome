"""Where the engine reads from. Every read is a SIGNED call to tenant_memory with the caller's verified identity, so the
knowledge layer applies its own module / role / private-owner filtering; nothing is read with elevated rights.

`Sources` is the seam tests replace. `gather()` turns sources into an EvidenceSet (stable ids, scrubbed excerpts).
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from services.agent_orchestrator import knowledge_client as KC
from services.agent_orchestrator.insights import config
from services.agent_orchestrator.insights.evidence import Evidence, EvidenceSet, frontmatter, parse_fact, scrub
from services.agent_orchestrator.insights.modules import PanelSpec

logger = logging.getLogger(__name__)

MAX_CARDS = 8
MAX_FACTS = 14
MAX_PERSONAL = 6


@dataclass
class Caller:
    tenant_id: str
    user_id: str
    roles: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)       # from the verified AuthContext, only used if the memory service cannot answer
    is_admin: bool = False

    @property
    def roles_hash(self) -> str:
        import hashlib
        return hashlib.sha256(",".join(sorted(r.lower() for r in self.roles)).encode()).hexdigest()[:12]


class Sources:
    """Interface. All methods must not raise: return None / [] and the engine records the degradation."""

    async def allowed_modules(self, caller: Caller) -> Optional[list[str]]:           # None = could not be determined
        raise NotImplementedError

    async def cards(self, caller: Caller, query: str, modules: list[str]) -> Optional[list[dict]]:
        raise NotImplementedError

    async def fact_rows(self, caller: Caller, metric_key: str) -> Optional[list[dict]]:
        raise NotImplementedError

    async def personal_day(self, caller: Caller) -> Optional[dict]:
        raise NotImplementedError

    async def skills(self, caller: Caller, spec: PanelSpec) -> tuple[list[str], str]:
        return [], ""

    async def memory_signal(self, caller: Caller, entry: dict) -> bool:
        return False


class HttpSources(Sources):
    def __init__(self, timeout: Optional[float] = None):
        self.timeout = timeout or config.source_timeout_s()

    async def _post(self, caller: Caller, path: str, body: dict) -> Optional[dict]:
        try:
            resp = await KC._request("POST", path, caller.tenant_id, caller.user_id, caller.roles, timeout=self.timeout,
                                     json_body=body)
        except Exception as exc:  # noqa: BLE001
            logger.warning("insights source %s unreachable: %s", path, type(exc).__name__)
            return None
        if resp.status_code not in (200, 201):
            logger.info("insights source %s -> %s", path, resp.status_code)
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    async def allowed_modules(self, caller: Caller) -> Optional[list[str]]:
        try:
            resp = await KC._request("GET", "/api/v1/knowledge/access", caller.tenant_id, caller.user_id, caller.roles,
                                     timeout=self.timeout)
            if resp.status_code != 200:
                return None
            return [str(m) for m in (resp.json().get("allowed_modules") or [])]
        except Exception as exc:  # noqa: BLE001
            logger.warning("insights access lookup failed: %s", type(exc).__name__)
            return None

    async def cards(self, caller: Caller, query: str, modules: list[str]) -> Optional[list[dict]]:
        body: dict[str, Any] = {"query": query, "k": MAX_CARDS + 4}
        if modules:
            body["modules"] = modules
        data = await self._post(caller, "/api/v1/knowledge/search", body)
        return None if data is None else list(data.get("results") or [])

    async def fact_rows(self, caller: Caller, metric_key: str) -> Optional[list[dict]]:
        body = {"query": metric_key.replace("_", " ").replace(".", " "), "k": 10, "source_types": ["metric_fact"]}
        data = await self._post(caller, "/api/v1/knowledge/search", body)
        return None if data is None else list(data.get("results") or [])

    async def personal_day(self, caller: Caller) -> Optional[dict]:
        return await self._post(caller, "/api/v1/knowledge/personal/day", {"limit": 12})

    async def memory_signal(self, caller: Caller, entry: dict) -> bool:
        """Private memory entry (importance = how useful the person found an insight). Stays inside the tenant."""
        data = await self._post(caller, "/api/v1/memories", entry)
        return data is not None

    async def skills(self, caller: Caller, spec: PanelSpec) -> tuple[list[str], str]:
        """Matching playbooks from the skills runtime, if it exists in this build. Feature-detected: absent/failing -> none."""
        try:
            from services.agent_orchestrator import skills_runtime
            select = getattr(skills_runtime, "select_for_turn", None)
            if select is None:
                return [], ""
            sel = await select(caller.tenant_id, "analytics", f"{spec.skill_hint} {spec.label}", actor_id=caller.user_id,
                               roles=caller.roles, allowed_tools=None, max_selected=2)
            names = [str(s.get("skill_name") or "") for s in (sel.selected or []) if s.get("skill_name")]
            return names, scrub(getattr(sel, "block", "") or "", 1800) if names else ""
        except Exception as exc:  # noqa: BLE001
            logger.info("insights skills lookup skipped: %s", type(exc).__name__)
            return [], ""


def _card_id(row: dict) -> str:
    return KC.card_id(row.get("source_type"), row.get("source_id"))


def _body(markdown: str) -> str:
    return re.sub(r"\A---\s*\n.*?\n---\s*\n?", "", markdown or "", count=1, flags=re.DOTALL)


async def gather(sources: Sources, caller: Caller, spec: PanelSpec, scope: str = "") -> EvidenceSet:
    ev = EvidenceSet()
    query = f"{spec.query} {scope}".strip()
    mods = list(spec.knowledge_modules)

    cards_t = asyncio.create_task(sources.cards(caller, query, mods))
    keys = list(spec.metric_keys)[:8]
    facts_t = [asyncio.create_task(sources.fact_rows(caller, k)) for k in keys]
    personal_t = asyncio.create_task(sources.personal_day(caller))
    skills_t = asyncio.create_task(sources.skills(caller, spec))

    n_card = n_fact = n_pers = 0

    rows = await cards_t
    if rows is None:
        ev.degraded.append("knowledge layer unavailable")
        rows = []
    for r in rows:
        if r.get("source_type") == "metric_fact":
            continue
        if len([e for e in ev.items if e.kind == "card"]) >= MAX_CARDS:
            break
        n_card += 1
        ev.items.append(Evidence(
            ref=f"E{n_card}", id=_card_id(r), kind="card", title=scrub(r.get("title"), 160), module=str(r.get("module") or ""),
            as_of=r.get("as_of"), deep_link=_safe_link(r.get("deep_link")), stale=bool(r.get("stale")),
            text=scrub(_body(r.get("markdown", "")), 520)))

    seen_fact: set[str] = set()
    facts: list[Evidence] = []
    fact_unavailable = 0
    for t, key in zip(facts_t, keys):
        frows = await t
        if frows is None:
            fact_unavailable += 1
            continue
        parsed = []
        for r in frows:
            p = parse_fact(r.get("markdown", ""), r.get("title", ""))
            if p and p["metric_key"] == key:
                parsed.append((r, p))
        facts.extend(_pick_facts(parsed, seen_fact))
    if keys and fact_unavailable == len(keys):
        ev.degraded.append("metric facts unavailable")
    for e in facts[:MAX_FACTS]:
        n_fact += 1
        e.ref = f"F{n_fact}"
        ev.items.append(e)

    day = await personal_t
    if day:
        if spec.module == "overview":      # whole-person counts only belong in the executive overview
            ev.headline = {k: int(v) for k, v in (day.get("headline") or {}).items() if isinstance(v, (int, float))}
        for it in _personal_items(day, spec):
            if n_pers >= MAX_PERSONAL:
                break
            n_pers += 1
            it.ref = f"P{n_pers}"
            ev.items.append(it)

    try:
        ev.used_skills, ev.skill_guidance = await skills_t
    except Exception:  # noqa: BLE001
        ev.used_skills, ev.skill_guidance = [], ""
    ev.allowed = []
    return ev


def _safe_link(link: Any) -> Optional[str]:
    s = str(link or "")
    return s if s.startswith("/dashboard") and len(s) <= 300 and "//" not in s and "<" not in s else None


def _pick_facts(parsed: list, seen: set[str]) -> list[Evidence]:
    """Per metric (and scope): the latest actual and the nearest forecast after it. Newest by period end."""
    out: list[Evidence] = []
    groups: dict[tuple, dict[str, list]] = {}
    for r, p in parsed:
        groups.setdefault((p["metric_key"], p["scope"]), {}).setdefault(p["fact_kind"], []).append((r, p))
    for (_key, _scope), kinds in groups.items():
        picks = []
        if kinds.get("actual"):
            picks.append(max(kinds["actual"], key=lambda x: x[1]["period_end"]))
        last_end = picks[0][1]["period_end"] if picks else ""
        fc = [x for x in kinds.get("forecast", []) if x[1]["period_end"] > last_end]
        if fc:
            picks.append(min(fc, key=lambda x: x[1]["period_end"]))
        for r, p in picks:
            eid = _card_id(r)
            if eid in seen:
                continue
            seen.add(eid)
            out.append(Evidence(
                ref="", id=eid, kind="fact", title=scrub(r.get("title"), 160), module=str(r.get("module") or "analytics"),
                as_of=r.get("as_of"), deep_link=_safe_link(r.get("deep_link")) or "/dashboard?section=analytics",
                stale=bool(r.get("stale")), text=scrub(_body(r.get("markdown", "")), 300), metric_key=p["metric_key"],
                fact_kind=p["fact_kind"], unit=p["unit"], period=p["period"], value_text=p["value_text"],
                delta_text=p["delta_text"], scope=p["scope"]))
    return out


def _personal_items(day: dict, spec: PanelSpec) -> list[Evidence]:
    """The caller's own items that belong to this panel (the overview takes the most urgent of everything)."""
    out: list[Evidence] = []

    def belongs(link: str) -> bool:
        if spec.module == "overview":
            return True
        return any(link.startswith(p) for p in spec.personal_links)

    for kind, key, title_key in (("escalation", "escalations", "reason"), ("task", "tasks", "title"),
                                 ("approval", "approvals", "title")):
        raw = day.get(key)
        items = raw.get("requests", []) if isinstance(raw, dict) else (raw or [])
        for it in items:
            link = str(it.get("link") or "")
            if not belongs(link) and spec.module != "overview":
                continue
            flags = []
            if it.get("overdue"):
                flags.append("overdue")
            if it.get("sla_breached"):
                flags.append("past SLA")
            if it.get("priority"):
                flags.append(f"priority {it['priority']}")
            if it.get("due"):
                flags.append(f"due {str(it['due'])[:10]}")
            title = scrub(it.get("title") or it.get("reason") or it.get(title_key) or kind, 160)
            out.append(Evidence(ref="", id=f"personal:{kind}:{it.get('id')}", kind="personal", title=f"Your {kind}: {title}",
                                module="personal", deep_link=_safe_link(link), text=", ".join(flags) or kind,
                                stale=False))
    out.sort(key=lambda e: (0 if ("overdue" in e.text or "past SLA" in e.text) else 1))
    return out
