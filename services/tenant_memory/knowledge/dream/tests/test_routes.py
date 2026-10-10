import os
import uuid

import pytest

os.environ.setdefault("AUTH_MODE", "header")
os.environ["AUTH_DB_ENFORCE"] = "false"
os.environ["AUTH_ENFORCE_MODULES"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from services.tenant_memory.knowledge import routes  # noqa: E402
from services.tenant_memory.knowledge.dream import routes as dream_routes  # noqa: E402
from services.tenant_memory.main import app  # noqa: E402

from .helpers import T1, T2, make_env, mk_card, run  # noqa: E402


def h(tenant, roles="admin"):
    return {"X-Tenant-Id": tenant, "X-User-Id": str(uuid.uuid4()), "X-Roles": roles, "X-Modules": "memory,support"}


@pytest.fixture
def env():
    e = make_env()
    e.index(T1, mk_card("ticket", "t1", "Soweto outage", "fibre cut", importance=0.9), mk_card("price", "a", "Router price", "router costs r499 per month fibre line"),
            mk_card("price", "b", "Router price", "router costs r599 per month fibre line"))
    e.renderer.script[("ticket", "t1")] = mk_card("ticket", "t1", "Soweto outage", "fibre repaired", importance=0.9)
    routes.set_runtime(e.store, e.emb)
    dream_routes.set_engine(e.engine)
    yield e
    routes._runtime.clear()
    dream_routes.set_engine(None)


@pytest.fixture
def client(env):
    return TestClient(app)


BASE = "/api/v1/knowledge/dream"


def test_every_endpoint_needs_an_admin(client):
    for method, path in (("get", "/status"), ("get", "/runs"), ("get", "/findings"), ("post", "/run"), ("get", "/settings")):
        r = getattr(client, method)(BASE + path, headers=h(T1, "agent"))
        assert r.status_code == 403, (method, path)
    assert client.post(f"{BASE}/findings/x/resolve", json={"action": "accept"}, headers=h(T1, "agent")).status_code == 403


def test_status_before_any_run_is_an_honest_empty_state(client):
    s = client.get(BASE + "/status", headers=h(T1)).json()
    assert s["ready"] is True and s["last_run"] is None and s["trend"] == [] and s["findings"]["total_open"] == 0
    assert s["jev"] == {"enabled": False, "credentials": True, "external": True} and s["phases"][0] == "drift" and s["kill_switch"] is False
    assert s["settings"]["window_start"] == "02:30" and s["settings"]["timezone"] == "Africa/Johannesburg"
    assert client.get(BASE + "/runs", headers=h(T1)).json() == {"runs": []}
    assert client.get(BASE + "/findings", headers=h(T1)).json() == {"findings": []}


def test_manual_run_defaults_to_dry_run_and_is_queued_for_the_worker(client, env):
    r = client.post(BASE + "/run", json={}, headers=h(T1))
    assert r.status_code == 202 and r.json()["dry_run"] is True and r.json()["status"] == "queued"
    job = env.store.jobs[-1]
    assert job["kind"] == "dream" and job["params"]["dry_run"] is True and job["tenant_id"] == T1
    assert client.post(BASE + "/run", json={"phases": ["nope"]}, headers=h(T1)).status_code == 400
    env.killed[0] = True
    assert client.post(BASE + "/run", json={}, headers=h(T1)).status_code == 409


def test_inline_run_then_status_runs_detail_and_findings(client, env):
    r = client.post(BASE + "/run", json={"dry_run": False, "inline": True}, headers=h(T1))
    assert r.status_code == 202 and r.json()["status"] == "completed" and r.json()["dry_run"] is False
    rid = r.json()["id"]
    s = client.get(BASE + "/status", headers=h(T1)).json()
    assert s["last_run"]["id"] == rid and s["last_run"]["health_score"] is not None and s["trend"][-1]["health_score"] == s["last_run"]["health_score"]
    assert s["cards"]["live_sources"] >= 3 and s["next_window"]
    runs = client.get(BASE + "/runs", headers=h(T1)).json()["runs"]
    assert runs[0]["id"] == rid and "phase_results" not in runs[0]
    d = client.get(f"{BASE}/runs/{rid}", headers=h(T1)).json()
    assert list(d["phase_results"]) == s["phases"] and d["report"]["health_score"] == d["health_score"]
    assert client.get(f"{BASE}/runs/{rid}", headers=h(T2)).status_code == 404                  # another tenant's run
    fs = client.get(BASE + "/findings", params={"type": "content_drift"}, headers=h(T1)).json()["findings"]
    assert len(fs) == 1 and fs[0]["status"] == "auto_applied"
    assert client.get(BASE + "/findings", params={"severity": "critical"}, headers=h(T1)).json()["findings"] == []
    assert client.get(BASE + "/findings", headers=h(T2)).json()["findings"] == []


def test_resolve_accept_dismiss_apply_and_conflicts(client, env):
    client.post(BASE + "/run", json={"dry_run": False, "inline": True, "phases": ["drift", "relevance"]}, headers=h(T1))
    conflict = client.get(BASE + "/findings", params={"type": "conflict"}, headers=h(T1)).json()["findings"][0]
    r = client.post(f"{BASE}/findings/{conflict['id']}/resolve", json={"action": "apply"}, headers=h(T1))
    assert r.status_code == 400                                                                 # a conflict has no automatic fix
    r = client.post(f"{BASE}/findings/{conflict['id']}/resolve", json={"action": "dismiss", "note": "both prices valid (plans differ)"}, headers=h(T1))
    assert r.json()["status"] == "dismissed" and r.json()["resolved_by"] and r.json()["resolution"]["note"].startswith("both")
    assert client.post(f"{BASE}/findings/{conflict['id']}/resolve", json={"action": "accept"}, headers=h(T1)).status_code == 409
    assert client.post(f"{BASE}/findings/{conflict['id']}/resolve", json={"action": "accept"}, headers=h(T2)).status_code == 404
    assert client.post(f"{BASE}/findings/{conflict['id']}/resolve", json={"action": "zap"}, headers=h(T1)).status_code == 422
    # apply: re-run the refresh of an auto-applied drift fix from its live source
    env.renderer.script[("ticket", "t1")] = mk_card("ticket", "t1", "Soweto outage", "fibre repaired and monitored", importance=0.9)
    drift = client.get(BASE + "/findings", params={"type": "content_drift"}, headers=h(T1)).json()["findings"][0]
    r = client.post(f"{BASE}/findings/{drift['id']}/resolve", json={"action": "apply"}, headers=h(T1))
    assert r.status_code == 200 and r.json()["status"] == "applied" and "monitored" in env.live(T1, "ticket", "t1")[0].markdown


def test_settings_roundtrip_validation_and_clamps(client, env):
    r = client.put(BASE + "/settings", json={"enabled": True, "window_start": "03:15", "jev_enabled": True, "jev_max_calls": 7, "jev_approve": 0.95}, headers=h(T1))
    assert r.status_code == 200 and r.json()["settings"]["window_start"] == "03:15" and r.json()["settings"]["jev_max_calls"] == 7
    g = client.get(BASE + "/settings", headers=h(T1)).json()
    assert g["overrides"]["enabled"] is True and g["settings"]["jev_approve"] == 0.95 and "window_start" in g["tunable"]
    assert client.put(BASE + "/settings", json={"jev_approve": 0.5}, headers=h(T1)).status_code == 422          # looser than the calibrated 0.80 floor
    assert client.put(BASE + "/settings", json={"jev_reject": 0.5}, headers=h(T1)).status_code == 422
    assert client.put(BASE + "/settings", json={"timezone": "Mars/Base"}, headers=h(T1)).status_code == 400
    assert client.put(BASE + "/settings", json={"window_start": "25:00"}, headers=h(T1)).status_code == 400
    r = client.put(BASE + "/settings", json={"jev_max_calls": None}, headers=h(T1))                           # null = back to the default
    assert "jev_max_calls" not in r.json()["overrides"]
    assert client.get(BASE + "/settings", headers=h(T2)).json()["overrides"] == {}                           # per-tenant
    s = client.get(BASE + "/status", headers=h(T1)).json()
    assert s["settings"]["enabled"] is True and s["next_window"] and s["jev"]["enabled"] is True


def test_settings_do_not_leak_between_tenants_in_the_engine(env):
    run(env.dstore.put_settings(T1, {"jev_enabled": True}, "u"))
    assert run(env.engine.settings_for(T1)).jev_enabled is True and run(env.engine.settings_for(T2)).jev_enabled is False
