"""API for the rules a tenant adds themselves (custom_rules.py): list, create, change, delete, and the
catalogue of events a rule can listen for.

Reading is open to any tenant member; changing rules needs the manager tier (same as the built-in rule
overrides). Saving a rule subscribes the support consumer to its event pattern straight away.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from services.common.auth import AuthContext, get_auth_context
from services.support import custom_rules, ticket_rules
from services.support.access import has_tier, require_tier
from services.support.database import get_session

logger = logging.getLogger("support.automation")
router = APIRouter()

# Events the platform raises that are worth a rule (each is published by a service today), shown even before
# they have fired for this tenant. Anything else the tenant's bus has carried appears from domain_events.
KNOWN_EVENTS = {
    "portal.cart.abandoned": "A portal visitor abandoned their cart",
    "sales.lead.created": "A new lead arrived",
    "sales.lead.stage_changed": "A lead moved to another stage",
    "sales.lead.assigned": "A lead was assigned to someone",
    "sales.deal.stage_changed": "A deal moved to another stage",
    "agents.approval.decided": "An agent action was approved or rejected",
}


class RuleBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    event_pattern: str = Field(min_length=3, max_length=120)
    conditions: list = Field(default_factory=list)
    source: str = "api"
    category: str = "GENERAL"
    priority: str = "NORMAL"
    queue: str = "support"
    outcome: str = "ticket"
    assigned_to: Optional[uuid.UUID] = None
    title_template: Optional[str] = Field(default=None, max_length=200)
    enabled: bool = True


class RulePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    event_pattern: Optional[str] = Field(default=None, min_length=3, max_length=120)
    conditions: Optional[list] = None
    source: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    queue: Optional[str] = None
    outcome: Optional[str] = None
    assigned_to: Optional[uuid.UUID] = None
    clear_assignee: bool = False
    title_template: Optional[str] = Field(default=None, max_length=200)
    enabled: Optional[bool] = None


def _checked(values: dict) -> dict:
    """Validate and normalise the routing fields of a rule; raises 422 with a message the user can act on."""
    out = dict(values)
    try:
        if "event_pattern" in out:
            out["event_pattern"] = custom_rules.validate_pattern(out["event_pattern"])
        if "conditions" in out:
            out["conditions"] = custom_rules.validate_conditions(out["conditions"])
    except custom_rules.RuleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    for key, allowed in (("category", ticket_rules.CATEGORIES), ("priority", ticket_rules.PRIORITIES)):
        if key in out:
            out[key] = str(out[key]).strip().upper()
            if out[key] not in allowed:
                raise HTTPException(status_code=422, detail=f"{key} must be one of {list(allowed)}")
    if "queue" in out:
        out["queue"] = str(out["queue"]).strip().lower()
        if out["queue"] not in ticket_rules.QUEUES:
            raise HTTPException(status_code=422, detail=f"queue must be one of {list(ticket_rules.QUEUES)}")
    if "source" in out:
        out["source"] = str(out["source"]).strip().lower()
        if out["source"] not in ticket_rules.SOURCES:
            raise HTTPException(status_code=422, detail=f"source must be one of {list(ticket_rules.SOURCES)}")
    if "outcome" in out:
        out["outcome"] = str(out["outcome"]).strip().lower()
        if out["outcome"] not in custom_rules.OUTCOMES:
            raise HTTPException(status_code=422, detail=f"outcome must be one of {list(custom_rules.OUTCOMES)}")
    return out


async def _verify_assignee(db, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
    ok = (await db.execute(text("SELECT 1 FROM users WHERE id = :u AND tenant_id = :t AND COALESCE(is_active, true)"),
                           {"u": str(user_id), "t": str(tenant_id)})).first()
    if ok is None:
        raise HTTPException(status_code=422, detail="Assignee is not an active member of this tenant")


async def load_rules(db, tenant_id) -> list[custom_rules.CustomRule]:
    rows = (await db.execute(text("""
        SELECT id, name, event_pattern, conditions, source, category, priority, queue, outcome, assigned_to,
               title_template, enabled FROM ticket_automation_rules
         WHERE tenant_id = :t AND enabled ORDER BY created_at, id"""), {"t": str(tenant_id)})).mappings().all()
    return [custom_rules.CustomRule(
        id=str(r["id"]), name=r["name"], event_pattern=r["event_pattern"], conditions=r["conditions"] or [],
        source=r["source"], category=r["category"], priority=r["priority"], queue=r["queue"], outcome=r["outcome"],
        assigned_to=str(r["assigned_to"]) if r["assigned_to"] else None, title_template=r["title_template"],
        enabled=bool(r["enabled"])) for r in rows]


async def active_patterns(db) -> set[str]:
    rows = (await db.execute(text("SELECT DISTINCT event_pattern FROM ticket_automation_rules WHERE enabled"))).all()
    return {r[0] for r in rows}


async def _subscribe(db, pattern: str) -> None:
    """Tell the bus the support consumer wants this pattern (idempotent)."""
    from services.support.consumer import CONSUMER_NAME
    await db.execute(text("INSERT INTO event_subscriptions (consumer, event_pattern) VALUES (:c, :p) ON CONFLICT DO NOTHING"),
                     {"c": CONSUMER_NAME, "p": pattern})


@router.get("/ticket-automation")
async def list_custom_rules(auth: AuthContext = Depends(get_auth_context), db=Depends(get_session)):
    rows = (await db.execute(text("""
        SELECT id, name, event_pattern, conditions, source, category, priority, queue, outcome, assigned_to,
               title_template, enabled, created_at FROM ticket_automation_rules
         WHERE tenant_id = :t ORDER BY created_at, id"""), {"t": str(auth.tenant_id)})).mappings().all()
    return {"rules": [custom_rules.rule_to_dict(r) for r in rows], "outcomes": list(custom_rules.OUTCOMES),
            "can_edit": await has_tier(auth, db, "manager"), "can_delete": await has_tier(auth, db, "admin"),
            "outcome_labels": custom_rules.OUTCOME_LABELS, "condition_ops": list(custom_rules.CONDITION_OPS),
            "limits": {"rules": custom_rules.MAX_RULES_PER_TENANT, "conditions": custom_rules.MAX_CONDITIONS}}


@router.get("/ticket-automation/events")
async def event_catalogue(auth: AuthContext = Depends(get_auth_context), db=Depends(get_session)):
    """Events a rule can listen for: ones this tenant has actually seen in the last 30 days, plus well-known ones.
    Built-in events are flagged: they already have a rule and cannot be given a second one."""
    rows = (await db.execute(text("""
        SELECT event_type, count(*) AS seen, max(created_at) AS last_seen FROM domain_events
         WHERE tenant_id = :t AND created_at > now() - interval '30 days' GROUP BY event_type
         ORDER BY count(*) DESC LIMIT 300"""), {"t": str(auth.tenant_id)})).mappings().all()
    items: dict[str, dict] = {}
    for key, label in KNOWN_EVENTS.items():
        items[key] = {"event": key, "label": label, "seen_30d": 0, "last_seen": None}
    for key, rule in ticket_rules.RULES.items():
        items.setdefault(key, {"event": key, "label": rule.label, "seen_30d": 0, "last_seen": None})
    for r in rows:
        et = r["event_type"]
        if et.startswith(custom_rules.FORBIDDEN_PREFIXES) or ticket_rules.is_noise({"type": et}):
            continue
        items[et] = {**items.get(et, {"event": et, "label": None}), "event": et, "seen_30d": int(r["seen"]),
                     "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None}
    for key, rule in ticket_rules.RULES.items():
        if key in items:
            items[key]["label"] = rule.label
    out = []
    for et, item in sorted(items.items(), key=lambda kv: (-kv[1]["seen_30d"], kv[0])):
        item["built_in"] = et in ticket_rules.RULES
        item["label"] = item.get("label") or et.replace(".", " › ").replace("_", " ")
        out.append(item)
    return {"events": out}


@router.post("/ticket-automation", status_code=status.HTTP_201_CREATED)
async def create_custom_rule(body: RuleBody, auth: AuthContext = Depends(require_tier("manager")), db=Depends(get_session)):
    values = _checked({k: v for k, v in body.model_dump().items() if k != "assigned_to"})
    count = (await db.execute(text("SELECT count(*) FROM ticket_automation_rules WHERE tenant_id = :t"),
                              {"t": str(auth.tenant_id)})).scalar() or 0
    if count >= custom_rules.MAX_RULES_PER_TENANT:
        raise HTTPException(status_code=409, detail=f"At most {custom_rules.MAX_RULES_PER_TENANT} rules per workspace")
    if body.assigned_to:
        await _verify_assignee(db, auth.tenant_id, body.assigned_to)
    rule_id = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO ticket_automation_rules (id, tenant_id, name, event_pattern, conditions, source, category, priority,
                                             queue, outcome, assigned_to, title_template, enabled, created_by)
        VALUES (:id, :t, :name, :event_pattern, CAST(:conditions AS jsonb), :source, :category, :priority, :queue,
                :outcome, :assigned_to, :title_template, :enabled, :by)"""),
        {"id": rule_id, "t": str(auth.tenant_id), **{**values, "conditions": json.dumps(values["conditions"])},
         "assigned_to": body.assigned_to, "by": auth.user_id})
    await _subscribe(db, values["event_pattern"])
    return await _one(db, auth.tenant_id, rule_id)


async def _one(db, tenant_id: uuid.UUID, rule_id: uuid.UUID) -> dict:
    row = (await db.execute(text("""
        SELECT id, name, event_pattern, conditions, source, category, priority, queue, outcome, assigned_to,
               title_template, enabled, created_at FROM ticket_automation_rules WHERE id = :id AND tenant_id = :t"""),
        {"id": rule_id, "t": str(tenant_id)})).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return custom_rules.rule_to_dict(row)


@router.put("/ticket-automation/{rule_id}")
async def update_custom_rule(rule_id: uuid.UUID, body: RulePatch, auth: AuthContext = Depends(require_tier("manager")),
                             db=Depends(get_session)):
    current = await _one(db, auth.tenant_id, rule_id)
    raw = body.model_dump(exclude_none=True, exclude={"clear_assignee", "assigned_to"})
    values = _checked(raw)
    sets, params = [], {"id": rule_id, "t": str(auth.tenant_id)}
    for key, value in values.items():
        sets.append(f"{key} = CAST(:{key} AS jsonb)" if key == "conditions" else f"{key} = :{key}")
        params[key] = json.dumps(value) if key == "conditions" else value
    if body.assigned_to:
        await _verify_assignee(db, auth.tenant_id, body.assigned_to)
        sets.append("assigned_to = :assigned_to")
        params["assigned_to"] = body.assigned_to
    elif body.clear_assignee:
        sets.append("assigned_to = NULL")
    if not sets:
        return current
    await db.execute(text(f"UPDATE ticket_automation_rules SET {', '.join(sets)}, updated_at = now() "
                          "WHERE id = :id AND tenant_id = :t"), params)
    if "event_pattern" in values:
        await _subscribe(db, values["event_pattern"])
    return await _one(db, auth.tenant_id, rule_id)


@router.delete("/ticket-automation/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_rule(rule_id: uuid.UUID, auth: AuthContext = Depends(require_tier("admin")), db=Depends(get_session)):
    """Delete a rule (admin tier, like every delete in the support service). Managers can switch a rule off instead."""
    gone = (await db.execute(text("DELETE FROM ticket_automation_rules WHERE id = :id AND tenant_id = :t RETURNING id"),
                             {"id": rule_id, "t": str(auth.tenant_id)})).first()
    if gone is None:
        raise HTTPException(status_code=404, detail="Rule not found")
