"""Catalogue products as a keyset knowledge source (table `catalogue_products`, owned by the inventory service).

Costs, supplier names and margins are not selected (see builders_catalogue). The (updated_at, id) keyset means any edit,
launch or archive re-builds the card, and an unchanged content hash is never re-embedded. A deleted product is
tombstoned by reconcile. A tenant whose inventory service never started has no table: the source is skipped.
"""
from __future__ import annotations

from typing import Optional

from services.tenant_memory.knowledge.cards import builders_catalogue as BC
from services.tenant_memory.knowledge.cards import sources as S
from services.tenant_memory.knowledge.cards.builders_ext import jsonish

# sources_ext is imported lazily (inside the functions): sources.py imports this module at its very end, and the
# worker imports sources_ext first, so a module-level import here is circular and crash-loops the indexer.

_COLS = ("t.product_number, t.name, t.category, t.range, t.family, t.nature, t.usage, t.status, t.owner, "
         "t.launched_at, (t.definition - 'costs' - 'supplier' - 'sources') AS definition, "
         # supplier ids and the preferred flag only: unit costs inside `sources` are never selected
         "(SELECT jsonb_agg(jsonb_build_object('supplier_id', s->>'supplier_id', 'preferred', COALESCE((s->>'preferred')::boolean, false))) "
         "FROM jsonb_array_elements(COALESCE(t.definition->'sources', '[]'::jsonb)) s) AS source_refs")


async def fetch_catalogue(session, tenant: str, wm: Optional[dict], limit: int) -> S.Page:
    from services.tenant_memory.knowledge.cards.sources_ext import table_exists
    if not await table_exists(session, "catalogue_products"):
        return S.Page()
    ks, kp = S._keyset("t.updated_at", "t.id::text", wm)
    rows = await S._rows(session, f"SELECT {_COLS}, t.updated_at AS ts, t.id::text AS id FROM catalogue_products t "
                                  f"WHERE t.tenant_id = CAST(:tenant_id AS uuid){ks} ORDER BY t.updated_at, t.id::text LIMIT :limit",
                         {"tenant_id": tenant, "limit": limit, **kp})
    page = S.Page()
    S._track(page, rows)
    wanted: set[str] = set()
    for r in rows:
        for c in (jsonish(r.get("definition")) or {}).get("components") or []:
            wanted.add(str(c.get("product_id")))
    supplier_ids = sorted({str(x.get("supplier_id")) for r in rows for x in (jsonish(r.get("source_refs")) or [])})
    supplier_names: dict[str, str] = {}
    if supplier_ids and await table_exists(session, "inventory_suppliers"):
        for sp in await S._rows(session, "SELECT id::text AS id, name FROM inventory_suppliers WHERE tenant_id = CAST(:t AS uuid) "
                                         "AND deleted_at IS NULL AND id::text = ANY(CAST(:ids AS text[]))", {"t": tenant, "ids": supplier_ids}):
            supplier_names[sp["id"]] = sp["name"]
    names: dict[str, tuple[str, str]] = {}
    if wanted:
        for n in await S._rows(session, "SELECT id::text AS id, product_number, name FROM catalogue_products "
                                        "WHERE tenant_id = CAST(:t AS uuid) AND id::text = ANY(CAST(:ids AS text[]))",
                               {"t": tenant, "ids": sorted(wanted)}):
            names[n["id"]] = (n["product_number"], n["name"])
    for r in rows:
        page.cards.append(BC.catalogue_product_card({**r, "id": r["id"]}, names, S._utc(r["ts"]), supplier_names))
    return page


async def ids_catalogue(session, tenant: str) -> dict:
    from services.tenant_memory.knowledge.cards.sources_ext import SourceUnavailable, table_exists
    if not await table_exists(session, "catalogue_products"):
        raise SourceUnavailable("table catalogue_products does not exist; refusing to reconcile catalogue_products")
    rows = await S._rows(session, "SELECT id::text AS id FROM catalogue_products WHERE tenant_id = CAST(:t AS uuid)", {"t": tenant})
    return {"catalogue_product": {r["id"] for r in rows}}


S.SOURCES["catalogue_products"] = S.Source("catalogue_products", "inventory", ("catalogue_product",), fetch_catalogue, ids_catalogue)


async def fetch_factsheets(session, tenant: str, wm: Optional[dict], limit: int) -> S.Page:
    from services.tenant_memory.knowledge.cards.sources_ext import table_exists
    if not await table_exists(session, "catalogue_assets"):
        return S.Page()
    ks, kp = S._keyset("a.created_at", "a.id::text", wm)
    rows = await S._rows(session, "SELECT a.filename, a.purpose, a.title, a.product_id::text AS product_id, a.text, p.product_number, p.name AS product_name, "
                                  "a.created_at AS ts, a.id::text AS id FROM catalogue_assets a "
                                  "JOIN catalogue_products p ON p.id = a.product_id AND p.tenant_id = a.tenant_id "
                                  f"WHERE a.tenant_id = CAST(:tenant_id AS uuid) AND a.purpose IN ('fact_sheet', 'certificate') AND a.text IS NOT NULL{ks} "
                                  "ORDER BY a.created_at, a.id::text LIMIT :limit", {"tenant_id": tenant, "limit": limit, **kp})
    page = S.Page()
    S._track(page, rows)
    page.cards = [BC.catalogue_factsheet_card(r, S._utc(r["ts"])) for r in rows]
    return page


async def ids_factsheets(session, tenant: str) -> dict:
    from services.tenant_memory.knowledge.cards.sources_ext import SourceUnavailable, table_exists
    if not await table_exists(session, "catalogue_assets"):
        raise SourceUnavailable("table catalogue_assets does not exist; refusing to reconcile catalogue_factsheets")
    rows = await S._rows(session, "SELECT id::text AS id FROM catalogue_assets WHERE tenant_id = CAST(:t AS uuid) AND purpose IN ('fact_sheet', 'certificate') AND text IS NOT NULL", {"t": tenant})
    return {"catalogue_factsheet": {r["id"] for r in rows}}


S.SOURCES["catalogue_factsheets"] = S.Source("catalogue_factsheets", "inventory", ("catalogue_factsheet",), fetch_factsheets, ids_factsheets)


# ── sourcing: requests, quotes, prospects (inventory tables; commercial terms, so cards are procurement-restricted) ──

_SOURCING_TABLES = ("sourcing_requests", "sourcing_responses", "sourcing_prospects", "sourcing_invitees")


async def _sourcing_ready(session, *tables: str) -> bool:
    from services.tenant_memory.knowledge.cards.sources_ext import table_exists
    for t in tables:
        if not await table_exists(session, t):
            return False
    return True


async def fetch_sourcing_requests(session, tenant: str, wm: Optional[dict], limit: int) -> S.Page:
    if not await _sourcing_ready(session, "sourcing_requests", "sourcing_invitees", "sourcing_responses"):
        return S.Page()
    ts = ("GREATEST(r.updated_at, COALESCE((SELECT max(x.created_at) FROM sourcing_responses x WHERE x.request_id = r.id), r.updated_at), "
          "COALESCE((SELECT max(i.sent_at) FROM sourcing_invitees i WHERE i.request_id = r.id), r.updated_at))")
    ks, kp = S._keyset(ts, "r.id::text", wm)
    rows = await S._rows(session, f"""SELECT r.number, r.kind, r.status, r.title, r.quantity, r.needed_by::text AS needed_by, r.subject, r.body, r.drafted_by, r.sent_at::text AS sent_at,
            r.award_note, r.created_by_agent, r.product_id::text AS product_id, p.product_number, p.name AS product_name,
            (SELECT i.name FROM sourcing_invitees i WHERE i.id = r.awarded_invitee_id) AS awarded_name,
            (SELECT jsonb_agg(jsonb_build_object('name', i.name, 'kind', i.kind, 'status', i.status) ORDER BY i.created_at) FROM sourcing_invitees i WHERE i.request_id = r.id) AS invitees,
            {ts} AS ts, r.id::text AS id
        FROM sourcing_requests r LEFT JOIN catalogue_products p ON p.id = r.product_id AND p.tenant_id = r.tenant_id
        WHERE r.tenant_id = CAST(:tenant_id AS uuid){ks} ORDER BY {ts}, r.id::text LIMIT :limit""", {"tenant_id": tenant, "limit": limit, **kp})
    page = S.Page()
    S._track(page, rows)
    page.cards = [BC.sourcing_request_card(r, S._utc(r["ts"])) for r in rows]
    return page


async def ids_sourcing_requests(session, tenant: str) -> dict:
    from services.tenant_memory.knowledge.cards.sources_ext import SourceUnavailable
    if not await _sourcing_ready(session, "sourcing_requests"):
        raise SourceUnavailable("table sourcing_requests does not exist; refusing to reconcile sourcing_requests")
    rows = await S._rows(session, "SELECT id::text AS id FROM sourcing_requests WHERE tenant_id = CAST(:t AS uuid)", {"t": tenant})
    return {"sourcing_request": {r["id"] for r in rows}}


async def fetch_sourcing_quotes(session, tenant: str, wm: Optional[dict], limit: int) -> S.Page:
    if not await _sourcing_ready(session, "sourcing_requests", "sourcing_invitees", "sourcing_responses"):
        return S.Page()
    ks, kp = S._keyset("x.created_at", "x.id::text", wm)
    rows = await S._rows(session, f"""SELECT x.unit_price, x.lead_time_days, x.moq, x.valid_until::text AS valid_until, x.notes, x.declined, x.request_id::text AS request_id,
            r.number, r.quantity, r.product_id::text AS product_id, p.product_number, p.name AS product_name, i.name AS supplier_name, i.kind AS supplier_kind,
            (r.awarded_invitee_id = i.id) AS awarded, x.created_at AS ts, x.id::text AS id
        FROM sourcing_responses x JOIN sourcing_requests r ON r.id = x.request_id AND r.tenant_id = x.tenant_id
        JOIN sourcing_invitees i ON i.id = x.invitee_id LEFT JOIN catalogue_products p ON p.id = r.product_id AND p.tenant_id = r.tenant_id
        WHERE x.tenant_id = CAST(:tenant_id AS uuid){ks} ORDER BY x.created_at, x.id::text LIMIT :limit""", {"tenant_id": tenant, "limit": limit, **kp})
    page = S.Page()
    S._track(page, rows)
    page.cards = [BC.sourcing_quote_card(r, S._utc(r["ts"])) for r in rows]
    return page


async def ids_sourcing_quotes(session, tenant: str) -> dict:
    from services.tenant_memory.knowledge.cards.sources_ext import SourceUnavailable
    if not await _sourcing_ready(session, "sourcing_responses"):
        raise SourceUnavailable("table sourcing_responses does not exist; refusing to reconcile sourcing_quotes")
    rows = await S._rows(session, "SELECT id::text AS id FROM sourcing_responses WHERE tenant_id = CAST(:t AS uuid)", {"t": tenant})
    return {"sourcing_quote": {r["id"] for r in rows}}


async def fetch_sourcing_prospects(session, tenant: str, wm: Optional[dict], limit: int) -> S.Page:
    if not await _sourcing_ready(session, "sourcing_prospects"):
        return S.Page()
    ks, kp = S._keyset("s.updated_at", "s.id::text", wm)
    rows = await S._rows(session, f"""SELECT s.name, s.domain, s.summary, s.fit, s.status, s.country, s.product_id::text AS product_id, p.product_number, p.name AS product_name,
            s.updated_at AS ts, s.id::text AS id
        FROM sourcing_prospects s LEFT JOIN catalogue_products p ON p.id = s.product_id AND p.tenant_id = s.tenant_id
        WHERE s.tenant_id = CAST(:tenant_id AS uuid) AND s.status <> 'dismissed'{ks} ORDER BY s.updated_at, s.id::text LIMIT :limit""", {"tenant_id": tenant, "limit": limit, **kp})
    page = S.Page()
    S._track(page, rows)
    page.cards = [BC.sourcing_prospect_card(r, S._utc(r["ts"])) for r in rows]
    return page


async def ids_sourcing_prospects(session, tenant: str) -> dict:
    from services.tenant_memory.knowledge.cards.sources_ext import SourceUnavailable
    if not await _sourcing_ready(session, "sourcing_prospects"):
        raise SourceUnavailable("table sourcing_prospects does not exist; refusing to reconcile sourcing_prospects")
    rows = await S._rows(session, "SELECT id::text AS id FROM sourcing_prospects WHERE tenant_id = CAST(:t AS uuid) AND status <> 'dismissed'", {"t": tenant})
    return {"sourcing_prospect": {r["id"] for r in rows}}


S.SOURCES["sourcing_requests"] = S.Source("sourcing_requests", "inventory", ("sourcing_request",), fetch_sourcing_requests, ids_sourcing_requests)
S.SOURCES["sourcing_quotes"] = S.Source("sourcing_quotes", "inventory", ("sourcing_quote",), fetch_sourcing_quotes, ids_sourcing_quotes)
S.SOURCES["sourcing_prospects"] = S.Source("sourcing_prospects", "inventory", ("sourcing_prospect",), fetch_sourcing_prospects, ids_sourcing_prospects)
