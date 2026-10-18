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
    rows = await S._rows(session, "SELECT a.filename, a.product_id::text AS product_id, a.text, p.product_number, p.name AS product_name, "
                                  "a.created_at AS ts, a.id::text AS id FROM catalogue_assets a "
                                  "JOIN catalogue_products p ON p.id = a.product_id AND p.tenant_id = a.tenant_id "
                                  f"WHERE a.tenant_id = CAST(:tenant_id AS uuid) AND a.purpose = 'fact_sheet' AND a.text IS NOT NULL{ks} "
                                  "ORDER BY a.created_at, a.id::text LIMIT :limit", {"tenant_id": tenant, "limit": limit, **kp})
    page = S.Page()
    S._track(page, rows)
    page.cards = [BC.catalogue_factsheet_card(r, S._utc(r["ts"])) for r in rows]
    return page


async def ids_factsheets(session, tenant: str) -> dict:
    from services.tenant_memory.knowledge.cards.sources_ext import SourceUnavailable, table_exists
    if not await table_exists(session, "catalogue_assets"):
        raise SourceUnavailable("table catalogue_assets does not exist; refusing to reconcile catalogue_factsheets")
    rows = await S._rows(session, "SELECT id::text AS id FROM catalogue_assets WHERE tenant_id = CAST(:t AS uuid) AND purpose = 'fact_sheet' AND text IS NOT NULL", {"t": tenant})
    return {"catalogue_factsheet": {r["id"] for r in rows}}


S.SOURCES["catalogue_factsheets"] = S.Source("catalogue_factsheets", "inventory", ("catalogue_factsheet",), fetch_factsheets, ids_factsheets)
