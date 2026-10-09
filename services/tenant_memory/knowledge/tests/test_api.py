"""Endpoint smoke tests with an in-memory store and the hash embedder (no database, no network)."""
import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest

os.environ.setdefault("AUTH_MODE", "header")
os.environ["AUTH_DB_ENFORCE"] = "false"
os.environ["AUTH_ENFORCE_MODULES"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from services.tenant_memory.knowledge import routes  # noqa: E402
from services.tenant_memory.knowledge.embeddings import HashEmbedder  # noqa: E402
from services.tenant_memory.knowledge.kdata import Chunk, content_hash  # noqa: E402
from services.tenant_memory.knowledge.store_memory import MemoryStore  # noqa: E402
from services.tenant_memory.main import app  # noqa: E402

T1, T2 = str(uuid.uuid4()), str(uuid.uuid4())


@pytest.fixture
def client():
    store, emb = MemoryStore(), HashEmbedder(32)

    async def seed():
        for t in (T1, T2):
            md = f"---\nsource: ticket\n---\n# Soweto outage {t[:4]}\nfibre outage soweto"
            await store.upsert_chunks(t, [Chunk(t, "ticket", "x1", 0, "support", "Soweto outage", md, content_hash(md),
                                                as_of=datetime.now(timezone.utc), embedding_model=emb.model,
                                                embedding=(await emb.embed_documents([md]))[0], source_ref={"deep_link": "/dashboard/support"})])

    asyncio.run(seed())
    routes.set_runtime(store, emb)
    yield TestClient(app)
    routes._runtime.clear()


def h(tenant, roles="", user=None):
    return {"X-Tenant-Id": tenant, "X-User-Id": user or str(uuid.uuid4()), "X-Roles": roles}


def test_search_and_context_are_tenant_scoped(client):
    r = client.post("/api/v1/knowledge/search", json={"query": "outage in soweto"}, headers=h(T1))
    assert r.status_code == 200, r.text
    res = r.json()["results"]
    assert len(res) == 1 and T1[:4] in res[0]["markdown"] and T2[:4] not in res[0]["markdown"]
    assert res[0]["deep_link"] == "/dashboard/support" and res[0]["source_type"] == "ticket"
    ctx = client.post("/api/v1/knowledge/context", json={"query": "soweto outage", "budget_tokens": 600}, headers=h(T2)).json()
    assert ctx["citations"][0]["ref"] == 1 and T1[:4] not in ctx["context"]


def test_admin_endpoints_need_admin_and_erase_needs_confirmation(client):
    assert client.get("/api/v1/knowledge/admin/coverage", headers=h(T1)).status_code == 403
    assert client.post("/api/v1/knowledge/admin/reindex", json={}, headers=h(T1)).status_code == 403
    adm = h(T1, "admin")
    cov = client.get("/api/v1/knowledge/admin/coverage", headers=adm).json()
    assert cov["sources"][0]["source_type"] == "ticket" and "customer" in cov["not_yet_indexed"]
    assert client.post("/api/v1/knowledge/admin/reindex", json={"sources": ["nope"]}, headers=adm).status_code == 400
    assert client.post("/api/v1/knowledge/admin/reindex", json={"modules": ["crm"], "full": True}, headers=adm).status_code == 202
    assert client.post("/api/v1/knowledge/admin/erase", json={"entire_tenant": True}, headers=adm).status_code == 400
    assert client.post("/api/v1/knowledge/admin/erase", json={"entire_tenant": True, "confirm": "ERASE"}, headers=adm).json()["erased"]["chunks"] == 1
    assert client.post("/api/v1/knowledge/search", json={"query": "outage soweto"}, headers=h(T1)).json()["results"] == []
    assert client.post("/api/v1/knowledge/search", json={"query": "outage soweto"}, headers=h(T2)).json()["results"]


def test_metric_fact_write_requires_permission(client):
    body = {"metric_key": "revenue", "period_start": "2026-03-01", "period_end": "2026-03-31", "value": 1, "method": "sum", "written_by": "bi_semantic"}
    assert client.post("/api/v1/metrics/facts", json=body, headers=h(T1, "admin")).status_code == 403
    assert client.post("/api/v1/metrics/facts", json={**body, "written_by": "llm"}, headers={**h(T1), "X-Permissions": "metrics.write"}).status_code == 422


def test_disabled_layer_is_503_not_500():
    routes._runtime.clear()
    os.environ.pop("KNOWLEDGE_DB_URL", None)
    r = TestClient(app).post("/api/v1/knowledge/search", json={"query": "anything"}, headers=h(T1))
    assert r.status_code == 503
