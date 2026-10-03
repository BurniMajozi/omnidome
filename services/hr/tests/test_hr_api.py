"""HR API behaviour with a scripted fake session: role tiers, payroll runs/pay, KPI state machine,
GET-never-writes, cascade, validation, manager cycles, performance summary.

Run from the repo root:  PYTHONPATH=. python -m pytest services/hr/tests -q
"""
import dataclasses
import asyncio
import json
import uuid
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from services.common.auth import get_auth_context
from services.hr import main as hr
from services.hr import tax_tables as tt
from services.hr.database import (
    BenefitEnrollment, CompanyKPIConfig, EmployeeKPISheet, LeaveRequest, PayrollProfile, PayrollRun, Payslip,
    get_session,
)
from services.hr.tests.fakes import (
    FakeDB, TENANT, caller_lookup, ctx, employee, employee_by_id, params_of, parent_map_query,
)

HR_ADMIN = ("hr_admin",)
MANAGER = ("manager",)
STAFF = ("org_user",)


def test_agent_registration_forwards_signed_caller_identity(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"agent_type": "custom_test"}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            captured.update(kwargs["headers"])
            return Response()

    monkeypatch.setattr(hr.httpx, "AsyncClient", Client)
    caller = ctx(HR_ADMIN)
    result = asyncio.run(hr._register_agent_employee(employee(), TENANT, caller))
    assert result["registration_status"] == "registered"
    assert captured["x-tenant-id"] == str(TENANT)
    assert captured["x-user-id"] == str(caller.user_id)
    assert "hr_admin" in captured["x-roles"]


@pytest.fixture
def env(monkeypatch):
    monkeypatch.delenv("HR_ENFORCE_ROLES", raising=False)
    monkeypatch.delenv("HR_ADMIN_EXTRA_ROLES", raising=False)
    monkeypatch.setattr(hr.guard, "is_licensed", lambda: True)
    monkeypatch.setattr(hr.guard, "enforce_modules", False)

    class NoHttp:  # the finance journal call is best-effort; never touch the network
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            raise RuntimeError("network disabled in tests")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(hr.httpx, "AsyncClient", NoHttp)
    return monkeypatch


@pytest.fixture
def make(env):
    def _make(db, auth_ctx):
        async def _session():
            yield db

        hr.app.dependency_overrides[get_session] = _session
        hr.app.dependency_overrides[get_auth_context] = lambda: auth_ctx
        return TestClient(hr.app, raise_server_exceptions=True)

    yield _make
    hr.app.dependency_overrides.clear()


def sheet_row(emp, status="DRAFT", kpis=None, fy="FY 2026/2027", overall=None, sh=20.0, val=10.0, ind=70.0):
    return EmployeeKPISheet(
        id=uuid.uuid4(), tenant_id=TENANT, employee_id=emp.id, fiscal_year=fy, position_level="STAFF",
        company_shared_weight_pct=sh, values_weight_pct=val, individual_target_weight_pct=ind, total_weight_pct=100.0,
        status=status, kpis_json=json.dumps(kpis or []), overall_score=overall, created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 2),
    )


def config_row(budgets=(1000.0, 500.0, 400.0), actuals=(900.0, 450.0, 380.0)):
    return CompanyKPIConfig(
        id=uuid.uuid4(), tenant_id=TENANT, fiscal_year="FY 2026/2027",
        sales_budget_zar=budgets[0], cost_budget_zar=budgets[1], profit_budget_zar=budgets[2],
        sales_actual_zar=actuals[0], cost_actual_zar=actuals[1], profit_actual_zar=actuals[2],
        values_weight_pct=10.0, level_weights_json=json.dumps({"STAFF": 20.0}), created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def payslip_row(emp, run_id=None, net=8000.0, status="PENDING", recipient="RCP_1"):
    return Payslip(
        id=uuid.uuid4(), tenant_id=TENANT, run_id=run_id or uuid.uuid4(), employee_id=emp.id, gross=10000.0,
        basic_salary=10000.0, commission=0.0, allowances=0.0, tax=1500.0, tax_rebate=17820.0, annual_taxable=120000.0,
        uif=100.0, uif_employer=100.0, sdl=100.0, other_deductions=0.0, net=net, currency="ZAR",
        payout_status=status, paystack_recipient_code=recipient, created_at=datetime(2026, 8, 1),
        tax_year=2026, tax_table_version="sars-2026/27@2026-10-01",
    )


# ═════════════════ C1: role tiers ═════════════════

PROTECTED = [
    ("PUT", "/employees/{emp}/payroll-profile", {"json": {"base_salary": 100.0}}),
    ("POST", "/payroll/runs", {"json": {"period": "2026-08"}}),
    ("POST", "/payroll/runs/{run}/pay", {}),
    ("POST", "/payroll/import", {"files": {"file": ("a.csv", b"full_name\nX\n")}}),
    ("POST", "/employees", {"json": {"full_name": "A", "job_title": "B", "department": "C", "hire_date": "2026-01-01", "employee_id": "E1"}}),
    ("PUT", "/employees/{emp}", {"json": {"job_title": "Boss"}}),
    ("DELETE", "/employees/{emp}", {}),
    ("GET", "/payroll/runs", {}),
    ("GET", "/payroll/roster", {}),
    ("POST", "/payroll/run", {"json": {"period": "2026-08"}}),
    ("PUT", "/kpis/company", {"json": {"sales_budget_zar": 1.0}}),
    ("POST", "/kpis/cascade", {"json": {}}),
    ("POST", "/kpis/sync-actuals", {}),
    ("GET", "/kpis/live-actuals", {}),
    ("PUT", "/employees/{emp}/link-user", {"json": {"user_id": str(uuid.uuid4())}}),
    ("POST", "/disciplinary", {"json": {"employee_id": str(uuid.uuid4()), "action_type": "WARNING", "reason": "x"}}),
    ("POST", "/cross-service/finance/post-payroll-run", {"json": {}}),
    ("GET", "/cross-service/finance/department-cost-allocation", {}),
    ("POST", "/cross-service/sales/commissions/claim-to-payroll", {"json": {}}),
]


@pytest.mark.parametrize("method,path,kw", PROTECTED)
def test_org_user_is_denied(make, method, path, kw):
    target = employee()
    db = FakeDB().when(employee_by_id, [target])
    client = make(db, ctx(STAFF))
    url = path.format(emp=target.id, run=uuid.uuid4())
    r = client.request(method, url, **kw)
    assert r.status_code == 403, (method, path, r.text)
    assert not db.wrote()


def test_hr_admin_may_write_employee_and_profile(make):
    target = employee()
    db = FakeDB().when(employee_by_id, [target]).when(parent_map_query, [(target.id, None)])
    client = make(db, ctx(HR_ADMIN))
    r = client.put(f"/employees/{target.id}", json={"job_title": "Lead"})
    assert r.status_code == 200 and r.json()["job_title"] == "Lead"
    r = client.put(f"/employees/{target.id}/payroll-profile", json={"base_salary": 25000.0})
    assert r.status_code == 200 and r.json()["profile"]["base_salary"] == 25000.0


def test_platform_admin_and_enforcement_off(make, monkeypatch):
    target = employee()
    db = FakeDB().when(employee_by_id, [target])
    assert make(db, ctx((), platform_admin=True)).put(f"/employees/{target.id}", json={"job_title": "x"}).status_code == 200
    monkeypatch.setenv("HR_ENFORCE_ROLES", "false")
    assert make(db, ctx(STAFF)).put(f"/employees/{target.id}", json={"job_title": "y"}).status_code == 200


def test_hr_manager_and_owner_count_as_hr_admin_org_admin_does_not(make):
    target = employee()
    db = FakeDB().when(employee_by_id, [target])
    for role, expected in (("hr_manager", 200), ("owner", 200), ("org_admin", 403)):
        assert make(db, ctx((role,))).put(f"/employees/{target.id}", json={"job_title": "z"}).status_code == expected, role


def test_rbac_failure_fails_closed(make, monkeypatch):
    """With RBAC not loaded and unreadable, token roles are not trusted (AUTH_ENFORCE_RBAC default on)."""
    from services.common import rbac

    async def boom(auth, db):
        raise RuntimeError("no rbac tables")

    monkeypatch.setattr(rbac, "_load_rbac", boom)
    target = employee()
    db = FakeDB().when(employee_by_id, [target])
    c = ctx(HR_ADMIN)
    c.rbac_loaded = False
    assert make(db, c).put(f"/employees/{target.id}", json={"job_title": "q"}).status_code == 403


# ═════════════════ self / redaction ═════════════════

def test_employee_list_is_redacted_for_non_admin(make):
    a = employee(name="A")
    db = FakeDB().when(lambda s: "FROM employees" in str(s) and "ORDER BY" in str(s), [a])
    rows = make(db, ctx(STAFF)).get("/employees").json()
    assert rows and "base_salary" not in rows[0] and "id_number" not in rows[0]


def test_self_reads_own_payslip_masked_not_others(make):
    me_user = uuid.uuid4()
    me = employee(user_id=me_user, id_number="8001015009087")
    other = employee()
    prof = PayrollProfile(employee_id=me.id, tenant_id=TENANT, base_salary=10000, bank_code="632005",
                          account_number="62001234567", account_name="Me")
    mine = payslip_row(me)
    theirs = payslip_row(other)
    db = FakeDB()
    db.when(caller_lookup, [me])
    db.when(lambda s: "FROM payslips" in str(s), lambda s: [(mine, me, prof)] if mine.id in params_of(s) else [(theirs, other, None)])
    client = make(db, ctx(STAFF, user_id=me_user))

    ok = client.get(f"/payroll/payslips/{mine.id}")
    assert ok.status_code == 200
    body = ok.json()
    assert body["net"] == 8000.0
    assert body["account_number"].endswith("4567") and "6200" not in body["account_number"]
    assert body["id_number"].endswith("87") and "800101" not in body["id_number"]
    assert "paystack_transfer_code" not in body

    assert client.get(f"/payroll/payslips/{theirs.id}").status_code == 403


def test_payslip_list_for_non_admin_is_forced_to_own_employee(make):
    me_user = uuid.uuid4()
    me = employee(user_id=me_user)
    db = FakeDB().when(caller_lookup, [me]).when(lambda s: "FROM payslips" in str(s), [])
    client = make(db, ctx(STAFF, user_id=me_user))
    assert client.get("/payroll/payslips").status_code == 200
    assert me.id in params_of(db.statements[-1])
    assert client.get(f"/payroll/payslips?employee_id={uuid.uuid4()}").status_code == 403


def test_unlinked_user_cannot_list_payslips(make):
    db = FakeDB()
    assert make(db, ctx(STAFF)).get("/payroll/payslips").status_code == 403


def test_payroll_profile_self_masked_other_denied(make):
    me_user = uuid.uuid4()
    me = employee(user_id=me_user)
    other = employee()
    prof = PayrollProfile(employee_id=me.id, tenant_id=TENANT, base_salary=10000, bank_code="632005",
                          account_number="62001234567", account_name="Me", paystack_recipient_code="RCP_1")
    db = FakeDB().when(caller_lookup, [me]).when(employee_by_id, lambda s: [me] if me.id in params_of(s) else [other])
    db.when(lambda s: "FROM payroll_profiles" in str(s), [prof])
    client = make(db, ctx(STAFF, user_id=me_user))
    mine = client.get(f"/employees/{me.id}/payroll-profile")
    assert mine.status_code == 200 and mine.json()["account_number"].endswith("4567") and "6200" not in mine.json()["account_number"]
    assert client.get(f"/employees/{other.id}/payroll-profile").status_code == 403
    admin = make(db, ctx(HR_ADMIN)).get(f"/employees/{other.id}/payroll-profile")
    assert admin.status_code == 200 and admin.json()["account_number"] == "62001234567"


def test_leave_approval_scoped_to_manager_or_hr(make):
    boss_user = uuid.uuid4()
    boss = employee(user_id=boss_user)
    report = employee(manager_id=boss.id)
    stranger = employee()
    leave = LeaveRequest(id=uuid.uuid4(), tenant_id=TENANT, employee_id=report.id, leave_type="ANNUAL",
                         start_date=date(2026, 8, 1), end_date=date(2026, 8, 2), status="PENDING")
    pm = [(boss.id, None), (report.id, boss.id), (stranger.id, None)]
    db = FakeDB().when(parent_map_query, pm).when(caller_lookup, [boss]).when(lambda s: "FROM leave_requests" in str(s), [leave])
    assert make(db, ctx(MANAGER, user_id=boss_user)).put(f"/leave/{leave.id}/approve").status_code == 200
    # org_user (no manager role) cannot approve even if matched
    assert make(db, ctx(STAFF, user_id=boss_user)).put(f"/leave/{leave.id}/approve").status_code == 403
    # a manager who is not in the chain cannot
    db2 = FakeDB().when(parent_map_query, pm).when(caller_lookup, [stranger]).when(lambda s: "FROM leave_requests" in str(s), [leave])
    assert make(db2, ctx(MANAGER)).put(f"/leave/{leave.id}/approve").status_code == 403
    # HR admin can
    assert make(FakeDB().when(lambda s: "FROM leave_requests" in str(s), [leave]), ctx(HR_ADMIN)).put(f"/leave/{leave.id}/decline").status_code == 200


# ═════════════════ H2 / H4 / H5: payroll run ═════════════════

def run_db(emps, profiles, bonus=0.0):
    db = FakeDB()
    db.when(lambda s: "FROM employees" in str(s), emps)
    db.when(lambda s: "FROM payroll_profiles" in str(s), profiles)
    db.when(lambda s: "benefit_enrollments" in str(s), [(bonus,)])
    return db


def test_payroll_run_computes_payslips_without_keyerror(make):
    e = employee(dob=date(1990, 5, 5))
    prof = PayrollProfile(employee_id=e.id, tenant_id=TENANT, base_salary=20000.0, currency="ZAR", pay_frequency="MONTHLY")
    db = run_db([e], [prof])
    admin = ctx(HR_ADMIN)
    r = make(db, admin).post("/payroll/runs", json={"period": "2026-08"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["tax_year"] == 2026 and body["tax_table_version"].startswith("sars-2026/27@")
    slip = body["payslips"][0]
    assert slip["gross"] == 20000.0 and slip["tax"] == pytest.approx(2115.0, abs=0.01)   # hand computed, 2026/27
    assert slip["annual_taxable"] == 240000.0 and slip["tax_rebate"] == 17820.0
    assert slip["uif"] == pytest.approx(177.12) and slip["net"] == pytest.approx(17707.88, abs=0.01)
    assert slip["tax_year"] == 2026 and slip["id_number"] is None and slip["tax_number"] is None
    # R240k annual payroll is under the R500k SDL exemption
    assert body["sdl_applied"] is False and body["tax_table"]["verified"] is True
    stored = [o for o in db.added if isinstance(o, Payslip)][0]
    assert stored.tax_year == 2026 and stored.tax_table_version == body["tax_table_version"]
    run = [o for o in db.added if isinstance(o, PayrollRun)][0]
    assert run.created_by == admin.user_id and run.acknowledged_unverified_tables is False


def test_run_picks_table_by_period_tax_year(make):
    e = employee(dob=date(1990, 5, 5))
    prof = PayrollProfile(employee_id=e.id, tenant_id=TENANT, base_salary=20000.0)
    r = make(run_db([e], [prof]), ctx(HR_ADMIN)).post("/payroll/runs", json={"period": "2026-02"})
    assert r.status_code == 201
    assert r.json()["tax_year"] == 2025
    assert r.json()["payslips"][0]["tax"] == pytest.approx(2183.08, abs=0.01)           # 2025/26 table


def test_run_bonus_is_taxed_as_annual_payment(make):
    e = employee(dob=date(1990, 5, 5))
    prof = PayrollProfile(employee_id=e.id, tenant_id=TENANT, base_salary=30000.0)
    r = make(run_db([e], [prof], bonus=50000.0), ctx(HR_ADMIN)).post("/payroll/runs", json={"period": "2026-12"})
    s = r.json()["payslips"][0]
    assert s["gross"] == 80000.0 and s["commission"] == 50000.0 and s["tax"] == pytest.approx(19026.0, abs=0.01)


def test_run_for_unverified_or_missing_year_is_503(make, monkeypatch):
    e = employee()
    prof = PayrollProfile(employee_id=e.id, tenant_id=TENANT, base_salary=20000.0)
    client = make(run_db([e], [prof]), ctx(HR_ADMIN))
    r = client.post("/payroll/runs", json={"period": "2027-05"})
    assert r.status_code == 503 and "not verified" in r.json()["detail"] and "2027/28" in r.json()["detail"]
    # no figures at all: acknowledgement cannot conjure them
    assert client.post("/payroll/runs", json={"period": "2027-05", "acknowledge_unverified_tables": True}).status_code == 503
    assert not make(run_db([e], [prof]), ctx(HR_ADMIN)).post("/payroll/runs", json={"period": "2027-05"}).status_code == 201


def test_run_for_unverified_loaded_table_needs_ack_and_records_it(make, monkeypatch):
    monkeypatch.setitem(tt.TABLES, 2027, dataclasses.replace(tt.TABLES[2026], tax_year=2027, verified=False))
    e = employee(dob=date(1990, 5, 5))
    prof = PayrollProfile(employee_id=e.id, tenant_id=TENANT, base_salary=20000.0)
    db = run_db([e], [prof])
    client = make(db, ctx(HR_ADMIN))
    assert client.post("/payroll/runs", json={"period": "2027-05"}).status_code == 503
    r = client.post("/payroll/runs", json={"period": "2027-05", "acknowledge_unverified_tables": True})
    assert r.status_code == 201 and r.json()["acknowledged_unverified_tables"] is True
    assert "unverified_tax_table_acknowledged" in r.json()["payslips"][0]["tax_flags"]
    assert [o for o in db.added if isinstance(o, PayrollRun)][-1].acknowledged_unverified_tables is True


def test_unknown_age_is_flagged_primary_rebate_only(make):
    e = employee()  # no dob, no id number
    prof = PayrollProfile(employee_id=e.id, tenant_id=TENANT, base_salary=20000.0)
    r = make(run_db([e], [prof]), ctx(HR_ADMIN)).post("/payroll/runs", json={"period": "2026-08"})
    assert "age_unknown_primary_rebate_only" in r.json()["payslips"][0]["tax_flags"]
    assert r.json()["employees_without_age_primary_rebate_only"] == 1


def test_age_from_date_of_birth_uses_secondary_rebate(make):
    e = employee(dob=date(1950, 1, 1))
    prof = PayrollProfile(employee_id=e.id, tenant_id=TENANT, base_salary=20000.0)
    r = make(run_db([e], [prof]), ctx(HR_ADMIN)).post("/payroll/runs", json={"period": "2026-08"})
    assert r.json()["payslips"][0]["tax"] == pytest.approx(1030.5, abs=0.01)             # 76 on 28 Feb 2027: primary+secondary+tertiary, (43,200 - 30,834)/12


def test_bad_period_is_422(make):
    assert make(FakeDB(), ctx(HR_ADMIN)).post("/payroll/runs", json={"period": "August"}).status_code == 422


def test_payslip_dict_never_invents_identity_or_figures():
    e = employee()  # id_number / tax_number None
    s = payslip_row(e)
    s.tax_rebate = None
    s.annual_taxable = None
    s.sdl = None
    d = hr._payslip_to_dict(s, e, None)
    assert d["id_number"] is None and d["tax_number"] is None
    assert d["tax_rebate"] is None and d["annual_taxable"] is None and d["sdl"] is None
    assert d["bank_code"] is None and d["account_number"] is None


def test_calculate_preview_cites_source_and_503_for_unverified(make):
    client = make(FakeDB(), ctx(STAFF))
    r = client.post("/payroll/calculate-preview", json={"gross_salary": 20000, "period": "2026-08", "medical_aid_members": 2})
    assert r.status_code == 200
    b = r.json()
    assert b["monthly_paye_tax"] == pytest.approx(2115.0 - 752.0, abs=0.01)             # credits 376 + 376
    assert b["tax_table"]["source_url"].startswith("https://www.sars.gov.za/")
    assert "estimate" not in json.dumps(b).lower()
    assert client.post("/payroll/calculate-preview", json={"gross_salary": 20000, "period": "2030-01"}).status_code == 503


# ═════════════════ pay: idempotent references ═════════════════

def test_transfer_reference_is_per_payslip_not_per_period_employee():
    a, b = uuid.uuid4(), uuid.uuid4()
    assert hr._transfer_reference(a) == f"pay-{a}" and hr._transfer_reference(a) != hr._transfer_reference(b)
    assert len(hr._transfer_reference(a)) >= 16 and hr._transfer_reference(a) == hr._transfer_reference(a).lower()


def test_pay_uses_payslip_reference_and_marks_run(make, monkeypatch):
    e1, e2 = employee(), employee()
    run = PayrollRun(id=uuid.uuid4(), tenant_id=TENANT, period="2026-08", status="DRAFT", currency="ZAR", employee_count=2,
                     total_gross=0, total_deductions=0, total_net=0, created_at=datetime(2026, 8, 1))
    s1, s2 = payslip_row(e1, run.id), payslip_row(e2, run.id)
    calls = []

    async def fake_transfer(amount_zar, recipient_code, reason, reference=None):
        calls.append(reference)
        return {"ok": True, "transfer_code": "TRF_1", "status": "success", "reference": reference,
                "message": "paid to 62001234567"}

    monkeypatch.setattr(hr.ps, "initiate_transfer", fake_transfer)
    db = FakeDB().when(lambda s: "FROM payroll_runs" in str(s), [run]).when(lambda s: "FROM payslips" in str(s), [s1, s2])
    r = make(db, ctx(HR_ADMIN)).post(f"/payroll/runs/{run.id}/pay", headers={"Idempotency-Key": "abc-123"})
    assert r.status_code == 200 and r.json()["run_id"] if "run_id" in r.json() else True
    assert calls == [f"pay-{s1.id}", f"pay-{s2.id}"]
    assert "2026-08" not in "".join(calls)
    assert run.status == "PAID" and s1.payout_status == "PAID"
    assert "62001234567" not in (s1.payout_message or "") and "4567" in s1.payout_message     # digits masked
    assert any("FOR UPDATE" in str(st) for st in db.statements)                              # row-locked


def test_pay_nothing_left_does_not_call_paystack(make, monkeypatch):
    run = PayrollRun(id=uuid.uuid4(), tenant_id=TENANT, period="2026-08", status="PAID", currency="ZAR", employee_count=0,
                     total_gross=0, total_deductions=0, total_net=0, created_at=datetime(2026, 8, 1))

    async def boom(*a, **k):
        raise AssertionError("must not call paystack")

    monkeypatch.setattr(hr.ps, "initiate_transfer", boom)
    db = FakeDB().when(lambda s: "FROM payroll_runs" in str(s), [run])
    assert make(db, ctx(HR_ADMIN)).post(f"/payroll/runs/{run.id}/pay").status_code == 200


# ═════════════════ H3: cost actual ═════════════════

def test_cost_statement_counts_only_paid_runs_inside_fiscal_year():
    stmt = hr._payroll_cost_statement(TENANT, "2026-03", "2027-02")
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "payroll_runs.status IN ('PAID', 'PARTIALLY_PAID')" in sql
    assert "payroll_runs.period >= '2026-03'" in sql and "payroll_runs.period <= '2027-02'" in sql
    assert "DRAFT" not in sql and "FAILED" not in sql.replace("payout_status", "")
    assert "payslips.payout_status IN ('PAID', 'PROCESSING')" in sql          # partially paid runs: paid slips only


def test_fiscal_year_period_range(monkeypatch):
    assert hr._fy_period_range(date(2026, 3, 1)) == ("2026-03", "2027-02")
    assert hr._fy_period_range(date(2026, 1, 1)) == ("2026-01", "2026-12")


def test_same_period_in_three_runs_counts_once_latest_wins():
    e = uuid.uuid4()
    rows = [
        (e, "2026-08", datetime(2026, 8, 1), 100.0),
        (e, "2026-08", datetime(2026, 8, 5), 120.0),     # latest run for the period
        (e, "2026-08", datetime(2026, 8, 3), 110.0),
        (e, "2026-09", datetime(2026, 9, 1), 100.0),
        (uuid.uuid4(), "2026-08", datetime(2026, 8, 1), 50.0),
    ]
    assert hr._dedupe_paid_cost(rows) == 270.0


def test_live_cost_none_when_no_paid_rows():
    import asyncio
    db = FakeDB().when(lambda s: "FROM payslips" in str(s), [])
    assert asyncio.run(hr._live_payroll_cost(db, TENANT, date(2026, 3, 1))) is None


# ═════════════════ H6 cascade ═════════════════

def test_cascade_skips_non_draft_and_reports_count(make):
    emps = [employee(title="Analyst") for _ in range(4)]
    states = {emps[0].id: "DRAFT", emps[1].id: "SUBMITTED", emps[2].id: "APPROVED", emps[3].id: None}
    sheets = {i: sheet_row(next(e for e in emps if e.id == i), st, sh=5.0) for i, st in states.items() if st}

    def sheet_for(stmt):
        for v in params_of(stmt):
            if v in sheets:
                return [sheets[v]]
        return []

    db = FakeDB()
    db.when(lambda s: "FROM employee_kpi_sheets" in str(s), sheet_for)
    db.when(lambda s: "FROM company_kpi_configs" in str(s), [config_row()])
    db.when(lambda s: "FROM employees" in str(s), emps)
    r = make(db, ctx(HR_ADMIN)).post("/kpis/cascade", json={"fiscal_year": "FY 2026/2027"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["sheets_skipped_not_draft"] == 2 and b["employees_cascaded"] == 2 and b["sheets_created"] == 1
    assert sheets[emps[0].id].company_shared_weight_pct == 20.0          # draft updated
    assert sheets[emps[1].id].company_shared_weight_pct == 5.0           # submitted untouched
    assert sheets[emps[2].id].company_shared_weight_pct == 5.0           # approved untouched


# ═════════════════ M9: GET never writes ═════════════════

def test_get_company_kpis_never_writes_and_flags_template(make):
    db = FakeDB()
    r = make(db, ctx(STAFF)).get("/kpis/company")
    assert r.status_code == 200
    b = r.json()
    assert b["is_template"] is True and b["company_missing"] is True
    assert b["corporate_attainment_index"] is None and b["cost_efficiency_pct"] is None
    assert not db.wrote()


def test_get_kpi_sheet_without_sheet_returns_unsaved_template(make):
    emp = employee(title="Support Agent")
    db = FakeDB().when(employee_by_id, [emp])
    r = make(db, ctx(HR_ADMIN)).get(f"/employees/{emp.id}/kpi-sheet")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["is_template"] is True and b["kpis"] == [] and b["overall_score"] is None and b["id"] is None
    assert b["status"] == "DRAFT" and b["composite"]["company_missing"] is True
    assert {"employee_id", "fiscal_year", "company_shared_weight_pct", "permissions", "company_benchmarks"} <= set(b)
    assert not db.wrote()


def test_get_kpi_sheet_visibility(make):
    me_user = uuid.uuid4()
    me = employee(user_id=me_user)
    other = employee()
    stranger_mgr = employee(user_id=uuid.uuid4())
    pm = [(me.id, None), (other.id, None), (stranger_mgr.id, None)]
    db = FakeDB().when(caller_lookup, [me]).when(parent_map_query, pm).when(employee_by_id, lambda s: [me] if me.id in params_of(s) else [other])
    c = make(db, ctx(STAFF, user_id=me_user))
    assert c.get(f"/employees/{me.id}/kpi-sheet").status_code == 200
    assert c.get(f"/employees/{other.id}/kpi-sheet").status_code == 403


def test_existing_sheet_returns_flag_false_and_server_score_basis(make):
    emp = employee()
    sh = sheet_row(emp, kpis=[{"title": "x", "weight_pct": 70, "current_level": 4}], overall=95.0)
    db = FakeDB().when(employee_by_id, [emp]).when(lambda s: "FROM employee_kpi_sheets" in str(s), [sh]).when(
        lambda s: "FROM company_kpi_configs" in str(s), [config_row()])
    b = make(db, ctx(HR_ADMIN)).get(f"/employees/{emp.id}/kpi-sheet").json()
    assert b["is_template"] is False and b["score_basis"].startswith("ui_points_v1")
    assert b["overall_score"] == 95.0     # stored value is returned untouched by a GET


# ═════════════════ M10 / M12 ═════════════════

def test_company_scores_null_when_any_budget_zero():
    cfg = config_row(budgets=(1000.0, 0.0, 400.0), actuals=(900.0, 0.0, 380.0))
    s = hr._calculate_company_scores(cfg)
    assert s["company_missing"] is True and s["corporate_attainment_index"] is None and s["cost_efficiency_pct"] is None
    assert s["sales_achievement_pct"] == 90.0


def test_company_scores_when_complete():
    s = hr._calculate_company_scores(config_row())
    # sales 90.0, cost 500/450 = 111.11, profit 95.0 -> 40.5 + 38.89 + 19.0 = 98.39
    assert s["company_missing"] is False
    assert s["corporate_attainment_index"] == pytest.approx(98.39, abs=0.01)


def test_zero_cost_actual_is_not_100_percent():
    s = hr._calculate_company_scores(config_row(actuals=(900.0, 0.0, 380.0)))
    assert s["cost_efficiency_pct"] is None and s["company_missing"] is True


def test_composite_matches_ui_points_formula_for_incomplete_weights():
    emp = employee()
    sh = sheet_row(emp, kpis=[{"title": "a", "weight_pct": 35, "current_level": 3}], sh=20, val=10, ind=70)
    sh.values_ratings = json.dumps({k: 3 for k in hr.VALUE_KEYS})
    comp = hr._compute_composite(sh, [{"title": "a", "weight_pct": 35, "current_level": 3}],
                                 {"corporate_attainment_index": 100.0}, False)
    # UI: 100*20/100 + 100*10/100 + (100 * 35 / 100) = 20 + 10 + 35 = 65 (NOT divided by the item-weight sum)
    assert comp["total"] == 65.0 and comp["weights_complete"] is False and "ui_points_v1" in comp["score_basis"]


# ═════════════════ M11: level validation ═════════════════

@pytest.mark.parametrize("bad", [0, 6, -1, None, float("nan"), float("inf"), 2.5, True, "3"])
def test_current_level_validation_rejects(bad):
    errs, _ = hr._validate_kpi_items([{"title": "t", "weight_pct": 10, "current_level": bad}])
    assert errs and "current_level" in errs[0]


@pytest.mark.parametrize("good", [1, 2, 3, 4, 5, 3.0])
def test_current_level_validation_accepts(good):
    errs, _ = hr._validate_kpi_items([{"title": "t", "weight_pct": 10, "current_level": good}])
    assert errs == []


def test_put_sheet_rejects_bad_level_with_422(make):
    emp = employee()
    db = FakeDB().when(employee_by_id, [emp])
    r = make(db, ctx(HR_ADMIN)).put(f"/employees/{emp.id}/kpi-sheet", json={"kpis": [{"title": "t", "weight_pct": 10, "current_level": 9}]})
    assert r.status_code == 422 and not db.wrote()


# ═════════════════ M14: manager cycles / same tenant ═════════════════

def test_manager_cycle_and_foreign_manager_rejected(make):
    a, b, c = employee(), employee(), employee()
    a.manager_id, b.manager_id, c.manager_id = None, a.id, b.id
    pm = [(a.id, None), (b.id, a.id), (c.id, b.id)]
    db = FakeDB().when(parent_map_query, pm).when(employee_by_id, lambda s: [next(e for e in (a, b, c) if e.id in params_of(s))])
    client = make(db, ctx(HR_ADMIN))
    assert client.put(f"/employees/{a.id}", json={"manager_id": str(c.id)}).status_code == 422     # loop
    assert client.put(f"/employees/{a.id}", json={"manager_id": str(a.id)}).status_code == 422     # self
    assert client.put(f"/employees/{a.id}", json={"manager_id": str(uuid.uuid4())}).status_code == 422   # other tenant / unknown
    ok = client.put(f"/employees/{c.id}", json={"manager_id": str(a.id)})
    assert ok.status_code == 200


def test_create_employee_validates_manager(make):
    pm = [(uuid.uuid4(), None)]
    db = FakeDB().when(parent_map_query, pm)
    body = {"full_name": "N", "job_title": "J", "department": "D", "hire_date": "2026-01-01", "employee_id": "E9",
            "manager_id": str(uuid.uuid4())}
    assert make(db, ctx(HR_ADMIN)).post("/employees", json=body).status_code == 422
    body["manager_id"] = str(pm[0][0])
    assert make(db, ctx(HR_ADMIN)).post("/employees", json=body).status_code == 201


# ═════════════════ H7 / H8: KPI state machine ═════════════════

def kpi_db(target, sheet, caller_emp=None, pm=None, config=True):
    db = FakeDB()
    db.when(employee_by_id, [target])
    db.when(parent_map_query, pm if pm is not None else [(target.id, target.manager_id)])
    if caller_emp is not None:
        db.when(caller_lookup, [caller_emp])
    db.when(lambda s: "FROM employee_kpi_sheets" in str(s), [sheet] if sheet else [])
    db.when(lambda s: "FROM company_kpi_configs" in str(s), [config_row()] if config else [])
    return db


def test_owner_cannot_approve_own_sheet(make):
    uid = uuid.uuid4()
    me = employee(user_id=uid)
    db = kpi_db(me, sheet_row(me, "SUBMITTED"), caller_emp=me)
    for roles in (MANAGER, HR_ADMIN):
        r = make(db, ctx(roles, user_id=uid)).post(f"/employees/{me.id}/kpi-sheet/approve")
        assert r.status_code == 403, roles


def test_unmatched_non_admin_is_denied_approve_and_reject(make):
    target = employee()
    sh = sheet_row(target, "SUBMITTED")
    db = kpi_db(target, sh)                       # caller_lookup returns nothing
    c = make(db, ctx(MANAGER))
    assert c.post(f"/employees/{target.id}/kpi-sheet/approve").status_code == 403
    assert c.post(f"/employees/{target.id}/kpi-sheet/reject", json={"reason": "no"}).status_code == 403
    assert sh.status == "SUBMITTED"


def test_manager_in_chain_can_approve_not_outside_chain(make):
    boss_uid = uuid.uuid4()
    boss = employee(user_id=boss_uid)
    target = employee(manager_id=boss.id)
    sh = sheet_row(target, "SUBMITTED")
    pm = [(boss.id, None), (target.id, boss.id)]
    r = make(kpi_db(target, sh, caller_emp=boss, pm=pm), ctx(MANAGER, user_id=boss_uid)).post(f"/employees/{target.id}/kpi-sheet/approve")
    assert r.status_code == 200 and sh.status == "APPROVED" and sh.approved_by == boss_uid
    other_uid = uuid.uuid4()
    other = employee(user_id=other_uid)
    sh2 = sheet_row(target, "SUBMITTED")
    r = make(kpi_db(target, sh2, caller_emp=other, pm=pm + [(other.id, None)]), ctx(MANAGER, user_id=other_uid)).post(f"/employees/{target.id}/kpi-sheet/approve")
    assert r.status_code == 403 and sh2.status == "SUBMITTED"
    # org_user in the chain without a manager role is denied
    sh3 = sheet_row(target, "SUBMITTED")
    r = make(kpi_db(target, sh3, caller_emp=boss, pm=pm), ctx(STAFF, user_id=boss_uid)).post(f"/employees/{target.id}/kpi-sheet/approve")
    assert r.status_code == 403


def test_hr_admin_unmatched_may_approve_others_and_state_is_checked(make):
    target = employee()
    sh = sheet_row(target, "DRAFT")
    c = make(kpi_db(target, sh), ctx(HR_ADMIN))
    assert c.post(f"/employees/{target.id}/kpi-sheet/approve").status_code == 409        # not SUBMITTED
    sh.status = "SUBMITTED"
    assert c.post(f"/employees/{target.id}/kpi-sheet/reject", json={"reason": " "}).status_code == 422
    assert c.post(f"/employees/{target.id}/kpi-sheet/reject", json={"reason": "fix weights"}).status_code == 200
    assert sh.status == "DRAFT" and sh.reject_reason == "fix weights"
    sh.status = "SUBMITTED"
    assert c.post(f"/employees/{target.id}/kpi-sheet/approve").status_code == 200 and sh.status == "APPROVED"
    assert c.post(f"/employees/{target.id}/kpi-sheet/reopen").status_code == 200 and sh.status == "DRAFT"


def test_manager_loop_blocks_everyone(make):
    a, b = employee(), employee()
    a.manager_id, b.manager_id = b.id, a.id
    sh = sheet_row(a, "SUBMITTED")
    db = kpi_db(a, sh, pm=[(a.id, b.id), (b.id, a.id)])
    assert make(db, ctx(HR_ADMIN)).post(f"/employees/{a.id}/kpi-sheet/approve").status_code == 403


def test_reopen_needs_hr_admin(make):
    target = employee()
    sh = sheet_row(target, "APPROVED")
    assert make(kpi_db(target, sh), ctx(MANAGER)).post(f"/employees/{target.id}/kpi-sheet/reopen").status_code == 403
    assert sh.status == "APPROVED"


def test_put_sheet_server_computes_score_and_ignores_client_value(make):
    emp = employee()
    kpis = [{"id": "1", "title": "Deliver", "weight_pct": 70, "current_level": 3}]
    db = kpi_db(emp, None)
    r = make(db, ctx(HR_ADMIN)).put(f"/employees/{emp.id}/kpi-sheet", json={"kpis": kpis, "overall_score": 99.9, "status": "DRAFT"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["overall_score"] != 99.9
    # company configured: shared index 98.39 x 20% = 19.678; values unrated 0; individual 100 x 70/100 = 70 -> 89.7
    assert b["overall_score"] == pytest.approx(89.7, abs=0.06) and b["score_basis"].startswith("ui_points_v1")
    created = [o for o in db.added if isinstance(o, EmployeeKPISheet)][0]
    assert created.overall_score == b["overall_score"]


def test_put_sheet_permissions(make):
    me_uid = uuid.uuid4()
    me = employee(user_id=me_uid)
    other = employee()
    kpis = [{"title": "Deliver", "weight_pct": 70, "current_level": 3}]
    # stranger (org_user, not self, not manager) -> 403
    db = kpi_db(other, sheet_row(other), caller_emp=me, pm=[(me.id, None), (other.id, None)])
    assert make(db, ctx(STAFF, user_id=me_uid)).put(f"/employees/{other.id}/kpi-sheet", json={"kpis": kpis}).status_code == 403
    # self while DRAFT -> ok, but weights/ratings/notes ignored
    own = sheet_row(me, "DRAFT")
    db = kpi_db(me, own, caller_emp=me, pm=[(me.id, None)])
    r = make(db, ctx(STAFF, user_id=me_uid)).put(f"/employees/{me.id}/kpi-sheet", json={
        "kpis": kpis, "company_shared_weight_pct": 0, "individual_target_weight_pct": 90, "reviewer_notes": "great",
        "values_ratings": {k: 5 for k in hr.VALUE_KEYS}})
    assert r.status_code == 200, r.text
    assert float(own.company_shared_weight_pct) == 20.0 and own.reviewer_notes is None and not own.values_ratings
    # self when SUBMITTED -> locked
    sub = sheet_row(me, "SUBMITTED")
    db = kpi_db(me, sub, caller_emp=me, pm=[(me.id, None)])
    assert make(db, ctx(STAFF, user_id=me_uid)).put(f"/employees/{me.id}/kpi-sheet", json={"kpis": kpis}).status_code == 409
    # approved locked even for HR
    app_ = sheet_row(me, "APPROVED")
    assert make(kpi_db(me, app_), ctx(HR_ADMIN)).put(f"/employees/{me.id}/kpi-sheet", json={"kpis": kpis}).status_code == 409


def test_put_company_kpis_hr_admin_only(make):
    db = FakeDB()
    assert make(db, ctx(MANAGER)).put("/kpis/company", json={"sales_budget_zar": 5.0}).status_code == 403
    assert make(db, ctx(HR_ADMIN)).put("/kpis/company", json={"sales_budget_zar": 5.0}).status_code == 200


# ═════════════════ M13: sync actuals ═════════════════

def test_sync_actuals_writes_only_what_was_read_and_logs(make, monkeypatch, caplog):
    async def sales(tenant_id, fy_start):
        return 1000.0

    async def billing(tenant_id, fy_start):
        return 900.0

    async def cost(db, tenant_id, fy_start):
        return 400.0

    monkeypatch.setattr(hr, "_live_sales_won_ytd", sales)
    monkeypatch.setattr(hr, "_live_billing_collected_ytd", billing)
    monkeypatch.setattr(hr, "_live_payroll_cost", cost)
    cfg = config_row(actuals=(0.0, 0.0, 0.0))
    db = FakeDB().when(lambda s: "FROM company_kpi_configs" in str(s), [cfg])
    with caplog.at_level("INFO", logger="hr"):
        r = make(db, ctx(HR_ADMIN)).post("/kpis/sync-actuals", json={"fiscal_year": "FY 2026/2027"})
    assert r.status_code == 200, r.text
    assert r.json()["written"] == {"sales_actual_zar": 1000.0, "cost_actual_zar": 400.0, "profit_actual_zar": 600.0}
    assert float(cfg.sales_actual_zar) == 1000.0 and float(cfg.cost_actual_zar) == 400.0
    assert "AUDIT hr.kpis.sync_actuals" in caplog.text


def test_live_actuals_get_does_not_store(make, monkeypatch):
    async def none_sales(*a):
        return None

    async def cost(db, tenant_id, fy_start):
        return None

    monkeypatch.setattr(hr, "_live_sales_won_ytd", none_sales)
    monkeypatch.setattr(hr, "_live_billing_collected_ytd", none_sales)
    monkeypatch.setattr(hr, "_live_payroll_cost", cost)
    db = FakeDB()
    r = make(db, ctx(HR_ADMIN)).get("/kpis/live-actuals")
    assert r.status_code == 200 and r.json()["sources"]["cost"]["source"] == "unavailable"
    assert not db.wrote()


# ═════════════════ summary endpoint ═════════════════

def test_performance_summary_admin_manager_and_denied(make):
    boss_uid = uuid.uuid4()
    boss = employee(user_id=boss_uid, name="Boss")
    r1 = employee(manager_id=boss.id, name="R1")
    r2 = employee(name="Outsider")
    pm = [(boss.id, None), (r1.id, boss.id), (r2.id, None)]
    sheets = [sheet_row(r1, "SUBMITTED", kpis=[{"title": "x", "weight_pct": 70, "current_level": 3}])]

    def base():
        db = FakeDB()
        db.when(parent_map_query, pm)
        db.when(caller_lookup, [boss])
        db.when(lambda s: "FROM employee_kpi_sheets" in str(s), sheets)
        db.when(lambda s: "FROM company_kpi_configs" in str(s), [config_row()])
        db.when(lambda s: "FROM employees" in str(s), [boss, r1, r2])
        return db

    rows = make(base(), ctx(HR_ADMIN)).get("/employees/performance/summary").json()
    assert {r["employee_id"] for r in rows} == {str(boss.id), str(r1.id), str(r2.id)}
    by = {r["employee_id"]: r for r in rows}
    assert by[str(r1.id)]["status"] == "SUBMITTED" and by[str(r1.id)]["overall_score"] is not None
    assert by[str(r2.id)]["status"] == "NO_SHEET" and by[str(r2.id)]["overall_score"] is None
    assert set(by[str(r1.id)]) == {"employee_id", "overall_score", "status", "fiscal_year", "composite"}

    mrows = make(base(), ctx(MANAGER, user_id=boss_uid)).get("/employees/performance/summary").json()
    assert {r["employee_id"] for r in mrows} == {str(r1.id)}

    assert make(base(), ctx(STAFF)).get("/employees/performance/summary").status_code == 403


def test_summary_route_is_declared_before_employee_id_routes():
    paths = [r.path for r in hr.app.routes if hasattr(r, "path")]
    assert paths.index("/employees/performance/summary") < paths.index("/employees/{emp_id}")


# ═════════════════ link-user ═════════════════

def test_link_user_one_login_one_employee(make):
    target = employee()
    uid = uuid.uuid4()
    db = FakeDB().when(employee_by_id, [target]).when(lambda s: "SELECT employees.id" in str(s) and "employees.user_id" in str(s), [])
    r = make(db, ctx(HR_ADMIN)).put(f"/employees/{target.id}/link-user", json={"user_id": str(uid)})
    assert r.status_code == 200 and target.user_id == uid
    clash = FakeDB().when(employee_by_id, [target]).when(lambda s: "SELECT employees.id" in str(s) and "employees.user_id" in str(s), [(uuid.uuid4(),)])
    assert make(clash, ctx(HR_ADMIN)).put(f"/employees/{target.id}/link-user", json={"user_id": str(uuid.uuid4())}).status_code == 409
