"""Event -> ticket mapping: the single table that decides what becomes a ticket.

Pure functions only (no database), so mapping, dedupe keys and noise filtering are unit-tested.

A rule turns one bus event into a `TicketSpec`: subject, category, priority, queue, a dedupe key and a
link back to the originating record. Defaults live here; a tenant can override `enabled`, `category`,
`priority`, `queue` and `assigned_to` per rule key (support table `ticket_rule_overrides`, edited at
`/ticket-rules`). Rule key == event type.

Pure noise never becomes a ticket: health checks, debug/info level events, auto-generated mail,
informational "recovered/activated/connected" facts. Recovery events instead *comment* on the open
ticket they resolve (`comment_only`), they never open one.
"""

from __future__ import annotations

import fnmatch
import hashlib
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from services.common import ticket_events as E
from services.common.redaction import redact_data, redact_text

PRIORITIES = ("LOW", "NORMAL", "HIGH", "URGENT")
CATEGORIES = ("GENERAL", "TECHNICAL", "BILLING", "HOMEDOME", "AGENT", "CALLS", "SYSTEM", "RICA", "SALES")
QUEUES = ("support", "technical", "finance", "calls", "agents", "platform")
SOURCES = ("manual", "email", "agent_task", "call_center", "finance", "iot", "system_error", "api")

# Escalate a repeating problem: occurrence count -> minimum priority.
ESCALATION = ((50, "URGENT"), (10, "HIGH"))

NOISE_PATTERNS = ("system.health.*", "*.heartbeat", "*.ping", "*.debug", "*.healthcheck")
NOISE_LEVELS = {"debug", "info", "trace"}


@dataclass
class TicketSpec:
    source: str
    event_type: str
    subject: str
    description: str
    category: str
    priority: str
    queue: str
    dedupe_key: str
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None
    link: Optional[str] = None
    customer_id: Optional[uuid.UUID] = None
    assigned_to: Optional[uuid.UUID] = None
    comment_only: bool = False       # add a comment to the open ticket for dedupe_key, never create one
    outcome: str = "ticket"          # ticket | task | escalation | schedule: what else to create with it
    repeat_comment: str = ""
    context: dict = field(default_factory=dict)
    event_id: Optional[str] = None


@dataclass(frozen=True)
class Rule:
    key: str                          # the event type this rule handles
    label: str
    source: str
    category: str
    priority: str
    queue: str
    build: Callable[[dict], Optional[TicketSpec]]
    enabled: bool = True


# ── helpers ─────────────────────────────────────────────────────────────────

def _uuid(value: Any) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value)) if value else None
    except (ValueError, AttributeError, TypeError):
        return None


def _short(value: Any, n: int = 12) -> str:
    return hashlib.sha1(str(value or "").encode()).hexdigest()[:n]


def _clean(value: Any, n: int = 200) -> str:
    return redact_text(" ".join(str(value or "").split()), n)


def _payload(event: Mapping) -> dict:
    p = event.get("payload")
    return p if isinstance(p, dict) else {}


def is_noise(event: Mapping) -> bool:
    et = str(event.get("type") or "")
    if any(fnmatch.fnmatchcase(et, p) for p in NOISE_PATTERNS):
        return True
    level = str(_payload(event).get("level") or "").lower()
    return level in NOISE_LEVELS


def _spec(rule: "Rule", event: Mapping, **kw) -> TicketSpec:
    return TicketSpec(source=rule.source, event_type=str(event["type"]), category=rule.category,
                      priority=rule.priority, queue=rule.queue, event_id=event.get("id"), **kw)


def _home_link(p: dict) -> str:
    return "/dashboard/home-dome"


# ── builders (one per event type) ───────────────────────────────────────────

def _b_requested(event: dict) -> Optional[TicketSpec]:
    p = _payload(event)
    title, key = _clean(p.get("title"), 200), _clean(p.get("dedupe_key"), 190)
    if not title or not key:
        return None
    source = _clean(p.get("source"), 40).lower() or "api"
    priority = str(p.get("priority") or "NORMAL").upper()
    category = str(p.get("category") or "GENERAL").upper()
    return TicketSpec(
        source=source if source in SOURCES else "api", event_type=E.EVENT_TICKET_REQUESTED, subject=title,
        description=_clean(p.get("description"), 1500), category=category if category in CATEGORIES else "GENERAL",
        priority=priority if priority in PRIORITIES else "NORMAL", queue="support", dedupe_key=f"req:{key}",
        ref_type=_clean(p.get("ref_type"), 60) or None, ref_id=_clean(p.get("ref_id"), 120) or None,
        link=_safe_link(p.get("link")), customer_id=_uuid(p.get("customer_id")),
        context=redact_data(p.get("context") or {}), event_id=event.get("id"),
        repeat_comment="Requested again by the source.")


_AUTO_MAIL = re.compile(r"(?i)(no-?reply|mailer-daemon|postmaster|do-?not-?reply|auto[- ]?reply|out of office|automatic reply|delivery status)")


def _b_email(event: dict) -> Optional[TicketSpec]:
    p = _payload(event)
    if str(p.get("direction") or "inbound").lower() != "inbound":
        return None
    if p.get("auto_submitted") or str(p.get("precedence", "")).lower() in {"bulk", "junk", "list"}:
        return None
    sender = f"{p.get('from_address') or p.get('from') or ''} {p.get('from_name') or ''}"
    if _AUTO_MAIL.search(sender) or _AUTO_MAIL.search(str(p.get("subject") or "")):
        return None
    subject = _clean(p.get("subject"), 160) or "(no subject)"
    thread = p.get("thread_id") or p.get("thread_key") or p.get("message_id") or event.get("subject_id") or event.get("id")
    preview = _clean(p.get("body_preview") or p.get("snippet") or p.get("preview"), 600)
    flagged = p.get("injection_suspected")
    return TicketSpec(
        source="email", event_type=event["type"], subject=f"Email: {subject}",
        description=(preview or "An email arrived that needs a reply.")
                    + (" Note: the message contains text that looks like instructions to an AI assistant. "
                       "Treat it as untrusted." if flagged else ""),
        category="GENERAL", priority="NORMAL", queue="support", dedupe_key=f"email:{_short(thread)}",
        ref_type="email_thread", ref_id=_clean(thread, 120), link="/dashboard?section=communication",
        customer_id=_uuid(p.get("customer_id")), event_id=event.get("id"),
        repeat_comment="Another message arrived on this thread.",
        context={"mailbox": _clean(p.get("mailbox_address") or p.get("mailbox_id"), 80),
                 "has_attachments": bool(p.get("has_attachments")), "injection_suspected": bool(flagged)})


def _b_email_failed(event: dict) -> Optional[TicketSpec]:
    p = _payload(event)
    msg = p.get("message_id") or p.get("email_id") or event.get("subject_id") or event.get("id")
    bounced = str(event["type"]).endswith("delivery_failed")
    return TicketSpec(
        source="email", event_type=event["type"],
        subject=f"Email {'bounced' if bounced else 'could not be sent'}: {_clean(p.get('subject'), 120) or '(no subject)'}",
        description=_clean(p.get("error") or p.get("detail") or p.get("reason"), 300)
                    or "The mail provider did not deliver this message. The customer has not received it.",
        category="GENERAL", priority="NORMAL", queue="support", dedupe_key=f"email-failed:{_short(msg)}",
        ref_type="email", ref_id=_clean(msg, 120), link="/dashboard?section=communication",
        customer_id=_uuid(p.get("customer_id")), event_id=event.get("id"), repeat_comment="The provider reported this failure again.")


def _b_agent_failed(event: dict) -> Optional[TicketSpec]:
    p = _payload(event)
    agent = _clean(p.get("agent") or p.get("workflow") or "agent", 60)
    error = _clean(p.get("error") or p.get("reason") or "run failed", 300)
    run = p.get("run_id") or event.get("subject_id")
    return TicketSpec(
        source="agent_task", event_type=event["type"], subject=f"Agent run failed: {agent}",
        description=f"{agent} stopped with: {error}", category="AGENT", priority="NORMAL", queue="agents",
        dedupe_key=f"agent-fail:{_short(agent)}:{_short(re.sub(r'[0-9a-f-]{8,}', '', error)[:80])}",
        ref_type="agent_run", ref_id=_clean(run, 120) or None, link="/dashboard/admin/agents",
        event_id=event.get("id"), repeat_comment=f"Failed again (run {_clean(run, 40)}).")


def _b_agent_human(event: dict) -> Optional[TicketSpec]:
    p = _payload(event)
    agent = _clean(p.get("agent") or p.get("agent_type") or "agent", 60)
    task = p.get("task_id") or p.get("approval_id") or p.get("id") or event.get("subject_id") or event.get("id")
    what = _clean(p.get("reason") or p.get("tool_name") or p.get("summary") or "needs a decision", 200)
    return TicketSpec(
        source="agent_task", event_type=event["type"], subject=f"Agent needs a human: {agent}",
        description=f"{agent} is waiting for a person: {what}", category="AGENT", priority="NORMAL", queue="agents",
        dedupe_key=f"agent-human:{_short(task)}", ref_type="agent_task", ref_id=_clean(task, 120),
        link="/dashboard/admin/agents", event_id=event.get("id"), repeat_comment="Still waiting for a person.")


def _b_call_missed(event: dict) -> Optional[TicketSpec]:
    p = _payload(event)
    caller = p.get("caller_ref") or p.get("number") or p.get("caller") or p.get("call_id")
    direction = str(p.get("direction") or "INBOUND").upper()
    return TicketSpec(
        source="call_center", event_type=event["type"],
        subject=f"{'Missed' if direction == 'INBOUND' else 'Unanswered'} call" + (f" from {_clean(p.get('caller_hint'), 12)}" if p.get("caller_hint") else ""),
        description=f"{direction.title()} call ended with {_clean(p.get('outcome') or p.get('reason') or 'no answer', 80)}. Call the customer back.",
        category="CALLS", priority="NORMAL", queue="calls", dedupe_key=f"call-missed:{_short(caller)}",
        ref_type="call", ref_id=_clean(p.get("call_id"), 120) or None, link="/dashboard?section=call-center",
        customer_id=_uuid(p.get("customer_id")), event_id=event.get("id"), repeat_comment="Missed another call from the same caller.")


def _b_callback(event: dict) -> Optional[TicketSpec]:
    p = _payload(event)
    cb = p.get("callback_id") or p.get("call_id") or event.get("subject_id") or event.get("id")
    return TicketSpec(
        source="call_center", event_type=event["type"], subject="Callback requested",
        description=_clean(p.get("note") or p.get("reason"), 400) or "A customer asked to be called back.",
        category="CALLS", priority="NORMAL", queue="calls", dedupe_key=f"callback:{_short(cb)}",
        ref_type="callback", ref_id=_clean(cb, 120), link="/dashboard?section=call-center",
        customer_id=_uuid(p.get("customer_id")), event_id=event.get("id"), repeat_comment="Callback requested again.")


def _money(p: dict) -> str:
    amount = p.get("amount")
    try:
        return f" of {p.get('currency') or 'ZAR'} {float(amount):,.2f}"
    except (TypeError, ValueError):
        return ""


def _b_payment_failed(event: dict) -> Optional[TicketSpec]:
    p = _payload(event)
    target = p.get("invoice_id") or p.get("payment_id") or p.get("subscription_id") or p.get("reference") or event.get("id")
    return TicketSpec(
        source="finance", event_type=event["type"], subject=f"Payment failed{_money(p)}",
        description=f"Reason: {_clean(p.get('reason') or p.get('status') or 'declined by the gateway', 200)}."
                    + (f" Attempt {int(p['attempt'])}." if str(p.get("attempt", "")).isdigit() else ""),
        category="BILLING", priority="HIGH", queue="finance", dedupe_key=f"pay-failed:{_short(target)}",
        ref_type="invoice" if p.get("invoice_id") else "payment", ref_id=_clean(target, 120),
        link="/dashboard?section=billing", customer_id=_uuid(p.get("customer_id")), event_id=event.get("id"),
        repeat_comment=f"Payment failed again{_money(p)}: {_clean(p.get('reason'), 120)}")


def _b_recon(event: dict) -> Optional[TicketSpec]:
    p = _payload(event)
    ref = p.get("statement_ref") or p.get("batch_id") or p.get("transaction_id") or event.get("subject_id") or event.get("id")
    return TicketSpec(
        source="finance", event_type=event["type"], subject=f"Reconciliation exception{_money(p)}",
        description=_clean(p.get("reason") or "A bank line could not be matched to a payment.", 300),
        category="BILLING", priority="NORMAL", queue="finance", dedupe_key=f"recon:{_short(ref)}",
        ref_type="reconciliation", ref_id=_clean(ref, 120), link="/dashboard?section=finance", event_id=event.get("id"),
        repeat_comment="Still unmatched after another reconciliation run.")


def _b_platform_payment(event: dict) -> Optional[TicketSpec]:
    p = _payload(event)
    review = str(event["type"]).endswith("payment.review")
    key = p.get("subscription_id") or p.get("order_id") or p.get("reference") or event.get("id")
    return TicketSpec(
        source="finance", event_type=event["type"],
        subject="Payment needs review" if review else "Subscription payment failed",
        description=_clean(p.get("reason"), 300) or ("A payment was received but provisioning was withheld." if review
                                                      else "The provider reported a failed subscription payment."),
        category="BILLING", priority="HIGH", queue="finance", dedupe_key=f"platform-pay:{_short(key)}:{'review' if review else 'failed'}",
        ref_type="platform_billing", ref_id=_clean(key, 120), link="/dashboard?section=billing", event_id=event.get("id"),
        repeat_comment="The provider reported this again.")


def _home_key(event: dict, p: dict) -> str:
    return str(p.get("home_id") or event.get("subject_id") or event.get("id"))


def _b_home_offline(event: dict) -> Optional[TicketSpec]:
    p = _payload(event)
    home = _home_key(event, p)
    return TicketSpec(
        source="iot", event_type=event["type"], subject="HomeDome connection offline",
        description="A HomeDome home gateway stopped reporting. Check the line, power and the gateway.",
        category="HOMEDOME", priority="HIGH", queue="technical", dedupe_key=f"iot-offline:{home}",
        ref_type="iot_home", ref_id=home, link=_home_link(p), event_id=event.get("id"),
        customer_id=_uuid(p.get("customer_id")), repeat_comment="Went offline again.")


def _b_home_recovered(event: dict) -> Optional[TicketSpec]:
    p = _payload(event)
    home = _home_key(event, p)
    return TicketSpec(
        source="iot", event_type=event["type"], subject="HomeDome connection offline", description="",
        category="HOMEDOME", priority="HIGH", queue="technical", dedupe_key=f"iot-offline:{home}",
        ref_type="iot_home", ref_id=home, comment_only=True, event_id=event.get("id"),
        repeat_comment="The home gateway is back online. Close this ticket once the customer confirms.")


def _b_home_support(event: dict) -> Optional[TicketSpec]:
    p = _payload(event)
    home = _home_key(event, p)
    return TicketSpec(
        source="iot", event_type=event["type"], subject="HomeDome support access requested",
        description="The customer asked support to view their HomeDome setup. Access is time-limited and logged.",
        category="HOMEDOME", priority="HIGH", queue="technical", dedupe_key=f"iot-support:{home}",
        ref_type="iot_home", ref_id=home, link=_home_link(p), event_id=event.get("id"),
        customer_id=_uuid(p.get("customer_id")), repeat_comment="The customer asked for support access again.")


def _b_home_failure(event: dict) -> Optional[TicketSpec]:
    p = _payload(event)
    home = _home_key(event, p)
    what = "gateway" if ".gateway." in event["type"] else "integration"
    which = _clean(p.get("integration") or p.get("domain"), 60)
    return TicketSpec(
        source="iot", event_type=event["type"], subject=f"HomeDome {what} failed" + (f": {which}" if which else ""),
        description=_clean(p.get("reason") or p.get("error"), 300) or f"A HomeDome {what} could not be set up or stopped working.",
        category="HOMEDOME", priority="NORMAL", queue="technical", dedupe_key=f"iot-{what}-fail:{home}:{_short(which)}",
        ref_type="iot_home", ref_id=home, link=_home_link(p), event_id=event.get("id"),
        customer_id=_uuid(p.get("customer_id")), repeat_comment=f"The {what} failed again.")


def _b_system(event: dict) -> Optional[TicketSpec]:
    p = _payload(event)
    svc, etype = _clean(p.get("service"), 40) or "unknown", _clean(p.get("exception_type"), 80) or "Error"
    fp = _clean(p.get("fingerprint"), 40)
    if not fp:
        return None
    job = p.get("kind") != "request"
    where = _clean(p.get("route") or p.get("job") or p.get("location"), 160)
    lines = [f"Service: {svc}", f"Type: {etype}", f"Message: {_clean(p.get('message'), 300)}",
             f"Where: {_clean(p.get('location'), 200)}"]
    if p.get("route"):
        lines.append(f"Route: {_clean(p.get('method'), 8)} {_clean(p.get('route'), 160)}")
    if p.get("frames"):
        lines.append("Frames:\n" + "\n".join(f"  {_clean(f, 160)}" for f in list(p["frames"])[:6]))
    suppressed = int(p.get("suppressed") or 0)
    return TicketSpec(
        source="system_error", event_type=event["type"],
        subject=f"[{svc}] {etype}" + (f" in {where}" if where else "") if not job else f"[{svc}] Job failed: {etype} ({where})",
        description="\n".join(lines), category="SYSTEM", priority="NORMAL", queue="platform",
        dedupe_key=f"sys:{fp}", ref_type="error_fingerprint", ref_id=fp, link=None, event_id=event.get("id"),
        repeat_comment=f"Happened again ({suppressed + 1} time{'s' if suppressed else ''} since the last report).",
        context={"fingerprint": fp, "service": svc, "suppressed": suppressed,
                 "affected_tenant": _clean(p.get("affected_tenant"), 40) or None})


def _build_rules() -> dict[str, Rule]:
    rows = [
        Rule(E.EVENT_TICKET_REQUESTED, "Explicit ticket request from a service", "api", "GENERAL", "NORMAL", "support", _b_requested),
        Rule(E.EVENT_EMAIL_RECEIVED, "Inbound email", "email", "GENERAL", "NORMAL", "support", _b_email),
        Rule(E.EVENT_EMAIL_SEND_FAILED, "Outbound email failed to send", "email", "GENERAL", "NORMAL", "support", _b_email_failed),
        Rule(E.EVENT_EMAIL_DELIVERY_FAILED, "Outbound email bounced", "email", "GENERAL", "NORMAL", "support", _b_email_failed),
        Rule(E.EVENT_AGENT_RUN_FAILED, "Agent run failed", "agent_task", "AGENT", "NORMAL", "agents", _b_agent_failed),
        Rule(E.EVENT_AGENT_NEEDS_HUMAN, "Agent task needs a person", "agent_task", "AGENT", "NORMAL", "agents", _b_agent_human),
        Rule("agents.approval.requested", "Agent action awaiting approval", "agent_task", "AGENT", "NORMAL", "agents", _b_agent_human),
        Rule(E.EVENT_CALL_MISSED, "Missed or abandoned call", "call_center", "CALLS", "NORMAL", "calls", _b_call_missed),
        Rule(E.EVENT_CALLBACK_REQUESTED, "Callback requested", "call_center", "CALLS", "NORMAL", "calls", _b_callback),
        Rule(E.EVENT_PAYMENT_FAILED, "Customer payment failed", "finance", "BILLING", "HIGH", "finance", _b_payment_failed),
        Rule(E.EVENT_RECONCILIATION_EXCEPTION, "Reconciliation exception", "finance", "BILLING", "NORMAL", "finance", _b_recon),
        Rule("platform.billing.subscription.payment_failed", "Platform subscription payment failed", "finance", "BILLING", "HIGH", "finance", _b_platform_payment),
        Rule("platform.billing.payment.review", "Platform payment needs review", "finance", "BILLING", "HIGH", "finance", _b_platform_payment),
        Rule("iot.home.offline", "HomeDome connection offline", "iot", "HOMEDOME", "HIGH", "technical", _b_home_offline),
        Rule("iot.home.recovered", "HomeDome connection recovered (comments on the offline ticket)", "iot", "HOMEDOME", "HIGH", "technical", _b_home_recovered),
        Rule("iot.support.requested", "HomeDome support access requested", "iot", "HOMEDOME", "HIGH", "technical", _b_home_support),
        Rule("iot.gateway.failed", "HomeDome gateway failed", "iot", "HOMEDOME", "NORMAL", "technical", _b_home_failure),
        Rule("iot.integration.failed", "HomeDome integration failed", "iot", "HOMEDOME", "NORMAL", "technical", _b_home_failure),
        Rule(E.EVENT_SYSTEM_ERROR, "Uncaught service exception", "system_error", "SYSTEM", "NORMAL", "platform", _b_system),
        Rule(E.EVENT_JOB_FAILED, "Failed background job", "system_error", "SYSTEM", "NORMAL", "platform", _b_system),
    ]
    return {r.key: r for r in rows}


RULES: dict[str, Rule] = _build_rules()

# Event patterns the support consumer subscribes to (rule keys; the bus matches them exactly).
SUBSCRIPTIONS = tuple(RULES)


# ── resolution ──────────────────────────────────────────────────────────────

def effective_rule(rule: Rule, override: Optional[Mapping]) -> dict:
    o = override or {}
    return {
        "key": rule.key, "label": rule.label, "source": rule.source,
        "enabled": rule.enabled if o.get("enabled") is None else bool(o["enabled"]),
        "category": (o.get("category") or rule.category), "priority": (o.get("priority") or rule.priority),
        "queue": (o.get("queue") or rule.queue), "assigned_to": o.get("assigned_to"),
        "outcome": o.get("outcome") or "ticket",
        "overridden": bool(o),
    }


def resolve(event: Mapping, overrides: Optional[Mapping[str, Mapping]] = None) -> Optional[TicketSpec]:
    """The ticket this event should produce for a tenant with `overrides`, or None (noise, disabled, no rule)."""
    rule = RULES.get(str(event.get("type") or ""))
    if rule is None or is_noise(event):
        return None
    eff = effective_rule(rule, (overrides or {}).get(rule.key))
    if not eff["enabled"]:
        return None
    spec = rule.build(dict(event))
    if spec is None:
        return None
    if rule.key != E.EVENT_TICKET_REQUESTED:
        spec.category, spec.priority, spec.queue = eff["category"], eff["priority"], eff["queue"]
    else:   # explicit requests carry their own category/priority; a tenant override only forces the queue
        spec.queue = eff["queue"]
    spec.assigned_to = _uuid(eff["assigned_to"])
    spec.outcome = eff["outcome"]
    spec.subject = _clean(spec.subject, 200)
    spec.description = redact_text(spec.description, 2000)
    spec.repeat_comment = redact_text(spec.repeat_comment, 400)
    spec.context = redact_data(spec.context)
    return spec


def escalated_priority(current: str, occurrences: int) -> str:
    """Raise (never lower) priority as a problem keeps recurring."""
    cur = PRIORITIES.index(current) if current in PRIORITIES else 1
    for threshold, level in ESCALATION:
        if occurrences >= threshold:
            return PRIORITIES[max(cur, PRIORITIES.index(level))]
    return PRIORITIES[cur]


def _safe_link(value: Any) -> Optional[str]:
    """Deep links stay inside the app: a relative /dashboard path only."""
    v = str(value or "").strip()
    return v[:300] if v.startswith("/dashboard") and "//" not in v and ".." not in v else None
