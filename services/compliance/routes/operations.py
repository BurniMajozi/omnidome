"""
Compliance Service — DR/BCP, Compliance Scoring, e-Services, Documents, Financial Scenarios
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.db import get_db
from services.compliance.database import (
    DrBcpPlan, DrBcpAssessment, DrBcpStatus,
    ComplianceScore, ComplianceObligation, ComplianceCategory, ComplianceStatus,
    EserviceSubmission, EservicePlatform, EserviceSubmissionStatus,
    ComplianceDocument, DocumentType,
    FinancialScenario,
)

router = APIRouter()


# ── DR/BCP ──────────────────────────────────────────────────────────────

dr_router = APIRouter(prefix="/dr-bcp", tags=["dr-bcp"])


@dr_router.get("/plans")
async def list_dr_bcp_plans(
    plan_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(DrBcpPlan)
    if plan_type:
        q = q.where(DrBcpPlan.plan_type == plan_type)
    if status:
        q = q.where(DrBcpPlan.status == status)
    result = await db.execute(q)
    return {"items": [p.__dict__ for p in result.scalars().all()]}


@dr_router.post("/plans")
async def create_dr_bcp_plan(body: dict, db: AsyncSession = Depends(get_db)):
    plan = DrBcpPlan(**body)
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan.__dict__


@dr_router.get("/plans/{plan_id}")
async def get_dr_bcp_plan(plan_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DrBcpPlan).where(DrBcpPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan.__dict__


@dr_router.put("/plans/{plan_id}")
async def update_dr_bcp_plan(plan_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DrBcpPlan).where(DrBcpPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    for k, v in body.items():
        setattr(plan, k, v)
    await db.commit()
    await db.refresh(plan)
    return plan.__dict__


@dr_router.post("/plans/{plan_id}/assessments")
async def create_dr_bcp_assessment(plan_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    body["plan_id"] = plan_id
    assessment = DrBcpAssessment(**body)
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return assessment.__dict__


@dr_router.get("/plans/{plan_id}/assessments")
async def list_dr_bcp_assessments(plan_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DrBcpAssessment)
        .where(DrBcpAssessment.plan_id == plan_id)
        .order_by(DrBcpAssessment.assessment_date.desc())
    )
    return {"items": [a.__dict__ for a in result.scalars().all()]}


@dr_router.get("/dashboard")
async def dr_bcp_dashboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DrBcpPlan))
    plans = result.scalars().all()
    total = len(plans)
    tested = sum(1 for p in plans if p.status == DrBcpStatus.tested)
    approved = sum(1 for p in plans if p.status == DrBcpStatus.approved)
    failed = sum(1 for p in plans if p.status == DrBcpStatus.failed)
    return {"total": total, "tested": tested, "approved": approved, "failed": failed}


# ── Compliance Scoring ──────────────────────────────────────────────────

score_router = APIRouter(prefix="/scores", tags=["scores"])


@score_router.get("/")
async def list_compliance_scores(
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(ComplianceScore)
    if category:
        q = q.where(ComplianceScore.category == category)
    q = q.order_by(ComplianceScore.calculated_at.desc())
    result = await db.execute(q)
    return {"items": [s.__dict__ for s in result.scalars().all()]}


@score_router.post("/calculate")
async def calculate_compliance_scores(db: AsyncSession = Depends(get_db)):
    """Calculate compliance scores across all categories."""
    scores = []
    for cat in ComplianceCategory:
        # Count obligations
        obl_result = await db.execute(
            select(ComplianceObligation).where(ComplianceObligation.category == cat)
        )
        obligations = obl_result.scalars().all()
        total = len(obligations)
        if total == 0:
            score = 100.0
            status = ComplianceStatus.exempt
            issues = 0
            critical = 0
        else:
            compliant = sum(1 for o in obligations if o.status == ComplianceStatus.compliant)
            non_compliant = sum(1 for o in obligations if o.status == ComplianceStatus.non_compliant)
            at_risk = sum(1 for o in obligations if o.status == ComplianceStatus.at_risk)
            score = (compliant / total) * 100 if total > 0 else 100
            issues = non_compliant + at_risk
            critical = non_compliant
            if score >= 90:
                status = ComplianceStatus.compliant
            elif score >= 70:
                status = ComplianceStatus.at_risk
            else:
                status = ComplianceStatus.non_compliant

        cs = ComplianceScore(
            category=cat,
            score=round(score, 2),
            status=status,
            issues_count=issues,
            critical_issues=critical,
        )
        db.add(cs)
        scores.append({"category": cat.value, "score": round(score, 2), "status": status.value})

    await db.commit()
    return {"scores": scores, "calculated_at": datetime.utcnow().isoformat()}


@score_router.get("/obligations")
async def list_obligations(
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(ComplianceObligation)
    if category:
        q = q.where(ComplianceObligation.category == category)
    if status:
        q = q.where(ComplianceObligation.status == status)
    q = q.order_by(ComplianceObligation.due_date)
    result = await db.execute(q)
    return {"items": [o.__dict__ for o in result.scalars().all()]}


@score_router.post("/obligations")
async def create_obligation(body: dict, db: AsyncSession = Depends(get_db)):
    obl = ComplianceObligation(**body)
    db.add(obl)
    await db.commit()
    await db.refresh(obl)
    return obl.__dict__


@score_router.put("/obligations/{obl_id}")
async def update_obligation(obl_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ComplianceObligation).where(ComplianceObligation.id == obl_id))
    obl = result.scalar_one_or_none()
    if not obl:
        raise HTTPException(404, "Obligation not found")
    for k, v in body.items():
        setattr(obl, k, v)
    await db.commit()
    await db.refresh(obl)
    return obl.__dict__


# ── e-Services Gateway ──────────────────────────────────────────────────

eservice_router = APIRouter(prefix="/eservices", tags=["eservices"])


@eservice_router.get("/submissions")
async def list_eservice_submissions(
    platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(EserviceSubmission)
    if platform:
        q = q.where(EserviceSubmission.platform == platform)
    if status:
        q = q.where(EserviceSubmission.status == status)
    q = q.order_by(EserviceSubmission.created_at.desc())
    result = await db.execute(q)
    return {"items": [s.__dict__ for s in result.scalars().all()]}


@eservice_router.post("/submissions")
async def create_eservice_submission(body: dict, db: AsyncSession = Depends(get_db)):
    sub = EserviceSubmission(**body)
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub.__dict__


@eservice_router.post("/submissions/{sub_id}/submit")
async def submit_to_platform(sub_id: int, db: AsyncSession = Depends(get_db)):
    """Submit form to external e-Services platform."""
    result = await db.execute(select(EserviceSubmission).where(EserviceSubmission.id == sub_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Submission not found")
    # In production, this would call the actual platform API
    sub.status = EserviceSubmissionStatus.submitted
    sub.submission_date = datetime.utcnow()
    await db.commit()
    return {"status": "submitted", "id": sub_id, "platform": sub.platform.value}


@eservice_router.get("/platforms")
async def list_platforms():
    return {"platforms": [p.value for p in EservicePlatform]}


# ── Document Understanding ──────────────────────────────────────────────

doc_router = APIRouter(prefix="/documents", tags=["documents"])


@doc_router.get("/")
async def list_documents(
    document_type: Optional[str] = Query(None),
    contract_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(ComplianceDocument)
    if document_type:
        q = q.where(ComplianceDocument.document_type == document_type)
    if contract_id:
        q = q.where(ComplianceDocument.contract_id == contract_id)
    q = q.order_by(ComplianceDocument.created_at.desc())
    result = await db.execute(q)
    return {"items": [d.__dict__ for d in result.scalars().all()]}


@doc_router.post("/")
async def create_document(body: dict, db: AsyncSession = Depends(get_db)):
    doc = ComplianceDocument(**body)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc.__dict__


@doc_router.post("/{doc_id}/ocr")
async def process_document_ocr(doc_id: int, db: AsyncSession = Depends(get_db)):
    """Process document with OCR and extract structured data."""
    result = await db.execute(select(ComplianceDocument).where(ComplianceDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    # In production, this would call OCR service (Tesseract, AWS Textract, etc.)
    doc.ocr_text = "OCR processing placeholder"
    doc.extracted_data = "{}"
    await db.commit()
    return {"status": "processed", "id": doc_id}


@doc_router.post("/{doc_id}/financial-summary")
async def extract_financial_summary(doc_id: int, db: AsyncSession = Depends(get_db)):
    """Extract financial data from document for scenario planning."""
    result = await db.execute(select(ComplianceDocument).where(ComplianceDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    # In production, this would use AI/ML to extract financial data
    doc.financial_summary = "{}"
    await db.commit()
    return {"status": "extracted", "id": doc_id}


# ── Financial Scenario Planning ─────────────────────────────────────────

scenario_router = APIRouter(prefix="/financial-scenarios", tags=["financial-scenarios"])


@scenario_router.get("/")
async def list_financial_scenarios(
    scenario_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(FinancialScenario)
    if scenario_type:
        q = q.where(FinancialScenario.scenario_type == scenario_type)
    q = q.order_by(FinancialScenario.period_start)
    result = await db.execute(q)
    return {"items": [s.__dict__ for s in result.scalars().all()]}


@scenario_router.post("/")
async def create_financial_scenario(body: dict, db: AsyncSession = Depends(get_db)):
    scenario = FinancialScenario(**body)
    db.add(scenario)
    await db.commit()
    await db.refresh(scenario)
    return scenario.__dict__


@scenario_router.get("/{scenario_id}")
async def get_financial_scenario(scenario_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FinancialScenario).where(FinancialScenario.id == scenario_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Scenario not found")
    return s.__dict__


@scenario_router.post("/{scenario_id}/match-funding")
async def match_funding_opportunities(scenario_id: int, db: AsyncSession = Depends(get_db)):
    """Match scenario with funding opportunities based on compliance score."""
    from services.compliance.database import FundingOpportunity
    result = await db.execute(select(FundingOpportunity).where(FundingOpportunity.status == "identified"))
    opportunities = result.scalars().all()
    return {
        "scenario_id": scenario_id,
        "matched_opportunities": [o.__dict__ for o in opportunities],
    }
