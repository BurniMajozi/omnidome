"""Jev for the ticket desk: routing, close review and stage checks.

The support service owns tickets; the orchestrator owns the Jev (TypeSafe) credentials and the egress
switches, so support asks here (routes/jev_tickets.py). Everything follows the same rules as jev_gate.py:

* nothing is sent unless `jev_gate_enabled` and a key are set, the tenant is not on a free-only model route,
  and `JEV_DATA_EGRESS` allows tenant data to leave the platform;
* what is sent is the ticket's already-redacted subject/description/resolution and counts. Never customer
  names, contact details or staff names. Assignee candidates are opaque ids with workload numbers;
* the answer is untrusted: a choice outside the offered options is dropped, probabilities are clamped;
* when Jev is unavailable the answer is "no opinion" (`evaluated_by_jev` False, empty proposal). The built-in
  rules already route deterministically, so there is nothing to fall back to that would be better than that.

This module only asks and parses. What to do with the answer (apply, suggest or ignore) is support's decision.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from services.agent_orchestrator.config import settings
from services.agent_orchestrator.jev_gate import DEFAULT_TIMEOUT_S, _get_credentials, _unit

logger = logging.getLogger("agent_orchestrator.jev_ticket")

MAX_CANDIDATES = 25
NO_ASSIGNEE = "none"

QUEUE_CRITERIA = {
    "support": "General customer questions and requests that do not need a specialist.",
    "technical": "Fibre, line, router, ONT and HomeDome connection faults that need technical diagnosis.",
    "finance": "Payments, invoices, debit orders, refunds and reconciliation.",
    "calls": "Missed calls and callbacks the customer is waiting on.",
    "agents": "Failures or approvals raised by the AI agents.",
    "platform": "Software errors and failed background jobs in the platform itself.",
}
CATEGORY_CRITERIA = {
    "GENERAL": "Anything that fits no other category.", "TECHNICAL": "A fault with the customer's connection or equipment.",
    "BILLING": "Money: invoices, payments, debit orders.", "HOMEDOME": "A HomeDome smart-home gateway or integration.",
    "AGENT": "An AI agent run failed or needs a person.", "CALLS": "A call that needs a call back.",
    "SYSTEM": "A platform software error.", "RICA": "RICA identity verification.", "SALES": "A sales enquiry or order.",
}
PRIORITY_CRITERIA = {
    "URGENT": "Service is down for many customers, safety or legal exposure, or a VIP is affected.",
    "HIGH": "One customer fully without service, or money is at risk today.",
    "NORMAL": "A problem or request that can wait for the normal response time.",
    "LOW": "Cosmetic, informational or no customer impact.",
}
OUTCOME_CRITERIA = {
    "ticket": "A ticket alone is enough: someone will pick it up from the queue.",
    "task": "There is a concrete to-do for a named person that is separate from the ticket.",
    "escalation": "A supervisor must act now: severe impact, repeated failure or a deadline already missed.",
    "schedule": "It needs a booked time: a site visit, installation or callback at a set time.",
}


def unavailable_reason(tenant_id: Optional[str] = None) -> Optional[str]:
    """Why Jev cannot be asked right now, or None when it can."""
    from services.agent_orchestrator import jev_retrieval
    _, api_key, _ = _get_credentials()
    if not settings.jev_gate_enabled or not api_key:
        return "Jev is not enabled for this deployment"
    if not jev_retrieval.egress_allowed():
        return "Jev is off: JEV_DATA_EGRESS=false keeps tenant data inside the platform"
    return None


async def _ask(state: Dict[str, Any], questions: Dict[str, Any], tenant_id: Optional[str]) -> tuple[Dict[str, Any], dict]:
    """POST one Jev System One evaluation. Raises on transport or HTTP failure."""
    from services.common.llm_routing import free_only
    if await free_only(tenant_id):
        raise RuntimeError("paid verifier excluded by this tenant's model route")
    provider, api_key, endpoint = _get_credentials()
    model_name = "typesafe/jev-1.13" if provider == "openrouter" else getattr(settings, "typesafe_model", "jev-latest")
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_S) as client:
        resp = await client.post(endpoint, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                                                    "User-Agent": "OmniDome-Agent-Orchestrator/1.0"},
                                 json={"state": state, "model": model_name, "questions": questions})
    if resp.status_code != 200:
        raise RuntimeError(f"Jev returned HTTP {resp.status_code}")
    body = resp.json()
    usage = {"provider": provider, "model": body.get("model") or model_name,
             "total_tokens": (body.get("usage") or {}).get("total_tokens"), "cost_usd": (body.get("usage") or {}).get("cost")}
    return body.get("answers", {}) or {}, usage


def parse_choice(answer: Any, options: List[str]) -> tuple[Optional[str], float, Dict[str, float]]:
    """(choice, confidence, distribution) from a Jev choice answer; (None, 0, {}) when it is not one of `options`."""
    if not isinstance(answer, dict):
        return None, 0.0, {}
    choice = answer.get("choice")
    probs = answer.get("probabilities")
    dist = {str(k): _unit(v) for k, v in probs.items() if str(k) in options} if isinstance(probs, dict) else {}
    if not isinstance(choice, str) or choice not in options:
        return None, 0.0, dist
    confidence = _unit(answer.get("confidence", dist.get(choice, 0.0)))
    return choice, confidence, dist


def parse_noul(answer: Any, default: float = 0.0) -> float:
    if isinstance(answer, dict):
        return _unit(answer.get("noul", answer.get("probability", default)))
    return _unit(answer, default)


def _ticket_state(ticket: dict) -> dict:
    return {k: ticket.get(k) for k in ("ref", "subject", "description", "source", "category", "priority", "queue",
                                         "status", "occurrence_count", "resolution", "event_type") if ticket.get(k) is not None}


async def route_ticket(ticket: dict, candidates: Optional[List[dict]] = None, tenant_id: Optional[str] = None) -> dict:
    """Propose queue, category, priority, outcome and (when there are candidates) assignee for a ticket."""
    reason = unavailable_reason(tenant_id)
    if reason:
        return {"evaluated_by_jev": False, "proposal": {}, "confidence": {}, "reason": reason}
    candidates = [c for c in (candidates or []) if c.get("id")][:MAX_CANDIDATES]
    questions: Dict[str, Any] = {
        "queue": {"type": "choice", "instructions": "Which work queue should handle this ticket?",
                  "options": list(QUEUE_CRITERIA), "criteria": QUEUE_CRITERIA},
        "category": {"type": "choice", "instructions": "Which category describes this ticket?",
                     "options": list(CATEGORY_CRITERIA), "criteria": CATEGORY_CRITERIA},
        "priority": {"type": "choice", "instructions": "How urgent is this ticket?",
                     "options": list(PRIORITY_CRITERIA), "criteria": PRIORITY_CRITERIA},
        "outcome": {"type": "choice", "instructions": "Does this need more than a ticket?",
                    "options": list(OUTCOME_CRITERIA), "criteria": OUTCOME_CRITERIA},
    }
    options = {"queue": list(QUEUE_CRITERIA), "category": list(CATEGORY_CRITERIA), "priority": list(PRIORITY_CRITERIA),
               "outcome": list(OUTCOME_CRITERIA)}
    if candidates:
        ids = [str(c["id"]) for c in candidates]
        options["assignee"] = ids + [NO_ASSIGNEE]
        questions["assignee"] = {
            "type": "choice",
            "instructions": "Which person is best placed to take this ticket? Pick `none` if nobody clearly is.",
            "options": options["assignee"],
            "criteria": {**{str(c["id"]): (f"Open tickets: {int(c.get('open') or 0)}. Resolved in 30 days: {int(c.get('resolved_30d') or 0)}. "
                                           f"Usually handles: {', '.join(c.get('top_categories') or []) or 'no history yet'}.")
                            for c in candidates},
                         NO_ASSIGNEE: "No candidate is clearly the right person."},
        }
    try:
        answers, usage = await _ask({"ticket": _ticket_state(ticket)}, questions, tenant_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Jev ticket routing failed: %s", exc)
        return {"evaluated_by_jev": False, "proposal": {}, "confidence": {}, "reason": f"Jev unavailable ({type(exc).__name__})"}
    proposal: Dict[str, str] = {}
    confidence: Dict[str, float] = {}
    distribution: Dict[str, Dict[str, float]] = {}
    for key, opts in options.items():
        choice, conf, dist = parse_choice(answers.get(key), opts)
        distribution[key] = dist
        if choice is None or (key == "assignee" and choice == NO_ASSIGNEE):
            continue
        proposal[key], confidence[key] = choice, conf
    return {"evaluated_by_jev": True, "proposal": proposal, "confidence": confidence, "distribution": distribution,
            "reason": "Jev classified the ticket", "usage": usage}


async def review_closed_ticket(ticket: dict, tenant_id: Optional[str] = None) -> dict:
    """Was the ticket properly resolved? `ticket` carries subject, description and resolution."""
    reason = unavailable_reason(tenant_id)
    if reason:
        return {"evaluated_by_jev": False, "reason": reason}
    questions = {
        "resolved_properly": {"type": "noul", "instructions":
            "The `resolution` describes an action that actually addresses the problem described in `subject` and `description`."},
        "resolution_specific": {"type": "noul", "instructions":
            "The `resolution` says what was done or found, in enough detail for someone else to understand it later, "
            "rather than only saying 'fixed' or 'done'."},
    }
    try:
        answers, usage = await _ask({"ticket": _ticket_state(ticket)}, questions, tenant_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Jev close review failed: %s", exc)
        return {"evaluated_by_jev": False, "reason": f"Jev unavailable ({type(exc).__name__})"}
    return {"evaluated_by_jev": True, "usage": usage,
            "resolved_properly": parse_noul(answers.get("resolved_properly")),
            "resolution_specific": parse_noul(answers.get("resolution_specific"))}


async def check_stage(ticket: dict, timing: dict, tenant_id: Optional[str] = None) -> dict:
    """Should this open ticket be escalated now, given how long it has sat in its stage?"""
    reason = unavailable_reason(tenant_id)
    if reason:
        return {"evaluated_by_jev": False, "reason": reason}
    questions = {
        "should_escalate": {"type": "noul", "instructions":
            "Given `timing` (hours open, hours since anyone touched it, hours past its deadline, times reassigned) and the "
            "ticket's priority, this ticket needs a supervisor to step in now rather than waiting longer."},
    }
    try:
        answers, usage = await _ask({"ticket": _ticket_state(ticket), "timing": timing}, questions, tenant_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Jev stage check failed: %s", exc)
        return {"evaluated_by_jev": False, "reason": f"Jev unavailable ({type(exc).__name__})"}
    return {"evaluated_by_jev": True, "usage": usage, "should_escalate": parse_noul(answers.get("should_escalate"))}
