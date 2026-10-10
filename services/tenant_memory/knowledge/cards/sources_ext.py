"""Source readers for the broad-coverage knowledge sources.

Every table/column below was verified against the owning service's ORM model (and, for tables that also exist in
config/master_schema.sql with an older shape - iot_devices, inventory_*, rica_verifications, employees, journal_entries,
knowledge_base - only columns present in BOTH shapes or added by that service's startup migration are used):

  compliance/database.py (String tenant_id, naive timestamps)   hr/database.py            network/models.py
  iot/models.py (+iot/database.py column migration)              rica/database.py          customer_journey/models.py (rica_flows)
  inventory/database.py (+inventory/schema.py migration)         finance/database.py      billing/models.py
  call_center/database.py (+_ALTERS migration)                   lifecycle/models.py      journey_engine/models.py
  retention/batch_churn.py                                       portal_builder/main.py   marketing/database.py
  config/master_schema.sql (knowledge_base)

Rules (same as sources.py): explicit SELECT lists (never `*`) so a new sensitive column cannot flow into the index; explicit
tenant filter on every query and every join; each read inside `begin_nested()` (via `sources._rows`); a table that does not
exist yet (service never started) yields an empty page instead of an error, and reconcile REFUSES to run against a missing table
(so a not-yet-created table can never tombstone indexed cards).

Two shapes, as in sources.py: keyset sources (paged by (updated_at, id)) and snapshot sources (recomputed windows).
Sources run one at a time (Indexer.run_tenant) in small pages (INDEX_BATCH_SIZE); each enrichment query is bounded by the page.
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from services.tenant_memory.knowledge.cards import builders_ext as X
from services.tenant_memory.knowledge.cards import sources as S
from services.tenant_memory.knowledge.cards.sources import Page, Source

Build = Callable[[dict, dict, Optional[datetime]], Optional[Any]]


async def table_exists(session, table: str) -> bool:
    rows = await S._rows(session, "SELECT to_regclass(CAST(:n AS text)) IS NOT NULL AS ok", {"n": table})
    return bool(rows and rows[0].get("ok"))


def keyset_source(name: str, module: str, stype: str, *, probe: str, frm: str, select: str, ts: str, build: Build,
                  tenant_kind: str = "uuid", naive_ts: bool = False, where: str = "", live: str = "",
                  enrich: Optional[Callable[..., Awaitable[dict]]] = None, idx: str = "t.id::text") -> Source:
    """A paged (ts, id) keyset source over one main table (`t`). `build` returns a Card, or None to tombstone the row.
    `where` restricts the rows considered at all; `live` additionally restricts which rows have a card (used by reconcile)."""
    tcond = "t.tenant_id = CAST(:tenant_id AS uuid)" if tenant_kind == "uuid" else "t.tenant_id = :tenant_id"
    tsx = f"(({ts}) AT TIME ZONE 'UTC')" if naive_ts else f"({ts})"
    extra = f" AND ({where})" if where else ""
    live_sql = f" AND ({live})" if live else ""

    async def fetch(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
        if not await table_exists(session, probe):
            return Page()
        ks, kp = S._keyset(tsx, idx, wm)
        rows = await S._rows(session, f"SELECT {select}, {tsx} AS ts, {idx} AS id FROM {frm} WHERE {tcond}{extra}{ks} "
                                      f"ORDER BY {tsx}, {idx} LIMIT :limit", {"tenant_id": tenant, "limit": limit, **kp})
        page = Page()
        S._track(page, rows)
        ctx = await enrich(session, tenant, rows) if (enrich and rows) else {}
        for r in rows:
            card = build(r, ctx, S._utc(r["ts"]))
            if card is None:
                page.tombstones.append((stype, str(r["id"])))
            else:
                page.cards.append(card)
        return page

    async def ids(session, tenant: str) -> dict:
        if not await table_exists(session, probe):
            raise RuntimeError(f"table {probe} does not exist; refusing to reconcile {name}")
        rows = await S._rows(session, f"SELECT {idx} AS id FROM {frm} WHERE {tcond}{extra}{live_sql}", {"tenant_id": tenant})
        return {stype: {r["id"] for r in rows}}

    return Source(name, module, (stype,), fetch, ids)


def snapshot_source(name: str, module: str, stype: str, fn: Callable[..., Awaitable[list]], ids_fn: Optional[Callable[..., Awaitable[dict]]] = None) -> Source:
    async def fetch(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
        cards = await fn(session, tenant)
        page = Page(rows=len(cards))
        page.cards = [c for c in cards if c is not None]
        return page

    async def ids(session, tenant: str) -> dict:
        return await ids_fn(session, tenant) if ids_fn else {}      # history digests are never tombstoned by reconcile

    return Source(name, module, (stype,), fetch, ids, snapshot=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _months(env: str = "KNOWLEDGE_DIGEST_MONTHS", default: int = 3) -> int:
    try:
        return max(1, min(24, int(os.getenv(env, str(default)))))
    except ValueError:
        return default


async def _guarded(session, tenant: str, tables: list[str], sql: str, params: Optional[dict] = None) -> list[dict]:
    """Run an aggregate only when every table it touches exists; otherwise nothing (the service never started)."""
    for t in tables:
        if not await table_exists(session, t):
            return []
    return await S._rows(session, sql, {"t": tenant, **(params or {})})


# ═══ Compliance ═══════════════════════════════════════════════════════════════════════════════════════════════════

def _compliance(name: str, stype: str, table: str, select: str, build: Build, **kw) -> Source:
    return keyset_source(name, "compliance", stype, probe=table, frm=f"{table} t", select=select,
                         ts="COALESCE(t.updated_at, t.created_at)", build=build, tenant_kind="text", naive_ts=True, **kw)


COMPLIANCE_SOURCES = [
    _compliance("compliance_documents", "compliance_document", "compliance_documents",
                "t.title, t.document_type::text AS document_type, t.mime_type, t.contract_id, t.ocr_text, t.financial_summary, t.tags, "
                "t.version, t.is_confidential, t.created_at, t.updated_at", lambda r, c, a: X.compliance_document_card(r, a)),
    _compliance("compliance_obligations", "compliance_obligation", "compliance_obligations",
                "t.category::text AS category, t.title, t.description, t.regulatory_reference, t.frequency, t.due_date, t.status::text AS status, "
                "t.responsible_department, t.evidence_required, t.notes, t.updated_at", lambda r, c, a: X.compliance_obligation_card(r, a)),
    _compliance("compliance_cipc", "cipc_filing", "compliance_cipc_filings",
                "t.filing_type, t.financial_year_end, t.status, t.due_date, t.filed_date, t.fee_amount, t.fee_paid, t.notes, t.updated_at",
                lambda r, c, a: X.cipc_filing_card(r, a)),
    _compliance("compliance_tax_returns", "tax_return", "compliance_tax_returns",
                "t.tax_type::text AS tax_type, t.period_start, t.period_end, t.status::text AS status, t.amount_payable, t.amount_refund, "
                "t.submission_date, t.sars_assessment_date, t.payment_date, t.notes, t.updated_at", lambda r, c, a: X.tax_return_card(r, a)),
    _compliance("compliance_tax_registrations", "tax_registration", "compliance_tax_registrations",
                "t.tax_type::text AS tax_type, t.status, t.registered_date, t.last_filed, t.next_due, t.notes, t.updated_at",
                lambda r, c, a: X.tax_registration_card(r, a)),
    keyset_source("compliance_emp201", "compliance", "emp201", probe="compliance_emp201_workpapers", frm="compliance_emp201_workpapers t",
                  select="t.period, t.status, t.due_date, t.employee_count, t.gross_remuneration, t.paye, t.uif_employee, t.uif_employer, t.sdl, "
                         "t.total_liability, t.rates_verified, t.filed_at",
                  ts="COALESCE(t.marked_filed_at, t.prepared_at, TIMESTAMP '1970-01-01')", tenant_kind="text", naive_ts=True,
                  build=lambda r, c, a: X.emp201_card(r, a)),
    _compliance("compliance_breaches", "compliance_breach", "compliance_breach_register",
                "t.title, t.category::text AS category, t.severity, t.status, t.identified_date, t.reported_date, t.resolved_date, t.description, "
                "t.root_cause, t.corrective_action, t.icasa_notified, t.popi_commission_notified, t.financial_impact, t.updated_at",
                lambda r, c, a: X.breach_card(r, a)),
]


async def _consents(session, tenant: str) -> list:
    rows = await _guarded(session, tenant, ["compliance_popi_consent_records"], """
        SELECT left(COALESCE(NULLIF(t.purpose, ''), 'unspecified'), 120) AS purpose, count(*) AS total,
               count(*) FILTER (WHERE t.consent_given AND t.withdrawal_date IS NULL) AS granted,
               count(*) FILTER (WHERE t.withdrawal_date IS NOT NULL) AS withdrawn,
               count(*) FILTER (WHERE t.expiry_date IS NOT NULL AND t.expiry_date < now() AT TIME ZONE 'UTC') AS expired
        FROM compliance_popi_consent_records t WHERE t.tenant_id = :t GROUP BY 1""")
    return [X.consent_digest_card(rows, _now())] if rows else []


COMPLIANCE_SOURCES.append(snapshot_source("compliance_consents", "compliance", "consent_digest", _consents))


# ═══ HR (org facts only) ══════════════════════════════════════════════════════════════════════════════════════════

async def _hr_org(session, tenant: str) -> list:
    rows = await _guarded(session, tenant, ["employees"], """
        SELECT COALESCE(NULLIF(e.department, ''), 'Unassigned') AS department, COALESCE(NULLIF(e.job_title, ''), 'Untitled') AS job_title,
               count(*) AS headcount
        FROM employees e WHERE e.tenant_id = CAST(:t AS uuid) AND upper(COALESCE(e.status, 'ACTIVE')) = 'ACTIVE' GROUP BY 1, 2""")
    return [X.hr_org_digest_card(rows, _now())] if rows else []


async def _course_stats(session, tenant: str, rows: list[dict]) -> dict:
    if not await table_exists(session, "training_enrollments"):
        return {}
    st = await S._rows(session, """
        SELECT en.course_id::text AS course_id, count(*) AS enrolled, count(*) FILTER (WHERE upper(en.status) = 'COMPLETED') AS completed
        FROM training_enrollments en WHERE en.tenant_id = CAST(:t AS uuid) AND en.course_id = ANY(CAST(:ids AS uuid[])) GROUP BY 1""",
                       {"t": tenant, "ids": [r["id"] for r in rows]})
    return {s["course_id"]: s for s in st}


HR_SOURCES = [
    snapshot_source("hr_org", "hr", "hr_org", _hr_org),
    keyset_source("hr_training", "hr", "training_course", probe="training_courses", frm="training_courses t",
                  select="t.title, t.description, t.category, t.duration_hours, t.mandatory, t.status, t.updated_at",
                  ts="COALESCE(t.updated_at, t.created_at)", live="upper(t.status) <> 'ARCHIVED'", enrich=_course_stats,
                  build=lambda r, c, a: None if str(r.get("status") or "").upper() == "ARCHIVED" else X.training_course_card(r, c.get(r["id"], {}), a)),
    keyset_source("hr_company_kpi", "hr", "company_kpi", probe="company_kpi_configs", frm="company_kpi_configs t",
                  select="t.fiscal_year, t.sales_budget_zar, t.sales_actual_zar, t.cost_budget_zar, t.cost_actual_zar, t.profit_budget_zar, "
                         "t.profit_actual_zar, t.values_weight_pct, t.values_description, t.updated_at",
                  ts="COALESCE(t.updated_at, t.created_at)", build=lambda r, c, a: X.company_kpi_card(r, a)),
]


# ═══ Network / IoT / RICA ═════════════════════════════════════════════════════════════════════════════════════════

async def _sla_digests(session, tenant: str) -> list:
    since = S._months_back(_months())
    br = await _guarded(session, tenant, ["network_sla_breaches"], """
        SELECT to_char(date_trunc('month', b.started_at), 'YYYY-MM') AS month, b.metric_type::text AS metric_type, b.severity::text AS severity,
               count(*) AS breaches, count(*) FILTER (WHERE b.resolved_at IS NOT NULL) AS resolved, COALESCE(avg(b.duration_seconds), 0) AS avg_seconds
        FROM network_sla_breaches b WHERE b.tenant_id = CAST(:t AS uuid) AND b.started_at >= :since GROUP BY 1, 2, 3""", {"since": since})
    fno = await _guarded(session, tenant, ["fno_sla_measurements"], """
        SELECT to_char(date_trunc('month', m.period_start), 'YYYY-MM') AS month, m.fno_provider::text AS fno_provider, m.metric::text AS metric,
               count(*) AS measurements, count(*) FILTER (WHERE m.is_breach) AS breach_count, COALESCE(sum(m.penalty_applied_zar), 0) AS penalty_zar
        FROM fno_sla_measurements m WHERE m.tenant_id = CAST(:t AS uuid) AND m.period_start >= :since GROUP BY 1, 2, 3""", {"since": since})
    months = sorted({r["month"] for r in br} | {r["month"] for r in fno})
    now = _now()
    return [X.sla_digest_card(m, [r for r in br if r["month"] == m], [r for r in fno if r["month"] == m], now) for m in months]


async def _incident_digests(session, tenant: str) -> list:
    rows = await _guarded(session, tenant, ["network_notifications"], """
        SELECT to_char(date_trunc('month', n.created_at), 'YYYY-MM') AS month, n.trigger_type::text AS trigger_type, n.severity::text AS severity,
               count(*) AS notifications, count(*) FILTER (WHERE n.error_message IS NOT NULL) AS failed
        FROM network_notifications n WHERE n.tenant_id = CAST(:t AS uuid) AND n.created_at >= :since GROUP BY 1, 2, 3""",
                          {"since": S._months_back(_months())})
    now = _now()
    return [X.incident_digest_card(m, [r for r in rows if r["month"] == m], now) for m in sorted({r["month"] for r in rows})]


async def _fleet(session, tenant: str) -> list:
    net = await _guarded(session, tenant, ["network_devices"], """
        SELECT d.device_type::text AS device_type, d.manufacturer, d.model, d.status::text AS status, count(*) AS devices,
               count(*) FILTER (WHERE d.last_seen IS NULL OR d.last_seen < now() - interval '24 hours') AS silent_24h
        FROM network_devices d WHERE d.tenant_id = CAST(:t AS uuid) GROUP BY 1, 2, 3, 4""")
    iot = await _guarded(session, tenant, ["iot_devices"], """
        SELECT d.device_type::text AS device_type, d.status::text AS status, count(*) AS devices,
               count(*) FILTER (WHERE d.last_seen IS NULL OR d.last_seen < now() - interval '24 hours') AS silent_24h
        FROM iot_devices d WHERE d.tenant_id = CAST(:t AS uuid) GROUP BY 1, 2""")
    return [X.fleet_digest_card(net, iot, _now())] if (net or iot) else []


async def _rica_digests(session, tenant: str) -> list:
    since = S._months_back(_months())
    ver = await _guarded(session, tenant, ["rica_verifications"], """
        SELECT to_char(date_trunc('month', r.created_at), 'YYYY-MM') AS month, r.verification_type::text AS verification_type, r.status::text AS status,
               count(*) AS verifications
        FROM rica_verifications r WHERE r.tenant_id = CAST(:t AS uuid) AND r.created_at >= :since GROUP BY 1, 2, 3""", {"since": since})
    flows = await _guarded(session, tenant, ["rica_flows"], """
        SELECT to_char(date_trunc('month', f.created_at), 'YYYY-MM') AS month, f.status::text AS status, f.trigger_source::text AS trigger_source,
               count(*) AS flows
        FROM rica_flows f WHERE f.tenant_id = CAST(:t AS uuid) AND f.created_at >= :since GROUP BY 1, 2, 3""", {"since": since})
    now = _now()
    months = sorted({r["month"] for r in ver} | {r["month"] for r in flows})
    return [X.rica_digest_card(m, [r for r in ver if r["month"] == m], [r for r in flows if r["month"] == m], now) for m in months]


NETWORK_SOURCES = [
    keyset_source("network_services", "network", "network_service", probe="network_services", frm="network_services t",
                  select="t.customer_id::text AS customer_id, t.service_reference, t.description, t.status::text AS status, "
                         "t.technology::text AS technology, t.fno_provider::text AS fno_provider, t.download_speed_mbps, t.upload_speed_mbps, "
                         "t.speed_profile_name, t.city, t.province, t.activated_at, t.suspended_at, t.terminated_at, t.updated_at",
                  ts="COALESCE(t.updated_at, t.created_at)", build=lambda r, c, a: X.network_service_card(r, a)),
    snapshot_source("network_sla_digests", "network", "sla_digest", _sla_digests),
    snapshot_source("network_incident_digests", "network", "incident_digest", _incident_digests),
    snapshot_source("network_fleet", "network", "fleet_digest", _fleet),
    snapshot_source("rica_digests", "network", "rica_digest", _rica_digests),
]


# ═══ Inventory ════════════════════════════════════════════════════════════════════════════════════════════════════

async def _package_items(session, tenant: str, rows: list[dict]) -> dict:
    items = await S._rows(session, """
        SELECT i.package_id::text AS package_id, i.product_id::text AS product_id, i.quantity, i.is_required, i.sort_order, p.name AS product_name
        FROM inventory_package_items i
        JOIN inventory_packages pk ON pk.id = i.package_id AND pk.tenant_id = CAST(:t AS uuid)
        LEFT JOIN inventory_products p ON p.id = i.product_id AND p.tenant_id = pk.tenant_id
        WHERE i.package_id = ANY(CAST(:ids AS uuid[]))""", {"t": tenant, "ids": [r["id"] for r in rows]})
    return S._group(items, "package_id")


async def _supplier_stats(session, tenant: str, rows: list[dict]) -> dict:
    st = await S._rows(session, """
        SELECT po.supplier_id::text AS supplier_id, count(*) AS pos,
               count(*) FILTER (WHERE po.status::text NOT IN ('received', 'cancelled', 'rejected')) AS open_pos, COALESCE(sum(po.total_zar), 0) AS total_zar
        FROM inventory_purchase_orders po WHERE po.tenant_id = CAST(:t AS uuid) AND po.supplier_id = ANY(CAST(:ids AS uuid[])) GROUP BY 1""",
                       {"t": tenant, "ids": [r["id"] for r in rows]})
    return {s["supplier_id"]: s for s in st}


async def _po_items(session, tenant: str, rows: list[dict]) -> dict:
    items = await S._rows(session, """
        SELECT i.po_id::text AS po_id, i.product_id::text AS product_id, p.name AS product_name, i.quantity_ordered, i.quantity_received, i.unit_cost_zar
        FROM inventory_purchase_order_items i
        JOIN inventory_purchase_orders po ON po.id = i.po_id AND po.tenant_id = CAST(:t AS uuid)
        LEFT JOIN inventory_products p ON p.id = i.product_id AND p.tenant_id = po.tenant_id
        WHERE i.po_id = ANY(CAST(:ids AS uuid[]))""", {"t": tenant, "ids": [r["id"] for r in rows]})
    return S._group(items, "po_id")


async def _stock_levels(session, tenant: str) -> list:
    if not (await table_exists(session, "inventory_warehouses") and await table_exists(session, "inventory_levels")):
        return []
    whs = await S._rows(session, "SELECT w.id::text AS id, w.code, w.name, w.is_external FROM inventory_warehouses w "
                                 "WHERE w.tenant_id = CAST(:t AS uuid) AND w.is_active ORDER BY w.id::text LIMIT 100", {"t": tenant})
    now, out = _now(), []
    for w in whs:
        p = {"t": tenant, "w": w["id"]}
        summ = (await S._rows(session, """
            SELECT count(*) AS products, COALESCE(sum(l.soh), 0) AS soh, COALESCE(sum(l.sit), 0) AS sit, COALESCE(sum(l.allocated), 0) AS allocated,
                   count(*) FILTER (WHERE COALESCE(l.reorder_point, 0) > 0 AND l.soh <= l.reorder_point) AS below_reorder
            FROM inventory_levels l WHERE l.tenant_id = CAST(:t AS uuid) AND l.warehouse_id = CAST(:w AS uuid)""", p))[0]
        low = await S._rows(session, """
            SELECT l.product_id::text AS product_id, pr.name, pr.sku, l.soh, l.reorder_point
            FROM inventory_levels l JOIN inventory_products pr ON pr.id = l.product_id AND pr.tenant_id = l.tenant_id
            WHERE l.tenant_id = CAST(:t AS uuid) AND l.warehouse_id = CAST(:w AS uuid) AND COALESCE(l.reorder_point, 0) > 0 AND l.soh <= l.reorder_point
            ORDER BY (l.soh - l.reorder_point), l.product_id::text LIMIT 15""", p)
        out.append(X.warehouse_stock_card(w, summ, low, now))
    return out


async def _stock_levels_ids(session, tenant: str) -> dict:
    if not await table_exists(session, "inventory_warehouses"):
        raise RuntimeError("table inventory_warehouses does not exist; refusing to reconcile stock_levels")
    rows = await S._rows(session, "SELECT w.id::text AS id FROM inventory_warehouses w WHERE w.tenant_id = CAST(:t AS uuid) AND w.is_active", {"t": tenant})
    return {"stock_digest": {r["id"] for r in rows}}


async def _stock_movements(session, tenant: str) -> list:
    rows = await _guarded(session, tenant, ["inventory_stock_movements"], """
        SELECT to_char(date_trunc('month', m.created_at), 'YYYY-MM') AS month, m.movement_type::text AS movement_type, count(*) AS movements,
               COALESCE(sum(abs(m.quantity)), 0) AS units
        FROM inventory_stock_movements m WHERE m.tenant_id = CAST(:t AS uuid) AND m.created_at >= :since GROUP BY 1, 2""",
                          {"since": S._months_back(_months())})
    now = _now()
    return [X.stock_movement_digest_card(m, [r for r in rows if r["month"] == m], now) for m in sorted({r["month"] for r in rows})]


_PRODUCT_FROM = ("inventory_products t LEFT JOIN inventory_product_categories c ON c.id = t.category_id AND c.tenant_id = t.tenant_id "
                 "LEFT JOIN inventory_service_types st ON st.id = t.service_type_id AND st.tenant_id = t.tenant_id "
                 "LEFT JOIN inventory_product_ranges rg ON rg.id = t.range_id AND rg.tenant_id = t.tenant_id")
_PACKAGE_FROM = ("inventory_packages t LEFT JOIN inventory_product_categories c ON c.id = t.category_id AND c.tenant_id = t.tenant_id "
                 "LEFT JOIN inventory_service_types st ON st.id = t.service_type_id AND st.tenant_id = t.tenant_id")

INVENTORY_SOURCES = [
    keyset_source("inventory_products", "inventory", "product", probe="inventory_products", frm=_PRODUCT_FROM,
                  select="t.sku, t.name, t.description, t.unit_of_measure, t.rrp, t.is_active, t.is_serialized, c.name AS category_name, "
                         "st.name AS service_type_name, rg.name AS range_name, t.updated_at",
                  ts="COALESCE(t.updated_at, t.created_at)", build=lambda r, c, a: X.product_card(r, a)),
    keyset_source("inventory_packages", "inventory", "package", probe="inventory_packages", frm=_PACKAGE_FROM,
                  select="t.sku, t.name, t.description, t.package_type::text AS package_type, t.rrp, t.is_active, t.is_sellable_standalone, t.version, "
                         "t.effective_from, t.effective_to, c.name AS category_name, st.name AS service_type_name, t.updated_at",
                  ts="COALESCE(t.updated_at, t.created_at)", enrich=_package_items,
                  build=lambda r, c, a: X.package_card(r, c.get(r["id"], []), a)),
    snapshot_source("stock_levels", "inventory", "stock_digest", _stock_levels, _stock_levels_ids),
    snapshot_source("stock_movement_digests", "inventory", "stock_movement_digest", _stock_movements),
    keyset_source("inventory_suppliers", "inventory", "supplier", probe="inventory_suppliers", frm="inventory_suppliers t",
                  select="t.code, t.name, t.payment_terms, t.lead_time_days, t.is_active, t.updated_at",
                  ts="COALESCE(t.updated_at, t.created_at)", enrich=_supplier_stats,
                  build=lambda r, c, a: X.supplier_card(r, c.get(r["id"], {}), a)),
    keyset_source("purchase_orders", "inventory", "purchase_order", probe="inventory_purchase_orders",
                  frm="inventory_purchase_orders t LEFT JOIN inventory_suppliers s ON s.id = t.supplier_id AND s.tenant_id = t.tenant_id "
                      "LEFT JOIN inventory_warehouses w ON w.id = t.warehouse_id AND w.tenant_id = t.tenant_id",
                  select="t.supplier_id::text AS supplier_id, s.name AS supplier_name, w.name AS warehouse_name, t.po_number, t.status::text AS status, "
                         "t.subtotal_zar, t.tax_zar, t.total_zar, t.order_date, t.expected_delivery, t.received_at, t.currency, t.approval_mode, "
                         "t.rejection_reason, t.cancelled_at, t.notes, t.updated_at",
                  ts="COALESCE(t.updated_at, t.created_at)", enrich=_po_items,
                  build=lambda r, c, a: X.purchase_order_card(r, c.get(r["id"], []), a)),
]


# ═══ Finance & billing-level ══════════════════════════════════════════════════════════════════════════════════════

async def _chart(session, tenant: str) -> list:
    rows = await _guarded(session, tenant, ["finance_accounts"],
                          "SELECT a.code, a.name FROM finance_accounts a WHERE a.tenant_id = CAST(:t AS uuid) ORDER BY a.code LIMIT 2000")
    return [X.chart_of_accounts_card(rows, _now())] if rows else []


async def _journals(session, tenant: str) -> list:
    since = S._months_back(_months()).date()
    p = {"since": since}
    summ = await _guarded(session, tenant, ["journal_entries"], """
        SELECT to_char(date_trunc('month', e.entry_date::timestamp), 'YYYY-MM') AS month,
               count(*) FILTER (WHERE e.is_posted) AS posted, count(*) FILTER (WHERE NOT e.is_posted) AS unposted
        FROM journal_entries e WHERE e.tenant_id = CAST(:t AS uuid) AND e.entry_date >= CAST(:since AS date) GROUP BY 1""", p)
    acc = await _guarded(session, tenant, ["journal_entries", "journal_entry_lines"], """
        SELECT to_char(date_trunc('month', e.entry_date::timestamp), 'YYYY-MM') AS month, l.account_code, max(l.account_name) AS account_name,
               count(*) AS lines, COALESCE(sum(l.debit), 0) AS debit, COALESCE(sum(l.credit), 0) AS credit,
               COALESCE(sum(l.debit), 0) + COALESCE(sum(l.credit), 0) AS volume
        FROM journal_entry_lines l JOIN journal_entries e ON e.id = l.journal_entry_id AND e.tenant_id = l.tenant_id
        WHERE l.tenant_id = CAST(:t AS uuid) AND e.is_posted AND e.entry_date >= CAST(:since AS date) GROUP BY 1, 2""", p)
    now, out = _now(), []
    for s in sorted(summ, key=lambda s: s["month"]):
        rows = [a for a in acc if a["month"] == s["month"]]
        groups: dict[str, dict] = defaultdict(lambda: {"debit": 0, "credit": 0, "lines": 0})
        for a in rows:
            g = groups[str(a["account_code"] or "?")[:1]]
            g["debit"] += float(a["debit"] or 0)
            g["credit"] += float(a["credit"] or 0)
            g["lines"] += int(a["lines"] or 0)
        summary = {"posted": s["posted"], "unposted": s["unposted"], "debit": sum(g["debit"] for g in groups.values()),
                   "credit": sum(g["credit"] for g in groups.values())}
        out.append(X.journal_digest_card(s["month"], summary, [{"grp": k, **v} for k, v in groups.items()], rows, now))
    return out


async def _invoice_lines(session, tenant: str, rows: list[dict]) -> dict:
    lines = await S._rows(session, """
        SELECT l.invoice_id::text AS invoice_id, l.id::text AS id, l.product_name, l.description, l.quantity, l.total_zar, l.line_type
        FROM invoice_lines l WHERE l.tenant_id = CAST(:t AS uuid) AND l.invoice_id = ANY(CAST(:ids AS uuid[]))""",
                         {"t": tenant, "ids": [r["id"] for r in rows]})
    return S._group(lines, "invoice_id")


def _invoice_build(r: dict, ctx: dict, a: Optional[datetime]):
    if str(r.get("status") or "").lower() in ("draft", "voided"):
        return None                                   # not an issued invoice: no card (an earlier card is tombstoned)
    return X.invoice_card(r, ctx.get(r["id"], [])[:12], a)


async def _dunning(session, tenant: str) -> list:
    rows = await _guarded(session, tenant, ["dunning_actions"], """
        SELECT to_char(date_trunc('month', d.created_at), 'YYYY-MM') AS month, d.action_type::text AS action_type, COALESCE(d.step, 0) AS step,
               count(*) AS actions, count(*) FILTER (WHERE d.executed_at IS NOT NULL) AS executed, count(*) FILTER (WHERE d.last_error IS NOT NULL) AS failed
        FROM dunning_actions d WHERE d.tenant_id = CAST(:t AS uuid) AND d.created_at >= :since GROUP BY 1, 2, 3""", {"since": S._months_back(_months())})
    now = _now()
    return [X.dunning_digest_card(m, [r for r in rows if r["month"] == m], now) for m in sorted({r["month"] for r in rows})]


FINANCE_SOURCES = [
    snapshot_source("finance_chart", "finance", "chart_of_accounts", _chart),
    snapshot_source("journal_digests", "finance", "journal_digest", _journals),
    keyset_source("invoices", "billing", "invoice", probe="invoices", frm="invoices t",
                  select="t.customer_id::text AS customer_id, t.subscription_id::text AS subscription_id, t.number, t.status::text AS status, "
                         "t.subtotal_zar, t.vat_zar, t.total_zar, t.amount_paid_zar, t.due_date, t.billing_period_start, t.billing_period_end, "
                         "t.credit_note_of::text AS credit_note_of, t.created_at, t.updated_at",
                  ts="COALESCE(t.updated_at, t.created_at)", live="t.status::text NOT IN ('draft', 'voided')", enrich=_invoice_lines, build=_invoice_build),
    keyset_source("subscriptions", "billing", "subscription", probe="subscriptions", frm="subscriptions t",
                  select="t.customer_id::text AS customer_id, t.plan, t.segment, t.status::text AS status, t.billing_interval::text AS billing_interval, "
                         "t.base_price_zar, t.quantity, t.current_period_start, t.current_period_end, t.trial_ends_at, t.cancelled_at, "
                         "t.cancel_at_period_end, t.created_at, t.updated_at",
                  ts="COALESCE(t.updated_at, t.created_at)", build=lambda r, c, a: X.subscription_card(r, a)),
    keyset_source("payment_arrangements", "billing", "payment_arrangement", probe="payment_arrangements", frm="payment_arrangements t",
                  select="t.customer_id::text AS customer_id, t.total_owed_zar, t.installment_zar, t.installments_count, t.installments_paid, "
                         "t.status::text AS status, t.next_due_date, t.created_at, t.updated_at",
                  ts="COALESCE(t.updated_at, t.created_at)", build=lambda r, c, a: X.payment_arrangement_card(r, a)),
    snapshot_source("dunning_digests", "billing", "dunning_digest", _dunning),
]


# ═══ Call centre ══════════════════════════════════════════════════════════════════════════════════════════════════

async def _call_digest(session, tenant: str) -> list:
    if not await table_exists(session, "call_sessions"):
        return []
    queues = await _guarded(session, tenant, ["call_queues"], """
        SELECT q.name, q.direction::text AS direction, q.routing_strategy::text AS routing_strategy, q.status::text AS status, q.queued_calls,
               q.active_calls, q.avg_wait_seconds, q.abandoned_count FROM call_queues q WHERE q.tenant_id = CAST(:t AS uuid) ORDER BY q.name LIMIT 100""")
    agents = await _guarded(session, tenant, ["call_center_agents"], """
        SELECT a.name, a.status::text AS status, a.csat_score, a.mttr_minutes, a.daily_sales
        FROM call_center_agents a WHERE a.tenant_id = CAST(:t AS uuid) ORDER BY a.name LIMIT 200""")
    months = await _guarded(session, tenant, ["call_sessions"], """
        SELECT to_char(date_trunc('month', s.start_time), 'YYYY-MM') AS month, s.direction, count(*) AS calls, COALESCE(avg(s.duration_seconds), 0) AS avg_seconds,
               COALESCE(avg(s.sentiment_score), 0) AS avg_sentiment,
               count(*) FILTER (WHERE upper(COALESCE(s.outcome, '')) IN ('RESOLVED', 'COMPLETED')) AS resolved
        FROM call_sessions s WHERE s.tenant_id = CAST(:t AS uuid) AND s.start_time >= :since GROUP BY 1, 2""", {"since": S._months_back(_months())})
    return [X.call_center_digest_card(queues, agents, months, _now())] if (queues or agents or months) else []


def _call_build(r: dict, c: dict, a: Optional[datetime]):
    return X.call_session_card(r, a)


CALL_CENTER_SOURCES = [
    # The consent/retention gate is applied IN SQL: a transcript that may not be indexed never leaves the database.
    keyset_source("call_sessions", "call_center", "call_session", probe="call_sessions",
                  frm="call_sessions t LEFT JOIN call_center_agents a ON a.id = t.agent_id AND a.tenant_id = t.tenant_id "
                      "LEFT JOIN call_queues q ON q.id = t.queue_id AND q.tenant_id = t.tenant_id",
                  select="a.name AS agent_name, t.customer_id::text AS customer_id, t.direction, q.name AS queue_name, t.start_time, t.end_time, "
                         "t.duration_seconds, t.sentiment_score, t.outcome, t.notes, t.recording_consent, "
                         "CASE WHEN lower(COALESCE(t.recording_consent, 'unknown')) IN ('given', 'not_required') "
                         "AND (t.retention_until IS NULL OR t.retention_until > now()) THEN t.transcript END AS transcript, "
                         "(t.transcript IS NOT NULL AND t.transcript <> '') AS has_transcript, "
                         "(t.retention_until IS NULL OR t.retention_until > now()) AS retention_ok, t.updated_at",
                  ts="COALESCE(t.updated_at, t.created_at)", where="t.end_time IS NOT NULL", live="t.end_time IS NOT NULL", build=_call_build),
    snapshot_source("call_center_digest", "call_center", "call_center_digest", _call_digest),
]


# ═══ Support KB, lifecycle, retention, portal, marketing ═════════════════════════════════════════════════════════

async def _levels(session, tenant: str, rows: list[dict]) -> dict:
    if not await table_exists(session, "retention_predictions"):
        return {}
    ids = [r["id"] for r in rows]
    p = {"t": tenant, "ids": ids}
    lv = await S._rows(session, """
        SELECT p.batch_run_id::text AS batch_id, p.risk_level::text AS risk_level, count(*) AS customers, COALESCE(avg(p.churn_probability), 0) AS avg_prob
        FROM retention_predictions p WHERE p.tenant_id = CAST(:t AS uuid) AND p.batch_run_id = ANY(CAST(:ids AS uuid[])) GROUP BY 1, 2""", p)
    rs = await S._rows(session, """
        SELECT p.batch_run_id::text AS batch_id, p.primary_reason, count(*) AS customers
        FROM retention_predictions p WHERE p.tenant_id = CAST(:t AS uuid) AND p.batch_run_id = ANY(CAST(:ids AS uuid[]))
              AND p.risk_level::text IN ('critical', 'high', 'medium') GROUP BY 1, 2""", p)
    cs = await S._rows(session, """
        SELECT x.batch_id, x.customer_id, x.risk_level, x.churn_probability, x.primary_reason, x.tenure_months, x.monthly_spend_zar,
               x.flagged_for_retention FROM (SELECT p.batch_run_id::text AS batch_id, p.customer_id::text AS customer_id, p.risk_level::text AS risk_level,
               p.churn_probability, p.primary_reason, p.tenure_months, p.monthly_spend_zar, p.flagged_for_retention,
               row_number() OVER (PARTITION BY p.batch_run_id ORDER BY p.churn_probability DESC, p.customer_id::text) AS rn
               FROM retention_predictions p WHERE p.tenant_id = CAST(:t AS uuid) AND p.batch_run_id = ANY(CAST(:ids AS uuid[]))
                    AND p.risk_level::text IN ('critical', 'high')) x WHERE rn <= 15""", p)
    return {"levels": S._group(lv, "batch_id"), "reasons": S._group(rs, "batch_id"), "cases": S._group(cs, "batch_id")}


async def _cancellations(session, tenant: str) -> list:
    since = S._months_back(_months())
    reasons = await _guarded(session, tenant, ["cancel_events"], """
        SELECT to_char(date_trunc('month', c.created_at), 'YYYY-MM') AS month, c.cancel_reason::text AS cancel_reason, c.source_channel::text AS source_channel,
               count(*) AS events FROM cancel_events c WHERE c.tenant_id = CAST(:t AS uuid) AND c.created_at >= :since GROUP BY 1, 2, 3""", {"since": since})
    wfs = await _guarded(session, tenant, ["cancellation_workflows"], """
        SELECT to_char(date_trunc('month', w.created_at), 'YYYY-MM') AS month, w.status::text AS status, w.router_return_status::text AS router_return_status,
               count(*) AS workflows, COALESCE(sum(w.early_termination_fee_zar), 0) AS etf_zar
        FROM cancellation_workflows w WHERE w.tenant_id = CAST(:t AS uuid) AND w.created_at >= :since GROUP BY 1, 2, 3""", {"since": since})
    outs = await _guarded(session, tenant, ["journey_outcomes"], """
        SELECT to_char(date_trunc('month', o.created_at), 'YYYY-MM') AS month, o.outcome::text AS outcome, count(*) AS outcomes,
               COALESCE(sum(o.discount_cost_zar), 0) AS discount_cost, COALESCE(sum(o.monthly_revenue_before), 0) AS rev_before,
               COALESCE(sum(o.monthly_revenue_after), 0) AS rev_after
        FROM journey_outcomes o WHERE o.tenant_id = CAST(:t AS uuid) AND o.created_at >= :since GROUP BY 1, 2""", {"since": since})
    months = sorted({r["month"] for r in reasons} | {r["month"] for r in wfs} | {r["month"] for r in outs})
    now = _now()
    pick_m = lambda rows, m: [r for r in rows if r["month"] == m]  # noqa: E731
    return [X.cancellation_digest_card(m, pick_m(reasons, m), pick_m(wfs, m), pick_m(outs, m), now) for m in months]


async def _portal_submissions(session, tenant: str) -> list:
    rows = await _guarded(session, tenant, ["portal_submissions", "portal_pages"], """
        SELECT to_char(date_trunc('month', s.created_at), 'YYYY-MM') AS month, s.page_id::text AS page_id, p.title, s.utm_source, s.utm_medium, s.utm_campaign,
               count(*) AS submissions, count(*) FILTER (WHERE s.converted) AS converted
        FROM portal_submissions s JOIN portal_pages p ON p.id = s.page_id AND p.tenant_id = s.tenant_id
        WHERE s.tenant_id = CAST(:t AS uuid) AND s.consent_given IS TRUE AND s.created_at >= :since GROUP BY 1, 2, 3, 4, 5, 6""",
                          {"since": S._months_back(_months())})
    now = _now()
    return [X.portal_submissions_digest_card(m, [r for r in rows if r["month"] == m], now) for m in sorted({r["month"] for r in rows})]


def _churn_build(r: dict, c: dict, a: Optional[datetime]):
    bid = r["id"]
    return X.churn_batch_card(r, c.get("levels", {}).get(bid, []), c.get("reasons", {}).get(bid, []), c.get("cases", {}).get(bid, []), a)


MISC_SOURCES = [
    # knowledge_base has no updated_at (master_schema.sql): edits are caught by the daily full reconcile, not the watermark.
    keyset_source("kb_articles", "support", "kb_article", probe="knowledge_base", frm="knowledge_base t",
                  select="t.title, t.content, t.category, t.tags, t.is_published, t.created_at", ts="t.created_at", live="t.is_published",
                  build=lambda r, c, a: X.kb_article_card(r, a)),
    keyset_source("retention_journeys", "lifecycle", "retention_journey", probe="retention_journeys", frm="retention_journeys t",
                  select="t.name, t.description, t.trigger_event::text AS trigger_event, t.status::text AS status, t.priority, t.offer_id::text AS offer_id, "
                         "t.fallback_offer_id::text AS fallback_offer_id, t.channel::text AS channel, t.ab_test_enabled, t.times_triggered, t.times_shown, "
                         "t.times_accepted, t.times_rejected, t.revenue_preserved, t.updated_at",
                  ts="COALESCE(t.updated_at, t.created_at)", build=lambda r, c, a: X.journey_card(r, a)),
    keyset_source("retention_offers", "lifecycle", "retention_offer", probe="retention_offers", frm="retention_offers t",
                  select="t.name, t.description, t.offer_type::text AS offer_type, t.parameters, t.max_per_customer, t.max_total_redemptions, "
                         "t.total_redemptions, t.estimated_cost_per_use, t.status::text AS status, t.updated_at",
                  ts="COALESCE(t.updated_at, t.created_at)", build=lambda r, c, a: X.offer_card(r, a)),
    keyset_source("lifecycle_summaries", "lifecycle", "lifecycle_summary", probe="lifecycle_summaries", frm="lifecycle_summaries t",
                  select="t.period_type::text AS period_type, t.period_date, t.total_leads, t.total_prospects, t.total_customers, t.total_at_risk, "
                         "t.total_churned, t.new_conversions, t.new_churns, t.new_reactivations, t.risk_escalations, t.mrr_at_start, t.mrr_new, "
                         "t.mrr_churned, t.mrr_reactivated, t.mrr_at_end, t.cancel_attempts, t.offers_shown, t.offers_accepted, t.revenue_preserved, t.created_at",
                  ts="t.created_at", build=lambda r, c, a: X.lifecycle_summary_card(r, a)),
    snapshot_source("cancellation_digests", "lifecycle", "cancellation_digest", _cancellations),
    keyset_source("churn_batches", "retention", "churn_batch", probe="retention_batch_runs", frm="retention_batch_runs t",
                  select="t.status, t.customers_scored, t.high_risk_count, t.medium_risk_count, t.low_risk_count, t.loyal_count, t.critical_count, "
                         "t.started_at, t.completed_at",
                  ts="COALESCE(t.completed_at, t.started_at)", where="t.status IN ('completed', 'completed_with_errors') AND t.started_at > now() - interval '120 days'",
                  live="t.status IN ('completed', 'completed_with_errors') AND t.started_at > now() - interval '120 days'", enrich=_levels, build=_churn_build),
    keyset_source("portal_pages", "portal", "portal_page", probe="portal_pages",
                  frm="portal_pages t LEFT JOIN portal_page_versions v ON v.page_id = t.id AND v.version_number = t.published_version",
                  select="t.slug, t.title, t.description, t.page_type, t.status, t.views, t.conversions, t.published_at, COALESCE(v.content, t.content) AS content, t.updated_at",
                  ts="COALESCE(t.updated_at, t.created_at)", live="t.status = 'published'",
                  build=lambda r, c, a: X.portal_page_card(r, r.get("content"), a)),
    snapshot_source("portal_submission_digests", "portal", "portal_submissions_digest", _portal_submissions),
    keyset_source("audience_segments", "marketing", "audience_segment", probe="marketing_audience_segments", frm="marketing_audience_segments t",
                  select="t.name, t.description, t.rules, t.member_count, t.created_at", ts="t.created_at",
                  build=lambda r, c, a: X.audience_segment_card(r, a)),
]

EXT_SOURCES: list[Source] = [*COMPLIANCE_SOURCES, *HR_SOURCES, *NETWORK_SOURCES, *INVENTORY_SOURCES, *FINANCE_SOURCES, *CALL_CENTER_SOURCES, *MISC_SOURCES]

# Verified-but-not-indexed sources and why (surfaced by the coverage endpoint and docs/knowledge-layer.md).
SKIPPED: dict[str, str] = {
    "communication_threads": "no thread/summary table: agent_emails only holds raw bodies and the agent's raw reply; raw e-mail bodies are never indexed",
    "hr_individual_records": "payroll, payslips, performance reviews, KPI sheets, disciplinary, exits, leave and schedules are named-individual or sensitive: excluded by design",
    "campaign_lead_edges": "no verified campaign->lead foreign key (leads carry a free-text source only); portal submissions carry utm_campaign text, not an id",
    "compliance_popia_dsar": "data-subject requests hold personal identities; only the consent digest (counts) is indexed",
}


def register(sources: dict) -> None:
    for s in EXT_SOURCES:
        sources[s.name] = s


register(S.SOURCES)
