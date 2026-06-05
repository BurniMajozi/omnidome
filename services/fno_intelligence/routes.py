"""FNO Intelligence routes — browser automation, data extraction, operational tasks.

Covers:
 1. Job management (create, execute, status, cancel)
 2. Screen recording & screenshot management
 3. Network intelligence (coverage, status, promotions, pricing, new areas)
 4. Lead generation from FNO data
 5. Operational automation (cancel, ticket, migration, pause, reports)
 6. Template management
"""

import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import get_current_tenant_id
from services.fno_intelligence.database import get_session
from services.fno_intelligence.models import (
    Base,
    FNOScreenshot,
    FNOAutomationJob,
    FNOAutomationStep,
    FNOAutomationTemplate,
    FNONetworkCoverage,
    FNONetworkStatus,
    FNOPromotion,
    FNOPricing,
    FNONewArea,
    FNOLead,
    FNOOperationalTask,
    FNOReport,
    FNOPortalSession,
)

router = APIRouter(tags=["FNO Intelligence"])


# ════════════════════════════════════════════════════════════════════════
# 1. AUTOMATION JOBS
# ════════════════════════════════════════════════════════════════════════

class JobCreate(BaseModel):
    job_type: str
    fno_portal: str
    fno_name: str
    customer_id: Optional[str] = None
    fno_account_number: Optional[str] = None
    priority: int = 5
    scheduled_at: Optional[datetime] = None
    payload: Optional[dict] = None


class JobUpdate(BaseModel):
    status: Optional[str] = None
    result_data: Optional[dict] = None
    error_message: Optional[str] = None
    confirmation_number: Optional[str] = None


@router.post("/jobs")
async def create_job(payload: JobCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    job = FNOAutomationJob(
        tenant_id=tenant_id, fno_portal=payload.fno_portal, fno_name=payload.fno_name,
        job_type=payload.job_type, priority=payload.priority,
        customer_id=uuid.UUID(payload.customer_id) if payload.customer_id else None,
        fno_account_number=payload.fno_account_number,
        scheduled_at=payload.scheduled_at, result_data=payload.payload,
    )
    db.add(job)
    await db.flush()
    return {"id": str(job.id), "status": job.status}


@router.post("/jobs/{job_id}/execute")
async def execute_job(job_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(FNOAutomationJob).where(FNOAutomationJob.id == job_id, FNOAutomationJob.tenant_id == tenant_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status not in ("queued", "failed", "cancelled"):
        raise HTTPException(400, f"Cannot execute job in '{job.status}' status")

    job.status = "running"
    job.started_at = datetime.utcnow()

    # Create browser session
    session = FNOPortalSession(tenant_id=tenant_id, session_id=f"sess_{uuid.uuid4().hex[:12]}", fno_portal=job.fno_portal)
    db.add(session)
    await db.flush()
    job.session_id = session.id

    # Execute based on job type
    # In production: subprocess call to Playwright automation
    # For now, simulate execution
    job.status = "completed"
    job.completed_at = datetime.utcnow()
    job.result_data = {"simulated": True, "steps_executed": 5}

    # Create automation steps
    for i in range(1, 6):
        db.add(FNOAutomationStep(
            job_id=job.id, tenant_id=tenant_id, step_number=i,
            action="navigate" if i == 1 else "click" if i < 5 else "screenshot",
            target_url=f"https://{job.fno_portal}.com/page{i}" if i == 1 else f"#element{i}",
            status="completed",
            started_at=datetime.utcnow(), completed_at=datetime.utcnow(), duration_seconds=2,
        ))

    # Capture screenshot
    db.add(FNOScreenshot(
        tenant_id=tenant_id, job_id=job.id,
        screenshot_path=f"screenshots/{job.id}/final.png",
        page_url=f"https://{job.fno_portal}.com/confirmation",
        page_title="Confirmation",
    ))

    # If operational task, update linked task
    if job.job_type in ("cancellation", "ticket_logging", "migration", "pause_service"):
        task_result = await db.execute(select(FNOOperationalTask).where(FNOOperationalTask.automation_job_id == job.id))
        task = task_result.scalar_one_or_none()
        if task:
            task.status = "completed"
            task.completed_at = datetime.utcnow()
            task.screenshot_after_path = f"screenshots/{job.id}/final.png"

    await db.flush()
    return {"id": str(job.id), "status": job.status, "steps": 5}


@router.get("/jobs")
async def list_jobs(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session),
                     status: Optional[str] = None, job_type: Optional[str] = None, limit: int = Query(50, le=200), offset: int = 0):
    query = select(FNOAutomationJob).where(FNOAutomationJob.tenant_id == tenant_id)
    if status:
        query = query.where(FNOAutomationJob.status == status)
    if job_type:
        query = query.where(FNOAutomationJob.job_type == job_type)
    query = query.order_by(desc(FNOAutomationJob.created_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    jobs = result.scalars().all()
    return [{"id": str(j.id), "job_type": j.job_type, "fno_portal": j.fno_portal, "status": j.status, "created_at": j.created_at.isoformat()} for j in jobs]


@router.get("/jobs/{job_id}")
async def get_job(job_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(FNOAutomationJob).where(FNOAutomationJob.id == job_id, FNOAutomationJob.tenant_id == tenant_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")

    steps_result = await db.execute(select(FNOAutomationStep).where(FNOAutomationStep.job_id == job_id).order_by(FNOAutomationStep.step_number))
    steps = steps_result.scalars().all()

    screenshots_result = await db.execute(select(FNOScreenshot).where(FNOScreenshot.job_id == job_id))
    screenshots = screenshots_result.scalars().all()

    return {
        "id": str(job.id), "job_type": job.job_type, "fno_portal": job.fno_portal,
        "status": job.status, "result_data": job.result_data,
        "screen_recording_path": job.screen_recording_path,
        "steps": [{"number": s.step_number, "action": s.action, "status": s.status, "duration": s.duration_seconds, "extracted_data": s.extracted_data} for s in steps],
        "screenshots": [{"path": s.screenshot_path, "caption": s.caption, "url": s.page_url} for s in screenshots],
    }


# ════════════════════════════════════════════════════════════════════════
# 2. SCREEN RECORDING
# ════════════════════════════════════════════════════════════════════════

class RecordingStart(BaseModel):
    job_id: str
    resolution: str = "1920x1080"
    fps: int = 15


@router.post("/recordings/start")
async def start_recording(payload: RecordingStart, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    job_result = await db.execute(select(FNOAutomationJob).where(FNOAutomationJob.id == uuid.UUID(payload.job_id), FNOAutomationJob.tenant_id == tenant_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")

    recording_path = f"recordings/{payload.job_id}/{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.webm"
    job.screen_recording_path = recording_path
    session_result = await db.execute(select(FNOPortalSession).where(FNOPortalSession.id == job.session_id))
    session = session_result.scalar_one_or_none()
    if session:
        session.is_recording = True
        session.recording_started_at = datetime.utcnow()

    await db.flush()
    return {"recording_path": recording_path, "started": True}


@router.post("/recordings/{job_id}/stop")
async def stop_recording(job_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    job_result = await db.execute(select(FNOAutomationJob).where(FNOAutomationJob.id == job_id, FNOAutomationJob.tenant_id == tenant_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")

    session_result = await db.execute(select(FNOPortalSession).where(FNOPortalSession.id == job.session_id))
    session = session_result.scalar_one_or_none()
    if session:
        session.is_recording = False

    await db.flush()
    return {"recording_path": job.screen_recording_path, "stopped": True}


# ════════════════════════════════════════════════════════════════════════
# 3. NETWORK INTELLIGENCE
# ════════════════════════════════════════════════════════════════════════

@router.get("/intelligence/coverage")
async def get_coverage(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session),
                        fno: Optional[str] = None, city: Optional[str] = None, status: Optional[str] = None):
    query = select(FNONetworkCoverage).where(FNONetworkCoverage.tenant_id == tenant_id)
    if fno:
        query = query.where(FNONetworkCoverage.fno_name == fno)
    if city:
        query = query.where(FNONetworkCoverage.city == city)
    if status:
        query = query.where(FNONetworkCoverage.status == status)
    result = await db.execute(query.order_by(FNONetworkCoverage.city, FNONetworkCoverage.area_name))
    items = result.scalars().all()
    return [{"fno": i.fno_name, "area": i.area_name, "city": i.city, "status": i.status, "technology": i.technology, "max_speed": i.max_speed_mbps} for i in items]


@router.get("/intelligence/network-status")
async def get_network_status(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session),
                              fno: Optional[str] = None, severity: Optional[str] = None):
    query = select(FNONetworkStatus).where(FNONetworkStatus.tenant_id == tenant_id)
    if fno:
        query = query.where(FNONetworkStatus.fno_name == fno)
    if severity:
        query = query.where(FNONetworkStatus.severity == severity)
    result = await db.execute(query.order_by(desc(FNONetworkStatus.reported_at)))
    items = result.scalars().all()
    return [{"fno": i.fno_name, "type": i.status_type, "severity": i.severity, "title": i.title, "areas": i.affected_areas, "reported": i.reported_at.isoformat()} for i in items]


@router.get("/intelligence/promotions")
async def get_promotions(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session),
                          fno: Optional[str] = None, active: bool = True):
    query = select(FNOPromotion).where(FNOPromotion.tenant_id == tenant_id, FNOPromotion.is_active == active)
    if fno:
        query = query.where(FNOPromotion.fno_name == fno)
    result = await db.execute(query.order_by(desc(FNOPromotion.first_detected_at)))
    items = result.scalars().all()
    return [{"fno": i.fno_name, "title": i.title, "type": i.promo_type, "original": float(i.original_price_zar) if i.original_price_zar else None, "discounted": float(i.discounted_price_zar) if i.discounted_price_zar else None, "valid_until": i.valid_until.isoformat() if i.valid_until else None} for i in items]


@router.get("/intelligence/pricing")
async def get_pricing(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session),
                       fno: Optional[str] = None, speed: Optional[int] = None):
    query = select(FNOPricing).where(FNOPricing.tenant_id == tenant_id)
    if fno:
        query = query.where(FNOPricing.fno_name == fno)
    if speed:
        query = query.where(FNOPricing.speed_mbps == speed)
    result = await db.execute(query.order_by(FNOPricing.fno_name, FNOPricing.speed_mbps))
    items = result.scalars().all()
    return [{"fno": i.fno_name, "package": i.package_name, "speed": i.speed_mbps, "monthly": float(i.monthly_price_zar) if i.monthly_price_zar else None, "installation": float(i.installation_fee_zar) if i.installation_fee_zar else None, "effective": i.effective_date.isoformat()} for i in items]


@router.get("/intelligence/new-areas")
async def get_new_areas(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session),
                         fno: Optional[str] = None, status: Optional[str] = None):
    query = select(FNONewArea).where(FNONewArea.tenant_id == tenant_id)
    if fno:
        query = query.where(FNONewArea.fno_name == fno)
    if status:
        query = query.where(FNONewArea.build_status == status)
    result = await db.execute(query.order_by(desc(FNONewArea.first_detected_at)))
    items = result.scalars().all()
    return [{"fno": i.fno_name, "area": i.area_name, "city": i.city, "status": i.build_status, "expected": i.expected_available_date.isoformat() if i.expected_available_date else None, "leads": i.leads_generated} for i in items]


# ════════════════════════════════════════════════════════════════════════
# 4. LEAD GENERATION
# ════════════════════════════════════════════════════════════════════════

@router.get("/leads")
async def get_leads(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session),
                     status: Optional[str] = None, source: Optional[str] = None, min_score: Optional[int] = None):
    query = select(FNOLead).where(FNOLead.tenant_id == tenant_id)
    if status:
        query = query.where(FNOLead.status == status)
    if source:
        query = query.where(FNOLead.lead_source == source)
    if min_score:
        query = query.where(FNOLead.score >= min_score)
    result = await db.execute(query.order_by(desc(FNOLead.score)))
    items = result.scalars().all()
    return [{"id": str(l.id), "source": l.lead_source, "fno": l.source_fno, "name": f"{l.first_name} {l.last_name}", "city": l.city, "status": l.status, "score": l.score, "reason": l.interest_reason} for l in items]


@router.post("/leads/{lead_id}/convert")
async def convert_lead(lead_id: uuid.UUID, customer_id: str, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(FNOLead).where(FNOLead.id == lead_id, FNOLead.tenant_id == tenant_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(404, "Lead not found")
    lead.status = "converted"
    lead.converted_to_customer_id = uuid.UUID(customer_id)
    lead.converted_at = datetime.utcnow()
    await db.flush()
    return {"id": str(lead.id), "status": "converted"}


# ════════════════════════════════════════════════════════════════════════
# 5. OPERATIONAL AUTOMATION
# ════════════════════════════════════════════════════════════════════════

class OperationalTaskCreate(BaseModel):
    task_type: str  # cancellation, ticket_logging, migration, pause_service
    fno_portal: str
    fno_name: str
    customer_id: str
    fno_account_number: Optional[str] = None
    description: Optional[str] = None
    payload: Optional[dict] = None


@router.post("/operational")
async def create_operational_task(payload: OperationalTaskCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    task = FNOOperationalTask(
        tenant_id=tenant_id, customer_id=uuid.UUID(payload.customer_id),
        task_type=payload.task_type, fno_portal=payload.fno_portal,
        fno_name=payload.fno_name, fno_account_number=payload.fno_account_number,
        description=payload.description, payload=payload.payload,
    )
    db.add(task)
    await db.flush()

    # Create linked automation job
    job = FNOAutomationJob(
        tenant_id=tenant_id, customer_id=uuid.UUID(payload.customer_id),
        job_type=payload.task_type, fno_portal=payload.fno_portal,
        fno_name=payload.fno_name, fno_account_number=payload.fno_account_number,
    )
    db.add(job)
    await db.flush()
    task.automation_job_id = job.id

    await db.flush()
    return {"task_id": str(task.id), "job_id": str(job.id)}


@router.get("/operational")
async def list_operational_tasks(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session),
                                  status: Optional[str] = None, task_type: Optional[str] = None):
    query = select(FNOOperationalTask).where(FNOOperationalTask.tenant_id == tenant_id)
    if status:
        query = query.where(FNOOperationalTask.status == status)
    if task_type:
        query = query.where(FNOOperationalTask.task_type == task_type)
    result = await db.execute(query.order_by(desc(FNOOperationalTask.created_at)))
    tasks = result.scalars().all()
    return [{"id": str(t.id), "type": t.task_type, "fno": t.fno_name, "status": t.status, "created_at": t.created_at.isoformat()} for t in tasks]


# ════════════════════════════════════════════════════════════════════════
# 6. TEMPLATES
# ════════════════════════════════════════════════════════════════════════

class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    fno_portal: str
    job_type: str
    steps_template: list = Field(default_factory=list)
    selectors: dict = Field(default_factory=dict)


@router.post("/templates")
async def create_template(payload: TemplateCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    template = FNOAutomationTemplate(
        tenant_id=tenant_id, name=payload.name, description=payload.description,
        fno_portal=payload.fno_portal, job_type=payload.job_type,
        steps_template=payload.steps_template, selectors=payload.selectors,
    )
    db.add(template)
    await db.flush()
    return {"id": str(template.id), "name": template.name}


@router.get("/templates")
async def list_templates(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session),
                          fno_portal: Optional[str] = None, job_type: Optional[str] = None):
    query = select(FNOAutomationTemplate).where(FNOAutomationTemplate.tenant_id == tenant_id, FNOAutomationTemplate.is_active == True)
    if fno_portal:
        query = query.where(FNOAutomationTemplate.fno_portal == fno_portal)
    if job_type:
        query = query.where(FNOAutomationTemplate.job_type == job_type)
    result = await db.execute(query)
    templates = result.scalars().all()
    return [{"id": str(t.id), "name": t.name, "fno_portal": t.fno_portal, "job_type": t.job_type, "success_rate": float(t.success_rate) if t.success_rate else None, "runs": t.total_runs} for t in templates]


# ════════════════════════════════════════════════════════════════════════
# 7. REPORTS
# ════════════════════════════════════════════════════════════════════════

class ReportCreate(BaseModel):
    report_type: str
    title: str
    description: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None


@router.post("/reports")
async def create_report(payload: ReportCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    report = FNOReport(
        tenant_id=tenant_id, report_type=payload.report_type, title=payload.title,
        description=payload.description, period_start=payload.period_start, period_end=payload.period_end,
    )
    db.add(report)
    await db.flush()
    return {"id": str(report.id), "type": report.report_type, "title": report.title}


@router.get("/reports")
async def list_reports(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session),
                        report_type: Optional[str] = None):
    query = select(FNOReport).where(FNOReport.tenant_id == tenant_id)
    if report_type:
        query = query.where(FNOReport.report_type == report_type)
    result = await db.execute(query.order_by(desc(FNOReport.created_at)))
    reports = result.scalars().all()
    return [{"id": str(r.id), "type": r.report_type, "title": r.title, "created_at": r.created_at.isoformat(), "pdf": r.pdf_path} for r in reports]
