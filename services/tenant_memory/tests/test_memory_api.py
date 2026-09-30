"""tenant_memory service against a real Postgres (TEST_DATABASE_URL).

Agents recall from and write to this service on every turn, so these pin:
tenant isolation, recall ranking, authorship, summaries and the OKF skill
lifecycle. Each test works in its own fresh tenant.

    TEST_DATABASE_URL=postgresql://…/omnidome_test python scripts/setup_test_db.py
    cd services/tenant_memory && python -m pytest tests -q
"""
import os
import sys
import uuid

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.common import testdb  # noqa: E402

testdb.use_test_database()

from fastapi.testclient import TestClient  # noqa: E402

from services.tenant_memory.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
    testdb.reset_engines()


@pytest.fixture
def tenant():
    return testdb.new_tenant("memory test")


def write(client, tenant, **fields):
    body = {"source_type": "test", "title": "note", "content": "text", **fields}
    r = client.post("/api/v1/memories", json=body, headers=testdb.headers(tenant))
    assert r.status_code == 201, r.text
    return r.json()


# ── Entries ─────────────────────────────────────────────────────────────────

def test_an_agent_actor_is_kept_in_metadata_not_as_created_by(client, tenant):
    # Agents write with ids that are not users; created_by is an FK to users.
    agent_actor = uuid.uuid4()
    r = client.post("/api/v1/memories", json={"source_type": "agent_action", "title": "t", "content": "c"},
                    headers=testdb.headers(tenant, agent_actor))
    assert r.status_code == 201, r.text
    assert r.json()["created_by"] is None and r.json()["metadata"]["actor_id"] == str(agent_actor)


def test_a_real_user_is_recorded_as_created_by(client, tenant):
    user = testdb.new_user(tenant)
    r = client.post("/api/v1/memories", json={"source_type": "note", "title": "t", "content": "c"},
                    headers=testdb.headers(tenant, user))
    assert r.json()["created_by"] == str(user) and "actor_id" not in r.json()["metadata"]


def test_entries_are_invisible_to_other_tenants(client, tenant):
    other = testdb.new_tenant("other")
    e = write(client, tenant, title="Thandi retention deal", content="15% off for 6 months")
    h = testdb.headers(other)
    assert client.get(f"/api/v1/memories/{e['id']}", headers=h).status_code == 404
    assert client.patch(f"/api/v1/memories/{e['id']}", json={"title": "x"}, headers=h).status_code == 404
    assert client.get("/api/v1/memories", headers=h).json()["items"] == []
    assert client.get("/api/v1/recall", params={"q": "Thandi", "match": "any"}, headers=h).json()["entries"] == []


def test_list_filters(client, tenant):
    h = testdb.headers(tenant)
    write(client, tenant, module="sales", scope_key="lead:1", tags=["vip"], title="Deal won", source_id="run-1")
    write(client, tenant, module="support", scope_key="ticket:9", title="Outage", source_type="agent_action")
    get = lambda **p: [e["title"] for e in client.get("/api/v1/memories", params=p, headers=h).json()["items"]]  # noqa: E731
    assert get(module="sales") == ["Deal won"]
    assert get(scope_key="ticket:9") == ["Outage"]
    assert get(source_type="agent_action") == ["Outage"]
    assert get(source_id="run-1") == ["Deal won"]
    assert get(tag="vip") == ["Deal won"]
    assert get(q="outage") == ["Outage"]


def test_archived_entries_leave_lists_and_recall_until_asked_for(client, tenant):
    h = testdb.headers(tenant)
    e = write(client, tenant, title="Old router note", content="replaced router")
    r = client.patch(f"/api/v1/memories/{e['id']}", json={"archived": True}, headers=h)
    assert r.status_code == 200 and r.json()["archived_at"]
    assert client.get("/api/v1/memories", headers=h).json()["items"] == []
    assert len(client.get("/api/v1/memories", params={"include_archived": "true"}, headers=h).json()["items"]) == 1
    assert client.get("/api/v1/recall", params={"q": "router"}, headers=h).json()["entries"] == []


def test_invalid_fields_are_rejected(client, tenant):
    h = testdb.headers(tenant)
    assert client.post("/api/v1/memories", json={"source_type": "x", "title": "t", "content": "c",
                                                 "visibility": "public"}, headers=h).status_code == 422
    assert client.post("/api/v1/memories", json={"source_type": "x", "title": "", "content": "c"},
                       headers=h).status_code == 422
    assert client.patch(f"/api/v1/memories/{uuid.uuid4()}", json={}, headers=h).status_code == 400


# ── Recall ──────────────────────────────────────────────────────────────────

def test_a_whole_question_recalls_with_match_any_but_not_match_all(client, tenant):
    h = testdb.headers(tenant)
    write(client, tenant, title="Thandi Mokoena agreement", content="We agreed 15% off for six months.")
    question = {"q": "what discount did we give Thandi last quarter?"}
    assert client.get("/api/v1/recall", params=question, headers=h).json()["entries"] == []
    hits = client.get("/api/v1/recall", params={**question, "match": "any"}, headers=h).json()["entries"]
    assert [e["title"] for e in hits] == ["Thandi Mokoena agreement"]


def test_match_any_ranks_the_best_match_first(client, tenant):
    h = testdb.headers(tenant)
    write(client, tenant, title="Router firmware", content="router updated")
    write(client, tenant, title="Thandi router swap", content="Thandi Mokoena got a new router, Thandi happy")
    hits = client.get("/api/v1/recall", params={"q": "Thandi router", "match": "any"}, headers=h).json()["entries"]
    assert [e["title"] for e in hits] == ["Thandi router swap", "Router firmware"]


def test_recall_scopes_to_a_module_and_includes_its_summaries(client, tenant):
    h = testdb.headers(tenant)
    write(client, tenant, module="retention", title="Save offer", content="offer")
    write(client, tenant, module="sales", title="Quote sent", content="quote")
    client.put("/api/v1/summaries/retention:overview", headers=h,
               json={"scope_key": "retention:overview", "module": "retention", "title": "Retention", "summary": "Two saves."})
    r = client.get("/api/v1/recall", params={"module": "retention"}, headers=h).json()
    assert [e["title"] for e in r["entries"]] == ["Save offer"]
    assert [s["summary"] for s in r["summaries"]] == ["Two saves."]


# ── Summaries ───────────────────────────────────────────────────────────────

def test_summary_upsert_keeps_one_row_per_scope(client, tenant):
    h = testdb.headers(tenant)
    body = {"scope_key": "lead:7", "module": "sales", "title": "Lead 7", "summary": "v1"}
    first = client.put("/api/v1/summaries/lead:7", json=body, headers=h).json()
    second = client.put("/api/v1/summaries/lead:7", json={**body, "summary": "v2"}, headers=h).json()
    assert first["id"] == second["id"] and second["summary"] == "v2"
    assert [s["summary"] for s in client.get("/api/v1/summaries", headers=h).json()] == ["v2"]


def test_summary_scope_key_must_match_the_path(client, tenant):
    body = {"scope_key": "lead:8", "title": "t", "summary": "s"}
    assert client.put("/api/v1/summaries/lead:9", json=body, headers=testdb.headers(tenant)).status_code == 400


# ── OKF skills ──────────────────────────────────────────────────────────────

def skill(client, tenant, **fields):
    body = {"skill_name": "Win-back", "description": "d", "source_agent_type": "support",
            "target_agent_types": ["support"], "tools_required": ["billing_get_balance"],
            "guidance_prompt": "Check the balance first.", **fields}
    r = client.post("/api/v1/skills", json=body, headers=testdb.headers(tenant))
    assert r.status_code == 201, r.text
    return r.json()


def test_skills_list_by_target_and_untargeted_skills_apply_to_everyone(client, tenant):
    h = testdb.headers(tenant)
    skill(client, tenant, skill_name="For support")
    skill(client, tenant, skill_name="For everyone", target_agent_types=[])
    names = lambda agent: sorted(s["skill_name"] for s in client.get(  # noqa: E731
        "/api/v1/skills", params={"target_agent_type": agent}, headers=h).json()["items"])
    assert names("support") == ["For everyone", "For support"]
    assert names("retention") == ["For everyone"]


def test_transfer_adds_the_target_and_is_remembered(client, tenant):
    h = testdb.headers(tenant)
    s = skill(client, tenant)
    r = client.post(f"/api/v1/skills/{s['id']}/transfer", json={"target_agent_type": "retention"}, headers=h)
    assert r.status_code == 200 and r.json()["target_agent_types"] == ["support", "retention"]
    again = client.post(f"/api/v1/skills/{s['id']}/transfer", json={"target_agent_type": "retention"}, headers=h)
    assert again.json()["target_agent_types"] == ["support", "retention"]          # no duplicate target
    logged = client.get("/api/v1/memories", params={"source_type": "skill_transfer"}, headers=h).json()["items"]
    assert logged and logged[0]["scope_key"] == "agent:retention"


def test_deactivated_skills_stop_applying_and_reregistering_revives_them(client, tenant):
    h = testdb.headers(tenant)
    s = skill(client, tenant)
    assert client.post(f"/api/v1/skills/{s['id']}/deactivate", headers=h).json()["is_active"] is False
    assert client.get("/api/v1/skills", headers=h).json()["items"] == []
    assert client.post(f"/api/v1/skills/{s['id']}/transfer", json={"target_agent_type": "x"},
                       headers=h).status_code == 404
    revived = skill(client, tenant)
    assert revived["id"] == s["id"] and revived["is_active"] is True


def test_skills_are_invisible_to_other_tenants(client, tenant):
    s = skill(client, tenant)
    h = testdb.headers(testdb.new_tenant("other"))
    assert client.get("/api/v1/skills", headers=h).json()["items"] == []
    assert client.post(f"/api/v1/skills/{s['id']}/deactivate", headers=h).status_code == 404
    assert client.post(f"/api/v1/skills/{s['id']}/transfer", json={"target_agent_type": "x"},
                       headers=h).status_code == 404
