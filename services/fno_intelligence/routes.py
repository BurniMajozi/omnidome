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
from services.common.firecrawl import FirecrawlError, FirecrawlUnavailable
from services.fno_intelligence import web_intel

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


# ════════════════════════════════════════════════════════════════════════
# 8. KML COVERAGE IMPORT
# ════════════════════════════════════════════════════════════════════════

from fastapi import UploadFile, File, Form, BackgroundTasks
from services.fno_intelligence.models import (
    FNOKMLImport,
    NetworkFaultReport,
    NetworkFaultUpdate,
)


class KMLImportResponse(BaseModel):
    id: str
    fno_name: str
    file_name: str
    status: str
    total_features: int = 0
    imported_features: int = 0


@router.post("/kml-imports", response_model=KMLImportResponse)
async def upload_kml(
    background_tasks: BackgroundTasks,
    fno_name: str = Form(...),
    fno_portal: str = Form(...),
    file: UploadFile = File(...),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Upload a KML/KMZ file for bulk coverage area import."""
    import os
    import aiofiles

    # Save file
    upload_dir = f"/opt/data/uploads/kml/{tenant_id}"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = f"{upload_dir}/{file.filename}"

    content = await file.read()
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    # Create import record
    kml_import = FNOKMLImport(
        tenant_id=tenant_id,
        fno_name=fno_name,
        fno_portal=fno_portal,
        file_name=file.filename,
        file_size_bytes=len(content),
        file_path=file_path,
        status="uploaded",
    )
    db.add(kml_import)
    await db.flush()

    # Process in background
    background_tasks.add_task(_process_kml_import, kml_import.id)

    return KMLImportResponse(
        id=str(kml_import.id),
        fno_name=fno_name,
        file_name=file.filename,
        status="uploaded",
    )


async def _process_kml_import(import_id: uuid.UUID):
    """Background task to parse KML and import coverage areas."""
    from services.fno_intelligence.database import get_session as _get_session
    from services.fno_intelligence.models import FNONetworkCoverage

    async with _get_session() as session:
        import_record = await session.get(FNOKMLImport, import_id)
        if not import_record:
            return

        import_record.status = "parsing"
        await session.flush()

        try:
            # Parse KML
            try:
                from pykml import parser as kml_parser
                from lxml import etree

                with open(import_record.file_path, "rb") as f:
                    root = kml_parser.parse(f).getroot()

                features = []
                # Extract Placemarks
                for placemark in root.iter("{http://www.opengis.net/kml/2.2}Placemark"):
                    name_elem = placemark.find("{http://www.opengis.net/kml/2.2}name")
                    name = name_elem.text if name_elem is not None else "Unknown"

                    desc_elem = placemark.find("{http://www.opengis.net/kml/2.2}description")
                    description = desc_elem.text if desc_elem is not None else ""

                    # Extract polygon coordinates
                    coords_elem = placemark.find(
                        ".//{http://www.opengis.net/kml/2.2}coordinates"
                    )
                    coords_text = coords_elem.text.strip() if coords_elem is not None else ""

                    # Extract extended data (custom FNO fields)
                    ext_data = {}
                    for data_elem in placemark.iter("{http://www.opengis.net/kml/2.2}Data"):
                        data_name = data_elem.get("name", "")
                        value_elem = data_elem.find("{http://www.opengis.net/kml/2.2}value")
                        if value_elem is not None and value_elem.text:
                            ext_data[data_name] = value_elem.text

                    features.append({
                        "name": name,
                        "description": description,
                        "coords": coords_text,
                        "extended": ext_data,
                    })

            except ImportError:
                # Fallback: basic XML parsing without pykml
                import xml.etree.ElementTree as ET

                tree = ET.parse(import_record.file_path)
                root = tree.getroot()
                ns = {"kml": "http://www.opengis.net/kml/2.2"}

                features = []
                for placemark in root.findall(".//kml:Placemark", ns):
                    name_elem = placemark.find("kml:name", ns)
                    name = name_elem.text if name_elem is not None else "Unknown"
                    features.append({
                        "name": name,
                        "description": "",
                        "coords": "",
                        "extended": {},
                    })

            import_record.total_features = len(features)

            # Import coverage areas
            imported = 0
            skipped = 0

            for feature in features:
                # Check for duplicate
                existing = await session.execute(
                    select(FNONetworkCoverage).where(
                        FNONetworkCoverage.tenant_id == import_record.tenant_id,
                        FNONetworkCoverage.fno_name == import_record.fno_name,
                        FNONetworkCoverage.area_name == feature["name"],
                    )
                )
                if existing.scalar_one_or_none():
                    skipped += 1
                    continue

                ext = feature.get("extended", {})
                coverage = FNONetworkCoverage(
                    tenant_id=import_record.tenant_id,
                    fno_name=import_record.fno_name,
                    fno_portal=import_record.fno_portal,
                    area_name=feature["name"],
                    suburb=ext.get("suburb"),
                    city=ext.get("city", "Unknown"),
                    province=ext.get("province"),
                    technology=ext.get("technology"),
                    max_speed_mbps=int(ext["max_speed_mbps"]) if ext.get("max_speed_mbps") else None,
                    status=ext.get("status", "available"),
                    source_job_id=None,
                    source_url=f"kml://{import_record.file_name}",
                )
                session.add(coverage)
                imported += 1

            import_record.imported_features = imported
            import_record.skipped_features = skipped
            import_record.status = "imported" if imported > 0 else "partial"
            import_record.processed_at = datetime.utcnow()

        except Exception as e:
            import_record.status = "failed"
            import_record.error_message = str(e)

        await session.flush()


@router.get("/kml-imports")
async def list_kml_imports(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    fno_name: Optional[str] = None,
    status: Optional[str] = None,
):
    """List KML import history."""
    query = select(FNOKMLImport).where(FNOKMLImport.tenant_id == tenant_id)
    if fno_name:
        query = query.where(FNOKMLImport.fno_name == fno_name)
    if status:
        query = query.where(FNOKMLImport.status == status)
    result = await db.execute(query.order_by(desc(FNOKMLImport.created_at)))
    imports = result.scalars().all()
    return [{
        "id": str(i.id), "fno_name": i.fno_name, "file_name": i.file_name,
        "status": i.status, "total": i.total_features, "imported": i.imported_features,
        "skipped": i.skipped_features, "created_at": i.created_at.isoformat(),
    } for i in imports]


@router.get("/kml-imports/{import_id}")
async def get_kml_import(
    import_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Get KML import details."""
    import_record = await session.get(FNOKMLImport, import_id)
    if not import_record or import_record.tenant_id != tenant_id:
        raise HTTPException(404, "Import not found")
    return {
        "id": str(import_record.id), "fno_name": import_record.fno_name,
        "file_name": import_record.file_name, "status": import_record.status,
        "total": import_record.total_features, "imported": import_record.imported_features,
        "skipped": import_record.skipped_features, "error": import_record.error_message,
        "created_at": import_record.created_at.isoformat(),
    }


# ════════════════════════════════════════════════════════════════════════
# 9. FAULT REPORTING
# ════════════════════════════════════════════════════════════════════════

class FaultReportCreate(BaseModel):
    source: str = "customer"
    fno_name: str
    fno_portal: Optional[str] = None
    fno_account_number: Optional[str] = None
    service_id: Optional[str] = None
    area_name: Optional[str] = None
    suburb: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    fault_type: str
    severity: str = "medium"
    title: str
    description: Optional[str] = None
    fault_started_at: Optional[datetime] = None


class FaultReportUpdate(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None
    fno_ticket_reference: Optional[str] = None
    resolution_notes: Optional[str] = None
    message: Optional[str] = None


@router.post("/faults")
async def create_fault_report(
    payload: FaultReportCreate,
    background_tasks: BackgroundTasks,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Create a fault report and optionally auto-create a support ticket + notify affected customers."""
    fault = NetworkFaultReport(
        tenant_id=tenant_id,
        source=payload.source,
        fno_name=payload.fno_name,
        fno_portal=payload.fno_portal,
        fno_account_number=payload.fno_account_number,
        service_id=uuid.UUID(payload.service_id) if payload.service_id else None,
        area_name=payload.area_name,
        suburb=payload.suburb,
        city=payload.city,
        province=payload.province,
        postal_code=payload.postal_code,
        fault_type=payload.fault_type,
        severity=payload.severity,
        title=payload.title,
        description=payload.description,
        fault_started_at=payload.fault_started_at,
    )
    db.add(fault)
    await db.flush()

    # Auto-create support ticket for high/critical severity
    if payload.severity in ("high", "critical"):
        background_tasks.add_task(
            _auto_create_support_ticket, fault.id, tenant_id
        )

    # Notify affected customers in the same area
    background_tasks.add_task(
        _notify_affected_customers, fault.id, tenant_id
    )

    return {"id": str(fault.id), "status": fault.status, "severity": fault.severity}


async def _auto_create_support_ticket(fault_id: uuid.UUID, tenant_id: uuid.UUID):
    """Auto-create a support ticket for high-severity faults."""
    from services.fno_intelligence.database import get_session as _get_session
    import httpx

    async with _get_session() as session:
        fault = await session.get(NetworkFaultReport, fault_id)
        if not fault:
            return

        support_url = "http://support:8008"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{support_url}/api/support/tickets",
                    json={
                        "title": f"[AUTO] {fault.title}",
                        "description": fault.description or f"Auto-created from fault report {fault.fault_type}",
                        "priority": "high" if fault.severity == "critical" else "medium",
                        "category": "network_fault",
                        "source": "fno_intelligence",
                    },
                    headers={"x-tenant-id": str(tenant_id)},
                )
                if resp.status_code == 200:
                    ticket_data = resp.json()
                    fault.internal_ticket_id = uuid.UUID(ticket_data.get("id", ticket_data.get("ticket_id")))
                    fault.status = "acknowledged"
                    await session.flush()
        except Exception as e:
            import logging
            logging.getLogger("fno_intelligence").error(f"Auto ticket creation failed: {e}")


async def _notify_affected_customers(fault_id: uuid.UUID, tenant_id: uuid.UUID):
    """Notify customers in the affected area about a fault."""
    from services.fno_intelligence.database import get_session as _get_session
    from services.network.models import NetworkService

    async with _get_session() as session:
        fault = await session.get(NetworkFaultReport, fault_id)
        if not fault:
            return

        # Find services in the affected area
        svc_query = select(NetworkService).where(
            NetworkService.tenant_id == tenant_id,
            NetworkService.fno_provider == fault.fno_name.lower(),
            NetworkService.status == "active",
        )
        if fault.city:
            svc_query = svc_query.where(NetworkService.city.ilike(f"%{fault.city}%"))
        if fault.postal_code:
            svc_query = svc_query.where(NetworkService.postal_code == fault.postal_code)

        services = (await session.execute(svc_query)).scalars().all()

        # Create notifications (in production, would dispatch via email/SMS/push)
        from services.network.models import NetworkNotification
        for svc in services:
            notification = NetworkNotification(
                tenant_id=tenant_id,
                service_id=svc.id,
                customer_id=svc.customer_id,
                trigger_type="fno_outage",
                trigger_id=fault.id,
                severity=fault.severity,
                title=f"Network Issue: {fault.title}",
                message=fault.description or f"A {fault.fault_type} issue has been reported in {fault.area_name or fault.city}.",
                channel="in_app",
                recipient=str(svc.customer_id),
            )
            session.add(notification)

        await session.flush()


@router.get("/faults")
async def list_fault_reports(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    status: Optional[str] = None,
    severity: Optional[str] = None,
    fno_name: Optional[str] = None,
    city: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    """List fault reports with filters."""
    query = select(NetworkFaultReport).where(NetworkFaultReport.tenant_id == tenant_id)
    if status:
        query = query.where(NetworkFaultReport.status == status)
    if severity:
        query = query.where(NetworkFaultReport.severity == severity)
    if fno_name:
        query = query.where(NetworkFaultReport.fno_name == fno_name)
    if city:
        query = query.where(NetworkFaultReport.city.ilike(f"%{city}%"))
    result = await db.execute(
        query.order_by(desc(NetworkFaultReport.created_at)).limit(limit).offset(offset)
    )
    faults = result.scalars().all()
    return [{
        "id": str(f.id), "fno": f.fno_name, "type": f.fault_type,
        "severity": f.severity, "status": f.status, "title": f.title,
        "city": f.city, "created_at": f.created_at.isoformat(),
    } for f in faults]


@router.get("/faults/{fault_id}")
async def get_fault_report(
    fault_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Get fault report details with update history."""
    fault = await db.get(NetworkFaultReport, fault_id)
    if not fault or fault.tenant_id != tenant_id:
        raise HTTPException(404, "Fault report not found")

    updates_result = await db.execute(
        select(NetworkFaultUpdate)
        .where(NetworkFaultUpdate.fault_id == fault_id)
        .order_by(NetworkFaultUpdate.created_at)
    )
    updates = updates_result.scalars().all()

    return {
        "id": str(fault.id), "fno": fault.fno_name, "type": fault.fault_type,
        "severity": fault.severity, "status": fault.status, "title": fault.title,
        "description": fault.description, "area": fault.area_name, "city": fault.city,
        "fno_ticket": fault.fno_ticket_reference, "internal_ticket": str(fault.internal_ticket_id) if fault.internal_ticket_id else None,
        "created_at": fault.created_at.isoformat(),
        "updates": [{"type": u.update_type, "message": u.message, "created_at": u.created_at.isoformat()} for u in updates],
    }


@router.put("/faults/{fault_id}")
async def update_fault_report(
    fault_id: uuid.UUID,
    payload: FaultReportUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Update fault report status and add audit trail entry."""
    fault = await db.get(NetworkFaultReport, fault_id)
    if not fault or fault.tenant_id != tenant_id:
        raise HTTPException(404, "Fault report not found")

    old_status = fault.status

    if payload.status:
        fault.status = payload.status
    if payload.severity:
        fault.severity = payload.severity
    if payload.fno_ticket_reference:
        fault.fno_ticket_reference = payload.fno_ticket_reference
    if payload.resolution_notes:
        fault.resolution_notes = payload.resolution_notes
        fault.resolved_at = datetime.utcnow()

    # Add audit trail entry
    update = NetworkFaultUpdate(
        fault_id=fault_id,
        tenant_id=tenant_id,
        update_type="status_change" if payload.status else "comment",
        message=payload.message or f"Status: {old_status} → {fault.status}",
        old_status=old_status,
        new_status=fault.status,
    )
    db.add(update)
    await db.flush()

    return {"id": str(fault.id), "status": fault.status}


@router.post("/faults/{fault_id}/escalate")
async def escalate_fault(
    fault_id: uuid.UUID,
    message: str = "",
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Escalate a fault report."""
    fault = await db.get(NetworkFaultReport, fault_id)
    if not fault or fault.tenant_id != tenant_id:
        raise HTTPException(404, "Fault report not found")

    fault.status = "escalated"
    fault.severity = "critical" if fault.severity != "critical" else fault.severity

    update = NetworkFaultUpdate(
        fault_id=fault_id,
        tenant_id=tenant_id,
        update_type="escalation",
        message=message or "Fault escalated",
        old_status="investigating",
        new_status="escalated",
    )
    db.add(update)
    await db.flush()

    return {"id": str(fault.id), "status": "escalated"}



# ════════════════════════════════════════════════════════════════════════
# 9. WEB INTELLIGENCE (Firecrawl-powered)
# ════════════════════════════════════════════════════════════════════════

class WebIntelRequest(BaseModel):
    fno_name: Optional[str] = None
    address: Optional[str] = None
    portal_url: Optional[str] = None
    city: Optional[str] = None
    product_query: Optional[str] = None
    competitors: list[str] = Field(default_factory=list)


@router.post("/web-intel/product-research")
async def web_product_research(
    payload: WebIntelRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Research an FNO's products/packages via web search + LLM summary."""
    if not payload.fno_name:
        raise HTTPException(400, "fno_name is required")
    try:
        return await web_intel.product_research(
            payload.fno_name, product_query=payload.product_query
        )
    except FirecrawlUnavailable as exc:
        raise HTTPException(503, str(exc))
    except FirecrawlError as exc:
        raise HTTPException(502, str(exc))


@router.post("/web-intel/fno-site-message")
async def web_fno_site_message(
    payload: WebIntelRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Scrape the latest message/announcement off an FNO portal page."""
    if not payload.portal_url:
        raise HTTPException(400, "portal_url is required")
    try:
        return await web_intel.fno_site_message(payload.portal_url)
    except FirecrawlUnavailable as exc:
        raise HTTPException(503, str(exc))
    except FirecrawlError as exc:
        raise HTTPException(502, str(exc))


@router.post("/web-intel/new-site-releases")
async def web_new_site_releases(
    payload: WebIntelRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Discover newly-released coverage areas / build sites for an FNO."""
    if not payload.fno_name:
        raise HTTPException(400, "fno_name is required")
    try:
        return await web_intel.new_site_releases(payload.fno_name, city=payload.city)
    except FirecrawlUnavailable as exc:
        raise HTTPException(503, str(exc))
    except FirecrawlError as exc:
        raise HTTPException(502, str(exc))


@router.post("/web-intel/cancellation-processing")
async def web_cancellation_processing(
    payload: WebIntelRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Extract the cancellation/termination procedure and required steps."""
    if not payload.fno_name:
        raise HTTPException(400, "fno_name is required")
    try:
        return await web_intel.cancellation_processing(
            payload.fno_name, portal_url=payload.portal_url
        )
    except FirecrawlUnavailable as exc:
        raise HTTPException(503, str(exc))
    except FirecrawlError as exc:
        raise HTTPException(502, str(exc))


@router.post("/web-intel/address-lookup")
async def web_address_lookup(
    payload: WebIntelRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Resolve a street address to fibre coverage / available FNOs."""
    if not payload.address:
        raise HTTPException(400, "address is required")
    try:
        return await web_intel.address_lookup(
            payload.address, fno_name=payload.fno_name
        )
    except FirecrawlUnavailable as exc:
        raise HTTPException(503, str(exc))
    except FirecrawlError as exc:
        raise HTTPException(502, str(exc))


@router.post("/web-intel/competitor-analysis")
async def web_competitor_analysis(
    payload: WebIntelRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Compare an FNO against named competitors (LLM-interpreted from web data)."""
    if not payload.fno_name:
        raise HTTPException(400, "fno_name is required")
    try:
        return await web_intel.competitor_analysis(
            payload.fno_name, competitors=payload.competitors
        )
    except FirecrawlUnavailable as exc:
        raise HTTPException(503, str(exc))
    except FirecrawlError as exc:
        raise HTTPException(502, str(exc))


@router.get("/web-intel/capabilities")
async def web_intel_capabilities():
    """List the six web-intel capabilities and which model powers each step."""
    return {
        "extraction_provider": "firecrawl",
        "reasoning_provider": "openrouter",
        "capabilities": web_intel.CAPABILITY_MODELS if hasattr(web_intel, "CAPABILITY_MODELS") else None,
        "endpoints": [
            "/web-intel/product-research",
            "/web-intel/fno-site-message",
            "/web-intel/new-site-releases",
            "/web-intel/cancellation-processing",
            "/web-intel/address-lookup",
            "/web-intel/competitor-analysis",
        ],
    }
