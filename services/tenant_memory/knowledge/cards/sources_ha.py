"""Home Assistant reference library as knowledge cards (module `iot`), so chats and apps can answer integration setup questions."""
from datetime import datetime, timezone

from sqlalchemy import text

from services.tenant_memory.knowledge.cards.base import Card
from services.tenant_memory.knowledge.cards import sources as S

MAX_CARD = 8000


def reference_card(row: dict) -> Card:
    kind = row["kind"]
    header = [f"# {row['title']}", f"Source: {row['url']}", f"Licence: {row['license']}",
              "This is Home Assistant reference material, not tenant data. Cite the source link when answering."]
    tags = ["home-assistant", "reference", kind] + ([row["integration_id"]] if row.get("integration_id") else [])
    as_of = row["fetched_at"] if isinstance(row["fetched_at"], datetime) else datetime.now(timezone.utc)
    return Card("ha_reference", row["doc_key"], "iot", row["title"], ("\n".join(header) + "\n\n" + row["body"])[:MAX_CARD],
                as_of, tags, importance=0.6 if kind == "integration" else 0.4,
                source_ref={"url": row["url"], "doc_key": row["doc_key"]}, visibility="tenant", required_roles=[])


async def _library(session) -> list[dict]:
    async with session.begin_nested():
        exists = (await session.execute(text("SELECT to_regclass('ha_reference_docs')"))).scalar()
        if not exists:
            return []
        res = await session.execute(text(
            "SELECT doc_key, kind, title, url, integration_id, body, license, fetched_at FROM ha_reference_docs"))
        return [dict(r) for r in res.mappings().all()]


async def fetch_ha_reference(session, tenant, wm, limit):
    rows = await _library(session)
    return S.Page(cards=[reference_card(r) for r in rows], rows=len(rows), last_ts=datetime.now(timezone.utc))


async def ids_ha_reference(session, tenant):
    return {"ha_reference": [r["doc_key"] for r in await _library(session)]}


S.SOURCES["ha_reference"] = S.Source("ha_reference", "iot", ("ha_reference",), fetch_ha_reference, ids_ha_reference, snapshot=True)
