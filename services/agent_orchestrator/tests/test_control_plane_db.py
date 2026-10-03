"""Tenant isolation and durable state against a disposable *_test Postgres DB."""

import os
import uuid

import pytest

from services.common import testdb

testdb.use_test_database()
os.environ["VOICE_DEV_SKIP_DB"] = "true"
os.environ["AGENT_JOB_WORKER_ENABLED"] = "false"
os.environ["AUTH_ENFORCE_RBAC"] = "false"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from services.agent_orchestrator.main import app, guard  # noqa: E402
from services.agent_orchestrator.models import Base, AgentJob, AgentTenantBudget, RegisteredAgent  # noqa: E402


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=testdb.sync_engine(), tables=[RegisteredAgent.__table__, AgentTenantBudget.__table__, AgentJob.__table__])
    old = guard.enforce_modules
    guard.enforce_modules = False
    try:
        with TestClient(app) as instance:
            yield instance
    finally:
        guard.enforce_modules = old
        testdb.reset_engines()


def headers(tenant):
    return {**testdb.headers(tenant), "X-Roles": "admin"}


def test_registered_agents_are_tenant_scoped_and_survive_new_requests(client):
    one, two = testdb.new_tenant("agent roster A"), testdb.new_tenant("agent roster B")
    employee_id = uuid.uuid4()
    body = {"employee_id": str(employee_id), "full_name": "Test Agent", "job_title": "Analyst",
            "department": "Operations", "financial_limit": 1000}
    first = client.post("/api/agents/register", json=body, headers=headers(one))
    assert first.status_code == 200, first.text
    agent_type = first.json()["agent_type"]
    again = client.post("/api/agents/register", json={**body, "full_name": "Renamed Agent"}, headers=headers(one))
    assert again.status_code == 200
    ours = client.get("/api/agents/registered", headers=headers(one)).json()
    theirs = client.get("/api/agents/registered", headers=headers(two)).json()
    assert len([item for item in ours if item["agent_type"] == agent_type]) == 1
    assert ours[0]["name"] == "Renamed Agent"
    assert theirs == []

    created = client.post("/api/agents/jobs", json={"agent_type": agent_type,
                          "objective": "Draft a concise operations summary for review."}, headers=headers(one))
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]
    assert client.get(f"/api/agents/jobs/{job_id}", headers=headers(two)).status_code == 404
    assert client.post(f"/api/agents/jobs/{job_id}/pause", headers=headers(one)).json()["status"] == "paused"
    assert client.post(f"/api/agents/jobs/{job_id}/resume", headers=headers(one)).json()["status"] == "queued"

    with testdb.sync_engine().begin() as conn:
        conn.execute(text("UPDATE agent_jobs SET status='awaiting_review' WHERE id=:id"), {"id": job_id})
    accepted = client.post(f"/api/agents/jobs/{job_id}/accept", headers=headers(one))
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "completed"
    assert accepted.json()["reviewed_by"] == str(one)


def test_agent_budget_blocks_new_work(client):
    tenant = testdb.new_tenant("agent budget")
    employee_id = uuid.uuid4()
    registered = client.post("/api/agents/register", json={"employee_id": str(employee_id),
                             "full_name": "Budget Agent"}, headers=headers(tenant))
    agent_type = registered.json()["agent_type"]
    changed = client.put(f"/api/agents/registered/{employee_id}/budget",
                         json={"monthly_budget_usd": 0}, headers=headers(tenant))
    assert changed.status_code == 200, changed.text
    blocked = client.post("/api/agents/jobs", json={"agent_type": agent_type,
                          "objective": "Draft a budget review summary for the manager."}, headers=headers(tenant))
    assert blocked.status_code == 409
