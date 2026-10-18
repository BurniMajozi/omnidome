"""Catalogue product knowledge cards: content, the cost/margin exclusion policy, index -> search round trip,
reconcile and SQL hygiene. No DB, no network."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from services.tenant_memory.knowledge.cards import builders_catalogue as BC
from services.tenant_memory.knowledge.cards import sources as S
from services.tenant_memory.knowledge.cards import sources_catalogue as SC
from services.tenant_memory.knowledge.cards.sources import Page, Source
from services.tenant_memory.knowledge.config import get_settings
from services.tenant_memory.knowledge.embeddings import HashEmbedder
from services.tenant_memory.knowledge.indexer import Indexer
from services.tenant_memory.knowledge.kdata import AccessScope, Filters
from services.tenant_memory.knowledge.retrieval import KnowledgeRetriever
from services.tenant_memory.knowledge.store_memory import MemoryStore

NOW = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)
T = "11111111-1111-1111-1111-111111111111"
EMB = HashEmbedder(32)
ROUTER = "aaaaaaaa-0000-0000-0000-000000000201"
FIBRE = "aaaaaaaa-0000-0000-0000-000000000101"


def run(c):
    return asyncio.run(c)


def fibre_row(**over):
    d = {"description": "Symmetrical home fibre with an included Wi-Fi router.", "price": 799, "recurring": True, "term": 24,
         "down": 100, "up": 100, "customer_name": "HomeFibre 100",
         "components": [{"product_id": ROUTER, "qty": 1}],
         "fees": [{"name": "Installation", "enabled": True, "amount": 950, "cadence": "Once-off", "mode": "Charge"},
                  {"name": "Callout", "enabled": False, "amount": 450, "cadence": "On event", "mode": "Charge"}],
         "documents": [{"name": "Service terms.pdf", "category": "Terms & conditions", "visibility": "Customer portal", "version": "2", "acceptance": True},
                       {"name": "Internal margin memo.pdf", "category": "Other", "visibility": "Internal only", "version": "1"}],
         "media": [{"name": "router.png", "visibility": "Customer portal"}], "policy_refs": ["early-termination-v1"],
         "research": {"rows": [{"name": "Rival ISP", "offer": "100/100 fibre", "price": 849, "spec": "100/100", "date": "2026-10-15"}], "kpis": ["subs", "mrr"]},
         "readiness": {"tests_required": True, "tests": [{"name": "A", "result": "Pass"}, {"name": "B", "result": "Pending"}],
                       "icasa": {"required": True, "items": [{"kind": "Product", "lodged": "2026-10-01", "effective": "2026-11-01", "ack": True}]}}}
    return {"id": FIBRE, "product_number": "OD-000101", "name": "Fibre 100", "category": "Connectivity", "range": "Home Fibre",
            "family": "Fibre", "nature": "Digital service", "usage": "Customer-facing", "status": "active", "owner": "Product team",
            "launched_at": NOW, "definition": d, **over}


NAMES = {ROUTER: ("OD-000201", "AX1800 Wi-Fi router")}


def test_card_has_the_sellable_facts():
    c = BC.catalogue_product_card(fibre_row(), NAMES, NOW)
    md = c.markdown
    assert c.source_type == "catalogue_product" and c.module == "inventory"
    for needle in ("HomeFibre 100", "OD-000101", "R799.00 excluding tax per month", "100 / 100 Mbps", "24 months",
                   "1 x AX1800 Wi-Fi router (OD-000201)", "Installation: R950.00", "Service terms.pdf",
                   "customer acceptance required", "early-termination-v1", "Rival ISP", "1 of 2 recorded tests passed",
                   "ICASA product notification: acknowledged by ICASA; effective 2026-11-01"):
        assert needle in md, needle
    assert "Callout" not in md                                   # disabled fee is not offered
    assert "Internal margin memo" not in md                      # internal-only documents are never indexed
    assert any(e.relation == "includes" and e.dst_id == ROUTER for e in c.edges)


def test_costs_suppliers_and_margins_are_never_indexed():
    row = fibre_row()
    row["definition"] = {**row["definition"], "costs": [{"name": "Wholesale access", "supplier": "Metro Fibre Wholesale", "amount": 480, "cadence": "Monthly"}],
                         "supplier": "Metro Fibre Wholesale"}
    md = BC.catalogue_product_card(row, NAMES, NOW).markdown.lower()
    for forbidden in ("wholesale access", "metro fibre", "480", "margin", "contribution"):
        assert forbidden not in md, forbidden


def test_market_research_is_indexed_as_a_labelled_unverified_note():
    row = fibre_row()
    row["definition"]["research"]["market"] = {"checked_at": "2026-10-17T10:00:00Z", "summary": "Rivals charge about R849 for 100/100 fibre [S1].",
                                               "sources": [{"id": "S1", "domain": "rival.example", "url": "https://rival.example/p"}]}
    md = BC.catalogue_product_card(row, NAMES, NOW).markdown
    assert "Market research (AI-assisted summary of public web pages, unverified)" in md
    assert "rival.example" in md and "https://rival.example" not in md          # domains only, no links in the index
    row["definition"]["research"]["market"]["summary"] = "x" * 5000
    assert len(BC.catalogue_product_card(row, NAMES, NOW).markdown) < 6000       # clipped


def test_suppliers_are_named_but_their_prices_never_appear():
    row = fibre_row(source_refs=[{"supplier_id": "s1", "preferred": True}, {"supplier_id": "s2", "preferred": False}])
    row["definition"]["sources"] = [{"supplier_id": "s1", "unit_cost": "612.50"}]      # would only arrive if the SQL leaked it
    md = BC.catalogue_product_card(row, NAMES, NOW, {"s1": "Network Devices Supply", "s2": "Metro Fibre Wholesale"}).markdown
    assert "## Suppliers" in md and "Network Devices Supply (preferred)" in md and "Metro Fibre Wholesale" in md
    assert "612" not in md


def test_draft_card_is_tagged_and_lower_importance():
    c = BC.catalogue_product_card(fibre_row(status="draft", launched_at=None), NAMES, NOW)
    assert "draft" in c.tags and "Draft (in development)" in c.markdown
    assert c.importance < BC.catalogue_product_card(fibre_row(), NAMES, NOW).importance


def test_direct_route_is_described_honestly():
    row = fibre_row()
    row["definition"]["readiness"] = {"tests_required": False, "icasa": {"required": False}}
    md = BC.catalogue_product_card(row, NAMES, NOW).markdown
    assert "Internal testing: skipped by decision" in md and "ICASA lodgment: not required" in md


def test_source_registered_and_sql_never_selects_costs():
    assert S.SOURCES["catalogue_products"].source_types == ("catalogue_product",)
    assert S.SOURCES["catalogue_products"].module == "inventory"
    src = open(SC.__file__, encoding="utf-8").read()
    assert "SELECT *" not in src.upper()
    assert "- 'costs' - 'supplier' - 'sources'" in SC._COLS      # stripped in SQL, not only in the builder
    assert "unit_cost" not in SC._COLS                           # supplier prices are never selected
    assert src.count("tenant_id = CAST(:") >= 3                  # every query is tenant filtered


def test_worker_import_order_has_no_circular_import():
    """The indexer worker imports sources_ext first. A module-level import of sources_ext from sources_catalogue is circular
    and crash-looped the knowledge_indexer container; each entry point must import cleanly in a fresh interpreter."""
    import subprocess, sys
    for entry in ("services.tenant_memory.knowledge.cards.sources_ext", "services.tenant_memory.knowledge.cards.sources",
                  "services.tenant_memory.knowledge.cards.sources_catalogue", "services.tenant_memory.knowledge.worker"):
        r = subprocess.run([sys.executable, "-c", f"import {entry}"], capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, f"{entry}: {r.stderr[-400:]}"


class FakeCatalogue:
    def __init__(self):
        self.rows = {FIBRE: fibre_row()}

    async def fetch(self, session, tenant, wm, limit):
        cards = [BC.catalogue_product_card(r, NAMES, NOW) for r in self.rows.values()]
        p = Page(cards=cards, rows=len(cards))
        p.last_ts = NOW
        return p

    async def ids(self, session, tenant):
        return {"catalogue_product": set(self.rows)}


def make(db, monkeypatch):
    monkeypatch.setenv("INDEX_SLEEP_S", "0")
    store = MemoryStore(now=lambda: NOW)

    @asynccontextmanager
    async def sess():
        yield None

    async def nosleep(_):
        return None

    src = {"catalogue_products": Source("catalogue_products", "inventory", ("catalogue_product",), db.fetch, db.ids)}
    return Indexer(store, EMB, sess, get_settings(), src, nosleep), store


def test_index_embeds_once_then_search_finds_the_product_and_delete_tombstones(monkeypatch):
    db = FakeCatalogue()
    ix, store = make(db, monkeypatch)
    first = run(ix.run_source(T, "catalogue_products", full=True))
    assert first["cards"] == 1 and first["chunks_embedded"] >= 1
    again = run(ix.run_source(T, "catalogue_products", full=True))
    assert again["chunks_embedded"] == 0 and again["chunks_unchanged"] >= 1       # unchanged content is not re-embedded
    scope = AccessScope(tenant_id=T, user_id="u1", roles=frozenset({"admin"}), is_admin=True)
    retr = KnowledgeRetriever(store, EMB, now=lambda: NOW)
    hits = run(retr.search("home fibre 100 mbps with included wifi router", scope, Filters(source_types=["catalogue_product"]), k=5)).hits
    assert hits and hits[0].chunk.source_type == "catalogue_product" and "OD-000101" in hits[0].chunk.markdown
    other = AccessScope(tenant_id="22222222-2222-2222-2222-222222222222", user_id="u2", roles=frozenset({"admin"}), is_admin=True)
    assert not run(retr.search("home fibre", other, Filters(source_types=["catalogue_product"]), k=5)).hits   # tenant isolation
    db.rows.clear()
    rep = run(ix.run_source(T, "catalogue_products", full=True))
    assert rep["tombstoned"] == 1
    assert not run(retr.search("home fibre", scope, Filters(source_types=["catalogue_product"]), k=5)).hits


def test_identification_and_fee_policies_are_in_the_card_but_commission_is_not():
    row = fibre_row()
    row["definition"].update({"barcode": {"value": "2000000000015", "format": "EAN-13", "source": "generated"}, "identifiers": ["Serial number", "MAC address"],
                              "provisioning": {"protocol": "TR-069", "profile": "ONT-Home-100"},
                              "fee_policies": [{"policy_id": "p1", "name": "Early termination 24m", "version": 2, "summary": "Recovers the discount and install cost pro rata"}],
                              "channels": [{"channel": "Field sales", "commission_type": "percent", "value": "12.5"}]})
    md = BC.catalogue_product_card(row, NAMES, NOW).markdown
    for needle in ("2000000000015", "Serial number, MAC address", "TR-069", "ONT-Home-100", "Early termination 24m (version 2)", "Recovers the discount"):
        assert needle in md, needle
    assert "12.5" not in md and "commission" not in md.lower() and "Field sales" not in md


def test_fact_sheet_card_and_source_registration():
    row = {"id": "a1", "product_id": FIBRE, "product_number": "OD-000201", "product_name": "AX1800 Wi-Fi router", "filename": "ax1800.pdf",
           "text": "The AX1800 delivers 1800 Mbps over dual bands."}
    c = BC.catalogue_factsheet_card(row, NOW)
    assert c.source_type == "catalogue_factsheet" and "1800 Mbps" in c.markdown and "AX1800 Wi-Fi router" in c.title
    assert any(e.relation == "describes" and e.dst_id == FIBRE for e in c.edges)
    assert S.SOURCES["catalogue_factsheets"].source_types == ("catalogue_factsheet",)
    src = open(SC.__file__, encoding="utf-8").read()
    assert "a.tenant_id = CAST(:tenant_id AS uuid)" in src and "SELECT *" not in src.upper()
