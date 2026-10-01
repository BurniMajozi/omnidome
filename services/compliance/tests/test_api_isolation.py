"""End-to-end API tests on SQLite: tenant isolation, mass assignment, seeder gone, scoring empty state,
EMP201 prepare / mark-filed flow, 501 on the fake filing routes, no invented values, role tiers.

Postgres-only SQL (payslip aggregate) is stubbed; everything else runs the real routes."""
import asyncio
import uuid
from datetime import date

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.common import db as common_db
from services.common.auth import AuthContext, get_auth_context
from services.common.db import set_tenant_context
from services.compliance import database as cdb
from services.compliance.sa_calendar import period_bounds, sast_today
from services.compliance.cross_service import router as cross_router
from services.compliance.routes import statutory as statutory_routes
from services.compliance.routes.compliance import breach_router, popi_router
from services.compliance.routes.contracts import router as contracts_router
from services.compliance.routes.hr_operations import vehicle_router
from services.compliance.routes.operations import doc_router, score_router
from services.compliance.routes.regulatory import hs_router
from services.compliance.routes.statutory import router as statutory_router

T1 = "00000000-0000-0000-0000-000000000001"
T2 = "00000000-0000-0000-0000-000000000002"
ADMIN = "owner"
PERIOD = sast_today().strftime("%Y-%m")  # filed_at (today) must fall on/after the period start


@pytest.fixture
def env(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'c.db'}"
    engine = create_async_engine(url)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(cdb.Base.metadata.create_all)

    asyncio.run(setup())
    Session = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    for r in (contracts_router, hs_router, popi_router, breach_router, vehicle_router, score_router, doc_router,
              cross_router, statutory_router):
        app.include_router(r, prefix="/api/v1")

    async def fake_auth(request: Request):
        tid = uuid.UUID(request.headers.get("x-t", T1))
        roles = [r for r in request.headers.get("x-r", "").split(",") if r]
        set_tenant_context(tid)
        return AuthContext(user_id=uuid.UUID(int=7), tenant_id=tid, roles=roles)

    async def fake_db():
        async with Session() as s:
            yield s
            await s.commit()

    app.dependency_overrides[get_auth_context] = fake_auth
    app.dependency_overrides[common_db.get_async_session] = fake_db
    with TestClient(app) as client:
        client.session_factory = Session
        yield client
    asyncio.run(engine.dispose())


def H(tenant=T1, roles=ADMIN):
    return {"x-t": tenant, "x-r": roles}


def count(client, model):
    async def run():
        async with client.session_factory() as s:
            return (await s.execute(select(func.count(model.id)))).scalar()
    return asyncio.run(run())


def test_dsar_list_get_update_never_cross_tenants(env):
    r = env.post("/api/v1/popi/dsar", json={"data_subject_name": "A", "request_type": "access"}, headers=H(T1))
    assert r.status_code == 200, r.text
    dsar_id = r.json()["id"]
    assert r.json()["tenant_id"] == T1 and r.json()["status"] == "received"
    assert env.get("/api/v1/popi/dsar", headers=H(T2)).json()["items"] == []
    assert env.get("/api/v1/popi/dsar/dashboard", headers=H(T2)).json()["total"] == 0
    assert env.put(f"/api/v1/popi/dsar/{dsar_id}/complete", json={}, headers=H(T2)).status_code == 404
    assert env.put(f"/api/v1/popi/dsar/{dsar_id}/complete", json={}, headers=H(T1)).status_code == 200
    assert len(env.get("/api/v1/popi/dsar", headers=H(T1)).json()["items"]) == 1


def test_breach_and_incident_idor(env):
    b = env.post("/api/v1/breaches/", json={"title": "t", "description": "d", "category": "popi", "severity": "high"}, headers=H(T1))
    assert b.status_code == 200, b.text
    bid = b.json()["id"]
    assert env.put(f"/api/v1/breaches/{bid}", json={"status": "resolved"}, headers=H(T2)).status_code == 404
    assert env.get("/api/v1/breaches/", headers=H(T2)).json()["items"] == []
    assert env.put(f"/api/v1/breaches/{bid}", json={"status": "resolved"}, headers=H(T1)).status_code == 200


def test_contracts_isolated_and_mass_assignment_rejected(env):
    body = {"contract_number": "C-1", "title": "T", "contract_type": "supplier", "counterparty_name": "X",
            "effective_date": "2026-01-01"}
    assert env.post("/api/v1/contracts/", json={**body, "tenant_id": T2}, headers=H(T1)).status_code == 422
    assert env.post("/api/v1/contracts/", json={**body, "id": 99}, headers=H(T1)).status_code == 422
    r = env.post("/api/v1/contracts/", json=body, headers=H(T1))
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json()["tenant_id"] == T1
    assert env.get(f"/api/v1/contracts/{cid}", headers=H(T2)).status_code == 404
    assert env.put(f"/api/v1/contracts/{cid}", json={"title": "z"}, headers=H(T2)).status_code == 404
    assert env.delete(f"/api/v1/contracts/{cid}", headers=H(T2)).status_code == 404
    assert env.get("/api/v1/contracts/", headers=H(T2)).json()["total"] == 0
    assert env.get("/api/v1/contracts/", headers=H(T1)).json()["total"] == 1


def test_dsar_mass_assignment_rejected(env):
    for evil in ({"tenant_id": T2}, {"status": "completed"}, {"due_date": "2020-01-01T00:00:00"}, {"id": 5}):
        r = env.post("/api/v1/popi/dsar", json={"data_subject_name": "A", "request_type": "access", **evil}, headers=H())
        assert r.status_code == 422, evil


def test_listener_scopes_even_without_explicit_filter(env):
    env.post("/api/v1/popi/dsar", json={"data_subject_name": "A", "request_type": "access"}, headers=H(T1))

    async def run():
        async with env.session_factory() as s:
            set_tenant_context(uuid.UUID(T2))
            other = (await s.execute(select(cdb.PopiDataAccessRequest))).scalars().all()
            set_tenant_context(uuid.UUID(T1))
            mine = (await s.execute(select(cdb.PopiDataAccessRequest))).scalars().all()
            return len(other), len(mine)
    assert asyncio.run(run()) == (0, 1)


def test_seeder_gone_reads_empty_and_write_nothing(env):
    for path in ("/cross-service/sales/contracts-sla", "/cross-service/technicians/fleet-safety",
                 "/cross-service/finance/statutory-status", "/cross-service/rica/subscriber-audit",
                 "/cross-service/call-center/popia-audit", "/cross-service/orchestrator/executive-summary"):
        r = env.get(f"/api/v1{path}", headers=H(T2))
        assert r.status_code == 200, (path, r.text)
    assert env.get("/api/v1/cross-service/sales/contracts-sla", headers=H(T2)).json()["total_contracts"] == 0
    fleet = env.get("/api/v1/cross-service/technicians/fleet-safety", headers=H(T2)).json()
    assert fleet["vehicles"] == [] and fleet["zero_incident_streak_days"] is None
    assert env.get("/api/v1/cross-service/finance/statutory-status", headers=H(T2)).json()["tax_obligations"] == []
    summ = env.get("/api/v1/cross-service/orchestrator/executive-summary", headers=H(T2)).json()
    assert summ["overall_compliance_score"] is None and summ["alerts"] == []
    for model in (cdb.Contract, cdb.ComplianceScore, cdb.VehicleRegistration, cdb.PopiDataAccessRequest,
                  cdb.TaxReturn, cdb.ComplianceDocument, cdb.HsIncident):
        assert count(env, model) == 0, model
    import services.compliance.cross_service as cs
    assert not hasattr(cs, "seed_demo_compliance_data")


def test_scores_empty_state_and_latest(env):
    r = env.post("/api/v1/scores/calculate", headers=H())
    assert r.status_code == 200, r.text
    assert all(s["score"] is None and s["status"] == "not_assessed" for s in r.json()["scores"])
    assert count(env, cdb.ComplianceScore) == 0
    latest = env.get("/api/v1/scores/latest", headers=H()).json()
    assert latest["overall_score"] is None
    o = env.post("/api/v1/scores/obligations", json={"category": "tax", "title": "VAT", "status": "compliant"}, headers=H())
    assert o.status_code == 200, o.text
    scores = env.post("/api/v1/scores/calculate", headers=H()).json()["scores"]
    tax = next(s for s in scores if s["category"] == "tax")
    assert tax["score"] == 100.0
    assert count(env, cdb.ComplianceScore) == 1
    row = env.get("/api/v1/scores/", headers=H(T2)).json()["items"]
    assert row == []                                       # other tenant sees nothing


def test_obligation_update_idor(env):
    o = env.post("/api/v1/scores/obligations", json={"category": "tax", "title": "VAT"}, headers=H(T1)).json()
    assert env.put(f"/api/v1/scores/obligations/{o['id']}", json={"status": "compliant"}, headers=H(T2)).status_code == 404


def test_role_tiers(env):
    body = {"data_subject_name": "A", "request_type": "access"}
    assert env.post("/api/v1/popi/dsar", json=body, headers=H(roles="viewer")).status_code == 403
    assert env.post("/api/v1/popi/dsar", json=body, headers=H(roles="compliance_officer")).status_code == 200
    assert env.get("/api/v1/popi/dsar", headers=H(roles="viewer")).status_code == 403          # subject data
    assert env.get("/api/v1/popi/dsar", headers=H(roles="hr_admin")).status_code == 200
    assert env.get("/api/v1/popi/dsar/dashboard", headers=H(roles="viewer")).status_code == 200  # counts only
    assert env.get("/api/v1/vehicles/", headers=H(roles="viewer")).status_code == 200
    assert env.post("/api/v1/cross-service/payroll-statutory/emp201/prepare", json={"period": "2026-09"},
                    headers=H(roles="viewer")).status_code == 403


def test_documents_metadata_cannot_set_file_path(env):
    r = env.post("/api/v1/documents/", json={"title": "x", "document_type": "other", "file_path": "/etc/passwd"}, headers=H())
    assert r.status_code == 422
    r = env.post("/api/v1/documents/", json={"title": "x", "document_type": "other"}, headers=H())
    assert r.status_code == 200 and r.json().get("file_path") is None
    assert env.post(f"/api/v1/documents/{r.json()['id']}/ocr", headers=H(T2)).status_code == 404


# ── EMP201 working paper flow ─────────────────────────────────────────
PATHS = ["/api/v1/statutory/emp201", "/api/v1/cross-service/payroll-statutory/emp201"]


def _stub_aggregate(monkeypatch, figures):
    async def fake(db, tenant, period):
        return figures
    monkeypatch.setattr(statutory_routes, "fetch_period_aggregate", fake)


REAL = {"employee_count": 3, "gross_remuneration": 30000.0, "paye": 4500.55, "uif_employee": 150.0,
        "uif_employer": 150.0, "sdl": 300.0, "net_pay": 24900.0, "total_liability": 5100.55, "run_ids": ["r1"]}
NONE = {k: None for k in REAL}
NONE["run_ids"] = []


@pytest.mark.parametrize("base", PATHS)
def test_prepare_and_mark_filed_flow(env, monkeypatch, base):
    _stub_aggregate(monkeypatch, REAL)
    r = env.post(f"{base}/prepare", json={"period": PERIOD}, headers=H(roles="hr_admin"))
    assert r.status_code == 200, r.text
    wp = r.json()
    assert wp["status"] == "PREPARED_NOT_FILED" and wp["paye_zar"] == 4500.55 and wp["rates_verified"] is False
    assert wp["due_date"] and "estimated" in wp["due_date_note"].lower() and "File manually on SARS eFiling" in wp["note"]
    assert wp["prn"] is None and wp["filed_by_this_service"] is False
    wid = wp["id"]
    # re-prepare updates the same row
    assert env.post(f"{base}/prepare", json={"period": PERIOD}, headers=H(roles="hr_admin")).json()["id"] == wid
    # another tenant cannot mark it filed
    mf = f"{base}/{wid}/mark-filed"
    good = {"prn": "1234567890123456", "filed_at": sast_today().isoformat()}
    assert env.post(mf, json=good, headers=H(T2, "hr_admin")).status_code == 404
    # compliance_officer (not hr/finance admin) cannot
    assert env.post(mf, json=good, headers=H(roles="compliance_officer")).status_code == 403
    assert env.post(mf, json={**good, "prn": "short"}, headers=H(roles="hr_admin")).status_code == 422
    assert env.post(mf, json={**good, "filed_at": "2999-01-01"}, headers=H(roles="hr_admin")).status_code == 422
    assert env.post(mf, json={**good, "filed_at": "2000-01-01"}, headers=H(roles="hr_admin")).status_code == 422
    ok = env.post(mf, json={**good, "receipt_reference": "REC-1"}, headers=H(roles="finance_admin"))
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "MARKED_FILED_BY_USER" and ok.json()["prn"] == "1234567890123456"
    assert ok.json()["marked_filed_by"] == str(uuid.UUID(int=7))
    assert env.post(mf, json=good, headers=H(roles="hr_admin")).status_code == 409
    assert env.post(f"{base}/prepare", json={"period": PERIOD}, headers=H(roles="hr_admin")).status_code == 409


def test_prepare_with_no_payroll_is_null_not_substituted(env, monkeypatch):
    _stub_aggregate(monkeypatch, NONE)
    wp = env.post("/api/v1/statutory/emp201/prepare", json={"period": "2026-09"}, headers=H()).json()
    assert wp["employee_count"] is None and wp["gross_remuneration_zar"] is None and wp["paye_zar"] is None
    assert "No paid payroll" in wp["note"] and wp["status"] == "PREPARED_NOT_FILED"
    assert env.post("/api/v1/statutory/emp201/prepare", json={"period": "bad"}, headers=H()).status_code == 422
    assert env.get("/api/v1/statutory/emp201", headers=H(T2)).json()["items"] == []


@pytest.mark.parametrize("path,body", [
    ("/payroll-statutory/emp201/file", {"period": "2026-09"}),
    ("/payroll-statutory/uif/submit", {"period": "2026-09", "declarer_name": "x"}),
    ("/payroll-statutory/uif/ui27-certificate", {"employee_id": "1", "reason_for_claim": "illness", "last_day_worked": "2026-01-01"}),
])
def test_fake_filing_routes_return_501(env, path, body):
    r = env.post(f"/api/v1/cross-service{path}", json=body, headers=H())
    assert r.status_code == 501
    assert "SARS" in r.text or "uFiling" in r.text or "UI-2.7" in r.text
    assert count(env, cdb.TaxReturn) == 0
