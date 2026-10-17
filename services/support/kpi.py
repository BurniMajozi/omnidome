"""Ticket KPIs, computed from the lifecycle timestamps on `tickets` and the `ticket_events` log.

Definitions (all over tickets OPENED in the window, in hours):

    time to respond      created -> first_response_at: the first time a person picked the ticket up
                         (assigned it, started it, or sent a customer-visible reply). System and
                         customer events never count.
    time to assign       created -> first_assigned_at
    time to resolve      created -> resolved_at (mean and median). This is the "mean time to repair" per
                         technician when grouped by assignee.
    first-touch resolution   resolved with at most one assignment, no queue transfer and no reopen
    SLA met              resolved_at <= sla_due_at
    time in stage        average hours spent in each status, from the status events

"Open now" numbers (open, unassigned, overdue, stale) are the current state and ignore the window.
Overdue = open past its resolution deadline. Stale = open with no activity for STALE_HOURS[priority].
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

CLOSED_STATUSES = ("RESOLVED", "CLOSED")
STALE_HOURS = {"URGENT": 2, "HIGH": 4, "NORMAL": 12, "LOW": 36}
DEFAULT_STALE_HOURS = 12
MAX_DAYS = 365


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    return None if v is None else (v if v.tzinfo else v.replace(tzinfo=timezone.utc))


def hours_between(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    """Hours from `start` to `end`, or None when either is missing or the order is wrong."""
    a, b = _aware(start), _aware(end)
    if a is None or b is None or b < a:
        return None
    return round((b - a).total_seconds() / 3600.0, 2)


def is_overdue(status: str, sla_due_at: Optional[datetime], now: Optional[datetime] = None) -> bool:
    due = _aware(sla_due_at)
    return bool(due) and status not in CLOSED_STATUSES and (now or datetime.now(timezone.utc)) > due


def is_stale(status: str, priority: Optional[str], last_activity: Optional[datetime], now: Optional[datetime] = None) -> bool:
    last = _aware(last_activity)
    if last is None or status in CLOSED_STATUSES:
        return False
    limit = STALE_HOURS.get((priority or "").upper(), DEFAULT_STALE_HOURS)
    return ((now or datetime.now(timezone.utc)) - last).total_seconds() > limit * 3600


def _r(v, n: int = 2):
    return None if v is None else round(float(v), n)


def _rate(num, den):
    return round(100.0 * num / den, 1) if den else None


_HOURS = "extract(epoch FROM ({end} - {start})) / 3600.0"
_RESP = _HOURS.format(end="first_response_at", start="created_at")
_ASSIGN = _HOURS.format(end="first_assigned_at", start="created_at")
_RESOLVE = _HOURS.format(end="resolved_at", start="created_at")

_METRICS = f"""
    count(*) AS opened,
    count(*) FILTER (WHERE resolved_at IS NOT NULL) AS resolved,
    count(*) FILTER (WHERE status NOT IN ('RESOLVED', 'CLOSED')) AS still_open,
    avg({_RESP}) FILTER (WHERE first_response_at >= created_at) AS mean_respond,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY {_RESP}) FILTER (WHERE first_response_at >= created_at) AS median_respond,
    avg({_ASSIGN}) FILTER (WHERE first_assigned_at >= created_at) AS mean_assign,
    avg({_RESOLVE}) FILTER (WHERE resolved_at >= created_at) AS mean_resolve,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY {_RESOLVE}) FILTER (WHERE resolved_at >= created_at) AS median_resolve,
    count(*) FILTER (WHERE resolved_at IS NOT NULL AND assignment_count <= 1 AND transfer_count = 0
                        AND reopen_count = 0) AS first_touch,
    count(*) FILTER (WHERE resolved_at IS NOT NULL AND sla_due_at IS NOT NULL) AS sla_judged,
    count(*) FILTER (WHERE resolved_at IS NOT NULL AND sla_due_at IS NOT NULL AND resolved_at <= sla_due_at) AS sla_met
"""

_STALE_SQL = """(status NOT IN ('RESOLVED', 'CLOSED')
        AND COALESCE(last_activity_at, updated_at, created_at) < now() - make_interval(hours => CASE priority
              WHEN 'URGENT' THEN 2 WHEN 'HIGH' THEN 4 WHEN 'LOW' THEN 36 ELSE 12 END))"""


STALE_SQL = _STALE_SQL        # shared with desk.ticket_summary


def _shape(r) -> dict:
    return {
        "opened": r["opened"], "resolved": r["resolved"], "still_open": r["still_open"],
        "mean_hours_to_respond": _r(r["mean_respond"]), "median_hours_to_respond": _r(r["median_respond"]),
        "mean_hours_to_assign": _r(r["mean_assign"]),
        "mean_hours_to_resolve": _r(r["mean_resolve"]), "median_hours_to_resolve": _r(r["median_resolve"]),
        "first_touch_resolution_pct": _rate(r["first_touch"], r["resolved"]),
        "sla_met_pct": _rate(r["sla_met"], r["sla_judged"]),
    }


async def compute(db, tenant_id: uuid.UUID, days: int = 30, assignee: Optional[uuid.UUID] = None) -> dict:
    days = max(1, min(int(days), MAX_DAYS))
    p = {"t": str(tenant_id), "d": days, "a": str(assignee) if assignee else None}
    scope = "tenant_id = CAST(:t AS uuid) AND created_at >= now() - make_interval(days => :d)" \
            + (" AND assigned_to = CAST(:a AS uuid)" if assignee else "")

    overall = (await db.execute(text(f"SELECT {_METRICS} FROM tickets WHERE {scope}"), p)).mappings().one()

    now_state = (await db.execute(text(f"""
        SELECT count(*) FILTER (WHERE status NOT IN ('RESOLVED', 'CLOSED')) AS open_now,
               count(*) FILTER (WHERE status NOT IN ('RESOLVED', 'CLOSED') AND assigned_to IS NULL) AS unassigned_now,
               count(*) FILTER (WHERE status = 'ESCALATED') AS escalated_now,
               count(*) FILTER (WHERE status NOT IN ('RESOLVED', 'CLOSED') AND sla_due_at IS NOT NULL
                                  AND sla_due_at < now()) AS overdue_now,
               count(*) FILTER (WHERE {_STALE_SQL}) AS stale_now
          FROM tickets WHERE tenant_id = CAST(:t AS uuid)"""), p)).mappings().one()

    by_assignee = (await db.execute(text(f"""
        SELECT a.*, COALESCE(NULLIF(u.full_name, ''), split_part(u.email, '@', 1)) AS name
          FROM (SELECT assigned_to AS uid, assigned_to::text AS id, {_METRICS}
                  FROM tickets WHERE {scope} AND assigned_to IS NOT NULL
                 GROUP BY assigned_to ORDER BY count(*) DESC LIMIT 50) a
          LEFT JOIN users u ON u.id = a.uid ORDER BY a.opened DESC"""), p)).mappings().all()

    async def grouped(column: str) -> list[dict]:
        rows = (await db.execute(text(f"""
            SELECT COALESCE({column}, 'none') AS key, {_METRICS} FROM tickets WHERE {scope}
             GROUP BY 1 ORDER BY count(*) DESC"""), p)).mappings().all()
        return [{"key": r["key"], **_shape(r)} for r in rows]

    stages = (await db.execute(text("""
        WITH s AS (
            SELECT e.ticket_id, e.to_value AS status, e.created_at AS at,
                   LEAD(e.created_at) OVER (PARTITION BY e.ticket_id ORDER BY e.created_at, e.id) AS until
              FROM ticket_events e JOIN tickets t ON t.id = e.ticket_id
             WHERE e.tenant_id = CAST(:t AS uuid) AND t.created_at >= now() - make_interval(days => :d)
               AND e.to_value IN ('OPEN', 'IN_PROGRESS', 'ESCALATED', 'ON_HOLD', 'PENDING', 'RESOLVED', 'CLOSED')
               AND e.event_type IN ('created', 'status_changed', 'escalated', 'resolved', 'closed', 'reopened'))
        SELECT status, count(DISTINCT ticket_id) AS tickets,
               avg(extract(epoch FROM (COALESCE(until, now()) - at)) / 3600.0) AS avg_hours
          FROM s WHERE status NOT IN ('RESOLVED', 'CLOSED') GROUP BY status ORDER BY avg_hours DESC"""), p)).mappings().all()

    return {
        "window_days": days,
        "assignee": str(assignee) if assignee else None,
        "overall": _shape(overall),
        "now": {k: int(v or 0) for k, v in now_state.items()},
        "by_assignee": [{"id": r["id"], "name": r["name"], **_shape(r)} for r in by_assignee],
        "by_queue": await grouped("queue"),
        "by_category": await grouped("category"),
        "time_in_stage": [{"status": r["status"], "tickets": r["tickets"], "avg_hours": _r(r["avg_hours"])} for r in stages],
    }


async def late_tickets(db, tenant_id: uuid.UUID, limit: int = 25) -> list[dict]:
    """Open tickets that are overdue or stale, worst first: the list an agent or the digest needs."""
    rows = (await db.execute(text(f"""
        SELECT id::text AS id, ticket_no, subject, priority, status, queue, category, assigned_to::text AS assigned_to,
               created_at, sla_due_at, COALESCE(last_activity_at, updated_at, created_at) AS last_activity,
               (sla_due_at IS NOT NULL AND sla_due_at < now()) AS overdue, {_STALE_SQL} AS stale
          FROM tickets WHERE tenant_id = CAST(:t AS uuid) AND status NOT IN ('RESOLVED', 'CLOSED')
           AND ((sla_due_at IS NOT NULL AND sla_due_at < now()) OR {_STALE_SQL})
         ORDER BY (sla_due_at IS NOT NULL AND sla_due_at < now()) DESC, sla_due_at NULLS LAST, created_at
         LIMIT :n"""), {"t": str(tenant_id), "n": max(1, min(int(limit), 200))})).mappings().all()
    now = datetime.now(timezone.utc)
    out = []
    for r in rows:
        due = _aware(r["sla_due_at"])
        out.append({
            "id": r["id"], "ref": f"T-{r['ticket_no']}" if r["ticket_no"] else None, "subject": r["subject"],
            "priority": r["priority"], "status": r["status"], "queue": r["queue"], "category": r["category"],
            "assigned_to": r["assigned_to"], "overdue": bool(r["overdue"]), "stale": bool(r["stale"]),
            "hours_overdue": round((now - due).total_seconds() / 3600.0, 1) if due and now > due else 0.0,
            "hours_idle": hours_between(r["last_activity"], now),
            "age_hours": hours_between(r["created_at"], now),
        })
    return out
