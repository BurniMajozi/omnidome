"""Rules a tenant adds themselves: "when THIS event happens, open a ticket like THAT".

The built-in rules in ticket_rules.py cover the events the platform knows about and can only be tuned.
These add to them: any event on the bus (a custom pattern such as `portal.cart.abandoned` or
`iot.alert.*`) can open a ticket routed to a chosen source, category, priority, queue and person, and can
also ask for a task, an escalation or a schedule item to go with it.

Pure functions only here (matching, conditions, title rendering, spec building), so they are unit-tested
without a database; the API in automation_api.py talks to Postgres.

What a custom rule may NOT do, so a typo cannot melt the platform:
* match the platform's own ticket events (`support.*`, `ticket.*`): a ticket opening a ticket is a loop;
* match an event a built-in rule already handles (tune that rule instead, it has the same controls);
* match everything (`*`), or a group that contains a built-in event (e.g. `iot.*`);
* match noise (health checks, heartbeats, debug-level events).
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from services.common.event_bus import normalise_event_type, pattern_matches
from services.common.redaction import redact_data, redact_text
from services.support import ticket_rules
from services.support.ticket_rules import TicketSpec

OUTCOMES = ("ticket", "task", "escalation", "schedule")
OUTCOME_LABELS = {"ticket": "Ticket only", "task": "Ticket and a task", "escalation": "Ticket and an escalation",
                  "schedule": "Ticket and a scheduled item"}
CONDITION_OPS = ("eq", "neq", "contains", "exists")
MAX_CONDITIONS = 5
MAX_RULES_PER_TENANT = 50
FORBIDDEN_PREFIXES = ("support.", "ticket.")

_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){0,3}$")
_TEMPLATE_FIELD = re.compile(r"\{([A-Za-z_][A-Za-z0-9_.]{0,60})\}")
_TITLE_FALLBACK_FIELDS = ("title", "subject", "summary", "message", "reason", "name")
_BODY_FIELDS = ("description", "message", "summary", "reason", "error", "detail", "body_preview", "note")


class RuleError(ValueError):
    """The rule is not acceptable (message is safe to show the user)."""


@dataclass
class CustomRule:
    id: str
    name: str
    event_pattern: str
    conditions: list = field(default_factory=list)
    source: str = "api"
    category: str = "GENERAL"
    priority: str = "NORMAL"
    queue: str = "support"
    outcome: str = "ticket"
    assigned_to: Optional[str] = None
    title_template: Optional[str] = None
    enabled: bool = True


def validate_pattern(raw: str) -> str:
    """Normalise a pattern (`a.b.c` or `a.b.*`) or raise RuleError."""
    value = (raw or "").strip().lower()
    wildcard = value.endswith(".*")
    prefix = value[:-2] if wildcard else value
    if "." not in prefix and not (wildcard and prefix):
        raise RuleError("The event needs at least two parts, like portal.cart_abandoned, or portal.* for a whole group")
    probe = prefix + ".probe" if wildcard else prefix
    try:
        normalise_event_type(probe)
    except ValueError as exc:
        raise RuleError(str(exc)) from None
    if probe.startswith(FORBIDDEN_PREFIXES):
        raise RuleError("Ticket events cannot create tickets (that would loop)")
    if ticket_rules.is_noise({"type": probe}):
        raise RuleError("Health checks, heartbeats and debug events never create tickets")
    for key in ticket_rules.RULES:
        if pattern_matches(value, key):
            raise RuleError(f"{key} already has a built-in rule: change it in the list above instead")
    return value


def validate_conditions(raw: Any) -> list[dict]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list) or len(raw) > MAX_CONDITIONS:
        raise RuleError(f"Use at most {MAX_CONDITIONS} conditions")
    out = []
    for c in raw:
        if not isinstance(c, dict):
            raise RuleError("Each condition needs a field, an operator and a value")
        fld, op = str(c.get("field") or "").strip(), str(c.get("op") or "eq").strip().lower()
        if not _FIELD_RE.match(fld):
            raise RuleError(f"'{fld}' is not a usable field name")
        if op not in CONDITION_OPS:
            raise RuleError(f"Operator must be one of {', '.join(CONDITION_OPS)}")
        value = c.get("value")
        if op != "exists" and (value is None or str(value).strip() == ""):
            raise RuleError(f"Condition on '{fld}' needs a value")
        out.append({"field": fld, "op": op, "value": None if op == "exists" else str(value).strip()[:200]})
    return out


def _dig(payload: Any, path: str) -> Any:
    cur = payload
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _same(actual: Any, expected: str) -> bool:
    return str(actual).strip().lower() == expected.strip().lower()


def conditions_match(conditions: list, payload: Mapping) -> bool:
    for c in conditions or []:
        actual = _dig(payload, c["field"])
        op = c.get("op", "eq")
        if op == "exists":
            ok = actual not in (None, "")
        elif actual is None:
            ok = op == "neq"
        elif op == "eq":
            ok = _same(actual, c["value"])
        elif op == "neq":
            ok = not _same(actual, c["value"])
        else:  # contains
            ok = c["value"].strip().lower() in str(actual).lower()
        if not ok:
            return False
    return True


def matches(rule: CustomRule, event: Mapping) -> bool:
    etype = str(event.get("type") or "")
    if not rule.enabled or etype in ticket_rules.RULES or etype.startswith(FORBIDDEN_PREFIXES):
        return False
    if ticket_rules.is_noise(event) or not pattern_matches(rule.event_pattern, etype):
        return False
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    return conditions_match(rule.conditions, payload)


def render_title(template: Optional[str], payload: Mapping, event_type: str) -> str:
    """Fill {field} placeholders from the event payload (no formatting, no attribute access)."""
    def fill(m: re.Match) -> str:
        v = _dig(payload, m.group(1))
        return "" if isinstance(v, (dict, list)) or v is None else str(v)
    if template:
        title = " ".join(_TEMPLATE_FIELD.sub(fill, template).split())
        if title:
            return redact_text(title, 200)
    for key in _TITLE_FALLBACK_FIELDS:
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return redact_text(" ".join(v.split()), 200)
    return redact_text(event_type.replace(".", " ").replace("_", " ").capitalize(), 200)


def _short(value: Any, n: int = 12) -> str:
    return hashlib.sha1(str(value or "").encode()).hexdigest()[:n]


def _uuid(value: Any) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value)) if value else None
    except (ValueError, TypeError):
        return None


def build_spec(rule: CustomRule, event: Mapping) -> TicketSpec:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    etype = str(event["type"])
    title = render_title(rule.title_template, payload, etype)
    body = " ".join(str(payload[k]) for k in _BODY_FIELDS
                    if isinstance(payload.get(k), (str, int, float)) and str(payload[k]).strip())
    anchor = event.get("subject_id") or payload.get("id") or payload.get("subject_id") or title
    return TicketSpec(
        source=rule.source, event_type=etype, subject=title,
        description=redact_text(body or f"Raised by the rule '{rule.name}' when {etype} happened.", 1500),
        category=rule.category, priority=rule.priority, queue=rule.queue,
        dedupe_key=f"custom:{rule.id[:8]}:{_short(anchor)}",
        ref_type=str(event.get("subject_type") or "event")[:60],
        ref_id=str(event.get("subject_id") or event.get("id") or "")[:120] or None,
        customer_id=_uuid(payload.get("customer_id")), assigned_to=_uuid(rule.assigned_to),
        event_id=event.get("id"), repeat_comment=f"{etype} happened again.", outcome=rule.outcome,
        context=redact_data({"rule": rule.name, "rule_id": rule.id}))


def resolve_custom(rules: list[CustomRule], event: Mapping) -> Optional[TicketSpec]:
    """The ticket the first matching custom rule produces for `event`, or None."""
    for rule in rules:
        if matches(rule, event):
            spec = build_spec(rule, event)
            spec.subject = ticket_rules._clean(spec.subject, 200)
            return spec
    return None


def rule_to_dict(row: Mapping) -> dict:
    created = row["created_at"] if "created_at" in row.keys() else None
    return {"id": str(row["id"]), "name": row["name"], "event_pattern": row["event_pattern"],
            "conditions": row["conditions"] or [], "source": row["source"], "category": row["category"],
            "priority": row["priority"], "queue": row["queue"], "outcome": row["outcome"],
            "assigned_to": str(row["assigned_to"]) if row["assigned_to"] else None,
            "title_template": row["title_template"], "enabled": bool(row["enabled"]),
            "created_at": created.isoformat() if created else None}
