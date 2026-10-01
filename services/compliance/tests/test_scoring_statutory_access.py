"""Pure logic: scoring empty state, no invented payroll figures, PRN format, role tiers, mass-assignment schemas."""
import uuid
from datetime import datetime
from types import SimpleNamespace as NS

import pytest
from pydantic import ValidationError

from services.compliance import access, scoring, statutory
from services.compliance.database import ComplianceCategory, ComplianceStatus, Contract, PopiDataAccessRequest
from services.compliance.write_schemas import create_schema, update_schema


def test_category_without_obligations_is_not_assessed():
    assert scoring.score_category([]) is None


def test_score_category_values():
    r = scoring.score_category([ComplianceStatus.compliant] * 9 + [ComplianceStatus.non_compliant])
    assert r == {"score": 90.0, "status": "compliant", "issues": 1, "critical": 1}
    r = scoring.score_category(["compliant", "at_risk", "compliant", "pending_review"])
    assert r["score"] == 50.0 and r["status"] == "non_compliant"


def _row(cat, score, ts, id_=1):
    return NS(category=cat, score=score, calculated_at=ts, id=id_)


def test_latest_per_category_ignores_history():
    rows = [
        _row(ComplianceCategory.tax, 40.0, datetime(2026, 1, 1)),
        _row(ComplianceCategory.tax, 80.0, datetime(2026, 6, 1)),
        _row(ComplianceCategory.popi, 100.0, datetime(2026, 5, 1)),
        _row(ComplianceCategory.popi, 20.0, datetime(2025, 5, 1)),
    ]
    latest = scoring.latest_per_category(rows)
    assert sorted(float(r.score) for r in latest) == [80.0, 100.0]
    assert scoring.overall_score(latest) == 90


def test_overall_none_when_nothing_assessed():
    assert scoring.overall_score([]) is None


def test_no_payslips_means_null_figures():
    for row in (None, (0, 0, 0, 0, 0, 0, 0, None)):
        out = statutory.aggregate_payslips(row)
        assert out["employee_count"] is None
        assert all(out[k] is None for k in ("gross_remuneration", "paye", "uif_employee", "uif_employer", "sdl", "total_liability"))
        assert "No paid payroll" in statutory.workpaper_note(out)


def test_aggregate_uses_stored_fields():
    out = statutory.aggregate_payslips((3, 30000, 4500.55, 150, 150, 300, 24900, "a,b"))
    assert out["paye"] == 4500.55 and out["sdl"] == 300.0
    assert out["total_liability"] == round(4500.55 + 150 + 150 + 300, 2)
    assert out["run_ids"] == ["a", "b"]


def test_rates_flagged_unverified_and_configurable(monkeypatch):
    monkeypatch.setenv("COMPLIANCE_SDL_ANNUAL_PAYROLL_THRESHOLD", "600000")
    rates = statutory.load_rates()
    assert rates.sdl_annual_payroll_threshold == 600000.0 and rates.rates_verified is False
    assert statutory.uif_for(50000, rates) == 177.12
    assert statutory.uif_for(None) is None


@pytest.mark.parametrize("prn,ok", [
    ("1234567890123456", True), ("ABCD1234EFGH5678", True), ("1234 5678 9012 3456 789", True),
    ("123456789012345", False), ("12345678901234567890", False), ("1234-5678-9012-3456", False), ("", False),
])
def test_prn_format(prn, ok):
    assert statutory.is_valid_prn(prn) is ok


def test_tier_membership():
    assert access.tier_allows("write", {"compliance_officer"}, set())
    assert access.tier_allows("write", {"manager"}, set())
    assert not access.tier_allows("write", {"viewer"}, set())
    assert access.tier_allows("sensitive", {"hr_admin"}, set())
    assert not access.tier_allows("sensitive", {"sales_agent"}, set())
    assert access.tier_allows("filing", {"finance_admin"}, set())
    assert not access.tier_allows("filing", {"compliance_officer"}, set())


@pytest.mark.anyio
async def test_require_and_enforce_flag(monkeypatch):
    from fastapi import HTTPException
    from services.common.auth import AuthContext

    ctx = AuthContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=["viewer"])
    with pytest.raises(HTTPException) as e:
        await access.require(ctx, None, "write")
    assert e.value.status_code == 403
    monkeypatch.setenv("COMPLIANCE_ENFORCE_ROLES", "false")
    await access.require(ctx, None, "write")


def test_create_schema_rejects_protected_and_unknown_fields():
    Dsar = create_schema(PopiDataAccessRequest, protected=("status", "due_date", "request_reference", "completed_date", "response_sent", "received_date"))
    ok = Dsar(data_subject_name="A", request_type="access")
    assert ok.model_dump(exclude_unset=True) == {"data_subject_name": "A", "request_type": "access"}
    for evil in ({"tenant_id": "x"}, {"id": 9}, {"created_at": "2020-01-01T00:00:00"}, {"status": "completed"}, {"nope": 1}):
        with pytest.raises(ValidationError):
            Dsar(data_subject_name="A", request_type="access", **evil)
    with pytest.raises(ValidationError):
        Dsar(request_type="access")


def test_update_schema_all_optional_and_forbids_tenant():
    Patch = update_schema(Contract)
    assert Patch().model_dump(exclude_unset=True) == {}
    with pytest.raises(ValidationError):
        Patch(tenant_id="other")
