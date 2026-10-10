"""Per-user working context read LIVE from the real operational tables (never from the dashboard's module_data blob).

Used by BOTH sides so they can never disagree:
  * the indexer (cards/sources_personal.py) calls `gather(session, tenant, now)` for every user with something open and
    turns each result into a PRIVATE knowledge card (owner_id = that user);
  * the agent tools (`my.day`, `my.tasks`, ...) call the route `POST /api/v1/knowledge/personal/{kind}`, which calls
    `gather(session, tenant, now, [caller])`. The route takes the user id from the signed identity only.

Verified backing tables (see docs/knowledge-access.md):
  tasks        communication/models.py  comm_tasks            (assignee_id, due_date, status todo|in-progress|done)
  escalations  communication/models.py  escalations           (assigned_to, created_by, status open|in_progress|...)
               support/database.py      tickets               (assigned_to, priority, status)
  schedule     communication/models.py  schedule_events       (user_id, start/end, status)
  KPIs         hr/database.py           employee_kpi_sheets   (+ employees.user_id / manager_id) - HR talent KPI engine
  approvals    communication/models.py  approvals (pending)   + KPI sheets SUBMITTED in the caller's report chain

Explicit column lists, explicit tenant filter on every query, every read in a SAVEPOINT, a missing table yields an empty
result (the owning service has not started yet). Free text is scrubbed and clipped; no e-mail/phone/ID columns are read.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from services.tenant_memory.knowledge.textutil import clip, scrub

KINDS = ("tasks", "escalations", "schedule", "kpis", "approvals")
OPEN_TASK = "status <> 'done'"
MANAGER_ROLES = frozenset({"manager", "line_manager", "team_lead", "hr_manager", "hr_admin", "hr", "admin", "org_admin",
                           "tenant_admin", "owner", "supervisor", "sales_manager", "support_manager", "call_center_manager"})
ESCALATION_SLA_HOURS = float(os.getenv("KNOWLEDGE_ESCALATION_SLA_HOURS", "24") or 24)
HIGH_TICKET = ("URGENT", "CRITICAL", "HIGH")


def local_tz():
    name = os.getenv("KNOWLEDGE_PERSONAL_TZ", "Africa/Johannesburg")
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - no tzdata on this host: South Africa is a fixed UTC+2 (no DST)
        return timezone(timedelta(hours=2))


def day_window(now: datetime) -> dict:
    tz = local_tz()
    loc = now.astimezone(tz)
    start = datetime(loc.year, loc.month, loc.day, tzinfo=tz)
    return {"today_start": start, "today_end": start + timedelta(days=1), "week_end": start + timedelta(days=7),
            "today": start.date(), "label": loc.strftime("%A %Y-%m-%d")}


def _aware(v: Any) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    return None


async def _rows(session, sql: str, params: dict) -> list[dict]:
    from sqlalchemy import text
    async with session.begin_nested():
        res = await session.execute(text(sql), params)
        return [dict(r) for r in res.mappings().all()]


async def _exists(session, table: str) -> bool:
    rows = await _rows(session, "SELECT to_regclass(CAST(:n AS text)) IS NOT NULL AS ok", {"n": table})
    return bool(rows and rows[0].get("ok"))


def _uid_clause(col: str, uids: Optional[list[str]]) -> tuple[str, dict]:
    return (f" AND {col} = ANY(CAST(:uids AS uuid[]))", {"uids": list(uids)}) if uids else ("", {})


def _initials(name: Any) -> str:
    parts = str(name or "").split()
    if not parts:
        return "Colleague"
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0].upper()}."


# ── tasks ───────────────────────────────────────────────────────────────────

async def fetch_tasks(session, tenant: str, uids: Optional[list[str]], now: datetime, limit: int = 400) -> dict[str, list]:
    if not await _exists(session, "comm_tasks"):
        return {}
    uc, up = _uid_clause("t.assignee_id", uids)
    rows = await _rows(session, f"""
        SELECT t.id::text AS id, t.assignee_id::text AS user_id, t.title, t.status, t.due_date, t.created_at, t.updated_at,
               t.channel_id::text AS channel_id, c.name AS channel_name
        FROM comm_tasks t LEFT JOIN channels c ON c.id = t.channel_id AND c.tenant_id = t.tenant_id
        WHERE t.tenant_id = CAST(:t AS uuid) AND t.assignee_id IS NOT NULL AND t.status <> 'done'{uc}
        ORDER BY t.due_date NULLS LAST, t.created_at LIMIT :lim""", {"t": tenant, "lim": limit, **up})
    out: dict[str, list] = defaultdict(list)
    for r in rows:
        due = _aware(r["due_date"])
        out[r["user_id"]].append({
            "id": r["id"], "title": clip(scrub(r["title"]), 140), "status": r["status"], "due": due.isoformat() if due else None,
            "overdue": bool(due and due < now), "channel": clip(scrub(r.get("channel_name")), 60) or None,
            "link": f"/dashboard/communication?task={r['id']}"})
    return dict(out)


# ── escalations (+ high-priority tickets assigned to the user) ──────────────

async def fetch_escalations(session, tenant: str, uids: Optional[list[str]], now: datetime, limit: int = 400) -> dict[str, list]:
    out: dict[str, list] = defaultdict(list)
    if await _exists(session, "escalations"):
        cond, up = "", {}
        if uids:
            cond, up = " AND (e.assigned_to = ANY(CAST(:uids AS uuid[])) OR e.created_by = ANY(CAST(:uids AS uuid[])))", {"uids": list(uids)}
        rows = await _rows(session, f"""
            SELECT e.id::text AS id, e.ticket_id, e.reason, e.status, e.assigned_to::text AS assigned_to, e.created_by::text AS created_by,
                   e.created_at, c.name AS channel_name
            FROM escalations e LEFT JOIN channels c ON c.id = e.channel_id AND c.tenant_id = e.tenant_id
            WHERE e.tenant_id = CAST(:t AS uuid) AND e.status IN ('open', 'in_progress'){cond}
            ORDER BY e.created_at LIMIT :lim""", {"t": tenant, "lim": limit, **up})
        want = set(uids) if uids else None
        for r in rows:
            created = _aware(r["created_at"]) or now
            age_h = max(0.0, (now - created).total_seconds() / 3600)
            base = {"id": r["id"], "kind": "escalation", "ticket_ref": clip(scrub(r.get("ticket_id")), 40) or None,
                    "reason": clip(scrub(r.get("reason")), 160), "status": r["status"], "opened": created.isoformat(),
                    "open_hours": round(age_h, 1), "sla_hours": ESCALATION_SLA_HOURS,
                    "sla_breached": age_h > ESCALATION_SLA_HOURS, "sla_basis": "tenant default (escalations carry no SLA field)",
                    "channel": clip(scrub(r.get("channel_name")), 60) or None, "link": f"/dashboard/communication?escalation={r['id']}"}
            for uid, role in ((r["assigned_to"], "assigned"), (r["created_by"], "raised")):
                if uid and (want is None or uid in want) and not (role == "raised" and uid == r["assigned_to"]):
                    out[uid].append({**base, "role": role})
    if await _exists(session, "tickets"):
        uc, up = _uid_clause("tk.assigned_to", uids)
        rows = await _rows(session, f"""
            SELECT tk.id::text AS id, tk.assigned_to::text AS user_id, tk.subject, tk.priority, tk.status, tk.created_at
            FROM tickets tk WHERE tk.tenant_id = CAST(:t AS uuid) AND tk.assigned_to IS NOT NULL
              AND upper(tk.status) NOT IN ('RESOLVED', 'CLOSED') AND upper(tk.priority) IN ('URGENT', 'CRITICAL', 'HIGH'){uc}
            ORDER BY tk.created_at LIMIT :lim""", {"t": tenant, "lim": limit, **up})
        for r in rows:
            created = _aware(r["created_at"]) or now
            out[r["user_id"]].append({
                "id": r["id"], "kind": "ticket", "role": "assigned", "reason": clip(scrub(r["subject"]), 140),
                "priority": r["priority"], "status": r["status"], "opened": created.isoformat(),
                "open_hours": round(max(0.0, (now - created).total_seconds() / 3600), 1), "link": f"/dashboard/service?ticket={r['id']}"})
    return dict(out)


# ── schedule ────────────────────────────────────────────────────────────────

async def fetch_schedule(session, tenant: str, uids: Optional[list[str]], now: datetime, win: dict, limit: int = 600) -> dict[str, list]:
    if not await _exists(session, "schedule_events"):
        return {}
    uc, up = _uid_clause("s.user_id", uids)
    rows = await _rows(session, f"""
        SELECT s.id::text AS id, s.user_id::text AS user_id, s.title, s.type, s.start_time, s.end_time, s.status
        FROM schedule_events s
        WHERE s.tenant_id = CAST(:t AS uuid) AND s.status IN ('upcoming', 'in_progress')
          AND s.end_time >= :d0 AND s.start_time < :d1{uc}
        ORDER BY s.start_time LIMIT :lim""", {"t": tenant, "d0": win["today_start"], "d1": win["week_end"], "lim": limit, **up})
    out: dict[str, list] = defaultdict(list)
    for r in rows:
        st, en = _aware(r["start_time"]), _aware(r["end_time"])
        out[r["user_id"]].append({"id": r["id"], "title": clip(scrub(r["title"]), 120), "type": r["type"], "status": r["status"],
                                  "start": st.isoformat() if st else None, "end": en.isoformat() if en else None,
                                  "today": bool(st and win["today_start"] <= st < win["today_end"]),
                                  "link": f"/dashboard/communication?event={r['id']}"})
    return dict(out)


# ── KPIs (talent KPI engine) ────────────────────────────────────────────────

def _kpi_items(raw: Any) -> list[dict]:
    try:
        data = json.loads(raw) if isinstance(raw, str) and raw else (raw or [])
    except ValueError:
        return []
    items = []
    for k in data if isinstance(data, list) else []:
        if not isinstance(k, dict):
            continue
        lvl = k.get("current_level")
        items.append({"title": clip(scrub(k.get("title")), 100), "weight_pct": k.get("weight_pct"),
                      "level": lvl if isinstance(lvl, (int, float)) else None,
                      "target": clip(scrub(k.get("target") or k.get("measure") or k.get("target_description")), 120) or None})
    return items


def _chain_under(boss: str, children: dict[str, list[str]], depth: int = 6) -> list[str]:
    seen, frontier, out = {boss}, [boss], []
    for _ in range(depth):
        nxt = []
        for p in frontier:
            for c in children.get(p, []):
                if c not in seen:
                    seen.add(c)
                    out.append(c)
                    nxt.append(c)
        frontier = nxt
    return out


async def fetch_kpis(session, tenant: str, uids: Optional[list[str]], roles_by_user: dict[str, set]) -> tuple[dict, dict]:
    """(kpis_by_user, kpi_approvals_by_user). Own sheet for everyone linked to an employee; a team aggregate and the
    list of SUBMITTED sheets awaiting a decision only for users who sit above those employees AND hold a manager role."""
    if not (await _exists(session, "employees") and await _exists(session, "employee_kpi_sheets")):
        return {}, {}
    emps = await _rows(session, """
        SELECT e.id::text AS id, e.user_id::text AS user_id, e.manager_id::text AS manager_id, e.full_name, e.job_title
        FROM employees e WHERE e.tenant_id = CAST(:t AS uuid) AND COALESCE(e.status, 'ACTIVE') = 'ACTIVE' AND COALESCE(e.is_agent, false) = false""",
                       {"t": tenant})
    sheets = await _rows(session, """
        SELECT DISTINCT ON (sh.employee_id) sh.employee_id::text AS employee_id, sh.fiscal_year, sh.status, sh.overall_score,
               sh.kpis_json, sh.reject_reason, sh.updated_at
        FROM employee_kpi_sheets sh WHERE sh.tenant_id = CAST(:t AS uuid)
        ORDER BY sh.employee_id, sh.updated_at DESC""", {"t": tenant})
    sheet_of = {s["employee_id"]: s for s in sheets}
    by_id = {e["id"]: e for e in emps}
    children: dict[str, list[str]] = defaultdict(list)
    for e in emps:
        if e["manager_id"] and e["manager_id"] in by_id:
            children[e["manager_id"]].append(e["id"])
    want = set(uids) if uids else None
    kpis: dict[str, dict] = {}
    approvals: dict[str, list] = {}
    for e in emps:
        uid = e["user_id"]
        if not uid or (want is not None and uid not in want):
            continue
        sh = sheet_of.get(e["id"])
        mine = None
        if sh:
            items = _kpi_items(sh["kpis_json"])
            levels = [i["level"] for i in items if i["level"] is not None]
            mine = {"fiscal_year": sh["fiscal_year"], "status": sh["status"],
                    "overall_score": float(sh["overall_score"]) if sh["overall_score"] is not None else None,
                    "average_level": round(sum(levels) / len(levels), 2) if levels else None, "scale": "levels 1-5, level 3 = on target",
                    "objectives": items[:12], "rejected_reason": clip(scrub(sh.get("reject_reason")), 160) or None,
                    "action": {"DRAFT": "finish and submit your KPI sheet", "SUBMITTED": "awaiting your manager's decision"}.get(str(sh["status"]).upper()),
                    "link": "/dashboard/talent?tab=objectives"}
        team = None
        roles = {r.lower() for r in roles_by_user.get(uid, set())}
        reports = _chain_under(e["id"], children)
        if reports and roles & MANAGER_ROLES:
            sts: dict[str, int] = defaultdict(int)
            scores, lv = [], []
            pending = []
            for rid in reports:
                s = sheet_of.get(rid)
                if not s:
                    sts["NO_SHEET"] += 1
                    continue
                sts[str(s["status"]).upper()] += 1
                if s["overall_score"] is not None:
                    scores.append(float(s["overall_score"]))
                lv += [i["level"] for i in _kpi_items(s["kpis_json"]) if i["level"] is not None]
                if str(s["status"]).upper() == "SUBMITTED":
                    pending.append({"employee": _initials(by_id[rid]["full_name"]), "job_title": clip(scrub(by_id[rid]["job_title"]), 60),
                                    "fiscal_year": s["fiscal_year"], "link": "/dashboard/talent?tab=objectives"})
            team = {"reports": len(reports), "by_status": dict(sts),
                    "average_score": round(sum(scores) / len(scores), 1) if scores else None,
                    "average_level": round(sum(lv) / len(lv), 2) if lv else None, "aggregate_only": True}
            if pending:
                approvals[uid] = pending[:10]
        if mine or team:
            kpis[uid] = {"mine": mine, "team": team}
    return kpis, approvals


# ── approvals (communication) ───────────────────────────────────────────────

async def fetch_comm_approvals(session, tenant: str, users: Iterable[str], limit: int = 20) -> dict[str, list]:
    if not await _exists(session, "approvals"):
        return {}
    out: dict[str, list] = {}
    for uid in list(users)[:300]:
        rows = await _rows(session, """
            SELECT a.id::text AS id, a.title, a.created_at, c.name AS channel_name
            FROM approvals a JOIN channels c ON c.id = a.channel_id AND c.tenant_id = a.tenant_id
            WHERE a.tenant_id = CAST(:t AS uuid) AND a.status = 'pending' AND a.created_by <> CAST(:u AS uuid) AND a.user_id <> CAST(:u AS uuid)
              AND (c.is_private IS NOT TRUE OR c.created_by = CAST(:u AS uuid)
                   OR EXISTS (SELECT 1 FROM channel_members m WHERE m.tenant_id = a.tenant_id AND m.channel_id = c.id AND m.user_id = CAST(:u AS uuid)))
            ORDER BY a.created_at LIMIT :lim""", {"t": tenant, "u": uid, "lim": limit})
        if rows:
            out[uid] = [{"id": r["id"], "title": clip(scrub(r["title"]), 140), "requested": (_aware(r["created_at"]) or datetime.now(timezone.utc)).isoformat(),
                         "channel": clip(scrub(r.get("channel_name")), 60) or None, "link": f"/dashboard/communication?approval={r['id']}"}
                   for r in rows]
    return out


async def fetch_roles(session, tenant: str, uids: Optional[list[str]]) -> dict[str, set]:
    if not (await _exists(session, "user_roles") and await _exists(session, "roles")):
        return {}
    uc, up = _uid_clause("ur.user_id", uids)
    rows = await _rows(session, f"""SELECT ur.user_id::text AS user_id, r.name FROM user_roles ur JOIN roles r ON r.id = ur.role_id
        WHERE ur.tenant_id = CAST(:t AS uuid){uc}""", {"t": tenant, **up})
    out: dict[str, set] = defaultdict(set)
    for r in rows:
        out[r["user_id"]].add(str(r["name"]).lower())
    return dict(out)


# ── public entry ────────────────────────────────────────────────────────────

async def gather(session, tenant: str, now: Optional[datetime] = None, uids: Optional[list[str]] = None,
                 roles: Optional[dict[str, set]] = None, kinds: Iterable[str] = KINDS) -> dict[str, dict]:
    """{user_id: {"tasks": [...], "escalations": [...], "schedule": [...], "kpis": {...}, "approvals": [...]}}.
    uids=None -> every user with something open (indexer); uids=[caller] -> only that user (tools)."""
    now = now or datetime.now(timezone.utc)
    kinds = set(kinds)
    win = day_window(now)
    roles_by = roles if roles is not None else await fetch_roles(session, tenant, uids)
    data: dict[str, dict] = defaultdict(dict)
    if "tasks" in kinds:
        for u, v in (await fetch_tasks(session, tenant, uids, now)).items():
            data[u]["tasks"] = v
    if "escalations" in kinds:
        for u, v in (await fetch_escalations(session, tenant, uids, now)).items():
            data[u]["escalations"] = v
    if "schedule" in kinds:
        for u, v in (await fetch_schedule(session, tenant, uids, now, win)).items():
            data[u]["schedule"] = v
    kpi_approvals: dict[str, list] = {}
    if "kpis" in kinds or "approvals" in kinds:
        kp, kpi_approvals = await fetch_kpis(session, tenant, uids, roles_by)
        if "kpis" in kinds:
            for u, v in kp.items():
                data[u]["kpis"] = v
    if "approvals" in kinds:
        managers = [u for u, rs in roles_by.items() if rs & MANAGER_ROLES and (uids is None or u in set(uids))]
        comm = await fetch_comm_approvals(session, tenant, managers)
        for u in set(comm) | set(kpi_approvals):
            data[u]["approvals"] = {"requests": comm.get(u, []), "kpi_sheets": kpi_approvals.get(u, [])}
    for u in data:
        data[u]["window"] = {"today": win["label"], "tz": str(getattr(local_tz(), "key", "UTC+02:00"))}
    return dict(data)


# ── shaping for the agent tools / API (compact, ordered, capped) ─────────────

def _cap(n: Any, default: int = 20) -> int:
    try:
        return max(1, min(100, int(n)))
    except (TypeError, ValueError):
        return default


def shape_tasks(items: list, limit: int = 20, status: Optional[str] = None, overdue_only: bool = False) -> dict:
    rows = [t for t in items if (not status or t["status"] == status) and (not overdue_only or t["overdue"])]
    rows.sort(key=lambda t: (not t["overdue"], t["due"] or "9999", t["title"]))
    return {"total": len(rows), "overdue": sum(1 for t in rows if t["overdue"]), "items": rows[:_cap(limit)]}


def shape_escalations(items: list, limit: int = 20, role: Optional[str] = None, breached_only: bool = False) -> dict:
    rows = [e for e in items if (not role or e["role"] == role) and (not breached_only or e.get("sla_breached"))]
    rows.sort(key=lambda e: (not e.get("sla_breached", e.get("priority") in HIGH_TICKET), -float(e["open_hours"])))
    return {"total": len(rows), "past_sla": sum(1 for e in rows if e.get("sla_breached")), "items": rows[:_cap(limit)]}


def shape_schedule(items: list, limit: int = 30, today_only: bool = False) -> dict:
    rows = [s for s in items if s["today"] or not today_only]
    return {"total": len(rows), "today": sum(1 for s in rows if s["today"]), "items": rows[:_cap(limit, 30)]}


def shape_kpis(k: Optional[dict], include_team: bool = True) -> dict:
    k = k or {}
    out = {"mine": k.get("mine"), "has_sheet": bool(k.get("mine"))}
    if include_team and k.get("team"):
        out["team"] = k["team"]
    return out


def shape_approvals(a: Optional[dict], limit: int = 20) -> dict:
    a = a or {"requests": [], "kpi_sheets": []}
    return {"total": len(a["requests"]) + len(a["kpi_sheets"]), "requests": a["requests"][:_cap(limit)], "kpi_sheets": a["kpi_sheets"][:_cap(limit)]}


def nudges(data: dict) -> list[str]:
    out = []
    k = (data.get("kpis") or {}).get("mine") or {}
    if k.get("action"):
        out.append(f"KPI sheet {k.get('fiscal_year')}: {k['action']}")
    if k.get("rejected_reason"):
        out.append("Your KPI sheet was sent back with feedback")
    team = (data.get("kpis") or {}).get("team") or {}
    if team.get("by_status", {}).get("SUBMITTED"):
        out.append(f"{team['by_status']['SUBMITTED']} team KPI sheet(s) are submitted and waiting")
    if team.get("by_status", {}).get("NO_SHEET"):
        out.append(f"{team['by_status']['NO_SHEET']} report(s) have no KPI sheet yet")
    return out


def day_summary(data: dict) -> dict:
    """Everything that matters today, compact enough for a model to narrate with links."""
    t = shape_tasks(data.get("tasks") or [], 8)
    e = shape_escalations(data.get("escalations") or [], 6)
    s = shape_schedule(data.get("schedule") or [], 8, today_only=True)
    up = shape_schedule([x for x in (data.get("schedule") or []) if not x["today"]], 5)
    a = shape_approvals(data.get("approvals"), 6)
    today = str((data.get("window") or {}).get("today", ""))[-10:]
    due_today = [x for x in (data.get("tasks") or []) if not x["overdue"] and x.get("due")
                 and datetime.fromisoformat(x["due"]).astimezone(local_tz()).date().isoformat() == today]
    return {
        "date": (data.get("window") or {}).get("today"), "timezone": (data.get("window") or {}).get("tz"),
        "headline": {"open_tasks": t["total"], "overdue_tasks": t["overdue"], "tasks_due_today": len(due_today),
                     "escalations_open": e["total"], "escalations_past_sla": e["past_sla"], "meetings_today": s["today"],
                     "approvals_waiting": a["total"], "kpi_nudges": len(nudges(data))},
        "tasks": t["items"], "escalations": e["items"], "schedule_today": s["items"], "schedule_next_days": up["items"],
        "approvals": {"requests": a["requests"], "kpi_sheets": a["kpi_sheets"]}, "kpi_nudges": nudges(data),
    }
