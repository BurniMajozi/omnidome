"""Evidence: everything the narrative may cite, with stable ids, plus the deterministic parts of metric facts.

A metric fact card is written by governed code (docs/knowledge-layer.md), so the figures in its heading are deterministic.
We parse them out (value text, delta text, period) and expose them to the narrative only as *tokens* ({{F3}},
{{F3.delta}}): the engine substitutes the platform-formatted text, the model never types a number.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

_TAG = re.compile(r"</?\s*(?:knowledge_reference|evidence|system|assistant|user)[^>]*>", re.IGNORECASE)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LONG_DIGITS = re.compile(r"(?<!\d)(?:\+27|0)?\d{9,}(?!\d)")


def scrub(text: Any, limit: int = 600) -> str:
    """Untrusted card/user text -> a short, single-spaced excerpt with markup removed and identifiers masked.
    This is what the narrative model AND any external verifier (JEV) ever see of a card."""
    t = _TAG.sub("[removed]", str(text or ""))
    t = _EMAIL.sub("[email]", t)
    t = _LONG_DIGITS.sub("[number]", t)
    t = " ".join(t.split())
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


@dataclass
class Evidence:
    ref: str                       # short id the model cites: E1 (card), F1 (metric fact), P1 (personal), S1 (skill)
    id: str                        # stable platform id: card:<type>:<id> | personal:<kind>:<id> | skill:<name>
    kind: str                      # card | fact | personal | skill
    title: str
    module: str = ""
    as_of: Optional[str] = None
    deep_link: Optional[str] = None
    stale: bool = False
    text: str = ""                 # scrubbed excerpt
    # fact-only
    metric_key: str = ""
    fact_kind: str = ""            # actual | forecast | target
    unit: str = ""
    period: str = ""
    value_text: str = ""
    delta_text: str = ""
    scope: str = ""

    def public(self) -> dict:
        d = {"id": self.id, "ref": self.ref, "kind": self.kind, "title": self.title, "module": self.module,
             "as_of": self.as_of, "deep_link": self.deep_link, "stale": self.stale}
        if self.kind == "fact":
            d.update(metric_key=self.metric_key, fact_kind=self.fact_kind, period=self.period)
        return d


@dataclass
class EvidenceSet:
    items: list[Evidence] = field(default_factory=list)
    headline: dict = field(default_factory=dict)      # caller's own counts (my.day headline), deterministic
    used_skills: list[str] = field(default_factory=list)
    skill_guidance: str = ""
    degraded: list[str] = field(default_factory=list)
    allowed: list[str] = field(default_factory=list)

    def by_ref(self) -> dict[str, Evidence]:
        return {e.ref: e for e in self.items}

    def by_id(self) -> dict[str, Evidence]:
        return {e.id: e for e in self.items}

    def facts(self) -> list[Evidence]:
        return [e for e in self.items if e.kind == "fact"]

    def empty(self) -> bool:
        return not self.items and not any(self.headline.values())

    def fingerprint(self, roles_hash: str = "") -> str:
        """Changes when a card/fact/personal item appears, disappears or is updated: the cache invalidation key."""
        basis = sorted((e.id, e.as_of or "", e.value_text) for e in self.items)
        raw = json.dumps([basis, sorted(self.headline.items()), roles_hash], default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def as_of(self) -> Optional[str]:
        stamps = [e.as_of for e in self.items if e.as_of and e.kind in ("fact", "card")]
        return max(stamps) if stamps else None

    def mostly_stale(self) -> bool:
        data = [e for e in self.items if e.kind in ("fact", "card")]
        return bool(data) and sum(1 for e in data if e.stale) * 2 >= len(data)


# ── metric fact parsing ──────────────────────────────────────────────────────

_FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_META = re.compile(r"-\s*Metric:\s*(\S+)\s*\|\s*Kind:\s*(\w+)\s*\|\s*Unit:\s*(\w+)")
_VALUE = re.compile(r":\s+(R-?[\d,]+(?:\.\d+)?|-?[\d,]+(?:\.\d+)?%?)(?=\s*(?:\(|,|$))")
_DELTA = re.compile(r",\s*([+-]\d+(?:\.\d+)?%)\s+vs\s+(.+?)\s*$")
_SCOPE = re.compile(r"-\s*Scope:\s*(.+)")


def frontmatter(markdown: str) -> dict:
    m = _FM.match(markdown or "")
    out: dict[str, str] = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                out[k.strip()] = v.strip().strip('"')
    return out


def parse_fact(markdown: str, row_title: str = "") -> Optional[dict]:
    """{metric_key, fact_kind, unit, value_text, delta_text, period, scope} from a metric_fact card, or None if it does not
    look like one (so an unexpected card can never smuggle numbers in as a 'fact')."""
    md = markdown or ""
    meta = _META.search(md)
    if not meta:
        return None
    body = _FM.sub("", md, count=1)
    heading = next((ln[2:].strip() for ln in body.splitlines() if ln.startswith("# ")), "")
    v = _VALUE.search(heading)
    if not v:
        return None
    delta = _DELTA.search(heading)
    fm = frontmatter(md)
    scope = _SCOPE.search(body)
    period = fm.get("period_end") or ""
    label_period = heading[: v.start()]
    return {"metric_key": meta.group(1).lower(), "fact_kind": meta.group(2).lower(), "unit": meta.group(3),
            "value_text": v.group(1), "delta_text": f"{delta.group(1)} vs {delta.group(2)}" if delta else "",
            "period": label_period.split(",")[-1].strip() or period, "period_end": period,
            "scope": scope.group(1).strip() if scope else ""}


# ── numeric literals ─────────────────────────────────────────────────────────

NUM = re.compile(r"(?<![\w.])R?\s?\d[\d,]*(?:\.\d+)?\s?%?|\d{4}-\d{2}-\d{2}")


def norm_number(token: str) -> str:
    """'R1,234.50' / '1 234.5' / '12%' -> a comparable key: digits (and one decimal point), plus % marker."""
    t = token.strip().replace("R", "").replace(" ", "").replace(",", "")
    pct = t.endswith("%")
    t = t.rstrip("%")
    if re.fullmatch(r"\d+\.0+", t):
        t = t.split(".")[0]
    return t + ("%" if pct else "")


def numbers_in(text: str) -> set[str]:
    return {norm_number(m.group(0)) for m in NUM.finditer(text or "")}
