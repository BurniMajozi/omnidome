"""
Compliance Service — Tax, H&S, CIPC, Bylaw, BBBEE Routes

Every query is filtered by the caller's tenant (from the signed identity, never
from the request), every {id} lookup 404s for another tenant's row, and request
bodies are explicit schemas that reject tenant_id / id / server-controlled fields.
Reads: any member. Writes: compliance_officer, manager or admin.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext
from services.common.db import get_async_session as get_db
from services.compliance import crud
from services.compliance.access import member_ctx, write_ctx
from services.compliance.database import (
    TaxRegistration, TaxReturn, TaxReturnStatus,
    HsRiskAssessment, HsIncident, HsSeverity,
    CipcFiling, BylawObligation, BbbeeScorecard, BbbeeLevel,
)
from services.compliance.write_schemas import create_schema, dump_set, update_schema

router = APIRouter()

TaxRegistrationIn = create_schema(TaxRegistration)
TaxReturnIn = create_schema(TaxReturn, protected=("status", "submission_date"))
HsRiskAssessmentIn = create_schema(HsRiskAssessment)
HsIncidentIn = create_schema(HsIncident)
HsIncidentPatch = update_schema(HsIncident)
CipcFilingIn = create_schema(CipcFiling, protected=("status", "filed_date", "confirmation_number"))
BylawObligationIn = create_schema(BylawObligation)
BylawObligationPatch = update_schema(BylawObligation)
BbbeeScorecardIn = create_schema(BbbeeScorecard)


class CipcFileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation_number: Optional[str] = None


class BbbeeCalcIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ownership_score: float = 0
    management_control_score: float = 0
    skills_development_score: float = 0
    enterprise_supplier_dev_score: float = 0
    socio_economic_dev_score: float = 0


# ── Tax Compliance ──────────────────────────────────────────────────────

tax_router = APIRouter(prefix="/tax", tags=["tax"])


@tax_router.get("/registrations")
async def list_tax_registrations(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    rows = await crud.list_rows(db, ctx, TaxRegistration)
    return {"items": [r.to_dict() for r in rows]}


@tax_router.post("/registrations")
async def create_tax_registration(body: TaxRegistrationIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.create_row(db, ctx, TaxRegistration, dump_set(body))).to_dict()


@tax_router.get("/returns")
async def list_tax_returns(
    tax_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = []
    if tax_type:
        where.append(TaxReturn.tax_type == tax_type)
    if status:
        where.append(TaxReturn.status == status)
    rows = await crud.list_rows(db, ctx, TaxReturn, *where, order_by=TaxReturn.period_end.desc())
    return {"items": [r.to_dict() for r in rows]}


@tax_router.post("/returns")
async def create_tax_return(body: TaxReturnIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    data = dump_set(body)
    await crud.assert_owned(db, ctx, TaxRegistration, data.get("registration_id"), "Tax registration")
    return (await crud.create_row(db, ctx, TaxReturn, data)).to_dict()


@tax_router.put("/returns/{return_id}/submit")
async def submit_tax_return(return_id: int, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    """Record that a return was submitted (by a person, on the SARS portal). Nothing is sent to SARS."""
    tr = await crud.get_owned(db, ctx, TaxReturn, return_id, "Tax return")
    tr.status = TaxReturnStatus.submitted
    tr.submission_date = date.today()
    await db.commit()
    return {"status": "submitted", "id": return_id}


@tax_router.get("/dashboard")
async def tax_dashboard(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    returns = await crud.list_rows(db, ctx, TaxReturn)
    total = len(returns)
    overdue = sum(1 for r in returns if r.status == TaxReturnStatus.overdue)
    pending = sum(1 for r in returns if r.status == TaxReturnStatus.pending)
    submitted = sum(1 for r in returns if r.status in (TaxReturnStatus.submitted, TaxReturnStatus.assessed, TaxReturnStatus.paid))
    total_payable = sum(float(r.amount_payable or 0) for r in returns)
    return {"total": total, "overdue": overdue, "pending": pending, "submitted": submitted, "total_payable": total_payable}


# ── Health & Safety ─────────────────────────────────────────────────────

hs_router = APIRouter(prefix="/health-safety", tags=["health-safety"])


@hs_router.get("/risk-assessments")
async def list_risk_assessments(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    rows = await crud.list_rows(db, ctx, HsRiskAssessment)
    return {"items": [r.to_dict() for r in rows]}


@hs_router.post("/risk-assessments")
async def create_risk_assessment(body: HsRiskAssessmentIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.create_row(db, ctx, HsRiskAssessment, dump_set(body))).to_dict()


@hs_router.get("/incidents")
async def list_incidents(
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = []
    if severity:
        where.append(HsIncident.severity == severity)
    if status:
        where.append(HsIncident.status == status)
    rows = await crud.list_rows(db, ctx, HsIncident, *where, order_by=HsIncident.incident_date.desc())
    return {"items": [i.to_dict() for i in rows]}


@hs_router.post("/incidents")
async def create_incident(body: HsIncidentIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.create_row(db, ctx, HsIncident, dump_set(body))).to_dict()


@hs_router.put("/incidents/{incident_id}")
async def update_incident(incident_id: int, body: HsIncidentPatch, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.update_row(db, ctx, HsIncident, incident_id, dump_set(body), "Incident")).to_dict()


@hs_router.get("/dashboard")
async def hs_dashboard(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    incidents = await crud.list_rows(db, ctx, HsIncident)
    total = len(incidents)
    open_count = sum(1 for i in incidents if i.status == "open")
    critical = sum(1 for i in incidents if i.severity == HsSeverity.critical)
    coida_reported = sum(1 for i in incidents if i.coida_reported)
    return {"total": total, "open": open_count, "critical": critical, "coida_reported": coida_reported}


# ── CIPC Compliance ─────────────────────────────────────────────────────

cipc_router = APIRouter(prefix="/cipc", tags=["cipc"])


@cipc_router.get("/filings")
async def list_cipc_filings(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    rows = await crud.list_rows(db, ctx, CipcFiling, order_by=CipcFiling.due_date)
    return {"items": [f.to_dict() for f in rows]}


@cipc_router.post("/filings")
async def create_cipc_filing(body: CipcFilingIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.create_row(db, ctx, CipcFiling, dump_set(body))).to_dict()


@cipc_router.put("/filings/{filing_id}/file")
async def file_cipc_return(filing_id: int, body: CipcFileIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    """Record that a person filed this return with CIPC and paste the real confirmation number."""
    filing = await crud.get_owned(db, ctx, CipcFiling, filing_id, "Filing")
    filing.status = "filed"
    filing.filed_date = date.today()
    filing.confirmation_number = body.confirmation_number
    await db.commit()
    return {"status": "filed", "id": filing_id}


# ── Bylaw Compliance ────────────────────────────────────────────────────

bylaw_router = APIRouter(prefix="/bylaw", tags=["bylaw"])


@bylaw_router.get("/obligations")
async def list_bylaw_obligations(
    municipality: Optional[str] = Query(None),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = [BylawObligation.municipality == municipality] if municipality else []
    rows = await crud.list_rows(db, ctx, BylawObligation, *where)
    return {"items": [o.to_dict() for o in rows]}


@bylaw_router.post("/obligations")
async def create_bylaw_obligation(body: BylawObligationIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.create_row(db, ctx, BylawObligation, dump_set(body))).to_dict()


@bylaw_router.put("/obligations/{obl_id}")
async def update_bylaw_obligation(obl_id: int, body: BylawObligationPatch, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.update_row(db, ctx, BylawObligation, obl_id, dump_set(body), "Obligation")).to_dict()


# ── BBBEE Compliance ────────────────────────────────────────────────────

bbbee_router = APIRouter(prefix="/bbbee", tags=["bbbee"])


@bbbee_router.get("/scorecards")
async def list_bbbee_scorecards(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    rows = await crud.list_rows(db, ctx, BbbeeScorecard, order_by=BbbeeScorecard.financial_year.desc())
    return {"items": [s.to_dict() for s in rows]}


@bbbee_router.post("/scorecards")
async def create_bbbee_scorecard(body: BbbeeScorecardIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.create_row(db, ctx, BbbeeScorecard, dump_set(body))).to_dict()


@bbbee_router.post("/scorecards/calculate")
async def calculate_bbbee_score(body: BbbeeCalcIn, ctx: AuthContext = Depends(member_ctx)):
    """Calculate B-BBEE score from element scores using Amended Codes 2023 weights (pure calculation, stores nothing)."""
    weights = {
        "ownership": 25,
        "management_control": 15,
        "skills_development": 20,
        "enterprise_supplier_dev": 40,
        "socio_economic_dev": 5,
    }
    scores = {
        "ownership": float(body.ownership_score),
        "management_control": float(body.management_control_score),
        "skills_development": float(body.skills_development_score),
        "enterprise_supplier_dev": float(body.enterprise_supplier_dev_score),
        "socio_economic_dev": float(body.socio_economic_dev_score),
    }
    total = sum(scores[k] * weights[k] / 100 for k in weights)

    if total >= 100:
        level = BbbeeLevel.level_1
    elif total >= 95:
        level = BbbeeLevel.level_2
    elif total >= 90:
        level = BbbeeLevel.level_3
    elif total >= 80:
        level = BbbeeLevel.level_4
    elif total >= 75:
        level = BbbeeLevel.level_5
    elif total >= 70:
        level = BbbeeLevel.level_6
    elif total >= 65:
        level = BbbeeLevel.level_7
    elif total >= 55:
        level = BbbeeLevel.level_8
    else:
        level = BbbeeLevel.non_compliant

    return {
        "overall_score": round(total, 2),
        "overall_level": level.value,
        "element_scores": scores,
        "weights": weights,
    }


@bbbee_router.get("/scorecards/{scorecard_id}")
async def get_bbbee_scorecard(scorecard_id: int, ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.get_owned(db, ctx, BbbeeScorecard, scorecard_id, "Scorecard")).to_dict()
