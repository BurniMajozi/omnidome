"""
Compliance Service — Tax, H&S, CIPC, Bylaw, BBBEE Routes
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.db import get_async_session as get_db
from services.compliance.database import (
    TaxRegistration, TaxReturn, TaxReturnStatus, TaxType,
    HsRiskAssessment, HsIncident, HsSeverity,
    CipcFiling, BylawObligation, BbbeeScorecard, BbbeeLevel,
    ComplianceStatus,
)

router = APIRouter()


# ── Tax Compliance ──────────────────────────────────────────────────────

tax_router = APIRouter(prefix="/tax", tags=["tax"])


@tax_router.get("/registrations")
async def list_tax_registrations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TaxRegistration))
    return {"items": [r.to_dict() for r in result.scalars().all()]}


@tax_router.post("/registrations")
async def create_tax_registration(body: dict, db: AsyncSession = Depends(get_db)):
    reg = TaxRegistration(**body)
    db.add(reg)
    await db.commit()
    await db.refresh(reg)
    return reg.to_dict()


@tax_router.get("/returns")
async def list_tax_returns(
    tax_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(TaxReturn)
    if tax_type:
        q = q.where(TaxReturn.tax_type == tax_type)
    if status:
        q = q.where(TaxReturn.status == status)
    q = q.order_by(TaxReturn.period_end.desc())
    result = await db.execute(q)
    return {"items": [r.to_dict() for r in result.scalars().all()]}


@tax_router.post("/returns")
async def create_tax_return(body: dict, db: AsyncSession = Depends(get_db)):
    tr = TaxReturn(**body)
    db.add(tr)
    await db.commit()
    await db.refresh(tr)
    return tr.to_dict()


@tax_router.put("/returns/{return_id}/submit")
async def submit_tax_return(return_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TaxReturn).where(TaxReturn.id == return_id))
    tr = result.scalar_one_or_none()
    if not tr:
        raise HTTPException(404, "Tax return not found")
    tr.status = TaxReturnStatus.submitted
    tr.submission_date = date.today()
    await db.commit()
    return {"status": "submitted", "id": return_id}


@tax_router.get("/dashboard")
async def tax_dashboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TaxReturn))
    returns = result.scalars().all()
    total = len(returns)
    overdue = sum(1 for r in returns if r.status == TaxReturnStatus.overdue)
    pending = sum(1 for r in returns if r.status == TaxReturnStatus.pending)
    submitted = sum(1 for r in returns if r.status in (TaxReturnStatus.submitted, TaxReturnStatus.assessed, TaxReturnStatus.paid))
    total_payable = sum(float(r.amount_payable or 0) for r in returns)
    return {"total": total, "overdue": overdue, "pending": pending, "submitted": submitted, "total_payable": total_payable}


# ── Health & Safety ─────────────────────────────────────────────────────

hs_router = APIRouter(prefix="/health-safety", tags=["health-safety"])


@hs_router.get("/risk-assessments")
async def list_risk_assessments(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(HsRiskAssessment))
    return {"items": [r.to_dict() for r in result.scalars().all()]}


@hs_router.post("/risk-assessments")
async def create_risk_assessment(body: dict, db: AsyncSession = Depends(get_db)):
    ra = HsRiskAssessment(**body)
    db.add(ra)
    await db.commit()
    await db.refresh(ra)
    return ra.to_dict()


@hs_router.get("/incidents")
async def list_incidents(
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(HsIncident)
    if severity:
        q = q.where(HsIncident.severity == severity)
    if status:
        q = q.where(HsIncident.status == status)
    q = q.order_by(HsIncident.incident_date.desc())
    result = await db.execute(q)
    return {"items": [i.to_dict() for i in result.scalars().all()]}


@hs_router.post("/incidents")
async def create_incident(body: dict, db: AsyncSession = Depends(get_db)):
    incident = HsIncident(**body)
    db.add(incident)
    await db.commit()
    await db.refresh(incident)
    return incident.to_dict()


@hs_router.put("/incidents/{incident_id}")
async def update_incident(incident_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(HsIncident).where(HsIncident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(404, "Incident not found")
    for k, v in body.items():
        setattr(incident, k, v)
    await db.commit()
    await db.refresh(incident)
    return incident.to_dict()


@hs_router.get("/dashboard")
async def hs_dashboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(HsIncident))
    incidents = result.scalars().all()
    total = len(incidents)
    open_count = sum(1 for i in incidents if i.status == "open")
    critical = sum(1 for i in incidents if i.severity == HsSeverity.critical)
    coida_reported = sum(1 for i in incidents if i.coida_reported)
    return {"total": total, "open": open_count, "critical": critical, "coida_reported": coida_reported}


# ── CIPC Compliance ─────────────────────────────────────────────────────

cipc_router = APIRouter(prefix="/cipc", tags=["cipc"])


@cipc_router.get("/filings")
async def list_cipc_filings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CipcFiling).order_by(CipcFiling.due_date))
    return {"items": [f.to_dict() for f in result.scalars().all()]}


@cipc_router.post("/filings")
async def create_cipc_filing(body: dict, db: AsyncSession = Depends(get_db)):
    filing = CipcFiling(**body)
    db.add(filing)
    await db.commit()
    await db.refresh(filing)
    return filing.to_dict()


@cipc_router.put("/filings/{filing_id}/file")
async def file_cipc_return(filing_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CipcFiling).where(CipcFiling.id == filing_id))
    filing = result.scalar_one_or_none()
    if not filing:
        raise HTTPException(404, "Filing not found")
    filing.status = "filed"
    filing.filed_date = date.today()
    filing.confirmation_number = body.get("confirmation_number")
    await db.commit()
    return {"status": "filed", "id": filing_id}


# ── Bylaw Compliance ────────────────────────────────────────────────────

bylaw_router = APIRouter(prefix="/bylaw", tags=["bylaw"])


@bylaw_router.get("/obligations")
async def list_bylaw_obligations(
    municipality: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(BylawObligation)
    if municipality:
        q = q.where(BylawObligation.municipality == municipality)
    result = await db.execute(q)
    return {"items": [o.to_dict() for o in result.scalars().all()]}


@bylaw_router.post("/obligations")
async def create_bylaw_obligation(body: dict, db: AsyncSession = Depends(get_db)):
    obl = BylawObligation(**body)
    db.add(obl)
    await db.commit()
    await db.refresh(obl)
    return obl.to_dict()


@bylaw_router.put("/obligations/{obl_id}")
async def update_bylaw_obligation(obl_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BylawObligation).where(BylawObligation.id == obl_id))
    obl = result.scalar_one_or_none()
    if not obl:
        raise HTTPException(404, "Obligation not found")
    for k, v in body.items():
        setattr(obl, k, v)
    await db.commit()
    await db.refresh(obl)
    return obl.to_dict()


# ── BBBEE Compliance ────────────────────────────────────────────────────

bbbee_router = APIRouter(prefix="/bbbee", tags=["bbbee"])


@bbbee_router.get("/scorecards")
async def list_bbbee_scorecards(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BbbeeScorecard).order_by(BbbeeScorecard.financial_year.desc()))
    return {"items": [s.to_dict() for s in result.scalars().all()]}


@bbbee_router.post("/scorecards")
async def create_bbbee_scorecard(body: dict, db: AsyncSession = Depends(get_db)):
    sc = BbbeeScorecard(**body)
    db.add(sc)
    await db.commit()
    await db.refresh(sc)
    return sc.to_dict()


@bbbee_router.post("/scorecards/calculate")
async def calculate_bbbee_score(body: dict, db: AsyncSession = Depends(get_db)):
    """Calculate B-BBEE score from element scores using Amended Codes 2023 weights."""
    weights = {
        "ownership": 25,
        "management_control": 15,
        "skills_development": 20,
        "enterprise_supplier_dev": 40,
        "socio_economic_dev": 5,
    }
    scores = {
        "ownership": float(body.get("ownership_score", 0)),
        "management_control": float(body.get("management_control_score", 0)),
        "skills_development": float(body.get("skills_development_score", 0)),
        "enterprise_supplier_dev": float(body.get("enterprise_supplier_dev_score", 0)),
        "socio_economic_dev": float(body.get("socio_economic_dev_score", 0)),
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
async def get_bbbee_scorecard(scorecard_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BbbeeScorecard).where(BbbeeScorecard.id == scorecard_id))
    sc = result.scalar_one_or_none()
    if not sc:
        raise HTTPException(404, "Scorecard not found")
    return sc.to_dict()
