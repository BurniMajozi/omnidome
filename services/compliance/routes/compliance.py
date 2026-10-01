"""
Compliance Service — ICASA, POPI, RICA, Breach Register, Funding Opportunities Routes

Tenant-scoped, explicit request schemas (no mass assignment), role tiers:
reads = any member, writes = compliance_officer/manager/admin, and personal
data (DSAR subjects, consent records, RICA subjects, anonymisation audit trail)
= compliance/hr/finance admin tiers.
"""
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext
from services.common.db import get_async_session as get_db
from services.compliance import crud
from services.compliance.access import member_ctx, sensitive_ctx, write_ctx
from services.compliance.database import (
    IcasaSubmission, IcasaScrapeJob, IcasaRegulationChange,
    PopiDataAccessRequest, PopiAnonymizationLog, PopiConsentRecord,
    RicaVerification, BreachRegister, FundingOpportunity, Contract,
)
from services.compliance.write_schemas import create_schema, dump_set, update_schema

router = APIRouter()

IcasaSubmissionIn = create_schema(IcasaSubmission, protected=("icasa_reference",))
IcasaSubmissionPatch = update_schema(IcasaSubmission)
IcasaScrapeJobIn = create_schema(IcasaScrapeJob, protected=("status", "last_run", "changes_detected", "last_changes"))
IcasaRegulationChangeIn = create_schema(IcasaRegulationChange)
DsarIn = create_schema(
    PopiDataAccessRequest,
    protected=("request_reference", "status", "received_date", "due_date", "completed_date", "response_sent"),
)
AnonymizationLogIn = create_schema(PopiAnonymizationLog, protected=("performed_at",))
ConsentRecordIn = create_schema(PopiConsentRecord)
BreachIn = create_schema(BreachRegister, protected=("breach_number", "resolved_date"))
BreachPatch = update_schema(BreachRegister, protected=("breach_number",))
FundingIn = create_schema(FundingOpportunity)


class DsarCompleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: Optional[str] = None


class RicaVerificationIn(BaseModel):
    """The raw ID number is hashed on receipt and never stored."""
    model_config = ConfigDict(extra="forbid")
    id_number: str = Field(min_length=5, max_length=40)
    id_type: str = Field(max_length=50)
    full_name: Optional[str] = Field(None, max_length=200)
    source: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


# ── ICASA Submissions ───────────────────────────────────────────────────

icasa_router = APIRouter(prefix="/icasa", tags=["icasa"])


@icasa_router.get("/submissions")
async def list_icasa_submissions(
    submission_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = []
    if submission_type:
        where.append(IcasaSubmission.submission_type == submission_type)
    if status:
        where.append(IcasaSubmission.status == status)
    rows = await crud.list_rows(db, ctx, IcasaSubmission, *where)
    return {"items": [s.to_dict() for s in rows]}


@icasa_router.post("/submissions")
async def create_icasa_submission(body: IcasaSubmissionIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    data = dump_set(body)
    await crud.assert_owned(db, ctx, Contract, data.get("contract_id"), "Contract")
    return (await crud.create_row(db, ctx, IcasaSubmission, data)).to_dict()


@icasa_router.get("/submissions/{sub_id}")
async def get_icasa_submission(sub_id: int, ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.get_owned(db, ctx, IcasaSubmission, sub_id, "Submission")).to_dict()


@icasa_router.put("/submissions/{sub_id}")
async def update_icasa_submission(sub_id: int, body: IcasaSubmissionPatch, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    data = dump_set(body)
    await crud.assert_owned(db, ctx, Contract, data.get("contract_id"), "Contract")
    return (await crud.update_row(db, ctx, IcasaSubmission, sub_id, data, "Submission")).to_dict()


# ── ICASA Scraping ──────────────────────────────────────────────────────

@icasa_router.get("/scrape-jobs")
async def list_scrape_jobs(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    rows = await crud.list_rows(db, ctx, IcasaScrapeJob)
    return {"items": [j.to_dict() for j in rows]}


@icasa_router.post("/scrape-jobs")
async def create_scrape_job(body: IcasaScrapeJobIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.create_row(db, ctx, IcasaScrapeJob, dump_set(body))).to_dict()


@icasa_router.post("/scrape-jobs/{job_id}/run")
async def run_scrape_job(job_id: int, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    """ICASA website scraping is not implemented. It used to record a fake 'completed' run with
    zero changes; it now says so honestly (the job row is not touched)."""
    await crud.get_owned(db, ctx, IcasaScrapeJob, job_id, "Scrape job")
    raise HTTPException(501, "ICASA scraping is not implemented; no run was performed.")


@icasa_router.get("/regulation-changes")
async def list_regulation_changes(
    impact_level: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = []
    if impact_level:
        where.append(IcasaRegulationChange.impact_level == impact_level)
    if status:
        where.append(IcasaRegulationChange.status == status)
    rows = await crud.list_rows(db, ctx, IcasaRegulationChange, *where, order_by=IcasaRegulationChange.detected_at.desc())
    return {"items": [c.to_dict() for c in rows]}


@icasa_router.post("/regulation-changes")
async def create_regulation_change(body: IcasaRegulationChangeIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    data = dump_set(body)
    await crud.assert_owned(db, ctx, IcasaScrapeJob, data.get("scrape_job_id"), "Scrape job")
    return (await crud.create_row(db, ctx, IcasaRegulationChange, data)).to_dict()


# ── POPI Act ────────────────────────────────────────────────────────────

popi_router = APIRouter(prefix="/popi", tags=["popi"])


@popi_router.get("/dsar")
async def list_dsar(
    status: Optional[str] = Query(None),
    ctx: AuthContext = Depends(sensitive_ctx),  # data-subject names / contact details
    db: AsyncSession = Depends(get_db),
):
    where = [PopiDataAccessRequest.status == status] if status else []
    rows = await crud.list_rows(db, ctx, PopiDataAccessRequest, *where, order_by=PopiDataAccessRequest.due_date)
    return {"items": [r.to_dict() for r in rows]}


@popi_router.post("/dsar")
async def create_dsar(body: DsarIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    data = dump_set(body)
    await crud.assert_owned(db, ctx, Contract, data.get("contract_id"), "Contract")
    now = datetime.utcnow()
    data["request_reference"] = f"DSAR-{uuid.uuid4().hex[:8].upper()}"
    data["status"] = "received"
    data["received_date"] = now
    data["due_date"] = now + timedelta(days=30)  # POPIA statutory response window
    return (await crud.create_row(db, ctx, PopiDataAccessRequest, data)).to_dict()


@popi_router.put("/dsar/{dsar_id}/complete")
async def complete_dsar(dsar_id: int, body: DsarCompleteIn, ctx: AuthContext = Depends(sensitive_ctx), db: AsyncSession = Depends(get_db)):
    dsar = await crud.get_owned(db, ctx, PopiDataAccessRequest, dsar_id, "DSAR")
    dsar.status = "completed"
    dsar.completed_date = datetime.utcnow()
    dsar.response_sent = True
    if body.notes:
        dsar.notes = body.notes
    await db.commit()
    return {"status": "completed", "id": dsar_id}


@popi_router.get("/dsar/dashboard")
async def dsar_dashboard(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    requests = await crud.list_rows(db, ctx, PopiDataAccessRequest)
    total = len(requests)
    now = datetime.utcnow()
    overdue = sum(1 for r in requests if r.due_date and r.due_date < now and r.status != "completed")
    pending = sum(1 for r in requests if r.status in ("received", "in_progress"))
    completed = sum(1 for r in requests if r.status == "completed")
    return {"total": total, "overdue": overdue, "pending": pending, "completed": completed}


@popi_router.get("/anonymization-logs")
async def list_anonymization_logs(
    table_name: Optional[str] = Query(None),
    ctx: AuthContext = Depends(sensitive_ctx),  # audit trail
    db: AsyncSession = Depends(get_db),
):
    where = [PopiAnonymizationLog.table_name == table_name] if table_name else []
    rows = await crud.list_rows(db, ctx, PopiAnonymizationLog, *where)
    return {"items": [r.to_dict() for r in rows]}


@popi_router.post("/anonymization-logs")
async def create_anonymization_log(body: AnonymizationLogIn, ctx: AuthContext = Depends(sensitive_ctx), db: AsyncSession = Depends(get_db)):
    data = dump_set(body)
    data["performed_by"] = str(ctx.user_id)  # who did it comes from the identity, not the client
    return (await crud.create_row(db, ctx, PopiAnonymizationLog, data)).to_dict()


@popi_router.get("/consent-records")
async def list_consent_records(
    data_subject_id: Optional[str] = Query(None),
    ctx: AuthContext = Depends(sensitive_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = [PopiConsentRecord.data_subject_id == data_subject_id] if data_subject_id else []
    rows = await crud.list_rows(db, ctx, PopiConsentRecord, *where)
    return {"items": [r.to_dict() for r in rows]}


@popi_router.post("/consent-records")
async def create_consent_record(body: ConsentRecordIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.create_row(db, ctx, PopiConsentRecord, dump_set(body))).to_dict()


# ── RICA ────────────────────────────────────────────────────────────────

rica_router = APIRouter(prefix="/rica", tags=["rica"])


@rica_router.get("/verifications")
async def list_rica_verifications(
    status: Optional[str] = Query(None),
    ctx: AuthContext = Depends(sensitive_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = [RicaVerification.status == status] if status else []
    rows = await crud.list_rows(db, ctx, RicaVerification, *where)
    return {"items": [v.to_dict() for v in rows]}


@rica_router.post("/verifications")
async def create_rica_verification(body: RicaVerificationIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    # Store only the hashed ID number (POPIA data minimisation)
    data = body.model_dump(exclude_unset=True)
    data["id_number_hash"] = hashlib.sha256(data.pop("id_number").encode()).hexdigest()
    return (await crud.create_row(db, ctx, RicaVerification, data)).to_dict()


@rica_router.get("/dashboard")
async def rica_dashboard(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    verifications = await crud.list_rows(db, ctx, RicaVerification)
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
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = []
    if severity:
        where.append(BreachRegister.severity == severity)
    if status:
        where.append(BreachRegister.status == status)
    if category:
        where.append(BreachRegister.category == category)
    rows = await crud.list_rows(db, ctx, BreachRegister, *where, order_by=BreachRegister.identified_date.desc())
    return {"items": [b.to_dict() for b in rows]}


@breach_router.post("/")
async def create_breach(body: BreachIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    data = dump_set(body)
    data["breach_number"] = f"BRC-{uuid.uuid4().hex[:8].upper()}"
    return (await crud.create_row(db, ctx, BreachRegister, data)).to_dict()


@breach_router.put("/{breach_id}")
async def update_breach(breach_id: int, body: BreachPatch, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    data = dump_set(body)
    if data.get("status") == "resolved":
        data["resolved_date"] = datetime.utcnow()
    return (await crud.update_row(db, ctx, BreachRegister, breach_id, data, "Breach")).to_dict()


@breach_router.get("/dashboard")
async def breach_dashboard(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    breaches = await crud.list_rows(db, ctx, BreachRegister)
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
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = []
    if status:
        where.append(FundingOpportunity.status == status)
    if funding_type:
        where.append(FundingOpportunity.funding_type == funding_type)
    rows = await crud.list_rows(db, ctx, FundingOpportunity, *where, order_by=FundingOpportunity.application_deadline)
    return {"items": [o.to_dict() for o in rows]}


@funding_router.post("/")
async def create_funding_opportunity(body: FundingIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.create_row(db, ctx, FundingOpportunity, dump_set(body))).to_dict()


@funding_router.post("/match")
async def match_funding_by_compliance(
    min_score: float = Query(0),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    """Opportunities this tenant has recorded whose minimum compliance score is at most `min_score`."""
    rows = await crud.list_rows(
        db, ctx, FundingOpportunity,
        FundingOpportunity.status == "identified",
        FundingOpportunity.min_compliance_score <= min_score,
    )
    return {"items": [o.to_dict() for o in rows], "min_score": min_score}
