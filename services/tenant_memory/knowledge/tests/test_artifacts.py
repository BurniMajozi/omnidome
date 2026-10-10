"""Artifact registry cards, deep links and the write-through upsert endpoint (no database, no network)."""
import asyncio
import contextlib
import os
import uuid
from datetime import datetime, timezone

import pytest

os.environ.setdefault("AUTH_MODE", "header")
os.environ["AUTH_DB_ENFORCE"] = "false"
os.environ["AUTH_ENFORCE_MODULES"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from services.tenant_memory.knowledge import routes  # noqa: E402
from services.tenant_memory.knowledge.cards import builders_artifacts as A  # noqa: E402
from services.tenant_memory.knowledge.cards.sources import SOURCES  # noqa: E402
from services.tenant_memory.knowledge.embeddings import HashEmbedder  # noqa: E402
from services.tenant_memory.knowledge.store_memory import MemoryStore  # noqa: E402
from services.tenant_memory.main import app  # noqa: E402

NOW = datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc)
DECK_ID = "11111111-2222-3333-4444-555555555555"
T1 = str(uuid.uuid4())


def deck_row(**extra):
    doc = {"title": "Sales Pipeline Overview", "queries": {"q1": {"dataset": "deals"}}, "slides": [
        {"id": "s1", "layout": "title", "title": "Sales Pipeline Overview", "notes": "", "blocks": []},
        {"id": "s2", "layout": "chart_full", "title": "Pipeline by stage", "notes": "Source: CRM export 2026-09", "blocks": [
            {"type": "chart", "id": "b1", "query": {"dataset": "tickets"}}]}]}
    return {"id": DECK_ID, "title": "Sales Pipeline Overview", "status": "draft", "version": 4, "doc": doc,
            "brand_kit_id": "kit-1", "created_by": "user-1", "published_at": None, "created_at": NOW, "updated_at": NOW, **extra}


CTX = {"users": {"user-1": "Thandi M."}, "kits": {"kit-1": "OmniDome Brand"}}


def test_deck_card_is_deterministic_with_expected_fields():
    a, b = A.deck_card(deck_row(), CTX, NOW), A.deck_card(deck_row(), CTX, NOW)
    assert a.markdown == b.markdown
    assert a.module == "analytics" and a.source_type == "bi_deck" and a.source_id == DECK_ID
    assert a.access() == ("tenant", [])                                  # tenant-visible; the panel gate keys on module analytics
    assert a.owner_id == "user-1"
    for needle in ("Sales Pipeline Overview", "Status: draft (version 4)", "Slides: 2", "OmniDome Brand", "Thandi M.",
                   "Pipeline by stage - layout chart_full", "deals, tickets", "Source: CRM export"):
        assert needle in a.markdown, needle
    assert "status: draft" in a.markdown and "version: 4" in a.markdown and "slide_count: 2" in a.markdown
    assert {"deck", "bi-studio", "artifact", "draft"} <= set(a.tags)
    assert a.source_ref["deep_link"] == f"/dashboard?section=analytics&sub=presentations&deck={DECK_ID}"


def test_deck_card_reflects_status_and_version_changes():
    pub = A.deck_card(deck_row(status="published", version=5, published_at=NOW), CTX, NOW)
    assert "published" in pub.tags and "Status: published (version 5)" in pub.markdown and "Published: 2026-10-09" in pub.markdown
    assert A.deck_card(deck_row(), CTX, NOW).markdown != pub.markdown


def test_brand_kit_card_has_names_only_no_logo_or_palette():
    row = {"id": "22222222-2222-3333-4444-555555555555", "name": "OmniDome Brand", "is_default": True, "updated_at": NOW,
           "logo_data_url": "data:image/png;base64,AAAA", "config": {"palette": {"primary": "#123456"}}}
    c = A.brand_kit_card(row, None, NOW)
    assert "OmniDome Brand" in c.markdown and "Default kit: yes" in c.markdown
    assert "base64" not in c.markdown and "#123456" not in c.markdown and "AAAA" not in c.markdown
    assert c.source_ref["deep_link"].startswith("/dashboard?section=analytics&sub=presentations&brand_kit=")


def test_deep_links_are_real_same_origin_dashboard_routes():
    for kind in A.ARTIFACT_KINDS:
        link = A.app_link(kind, DECK_ID)
        assert link.startswith("/dashboard?section=") and "sub=" in link and "//" not in link and " " not in link
    assert A.app_link("portal_page", DECK_ID) == f"/dashboard?section=portal&sub=website&page={DECK_ID}"
    assert "deck=" not in A.app_link("bi_deck", "x; drop table")          # non-uuid ids never reach the URL


def test_existing_analytics_cards_use_real_deep_links():
    from services.tenant_memory.knowledge.cards import builders as B
    run = {"id": DECK_ID, "question": "q", "report": {"summary": "s"}, "sources": []}
    assert B.research_card(run, NOW).source_ref["deep_link"] == f"/dashboard?section=analytics&sub=research&research={DECK_ID}"
    comp = B.competitor_card({"id": DECK_ID, "name": "Rival", "website": "https://r.example"}, None, [], NOW)
    assert comp.source_ref["deep_link"].startswith("/dashboard?section=analytics&sub=competitors&competitor=")
    camp = B.campaign_analysis_card({"id": DECK_ID, "name": "n", "subject": "s", "item_count": 0}, NOW)
    assert camp.source_ref["deep_link"].startswith("/dashboard?section=analytics&sub=campaign-analysis&analysis=")


def test_sources_registered():
    assert {"bi_decks", "bi_brand_kits"} <= set(SOURCES)
    assert SOURCES["bi_decks"].module == "analytics" and SOURCES["bi_decks"].source_types == ("bi_deck",)


# ── write-through endpoint ───────────────────────────────────────────────

def h(roles="analyst", tenant=T1):
    return {"X-Tenant-Id": tenant, "X-User-Id": str(uuid.uuid4()), "X-Roles": roles}


@pytest.fixture
def client(monkeypatch):
    store, emb = MemoryStore(), HashEmbedder(32)
    routes.set_runtime(store, emb)
    routes._upsert_hits.clear()
    calls = []

    async def fake_load(sess, tenant, source_type, source_id):
        calls.append((tenant, source_type, source_id))
        return A.deck_card(deck_row(id=source_id), CTX, NOW) if source_id == DECK_ID else None

    @contextlib.asynccontextmanager
    async def fake_scope():
        yield object()

    monkeypatch.setattr(A, "load_card", fake_load)
    monkeypatch.setattr("services.common.db.session_scope", fake_scope)
    c = TestClient(app)
    c.store, c.calls = store, calls
    yield c
    routes._runtime.clear()


def live(c, st="bi_deck"):
    return asyncio.run(c.store.live_source_ids(T1, st))


URL = "/api/v1/knowledge/admin/upsert-source"


def test_upsert_indexes_the_card_and_is_idempotent(client):
    body = {"source_type": "bi_deck", "source_id": DECK_ID}
    r = client.post(URL, json=body, headers=h())
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "indexed" and r.json()["stats"]["inserted"] >= 1
    assert live(client) == {DECK_ID}
    again = client.post(URL, json=body, headers=h()).json()
    assert again["stats"]["inserted"] == 0 and again["stats"]["chunks_embedded"] == 0     # same content hash: nothing re-embedded
    assert client.calls[0] == (T1, "bi_deck", DECK_ID)                                    # tenant comes from the verified identity


def test_upsert_tombstones_on_delete_and_when_row_is_gone(client):
    client.post(URL, json={"source_type": "bi_deck", "source_id": DECK_ID}, headers=h())
    assert live(client) == {DECK_ID}
    r = client.post(URL, json={"source_type": "bi_deck", "source_id": DECK_ID, "deleted": True}, headers=h())
    assert r.json()["status"] == "tombstoned" and live(client) == set()
    client.post(URL, json={"source_type": "bi_deck", "source_id": DECK_ID}, headers=h())
    gone = "99999999-2222-3333-4444-555555555555"
    r = client.post(URL, json={"source_type": "bi_deck", "source_id": gone}, headers=h())
    assert r.json()["status"] == "tombstoned"                                             # loader returned None -> no stale card


def test_upsert_checks_role_type_id_and_rate(client, monkeypatch):
    ok = {"source_type": "bi_deck", "source_id": DECK_ID}
    assert client.post(URL, json=ok, headers=h("viewer")).status_code == 403
    assert client.post(URL, json={**ok, "source_type": "customer"}, headers=h()).status_code == 400
    assert client.post(URL, json={**ok, "source_id": "x; drop table"}, headers=h()).status_code == 400
    monkeypatch.setenv("KNOWLEDGE_UPSERT_PER_MINUTE", "2")
    codes = [client.post(URL, json=ok, headers=h()).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
