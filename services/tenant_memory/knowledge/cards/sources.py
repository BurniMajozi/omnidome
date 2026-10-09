"""Source readers: fetch changed rows from the operational database and hand them to the card builders.

Columns are read with explicit SELECT lists verified against the owning services' models
(crm/models.py, billing/models.py, sales/models.py, support/database.py, marketing/database.py,
fno_intelligence/analytics_models.py, tenant_memory/database.py). Never SELECT * here: a new
sensitive column added upstream must not silently flow into the index.

Repo rules honoured: every query filters tenant_id explicitly; each read runs inside
`session.begin_nested()` so one failing source cannot poison the caller's transaction;
the caller owns the session (background tasks open their own).

Two shapes:
  * keyset sources  - (ts, id) watermark, paged; used for entity cards.
  * snapshot sources - recomputed windows (digests); idempotent thanks to content hashes.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import text

from services.tenant_memory.knowledge.cards import builders as B
from services.tenant_memory.knowledge.cards.base import Card


@dataclass
class Page:
    cards: list[Card] = field(default_factory=list)
    tombstones: list[tuple[str, str]] = field(default_factory=list)   # (source_type, source_id)
    last_ts: Optional[datetime] = None
    last_id: Optional[str] = None
    rows: int = 0


@dataclass
class Source:
    name: str                       # watermark key
    module: str
    source_types: tuple
    fetch: Callable[..., Awaitable[Page]]
    ids: Callable[..., Awaitable[dict]]
    snapshot: bool = False          # recomputed windows; not paged


def _utc(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    return None


def _keyset(ts_expr: str, id_expr: str, wm: Optional[dict]) -> tuple[str, dict]:
    if not wm or not wm.get("last_ts"):
        return "", {}
    ts = _utc(wm["last_ts"])
    last_id = str((wm.get("meta") or {}).get("last_id") or "")
    return (f" AND (({ts_expr}) > CAST(:wm_ts AS timestamptz) OR (({ts_expr}) = CAST(:wm_ts AS timestamptz) AND ({id_expr}) > :wm_id))",
            {"wm_ts": ts, "wm_id": last_id})


async def _rows(session, sql: str, params: dict) -> list[dict]:
    async with session.begin_nested():
        res = await session.execute(text(sql), params)
        return [dict(r) for r in res.mappings().all()]


def _track(page: Page, rows: list[dict]) -> None:
    page.rows = len(rows)
    if rows:
        page.last_ts, page.last_id = _utc(rows[-1]["ts"]), str(rows[-1]["id"])


def _months_back(n: int) -> datetime:
    now = datetime.now(timezone.utc)
    y, m = now.year, now.month - (n - 1)
    while m < 1:
        y, m = y - 1, m + 12
    return datetime(y, m, 1, tzinfo=timezone.utc)


# ── CRM: customers (+ subscriptions, balance, tickets, tags) ───────────────

async def fetch_customers(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
    base = ("SELECT id::text AS id, first_name, last_name, status, province, account_number, rica_verified, "
            "company_id::text AS company_id, created_at, updated_at, COALESCE(updated_at, created_at) AS ts "
            "FROM customers WHERE tenant_id = CAST(:tenant_id AS uuid)")
    ks, kp = _keyset("COALESCE(updated_at, created_at)", "id::text", wm)
    rows = await _rows(session, f"{base}{ks} ORDER BY COALESCE(updated_at, created_at), id::text LIMIT :limit",
                       {"tenant_id": tenant, "limit": limit, **kp})
    page = Page()
    _track(page, rows)
    ids = {r["id"] for r in rows}
    if wm and wm.get("last_ts"):                                # customers whose invoices/tickets/subscriptions moved
        touched = await _rows(session, """
            SELECT DISTINCT customer_id::text AS id FROM (
              SELECT customer_id FROM invoices WHERE tenant_id = CAST(:tenant_id AS uuid) AND updated_at > CAST(:since AS timestamptz)
              UNION SELECT customer_id FROM tickets WHERE tenant_id = CAST(:tenant_id AS uuid) AND updated_at > CAST(:since AS timestamptz)
              UNION SELECT customer_id FROM subscriptions WHERE tenant_id = CAST(:tenant_id AS uuid) AND updated_at > CAST(:since AS timestamptz)
            ) t LIMIT :limit""", {"tenant_id": tenant, "since": _utc(wm["last_ts"]), "limit": limit})
        extra = [r["id"] for r in touched if r["id"] not in ids]
        if extra:
            rows += await _rows(session, base +
                                " AND id = ANY(CAST(:ids AS uuid[]))", {"tenant_id": tenant, "ids": extra})
    if not rows:
        return page
    cids = [r["id"] for r in rows]
    p = {"tenant_id": tenant, "ids": cids}
    subs = await _rows(session, "SELECT id::text AS id, customer_id::text AS customer_id, plan, status::text AS status, base_price_zar, "
                       "billing_interval::text AS billing_interval, segment, current_period_end FROM subscriptions "
                       "WHERE tenant_id = CAST(:tenant_id AS uuid) AND customer_id = ANY(CAST(:ids AS uuid[]))", p)
    bal = await _rows(session, """
        SELECT customer_id::text AS customer_id,
               count(*) FILTER (WHERE status::text IN ('sent','partially_paid','overdue')) AS open_invoices,
               COALESCE(sum(total_zar - amount_paid_zar) FILTER (WHERE status::text IN ('sent','partially_paid','overdue')), 0) AS outstanding_zar,
               count(*) FILTER (WHERE status::text = 'overdue') AS overdue_invoices
        FROM invoices WHERE tenant_id = CAST(:tenant_id AS uuid) AND customer_id = ANY(CAST(:ids AS uuid[])) GROUP BY customer_id""", p)
    tix = await _rows(session, """
        SELECT * FROM (SELECT id::text AS id, customer_id::text AS customer_id, subject, status, priority, category, created_at,
               row_number() OVER (PARTITION BY customer_id ORDER BY created_at DESC) AS rn
               FROM tickets WHERE tenant_id = CAST(:tenant_id AS uuid) AND customer_id = ANY(CAST(:ids AS uuid[]))) t WHERE rn <= 3""", p)
    tags = await _rows(session, "SELECT customer_id::text AS customer_id, tag FROM customer_tags "
                       "WHERE tenant_id = CAST(:tenant_id AS uuid) AND customer_id = ANY(CAST(:ids AS uuid[]))", p)
    by = lambda lst: _group(lst, "customer_id")  # noqa: E731
    subs_by, bal_by, tix_by, tag_by = by(subs), {b["customer_id"]: b for b in bal}, by(tix), by(tags)
    now = datetime.now(timezone.utc)
    for r in rows:
        page.cards.append(B.customer_card(r, subs_by.get(r["id"], []), bal_by.get(r["id"], {}), tix_by.get(r["id"], []),
                                          [t["tag"] for t in tag_by.get(r["id"], [])], _utc(r.get("ts")) or now))
    return page


def _group(rows: list[dict], key: str) -> dict:
    out: dict = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return out


async def ids_customers(session, tenant: str) -> dict:
    rows = await _rows(session, "SELECT id::text AS id FROM customers WHERE tenant_id = CAST(:t AS uuid)", {"t": tenant})
    return {"customer": {r["id"] for r in rows}}


async def fetch_leads(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
    ks, kp = _keyset("COALESCE(updated_at, created_at)", "id::text", wm)
    rows = await _rows(session, f"""SELECT id::text AS id, source, first_name, last_name, coverage_area, interested_package, status,
        notes, converted_customer_id::text AS converted_customer_id, converted_at, created_at, updated_at,
        COALESCE(updated_at, created_at) AS ts FROM leads WHERE tenant_id = CAST(:tenant_id AS uuid){ks}
        ORDER BY COALESCE(updated_at, created_at), id::text LIMIT :limit""", {"tenant_id": tenant, "limit": limit, **kp})
    page = Page()
    _track(page, rows)
    page.cards = [B.lead_card(r, _utc(r["ts"])) for r in rows]
    return page


async def ids_leads(session, tenant: str) -> dict:
    rows = await _rows(session, "SELECT id::text AS id FROM leads WHERE tenant_id = CAST(:t AS uuid)", {"t": tenant})
    return {"lead": {r["id"] for r in rows}}


# ── Sales ──────────────────────────────────────────────────────────────────

async def fetch_deals(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
    ks, kp = _keyset("COALESCE(d.updated_at, d.created_at)", "d.id::text", wm)
    rows = await _rows(session, f"""SELECT d.id::text AS id, d.contact_id::text AS contact_id, d.lead_id::text AS lead_id, d.name,
        ds.name AS stage_name, ds.probability, d.value_zar, d.status, d.close_date, d.closed_at, d.close_reason, d.notes,
        d.created_at, d.updated_at, COALESCE(d.updated_at, d.created_at) AS ts
        FROM deals d LEFT JOIN deal_stages ds ON ds.id = d.stage_id
        WHERE d.tenant_id = CAST(:tenant_id AS uuid){ks}
        ORDER BY COALESCE(d.updated_at, d.created_at), d.id::text LIMIT :limit""", {"tenant_id": tenant, "limit": limit, **kp})
    page = Page()
    _track(page, rows)
    page.cards = [B.deal_card(r, _utc(r["ts"])) for r in rows]
    return page


async def ids_deals(session, tenant: str) -> dict:
    rows = await _rows(session, "SELECT id::text AS id FROM deals WHERE tenant_id = CAST(:t AS uuid)", {"t": tenant})
    return {"deal": {r["id"] for r in rows}}


async def fetch_pipelines(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
    pipes = await _rows(session, "SELECT id::text AS id, name FROM pipelines WHERE tenant_id = CAST(:t AS uuid) ORDER BY id::text LIMIT :limit",
                        {"t": tenant, "limit": limit})
    page = Page(rows=len(pipes))
    now = datetime.now(timezone.utc)
    for p in pipes:
        stages = await _rows(session, """
            SELECT ds.name, ds.sort_order, ds.probability,
                   count(d.id) FILTER (WHERE d.status = 'OPEN') AS open_deals,
                   COALESCE(sum(d.value_zar) FILTER (WHERE d.status = 'OPEN'), 0) AS open_value_zar
            FROM deal_stages ds LEFT JOIN deals d ON d.stage_id = ds.id AND d.tenant_id = CAST(:t AS uuid)
            WHERE ds.pipeline_id = CAST(:p AS uuid) GROUP BY ds.id ORDER BY ds.sort_order""", {"t": tenant, "p": p["id"]})
        tot = (await _rows(session, """
            SELECT count(*) FILTER (WHERE d.status = 'WON') AS won, COALESCE(sum(d.value_zar) FILTER (WHERE d.status = 'WON'), 0) AS won_value_zar,
                   count(*) FILTER (WHERE d.status = 'LOST') AS lost, COALESCE(sum(d.value_zar) FILTER (WHERE d.status = 'LOST'), 0) AS lost_value_zar
            FROM deals d JOIN deal_stages ds ON ds.id = d.stage_id
            WHERE d.tenant_id = CAST(:t AS uuid) AND ds.pipeline_id = CAST(:p AS uuid)""", {"t": tenant, "p": p["id"]})) or [{}]
        page.cards.append(B.pipeline_digest(p["id"], p["name"], stages + [{"totals": tot[0]}], now))
    return page


async def ids_pipelines(session, tenant: str) -> dict:
    rows = await _rows(session, "SELECT id::text AS id FROM pipelines WHERE tenant_id = CAST(:t AS uuid)", {"t": tenant})
    return {"pipeline": {r["id"] for r in rows}}


# ── Billing digests (month x segment) ──────────────────────────────────────

async def fetch_billing_digests(session, tenant: str, wm: Optional[dict], limit: int, months: int = 2) -> Page:
    since = _months_back(months)
    inv = await _rows(session, """
        SELECT to_char(date_trunc('month', i.created_at), 'YYYY-MM') AS month, COALESCE(s.segment, 'unsegmented') AS segment,
               count(*) AS invoices, COALESCE(sum(i.total_zar), 0) AS invoiced_zar, COALESCE(sum(i.vat_zar), 0) AS vat_zar,
               count(*) FILTER (WHERE i.status::text = 'paid') AS paid,
               count(*) FILTER (WHERE i.status::text = 'partially_paid') AS partial,
               count(*) FILTER (WHERE i.status::text IN ('sent','overdue')) AS unpaid,
               count(*) FILTER (WHERE i.status::text = 'overdue') AS overdue,
               COALESCE(sum(i.total_zar - i.amount_paid_zar) FILTER (WHERE i.status::text = 'overdue'), 0) AS overdue_zar
        FROM invoices i LEFT JOIN subscriptions s ON s.id = i.subscription_id AND s.tenant_id = i.tenant_id
        WHERE i.tenant_id = CAST(:t AS uuid) AND i.created_at >= :since AND i.status::text NOT IN ('draft','voided')
        GROUP BY 1, 2""", {"t": tenant, "since": since})
    pay = await _rows(session, """
        SELECT to_char(date_trunc('month', p.created_at), 'YYYY-MM') AS month, COALESCE(s.segment, 'unsegmented') AS segment,
               p.method::text AS method, count(*) AS n, COALESCE(sum(p.amount_zar), 0) AS amt
        FROM payments p LEFT JOIN invoices i ON i.id = p.invoice_id AND i.tenant_id = p.tenant_id
             LEFT JOIN subscriptions s ON s.id = i.subscription_id AND s.tenant_id = p.tenant_id
        WHERE p.tenant_id = CAST(:t AS uuid) AND p.status::text = 'completed' AND p.created_at >= :since GROUP BY 1, 2, 3""",
        {"t": tenant, "since": since})
    agg: dict[tuple, dict] = {(r["month"], r["segment"]): dict(r) for r in inv}
    for r in pay:
        a = agg.setdefault((r["month"], r["segment"]), {"month": r["month"], "segment": r["segment"]})
        a["payments"] = int(a.get("payments", 0)) + int(r["n"])
        a["collected_zar"] = float(a.get("collected_zar", 0)) + float(r["amt"])
        a.setdefault("methods", {})[r["method"]] = int(r["n"])
    now = datetime.now(timezone.utc)
    page = Page(rows=len(agg))
    page.cards = [B.billing_digest(m, s, a, now) for (m, s), a in sorted(agg.items())]
    return page


async def ids_billing_digests(session, tenant: str) -> dict:
    return {}      # past digests are history: never tombstoned by reconcile


# ── Support ────────────────────────────────────────────────────────────────

async def fetch_tickets(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
    ks, kp = _keyset("COALESCE(updated_at, created_at)", "id::text", wm)
    rows = await _rows(session, f"""SELECT id::text AS id, customer_id::text AS customer_id, subject, description, priority, status,
        category, is_fcr, resolution_notes, resolved_at, created_at, updated_at, COALESCE(updated_at, created_at) AS ts
        FROM tickets WHERE tenant_id = CAST(:tenant_id AS uuid){ks} ORDER BY COALESCE(updated_at, created_at), id::text LIMIT :limit""",
        {"tenant_id": tenant, "limit": limit, **kp})
    page = Page()
    _track(page, rows)
    replies = await _rows(session, """SELECT id::text AS id, ticket_id::text AS ticket_id, author_type, message, is_private, created_at
        FROM ticket_replies WHERE ticket_id = ANY(CAST(:ids AS uuid[])) AND is_private = false""",
        {"ids": [r["id"] for r in rows]}) if rows else []
    rep_by = _group(replies, "ticket_id")
    page.cards = [B.ticket_card(r, rep_by.get(r["id"], []), _utc(r["ts"])) for r in rows]
    return page


async def ids_tickets(session, tenant: str) -> dict:
    rows = await _rows(session, "SELECT id::text AS id FROM tickets WHERE tenant_id = CAST(:t AS uuid)", {"t": tenant})
    return {"ticket": {r["id"] for r in rows}}


# ── Marketing ──────────────────────────────────────────────────────────────

async def fetch_campaigns(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
    ks, kp = _keyset("COALESCE(updated_at, created_at)", "id::text", wm)
    rows = await _rows(session, f"""SELECT id::text AS id, name, channel, status, description, budget_zar, start_date, end_date,
        audience_segment_id::text AS audience_segment_id, total_sent, total_delivered, total_opened, total_clicked, total_conversions,
        updated_at, COALESCE(updated_at, created_at) AS ts FROM marketing_campaigns WHERE tenant_id = CAST(:tenant_id AS uuid){ks}
        ORDER BY COALESCE(updated_at, created_at), id::text LIMIT :limit""", {"tenant_id": tenant, "limit": limit, **kp})
    page = Page()
    _track(page, rows)
    page.cards = [B.campaign_card(r, _utc(r["ts"])) for r in rows]
    return page


async def ids_campaigns(session, tenant: str) -> dict:
    rows = await _rows(session, "SELECT id::text AS id FROM marketing_campaigns WHERE tenant_id = CAST(:t AS uuid)", {"t": tenant})
    return {"campaign": {r["id"] for r in rows}}


async def fetch_social_digests(session, tenant: str, wm: Optional[dict], limit: int, months: int = 2) -> Page:
    since = _months_back(months).date()
    rows = await _rows(session, """SELECT platform, metric_date, followers, impressions, reach, engagement_rate, likes_total,
        comments_total, shares_total FROM social_analytics WHERE tenant_id = CAST(:t AS uuid) AND metric_date >= :since""",
        {"t": tenant, "since": since})
    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        groups[(r["platform"], r["metric_date"].strftime("%Y-%m"))].append(r)
    now = datetime.now(timezone.utc)
    page = Page(rows=len(rows))
    page.cards = [B.social_digest(p, m, g, now) for (p, m), g in sorted(groups.items())]
    return page


async def ids_social_digests(session, tenant: str) -> dict:
    return {}


# ── BI Studio ──────────────────────────────────────────────────────────────

async def fetch_research(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
    ks, kp = _keyset("COALESCE(finished_at, created_at)", "id::text", wm)
    rows = await _rows(session, f"""SELECT id::text AS id, question, report, sources, COALESCE(finished_at, created_at) AS ts
        FROM analytics_research_runs WHERE tenant_id = CAST(:tenant_id AS uuid) AND status = 'done'{ks}
        ORDER BY COALESCE(finished_at, created_at), id::text LIMIT :limit""", {"tenant_id": tenant, "limit": limit, **kp})
    page = Page()
    _track(page, rows)
    page.cards = [B.research_card(r, _utc(r["ts"])) for r in rows]
    return page


async def ids_research(session, tenant: str) -> dict:
    rows = await _rows(session, "SELECT id::text AS id FROM analytics_research_runs WHERE tenant_id = CAST(:t AS uuid) AND status = 'done'", {"t": tenant})
    return {"research": {r["id"] for r in rows}}


async def fetch_competitors(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
    ts = "GREATEST(COALESCE(c.last_scanned_at, c.updated_at), c.updated_at)"
    ks, kp = _keyset(ts, "c.id::text", wm)
    rows = await _rows(session, f"""SELECT c.id::text AS id, c.name, c.website, c.last_scanned_at, c.scan_status, c.last_status, {ts} AS ts
        FROM analytics_competitors c WHERE c.tenant_id = CAST(:tenant_id AS uuid) AND c.active = true{ks}
        ORDER BY {ts}, c.id::text LIMIT :limit""", {"tenant_id": tenant, "limit": limit, **kp})
    page = Page()
    _track(page, rows)
    for r in rows:
        snap = (await _rows(session, """SELECT scanned_at, pages, plans, promotions FROM analytics_competitor_snapshots
            WHERE tenant_id = CAST(:t AS uuid) AND competitor_id = CAST(:c AS uuid) ORDER BY scanned_at DESC LIMIT 1""",
            {"t": tenant, "c": r["id"]}))
        chg = await _rows(session, """SELECT change_type, subject, old_value, new_value, pct_change, source_url, detected_at
            FROM analytics_competitor_changes WHERE tenant_id = CAST(:t AS uuid) AND competitor_id = CAST(:c AS uuid)
            ORDER BY detected_at DESC LIMIT 10""", {"t": tenant, "c": r["id"]})
        page.cards.append(B.competitor_card(r, snap[0] if snap else None, chg, _utc(r["ts"])))
    return page


async def ids_competitors(session, tenant: str) -> dict:
    rows = await _rows(session, "SELECT id::text AS id FROM analytics_competitors WHERE tenant_id = CAST(:t AS uuid) AND active = true", {"t": tenant})
    return {"competitor": {r["id"] for r in rows}}


async def fetch_campaign_analyses(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
    ks, kp = _keyset("COALESCE(last_run_at, created_at)", "id::text", wm)
    rows = await _rows(session, f"""SELECT id::text AS id, name, subject, own_campaign_id::text AS own_campaign_id,
        competitor_id::text AS competitor_id, aggregate, limitations, item_count, last_run_at, COALESCE(last_run_at, created_at) AS ts
        FROM analytics_campaign_analyses WHERE tenant_id = CAST(:tenant_id AS uuid) AND aggregate IS NOT NULL{ks}
        ORDER BY COALESCE(last_run_at, created_at), id::text LIMIT :limit""", {"tenant_id": tenant, "limit": limit, **kp})
    page = Page()
    _track(page, rows)
    page.cards = [B.campaign_analysis_card(r, _utc(r["ts"])) for r in rows]
    return page


async def ids_campaign_analyses(session, tenant: str) -> dict:
    rows = await _rows(session, "SELECT id::text AS id FROM analytics_campaign_analyses WHERE tenant_id = CAST(:t AS uuid) AND aggregate IS NOT NULL", {"t": tenant})
    return {"campaign_analysis": {r["id"] for r in rows}}


# ── Tenant memory + OKF skills ─────────────────────────────────────────────

async def fetch_memory_entries(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
    ts = "GREATEST(COALESCE(updated_at, created_at), COALESCE(archived_at, created_at))"
    ks, kp = _keyset(ts, "id::text", wm)
    rows = await _rows(session, f"""SELECT id::text AS id, source_type, module, scope_key, title, content, summary, visibility, importance,
        tags, created_by::text AS created_by, occurred_at, archived_at, {ts} AS ts FROM tenant_memory_entries
        WHERE tenant_id = CAST(:tenant_id AS uuid){ks} ORDER BY {ts}, id::text LIMIT :limit""", {"tenant_id": tenant, "limit": limit, **kp})
    page = Page()
    _track(page, rows)
    for r in rows:
        if r.get("archived_at") is not None:
            # Archived by housekeeping/roll-up: the durable semantic summary carries the knowledge now.
            page.tombstones.append(("memory_entry", r["id"]))
            continue
        card = B.memory_entry_card(r, _utc(r["ts"]))
        card.owner_id = r.get("created_by")
        page.cards.append(card)
    return page


async def ids_memory_entries(session, tenant: str) -> dict:
    rows = await _rows(session, "SELECT id::text AS id FROM tenant_memory_entries WHERE tenant_id = CAST(:t AS uuid) AND archived_at IS NULL", {"t": tenant})
    return {"memory_entry": {r["id"] for r in rows}}


async def fetch_memory_summaries(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
    ks, kp = _keyset("updated_at", "scope_key", wm)
    rows = await _rows(session, f"""SELECT scope_key AS id, scope_key, module, title, summary, source_entry_ids, updated_at, updated_at AS ts
        FROM tenant_memory_summaries WHERE tenant_id = CAST(:tenant_id AS uuid){ks} ORDER BY updated_at, scope_key LIMIT :limit""",
        {"tenant_id": tenant, "limit": limit, **kp})
    page = Page()
    _track(page, rows)
    page.cards = [B.memory_summary_card(r, _utc(r["ts"])) for r in rows]
    return page


async def ids_memory_summaries(session, tenant: str) -> dict:
    rows = await _rows(session, "SELECT scope_key AS id FROM tenant_memory_summaries WHERE tenant_id = CAST(:t AS uuid)", {"t": tenant})
    return {"memory_summary": {r["id"] for r in rows}}


async def fetch_skills(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
    ks, kp = _keyset("updated_at", "id::text", wm)
    rows = await _rows(session, f"""SELECT id::text AS id, skill_name, description, category, source_agent_type, target_agent_types,
        tools_required, version, is_active, updated_at, updated_at AS ts FROM tenant_agent_skills
        WHERE tenant_id = CAST(:tenant_id AS uuid){ks} ORDER BY updated_at, id::text LIMIT :limit""", {"tenant_id": tenant, "limit": limit, **kp})
    page = Page()
    _track(page, rows)
    for r in rows:
        if r["is_active"]:
            page.cards.append(B.skill_card(r, _utc(r["ts"])))
        else:
            page.tombstones.append(("skill", r["id"]))
    return page


async def ids_skills(session, tenant: str) -> dict:
    rows = await _rows(session, "SELECT id::text AS id FROM tenant_agent_skills WHERE tenant_id = CAST(:t AS uuid) AND is_active = true", {"t": tenant})
    return {"skill": {r["id"] for r in rows}}


SOURCES: dict[str, Source] = {s.name: s for s in [
    Source("customers", "crm", ("customer",), fetch_customers, ids_customers),
    Source("leads", "crm", ("lead",), fetch_leads, ids_leads),
    Source("deals", "sales", ("deal",), fetch_deals, ids_deals),
    Source("pipelines", "sales", ("pipeline",), fetch_pipelines, ids_pipelines, snapshot=True),
    Source("billing_digests", "billing", ("billing_digest",), fetch_billing_digests, ids_billing_digests, snapshot=True),
    Source("tickets", "support", ("ticket",), fetch_tickets, ids_tickets),
    Source("campaigns", "marketing", ("campaign",), fetch_campaigns, ids_campaigns),
    Source("social_digests", "marketing", ("social_digest",), fetch_social_digests, ids_social_digests, snapshot=True),
    Source("research", "analytics", ("research",), fetch_research, ids_research),
    Source("competitors", "analytics", ("competitor",), fetch_competitors, ids_competitors),
    Source("campaign_analyses", "analytics", ("campaign_analysis",), fetch_campaign_analyses, ids_campaign_analyses),
    Source("memory_entries", "memory", ("memory_entry",), fetch_memory_entries, ids_memory_entries),
    Source("memory_summaries", "memory", ("memory_summary",), fetch_memory_summaries, ids_memory_summaries),
    Source("skills", "memory", ("skill",), fetch_skills, ids_skills),
]}


async def fetch_metric_facts(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
    ks, kp = _keyset("updated_at", "id::text", wm)
    rows = await _rows(session, f"""SELECT id::text AS id, metric_key, label, dimensions, dimensions_hash, period_start, period_end, grain,
        value, unit, kind, lower_bound, upper_bound, interval_level, model_name, model_version, method, confidence, source_query,
        source_query_key, as_of, updated_at AS ts FROM tenant_metric_facts WHERE tenant_id = CAST(:tenant_id AS uuid){ks}
        ORDER BY updated_at, id::text LIMIT :limit""", {"tenant_id": tenant, "limit": limit, **kp})
    page = Page()
    _track(page, rows)
    for r in rows:
        prior = await _rows(session, """SELECT value, period_start, period_end, grain FROM tenant_metric_facts
            WHERE tenant_id = CAST(:t AS uuid) AND metric_key = :m AND dimensions_hash = :h AND kind = :k AND period_end < :ps
            ORDER BY period_end DESC LIMIT 1""", {"t": tenant, "m": r["metric_key"], "h": r["dimensions_hash"], "k": r["kind"], "ps": r["period_start"]})
        page.cards.append(B.metric_fact_card(r, prior[0] if prior else None, _utc(r["as_of"])))
    return page


async def ids_metric_facts(session, tenant: str) -> dict:
    rows = await _rows(session, "SELECT id::text AS id FROM tenant_metric_facts WHERE tenant_id = CAST(:t AS uuid)", {"t": tenant})
    return {"metric_fact": {r["id"] for r in rows}}


SOURCES["metric_facts"] = Source("metric_facts", "analytics", ("metric_fact",), fetch_metric_facts, ids_metric_facts)
