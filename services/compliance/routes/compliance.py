"""
Compliance Service — ICASA, POPI, RICA, Breach Register, Funding Opportunities Routes
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.db import get_async_session as get_db
from services.compliance.database import (
    IcasaSubmission, IcasaScrapeJob, IcasaRegulationChange,
    PopiDataAccessRequest, PopiAnonymizationLog, PopiConsentRecord,
    RicaVerification,
    BreachRegister, BreachRegister, ComplianceCategory,
    FundingOpportunity, BbbeeLevel,
)

router = APIRouter()


# ── ICASA Submissions ───────────────────────────────────────────────────

icasa_router = APIRouter(prefix="/icasa", tags=["icasa"])


@icasa_router.get("/submissions")
async def list_icasa_submissions(
    submission_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(IcasaSubmission)
    if submission_type:
        q = q.where(IcasaSubmission.submission_type == submission_type)
    if status:
        q = q.where(IcasaSubmission.status == status)
    result = await db.execute(q)
    return {"items": [s.to_dict() for s in result.scalars().all()]}


@icasa_router.post("/submissions")
async def create_icasa_submission(body: dict, db: AsyncSession = Depends(get_db)):
    sub = IcasaSubmission(**body)
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub.to_dict()


@icasa_router.get("/submissions/{sub_id}")
async def get_icasa_submission(sub_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(IcasaSubmission).where(IcasaSubmission.id == sub_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Submission not found")
    return sub.to_dict()


@icasa_router.put("/submissions/{sub_id}")
async def update_icasa_submission(sub_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(IcasaSubmission).where(IcasaSubmission.id == sub_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Submission not found")
    for k, v in body.items():
        setattr(sub, k, v)
    await db.commit()
    await db.refresh(sub)
    return sub.to_dict()


# ── ICASA Scraping ──────────────────────────────────────────────────────

@icasa_router.get("/scrape-jobs")
async def list_scrape_jobs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(IcasaScrapeJob))
    return {"items": [j.to_dict() for j in result.scalars().all()]}


@icasa_router.post("/scrape-jobs")
async def create_scrape_job(body: dict, db: AsyncSession = Depends(get_db)):
    job = IcasaScrapeJob(**body)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job.to_dict()


@icasa_router.post("/scrape-jobs/{job_id}/run")
async def run_scrape_job(job_id: int, db: AsyncSession = Depends(get_db)):
    """Trigger ICASA website scrape job."""
    result = await db.execute(select(IcasaScrapeJob).where(IcasaScrapeJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Scrape job not found")
    # In production, this would trigger actual web scraping
    job.last_run = datetime.utcnow()
    job.status = "completed"
    job.changes_detected = 0
    await db.commit()
    return {"status": "completed", "job_id": job_id}


@icasa_router.get("/regulation-changes")
async def list_regulation_changes(
    impact_level: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(IcasaRegulationChange)
    if impact_level:
        q = q.where(IcasaRegulationChange.impact_level == impact_level)
    if status:
        q = q.where(IcasaRegulationChange.status == status)
    q = q.order_by(IcasaRegulationChange.detected_at.desc())
    result = await db.execute(q)
    return {"items": [c.to_dict() for c in result.scalars().all()]}


@icasa_router.post("/regulation-changes")
async def create_regulation_change(body: dict, db: AsyncSession = Depends(get_db)):
    change = IcasaRegulationChange(**body)
    db.add(change)
    await db.commit()
    await db.refresh(change)
    return change.to_dict()


# ── POPI Act ────────────────────────────────────────────────────────────

popi_router = APIRouter(prefix="/popi", tags=["popi"])


@popi_router.get("/dsar")
async def list_dsar(
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(PopiDataAccessRequest)
    if status:
        q = q.where(PopiDataAccessRequest.status == status)
    q = q.order_by(PopiDataAccessRequest.due_date)
    result = await db.execute(q)
    return {"items": [r.to_dict() for r in result.scalars().all()]}


@popi_router.post("/dsar")
async def create_dsar(body: dict, db: AsyncSession = Depends(get_db)):
    # Auto-set due date to 30 days from now (POPI requirement)
    if "due_date" not in body:
        body["due_date"] = datetime.utcnow() + timedelta(days=30)
    dsar = PopiDataAccessRequest(**body)
    db.add(dsar)
    await db.commit()
    await db.refresh(dsar)
    return dsar.to_dict()


@popi_router.put("/dsar/{dsar_id}/complete")
async def complete_dsar(dsar_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PopiDataAccessRequest).where(PopiDataAccessRequest.id == dsar_id))
    dsar = result.scalar_one_or_none()
    if not dsar:
        raise HTTPException(404, "DSAR not found")
    dsar.status = "completed"
    dsar.completed_date = datetime.utcnow()
    dsar.response_sent = True
    await db.commit()
    return {"status": "completed", "id": dsar_id}


@popi_router.get("/dsar/dashboard")
async def dsar_dashboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PopiDataAccessRequest))
    requests = result.scalars().all()
    total = len(requests)
    overdue = sum(1 for r in requests if r.due_date and r.due_date < datetime.utcnow() and r.status != "completed")
    pending = sum(1 for r in requests if r.status in ("received", "in_progress"))
    completed = sum(1 for r in requests if r.status == "completed")
    return {"total": total, "overdue": overdue, "pending": pending, "completed": completed}


@popi_router.get("/anonymization-logs")
async def list_anonymization_logs(
    table_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(PopiAnonymizationLog)
    if table_name:
        q = q.where(PopiAnonymizationLog.table_name == table_name)
    result = await db.execute(q)
    return {"items": [l.to_dict() for l in result.scalars().all()]}


@popi_router.post("/anonymization-logs")
async def create_anonymization_log(body: dict, db: AsyncSession = Depends(get_db)):
    log = PopiAnonymizationLog(**body)
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log.to_dict()


@popi_router.get("/consent-records")
async def list_consent_records(
    data_subject_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(PopiConsentRecord)
    if data_subject_id:
        q = q.where(PopiConsentRecord.data_subject_id == data_subject_id)
    result = await db.execute(q)
    return {"items": [r.to_dict() for r in result.scalars().all()]}


@popi_router.post("/consent-records")
async def create_consent_record(body: dict, db: AsyncSession = Depends(get_db)):
    rec = PopiConsentRecord(**body)
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec.to_dict()


# ── RICA ────────────────────────────────────────────────────────────────

rica_router = APIRouter(prefix="/rica", tags=["rica"])


@rica_router.get("/verifications")
async def list_rica_verifications(
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(RicaVerification)
    if status:
        q = q.where(RicaVerification.status == status)
    result = await db.execute(q)
    return {"items": [v.to_dict() for v in result.scalars().all()]}


@rica_router.post("/verifications")
async def create_rica_verification(body: dict, db: AsyncSession = Depends(get_db)):
    # Store only hashed ID number (POPI compliance)
    import hashlib
    if "id_number" in body:
        body["id_number_hash"] = hashlib.sha256(body.pop("id_number").encode()).hexdigest()
    v = RicaVerification(**body)
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return v.to_dict()


@rica_router.get("/dashboard")
async def rica_dashboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RicaVerification))
    verifications = result.scalars().all()
    total = len(verifications)
    verified = sum(1 for v in verifications if v.status == "verified")
    pending = sum(1 for v in verifications if v.status == "pending")
    expired = sum(1 for v in verifications if v.expiry_date and v.expiry_date < datetime.utcnow())
    return {"total": total, "verified": verified, "pending": pending, "expired": expired}


# ── Breach Register ─────────────────────────────────────────────────────

breach_router = APIRouter(prefix="/breaches", tags=["breaches"])


@breach_router.get("/")
async def list_breaches(
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(BreachRegister)
    if severity:
        q = q.where(BreachRegister.severity == severity)
    if status:
        q = q.where(BreachRegister.status == status)
    if category:
        q = q.where(BreachRegister.category == category)
    q = q.order_by(BreachRegister.identified_date.desc())
    result = await db.execute(q)
    return {"items": [b.to_dict() for b in result.scalars().all()]}


@breach_router.post("/")
async def create_breach(body: dict, db: AsyncSession = Depends(get_db)):
    breach = BreachRegister(**body)
    db.add(breach)
    await db.commit()
    await db.refresh(breach)
    return breach.to_dict()


@breach_router.put("/{breach_id}")
async def update_breach(breach_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BreachRegister).where(BreachRegister.id == breach_id))
    breach = result.scalar_one_or_none()
    if not breach:
        raise HTTPException(404, "Breach not found")
    for k, v in body.items():
        setattr(breach, k, v)
    await db.commit()
    await db.refresh(breach)
    return breach.to_dict()


@breach_router.get("/dashboard")
async def breach_dashboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BreachRegister))
    breaches = result.scalars().all()
    total = len(breaches)
    open_count = sum(1 for b in breaches if b.status in ("identified", "investigating"))
    critical = sum(1 for b in breaches if b.severity == "critical")
    icasa_notified = sum(1 for b in breaches if b.icasa_notified)
    popi_notified = sum(1 for b in breaches if b.popi_commission_notified)
    total_impact = sum(float(b.financial_impact or 0) for b in breaches)
    return {
        "total": total, "open": open_count, "critical": critical,
        "icasa_notified": icasa_notified, "popi_notified": popi_notified,
        "total_financial_impact": total_impact,
    }


# ── Funding Opportunities ───────────────────────────────────────────────

funding_router = APIRouter(prefix="/funding", tags=["funding"])


@funding_router.get("/")
async def list_funding_opportunities(
    status: Optional[str] = Query(None),
    funding_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(FundingOpportunity)
    if status:
        q = q.where(FundingOpportunity.status == status)
    if funding_type:
        q = q.where(FundingOpportunity.funding_type == funding_type)
    q = q.order_by(FundingOpportunity.application_deadline)
    result = await db.execute(q)
    return {"items": [o.to_dict() for o in result.scalars().all()]}


@funding_router.post("/")
async def create_funding_opportunity(body: dict, db: AsyncSession = Depends(get_db)):
    opp = FundingOpportunity(**body)
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return opp.to_dict()


@funding_router.post("/match")
async def match_funding_by_compliance(
    min_score: float = Query(0),
    db: AsyncSession = Depends(get_db),
):
    """Match funding opportunities based on compliance score and BBBEE level."""
    result = await db.execute(
        select(FundingOpportunity)
        .where(FundingOpportunity.status == "identified")
        .where(FundingOpportunity.min_compliance_score <= min_score)
    )
    return {"items": [o.to_dict() for o in result.scalars().all()], "min_score": min_score}
