"""Runs the pgvector store against a REAL server. Skipped unless KNOWLEDGE_TEST_DB_URL is set, e.g.

    docker run -d --name kt -e POSTGRES_PASSWORD=x -p 55432:5432 pgvector/pgvector:pg16
    KNOWLEDGE_TEST_DB_URL=postgresql://postgres:x@localhost:55432/postgres EMBEDDING_DIM=64 \
        python -m pytest services/tenant_memory/knowledge/tests/test_pg_integration.py -q

The URL must be a superuser; the test creates the knowledge_app role and queries through it so RLS applies.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest

URL = os.getenv("KNOWLEDGE_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not URL, reason="KNOWLEDGE_TEST_DB_URL not set")


def test_roundtrip_hybrid_rls_and_graph(monkeypatch):
    from sqlalchemy.engine import make_url

    from services.tenant_memory.knowledge.embeddings import HashEmbedder
    from services.tenant_memory.knowledge.kdata import AccessScope, Chunk, Edge, Filters, content_hash
    from services.tenant_memory.knowledge.retrieval import KnowledgeRetriever
    from services.tenant_memory.knowledge.store_pg import PgVectorStore

    monkeypatch.setenv("EMBEDDING_DIM", os.getenv("EMBEDDING_DIM", "64"))
    monkeypatch.setenv("KNOWLEDGE_APP_PASSWORD", "app-test-pw")
    from services.tenant_memory.knowledge.config import get_settings

    owner = PgVectorStore(URL, get_settings(), admin_url=URL)
    app_url = make_url(URL).set(username="knowledge_app", password="app-test-pw").render_as_string(hide_password=False)

    async def go():
        await owner.ensure_schema()
        store = PgVectorStore(app_url, get_settings())
        emb = HashEmbedder(int(os.getenv("EMBEDDING_DIM", "64")))
        t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        for t in (t1, t2):
            md = "# Soweto outage\nfibre outage soweto"
            c = Chunk(t, "ticket", "x1", 0, "support", "Soweto outage", md, content_hash(md), as_of=now, embedding_model=emb.model,
                      embedding=(await emb.embed_documents([md]))[0], tags=["net"])
            assert (await store.upsert_chunks(t, [c]))["inserted"] == 1
            assert (await store.upsert_chunks(t, [c]))["unchanged"] == 1
        await store.replace_edges(t1, "ticket:x1", [Edge("ticket", "x1", "customer", "c1", "raised_by")])
        scope = AccessScope(t1, "u", frozenset(), frozenset(), True)
        res = await KnowledgeRetriever(store, emb).search("outage soweto", scope, Filters(modules=["support"]), k=3)
        assert [h.chunk.tenant_id for h in res.hits] == [t1]
        assert (await store.traverse(t1, [("ticket", "x1")], 2, None, 10))[0]["node_id"] == "c1"
        # RLS: a wrong tenant context sees nothing even with an explicit filter for t1's id
        async with store._tx(t2) as conn:
            from sqlalchemy import text
            n = (await conn.execute(text("SELECT count(*) FROM knowledge_chunks WHERE tenant_id = CAST(:t AS uuid)"), {"t": t1})).scalar()
            assert n == 0
        assert (await store.erase(t1))["chunks"] == 1
        assert (await store.erase(t2))["chunks"] == 1

    asyncio.run(go())
