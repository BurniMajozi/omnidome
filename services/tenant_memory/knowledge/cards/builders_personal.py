"""PRIVATE per-user context cards: my tasks, escalations, schedule, KPIs and approvals.

Every card is `module="personal"`, `visibility="private"` and `owner_id=<that user>`: retrieval returns it to its owner
only (admins included), and it expires quickly (`valid_to` = now + PERSONAL_TTL_MIN) so a stale list can never be quoted
after the worker stops. Bodies avoid relative wording ("in 2 hours") so unchanged data keeps an identical content hash
and is never re-embedded by the frequent sweep.

Also hosts `build_mail_thread_card`: the Communication panel's per-mailbox thread digest card (see sources_personal.py).
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from services.tenant_memory.knowledge.cards.base import Card, frontmatter
from services.tenant_memory.knowledge.kdata import IMPORTANCE
from services.tenant_memory.knowledge.textutil import clip, scrub

import os

PERSONAL_TTL_MIN = int(os.getenv("KNOWLEDGE_PERSONAL_TTL_MIN", "20") or 20)
PERSONAL_TYPES = {"tasks": "my_tasks", "escalations": "my_escalations", "schedule": "my_schedule", "kpis": "my_kpis",
                  "approvals": "my_approvals"}
TITLES = {"tasks": "My tasks", "escalations": "My escalations", "schedule": "My schedule", "kpis": "My KPIs",
          "approvals": "Approvals waiting for me"}
LINKS = {"tasks": "/dashboard/communication", "escalations": "/dashboard/communication", "schedule": "/dashboard/communication",
         "kpis": "/dashboard/talent", "approvals": "/dashboard/communication"}


def _d(v: Any) -> str:
    return str(v or "")[:16].replace("T", " ")


def _tasks_md(items: list) -> list[str]:
    over = [t for t in items if t["overdue"]]
    lines = [f"Open tasks assigned to me: {len(items)} ({len(over)} overdue)", ""]
    for t in items[:25]:
        flag = " OVERDUE" if t["overdue"] else ""
        due = f" - due {_d(t['due'])}" if t.get("due") else " - no due date"
        ch = f" [{t['channel']}]" if t.get("channel") else ""
        lines.append(f"- {t['title']} ({t['status']}){due}{flag}{ch} [[task:{t['id']}]]")
    return lines


def _esc_md(items: list) -> list[str]:
    br = [e for e in items if e.get("sla_breached")]
    lines = [f"Escalations and priority tickets involving me: {len(items)} ({len(br)} past the {int(items[0].get('sla_hours') or 0) or 'default'}h response window)" if items and items[0]["kind"] == "escalation" else f"Escalations and priority tickets involving me: {len(items)}", ""]
    for e in items[:25]:
        if e["kind"] == "escalation":
            ref = f" ticket {e['ticket_ref']}" if e.get("ticket_ref") else ""
            lines.append(f"- Escalation ({e['role']}, {e['status']}){ref}: {e.get('reason') or 'no reason given'}; opened {_d(e['opened'])}, "
                         f"open {e['open_hours']}h{' PAST SLA' if e.get('sla_breached') else ''} [[escalation:{e['id']}]]")
        else:
            lines.append(f"- Ticket ({e['priority']}, {e['status']}): {e.get('reason')}; opened {_d(e['opened'])}, open {e['open_hours']}h [[ticket:{e['id']}]]")
    return lines


def _sched_md(items: list) -> list[str]:
    today = [s for s in items if s["today"]]
    lines = [f"Today: {len(today)} item(s). Next 7 days: {len(items)}.", ""]
    for s in items[:30]:
        lines.append(f"- {_d(s['start'])} to {_d(s['end'])[11:]} {s['title']} ({s['type']}, {s['status']}){' TODAY' if s['today'] else ''} [[event:{s['id']}]]")
    return lines


def _kpi_md(k: dict) -> list[str]:
    lines = []
    m = k.get("mine")
    if m:
        score = f", overall score {m['overall_score']}" if m.get("overall_score") is not None else ""
        lines += [f"My KPI sheet {m['fiscal_year']}: status {m['status']}{score}; average level {m.get('average_level')} ({m['scale']})."]
        if m.get("action"):
            lines.append(f"Next step: {m['action']}.")
        if m.get("rejected_reason"):
            lines.append(f"Manager feedback: {m['rejected_reason']}")
        lines.append("")
        for o in m["objectives"]:
            lines.append(f"- {o['title']}: level {o['level']} of 5, weight {o['weight_pct']}%" + (f", target {o['target']}" if o.get("target") else ""))
    t = k.get("team")
    if t:
        lines += ["", "## My team (aggregate only)", f"- Reports in my chain: {t['reports']}; sheets by status: "
                  + ", ".join(f"{k2}={v}" for k2, v in sorted(t["by_status"].items())),
                  f"- Average score {t.get('average_score')}, average level {t.get('average_level')}"]
    return lines


def _appr_md(a: dict) -> list[str]:
    lines = [f"Requests waiting for my decision: {len(a['requests'])}; KPI sheets awaiting my approval: {len(a['kpi_sheets'])}", ""]
    for r in a["requests"][:20]:
        lines.append(f"- Approval: {r['title']} (requested {_d(r['requested'])}) [[approval:{r['id']}]]")
    for s in a["kpi_sheets"][:10]:
        lines.append(f"- KPI sheet for {s['employee']} ({s['job_title']}, {s['fiscal_year']}) submitted - needs my decision")
    return lines


BODY = {"tasks": _tasks_md, "escalations": _esc_md, "schedule": _sched_md, "kpis": _kpi_md, "approvals": _appr_md}


def personal_cards(user_id: str, data: dict, now: Optional[datetime] = None) -> list[Card]:
    now = now or datetime.now(timezone.utc)
    win = data.get("window", {})
    cards: list[Card] = []
    for kind, stype in PERSONAL_TYPES.items():
        payload = data.get(kind)
        if kind == "approvals" and payload and not (payload["requests"] or payload["kpi_sheets"]):
            payload = None
        if kind == "kpis" and payload and not (payload.get("mine") or payload.get("team")):
            payload = None
        if not payload:
            continue
        lines = [f"# {TITLES[kind]}", "", f"(Private to me. Snapshot for {win.get('today', 'today')}, timezone {win.get('tz', 'UTC')}.)", ""]
        lines += BODY[kind](payload)
        md = frontmatter(stype, user_id, "personal", now, ["personal", stype, "private"]) + "\n".join(lines) + "\n"
        cards.append(Card(stype, user_id, "personal", TITLES[kind], md, now, ["personal", stype, "private"], 0.85,
                          {"deep_link": LINKS[kind], "private": True}, [],
                          valid_to=now + timedelta(minutes=PERSONAL_TTL_MIN), owner_id=user_id, visibility="private",
                          required_roles=[]))
    return cards


# ── Communication panel: mailbox thread digest ───────────────────────────────

_RE_PREFIX = re.compile(r"^\s*((re|fw|fwd|aw|sv)\s*:\s*)+", re.I)
_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_QUOTE_HEAD = re.compile(r"(?im)^(on .{5,120} wrote:|-{2,}\s*original message\s*-{2,}|from:\s.+)$")
_NAME_EMAIL = re.compile(r'^\s*"?([^"<]*?)"?\s*<[^>]+>\s*$')

# Which panel's data a mailbox's threads belong to (agent_mailboxes.agent_type). Anything unmapped needs communication admin.
AGENT_MODULE = {"support": "support", "sales": "sales", "billing": "billing", "collections": "billing", "retention": "retention",
                "marketing": "marketing", "hr": "hr", "finance": "finance", "compliance": "compliance", "customer_facing": "support",
                "call_center": "call_center", "network": "network", "inventory": "inventory"}


def thread_key(subject: Any) -> str:
    norm = " ".join(_RE_PREFIX.sub("", str(subject or "")).lower().split())[:200] or "(no subject)"
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def display_name(addr: Any, fallback: str = "External sender") -> str:
    """'Thandi Mokoena <t@x.co.za>' -> 'Thandi M.'; a bare address gives the generic fallback (addresses are never indexed)."""
    m = _NAME_EMAIL.match(str(addr or ""))
    name = (m.group(1).strip() if m else "").strip()
    if not name or "@" in name:
        return fallback
    parts = name.split()
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0].upper()}."


def inbound_excerpt(body: Any, limit: int = 300) -> str:
    """Last inbound message excerpt: quoted history and signatures dropped, links removed entirely, scrubbed, clipped."""
    text = str(body or "")[:4000]
    m = _QUOTE_HEAD.search(text)
    if m:
        text = text[:m.start()]
    text = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith(">"))
    text = _URL.sub("[link removed]", text)
    return clip(scrub(text), limit)


def build_mail_thread_card(mailbox: dict, emails: list[dict], suppressed: bool = False, now: Optional[datetime] = None) -> Optional[Card]:
    """One card per (mailbox, subject thread). Returns None (=> tombstone) when the thread is suppressed / unsubscribed /
    forgotten, or empty. `emails` are non-deleted rows of ONE thread, any order."""
    if not emails:
        return None
    flags = {k for e in emails for k, v in (e.get("flags") or {}).items() if v}
    if suppressed or flags & {"unsubscribed", "suppressed", "knowledge_forget", "do_not_contact"}:
        return None
    emails = sorted(emails, key=lambda e: e["created_at"])
    last = emails[-1]
    inbound = [e for e in emails if e["direction"] == "inbound"]
    last_in = inbound[-1] if inbound else None
    as_of = last["created_at"] if isinstance(last["created_at"], datetime) else (now or datetime.now(timezone.utc))
    mb_name = scrub(str(mailbox.get("display_name") or mailbox.get("agent_type") or "Mailbox"))
    names = []
    for e in emails:
        n = display_name(e["sender"]) if e["direction"] == "inbound" else mb_name
        if n not in names:
            names.append(n)
    unread = sum(1 for e in inbound if not (e.get("flags") or {}).get("is_read"))
    needs_reply = bool(last_in is last and str(last["status"]) in ("received", "dispatched", "processed") and not (last.get("flags") or {}).get("agent_reply_sent"))
    hold = bool(flags & {"legal_hold"})
    subj = clip(scrub(_RE_PREFIX.sub("", str(emails[0]["subject"] or ""))), 140) or "(no subject)"
    key = thread_key(emails[0]["subject"])
    mid = str(mailbox["id"])
    lines = [f"# Mail thread: {subj}", "", f"- Mailbox: {mb_name} ({mailbox.get('agent_type')})",
             f"- Messages: {len(emails)} ({len(inbound)} inbound, {len(emails) - len(inbound)} outbound); unread inbound: {unread}",
             f"- Participants: {', '.join(names[:6])}", f"- Last activity: {as_of.strftime('%Y-%m-%d %H:%M') if isinstance(as_of, datetime) else ''} ({last['direction']}, status {last['status']})",
             f"- Needs a reply: {'yes' if needs_reply else 'no'}", "- Assigned to: not tracked (mailboxes are team inboxes)"]
    if hold:
        lines.append("- LEGAL HOLD: do not alter or forget")
    if last_in is not None:
        lines += ["", "## Last inbound message (excerpt, links removed)", inbound_excerpt(last_in.get("body")) or "(empty)"]
    mod = AGENT_MODULE.get(str(mailbox.get("agent_type") or "").lower())
    tags = ["communication", "mail", "thread"] + (["legal_hold"] if hold else []) + (["needs_reply"] if needs_reply else [])
    md = frontmatter("mail_thread", f"{mid}:{key}", "communication", as_of, tags, {"mailbox": mailbox.get("agent_type")}) + "\n".join(lines) + "\n"
    card = Card("mail_thread", f"{mid}:{key}", "communication", f"Mail: {subj}", md, as_of if isinstance(as_of, datetime) else None, tags,
                IMPORTANCE["high"] if needs_reply else IMPORTANCE["normal"], {"deep_link": f"/dashboard/communication?mailbox={mid}", "mailbox_id": mid},
                [], visibility="team", required_roles=[])
    # Team inbox: the panel is `communication`, plus read access to the area the mailbox serves (admin-only if unmapped).
    card.required_permission = f"{mod}.read" if mod else "communication.admin"
    return card
