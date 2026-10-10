"""Deterministic briefing: no LLM, no external calls. Used when the model / verifier / budget is unavailable, or when the
model's output failed verification. Figures are the platform-formatted values from metric facts and the caller's own
counts; recommendations come from simple rules over the same evidence, each citing it.
"""
from __future__ import annotations

from typing import Optional

from services.agent_orchestrator.insights.evidence import Evidence, EvidenceSet
from services.agent_orchestrator.insights.modules import PanelSpec
from services.agent_orchestrator.insights.narrative import rec_id


def _pct(delta_text: str) -> Optional[float]:
    try:
        return float(delta_text.split("%")[0])
    except (ValueError, IndexError):
        return None


def kpis(ev: EvidenceSet, limit: int = 6) -> list[dict]:
    """Headline numbers straight from metric facts (actuals first, then the nearest forecast). Never model-written."""
    facts = ev.facts()
    ordered = [f for f in facts if f.fact_kind == "actual"] + [f for f in facts if f.fact_kind == "forecast"]
    out = []
    for f in ordered[:limit]:
        out.append({"id": f.id, "label": f.title, "value": f.value_text, "delta": f.delta_text or None,
                    "period": f.period, "kind": f.fact_kind, "unit": f.unit, "scope": f.scope or None,
                    "as_of": f.as_of, "stale": f.stale, "deep_link": f.deep_link})
    return out


def template(spec: PanelSpec, ev: EvidenceSet) -> dict:
    actuals = [f for f in ev.facts() if f.fact_kind == "actual"]
    forecasts = [f for f in ev.facts() if f.fact_kind == "forecast"]
    cards = [e for e in ev.items if e.kind == "card"]
    mine = [e for e in ev.items if e.kind == "personal"]
    urgent = [e for e in mine if "overdue" in e.text or "past SLA" in e.text]

    sentences: list[str] = []
    for f in actuals[:3]:
        s = f"{f.title.rsplit(' ' + f.period, 1)[0] if f.period else f.title} for {f.period or 'the latest period'}: {f.value_text}"
        sentences.append(s + (f" ({f.delta_text})." if f.delta_text else "."))
    if forecasts:
        f = forecasts[0]
        sentences.append(f"Projection ({f.fact_kind}): {f.title} is {f.value_text}.")
    if cards:
        sentences.append(f"{len(cards)} knowledge item(s) from the {spec.label} area were considered.")
    if mine:
        sentences.append(f"You have {len(mine)} open item(s) here" + (f", {len(urgent)} of them overdue or past SLA." if urgent else "."))
    if not sentences:
        sentences.append(f"There is not enough data yet for a {spec.label} briefing.")

    recs: list[dict] = []

    def add(title: str, why: str, priority: str, impact: str, effort: str, owner: str, cited: list[Evidence], link: Optional[str]) -> None:
        recs.append({"id": rec_id(spec.module, title), "title": title, "why": why, "priority": priority, "impact": impact,
                     "effort": effort, "owner_hint": owner,
                     "suggested_action": {"kind": "open", "label": "Open in panel", "link": link or spec.deep_link, "executes": False},
                     "confidence": 0.6, "evidence": [e.public() for e in cited]})

    for e in urgent[:2]:
        add(f"Clear: {e.title.replace('Your ', '', 1)}", f"It is {e.text}.", "high", "medium", "low", "You", [e], e.deep_link)
    drops = [f for f in actuals if f.delta_text and (_pct(f.delta_text) or 0) <= -10]
    for f in sorted(drops, key=lambda x: _pct(x.delta_text) or 0)[:2]:
        add(f"Look into the fall in {f.title.rsplit(' ' + f.period, 1)[0] if f.period else f.title}",
            f"{f.title}: {f.value_text} ({f.delta_text}).", "high", "high", "medium", f"{spec.label} lead", [f], f.deep_link)
    rises = [f for f in actuals if f.delta_text and (_pct(f.delta_text) or 0) >= 10]
    for f in sorted(rises, key=lambda x: -(_pct(x.delta_text) or 0))[:1]:
        add(f"Find out what drove the rise in {f.title.rsplit(' ' + f.period, 1)[0] if f.period else f.title}",
            f"{f.title}: {f.value_text} ({f.delta_text}).", "medium", "medium", "low", f"{spec.label} lead", [f], f.deep_link)
    stale = [e for e in ev.items if e.kind in ("fact", "card") and e.stale]
    if stale and len(stale) * 2 >= max(1, len([e for e in ev.items if e.kind in ("fact", "card")])):
        add("Refresh the data behind this panel", f"{len(stale)} of the items used here are older than their freshness window.",
            "low", "medium", "low", "Panel owner", stale[:2], stale[0].deep_link)
    return {"summary": " ".join(sentences[:6]), "summary_evidence": [e.public() for e in (actuals[:3] + cards[:2])],
            "recommendations": recs[:5], "risks": []}
