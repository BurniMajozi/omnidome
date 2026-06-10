"""Compliance Service (port 8019) — RICA, POPI, ICASA, Contact Management, SLA.

Manages:
- RICA identity verification (extended from existing service)
- Contact management with PII tracking and data retention
- POPI Act compliance (consent, data subject access requests, breach register)
- ICASA regulations (scraping, product lodgment, regulatory changes)
- SLA management (internal + regulatory)
- ICASA web scraper for regulation changes and announcements
"""

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, UploadFile, File, Form, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import get_current_tenant_id
from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
from services.compliance.database import (
    Base, ComplianceContact, ComplianceConsent, ComplianceSLA, ComplianceSLAMeasurement,
    DataBreachRecord, DataRetentionSchedule, IcasaProductLodgment, IcasaRegulation,
    IcasaScrapeLog, PopiDataRequest, RicaVerification,
    get_session, init_tables,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="OmniDome Compliance Service", version="1.0.0")
guard = EntitlementGuard(
    module_id="compliance",
    public_paths={"/health", "/icasa/scrape-webhook"},
)

configure_production(app)


@app.on_event("startup")
async def startup():
    await init_tables()
    guard.ensure_startup()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "compliance"}


# ===========================================================================
# 1. CONTACT MANAGEMENT
# ===========================================================================

class ContactCreate(BaseModel):
    customer_id: uuid.UUID
    id_number: Optional[str] = None
    id_type: str = "sa_id"
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    phone_primary: Optional[str] = None
    phone_secondary: Optional[str] = None
    email: Optional[str] = None
    property_id: Optional[uuid.UUID] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None


class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_primary: Optional[str] = None
    phone_secondary: Optional[str] = None
    email: Optional[str] = None
    rica_status: Optional[str] = None


class ContactRead(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    id_number: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    rica_status: str
    is_anonymized: bool
    retention_policy: str
    retention_until: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


def _contact_to_dict(c: ComplianceContact) -> dict:
    return {
        "id": str(c.id), "customer_id": str(c.customer_id),
        "id_number": c.id_number, "first_name": c.first_name,
        "last_name": c.last_name, "rica_status": c.rica_status,
        "is_anonymized": c.is_anonymized, "retention_policy": c.retention_policy,
        "retention_until": c.retention_until.isoformat() if c.retention_until else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@app.post("/contacts", response_model=ContactRead, status_code=status.HTTP_201_CREATED)
async def create_contact(
    body: ContactCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Create a compliance contact record with PII tracking."""
    contact = ComplianceContact(
        tenant_id=tenant_id,
        customer_id=body.customer_id,
        id_number=body.id_number,
        id_type=body.id_type,
        first_name=body.first_name,
        last_name=body.last_name,
        phone_primary=body.phone_primary,
        phone_secondary=body.phone_secondary,
        email=body.email,
        property_id=body.property_id,
        address_line1=body.address_line1,
        city=body.city,
        province=body.province,
        postal_code=body.postal_code,
    )
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    return ContactRead.model_validate(contact)


@app.get("/contacts")
async def list_contacts(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    rica_status: Optional[str] = None,
    is_anonymized: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    stmt = select(ComplianceContact).where(ComplianceContact.tenant_id == tenant_id)
    if rica_status:
        stmt = stmt.where(ComplianceContact.rica_status == rica_status)
    if is_anonymized is not None:
        stmt = stmt.where(ComplianceContact.is_anonymized == is_anonymized)
    total = (await db.execute(select(func.count(ComplianceContact.id)).where(
        ComplianceContact.tenant_id == tenant_id
    ))).scalar() or 0
    stmt = stmt.order_by(desc(ComplianceContact.created_at)).offset((page - 1) * page_size).limit(page_size)
    contacts = (await db.execute(stmt)).scalars().all()
    return {"items": [_contact_to_dict(c) for c in contacts], "total": total, "page": page, "page_size": page_size}


@app.get("/contacts/{contact_id}")
async def get_contact(
    contact_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    contact = await db.get(ComplianceContact, contact_id)
    if not contact or contact.tenant_id != tenant_id:
        raise HTTPException(404, "Contact not found")
    # Track access for POPI audit
    contact.last_accessed_at = datetime.now(timezone.utc)
    contact.access_count += 1
    await db.flush()
    return _contact_to_dict(contact)


@app.put("/contacts/{contact_id}")
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    contact = await db.get(ComplianceContact, contact_id)
    if not contact or contact.tenant_id != tenant_id:
        raise HTTPException(404, "Contact not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    await db.flush()
    return _contact_to_dict(contact)


@app.post("/contacts/{contact_id}/anonymize")
async def anonymize_contact(
    contact_id: uuid.UUID,
    method: str = "masking",
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Anonymize a contact's PII data per POPI Act requirements."""
    contact = await db.get(ComplianceContact, contact_id)
    if not contact or contact.tenant_id != tenant_id:
        raise HTTPException(404, "Contact not found")

    # Anonymize PII fields
    contact.id_number = "ANONYMIZED" if contact.id_number else None
    contact.first_name = "ANONYMIZED" if contact.first_name else None
    contact.last_name = "ANONYMIZED" if contact.last_name else None
    contact.phone_primary = None
    contact.phone_secondary = None
    contact.email = None
    contact.address_line1 = None
    contact.is_anonymized = True
    contact.anonymized_at = datetime.now(timezone.utc)
    contact.anonymization_method = method
    await db.flush()
    return {"id": str(contact.id), "is_anonymized": True, "method": method}


# ===========================================================================
# 2. CONSENT MANAGEMENT
# ===========================================================================

class ConsentCreate(BaseModel):
    contact_id: uuid.UUID
    purpose: str
    status: str = "granted"
    collection_method: str = "web_form"
    collection_context: Optional[str] = None
    expires_at: Optional[datetime] = None


class ConsentRead(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    purpose: str
    status: str
    granted_at: datetime
    withdrawn_at: Optional[datetime]
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True


@app.post("/consents", response_model=ConsentRead, status_code=status.HTTP_201_CREATED)
async def create_consent(
    body: ConsentCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    consent = ComplianceConsent(
        tenant_id=tenant_id,
        contact_id=body.contact_id,
        purpose=body.purpose,
        status=body.status,
        collection_method=body.collection_method,
        collection_context=body.collection_context,
        expires_at=body.expires_at,
    )
    db.add(consent)
    await db.flush()
    await db.refresh(consent)
    return ConsentRead.model_validate(consent)


@app.get("/consents")
async def list_consents(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    contact_id: Optional[uuid.UUID] = None,
    purpose: Optional[str] = None,
    status: Optional[str] = None,
):
    stmt = select(ComplianceConsent).where(ComplianceConsent.tenant_id == tenant_id)
    if contact_id:
        stmt = stmt.where(ComplianceConsent.contact_id == contact_id)
    if purpose:
        stmt = stmt.where(ComplianceConsent.purpose == purpose)
    if status:
        stmt = stmt.where(ComplianceConsent.status == status)
    result = await db.execute(stmt)
    return [ConsentRead.model_validate(c) for c in result.scalars().all()]


@app.post("/consents/{consent_id}/withdraw")
async def withdraw_consent(
    consent_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    consent = await db.get(ComplianceConsent, consent_id)
    if not consent or consent.tenant_id != tenant_id:
        raise HTTPException(404, "Consent not found")
    consent.status = "withdrawn"
    consent.withdrawn_at = datetime.now(timezone.utc)
    await db.flush()
    return {"id": str(consent.id), "status": "withdrawn"}


# ===========================================================================
# 3. POPI DATA SUBJECT ACCESS REQUESTS
# ===========================================================================

class PopiRequestCreate(BaseModel):
    contact_id: uuid.UUID
    request_type: str
    description: Optional[str] = None
    requested_data_categories: Optional[list[str]] = None


class PopiRequestRead(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    request_type: str
    status: str
    submitted_at: datetime
    due_date: datetime
    fulfilled_at: Optional[datetime]

    class Config:
        from_attributes = True


@app.post("/popi-requests", response_model=PopiRequestRead, status_code=status.HTTP_201_CREATED)
async def create_popi_request(
    body: PopiRequestCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Create a POPI data subject access request. Due date is 30 days from submission."""
    now = datetime.now(timezone.utc)
    request = PopiDataRequest(
        tenant_id=tenant_id,
        contact_id=body.contact_id,
        request_type=body.request_type,
        description=body.description,
        requested_data_categories=body.requested_data_categories,
        submitted_at=now,
        due_date=now + timedelta(days=30),
    )
    db.add(request)
    await db.flush()
    await db.refresh(request)
    return PopiRequestRead.model_validate(request)


@app.get("/popi-requests")
async def list_popi_requests(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    status: Optional[str] = None,
    overdue: bool = False,
):
    stmt = select(PopiDataRequest).where(PopiDataRequest.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(PopiDataRequest.status == status)
    if overdue:
        stmt = stmt.where(
            PopiDataRequest.due_date < datetime.now(timezone.utc),
            PopiDataRequest.status.notin_(("fulfilled", "rejected")),
        )
    result = await db.execute(stmt.order_by(PopiDataRequest.due_date))
    return [PopiRequestRead.model_validate(r) for r in result.scalars().all()]


@app.post("/popi-requests/{request_id}/fulfill")
async def fulfill_popi_request(
    request_id: uuid.UUID,
    response_notes: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    request = await db.get(PopiDataRequest, request_id)
    if not request or request.tenant_id != tenant_id:
        raise HTTPException(404, "Request not found")
    request.status = "fulfilled"
    request.fulfilled_at = datetime.now(timezone.utc)
    request.response_notes = response_notes
    await db.flush()
    return {"id": str(request.id), "status": "fulfilled"}


# ===========================================================================
# 4. DATA BREACH REGISTER
# ===========================================================================

class BreachCreate(BaseModel):
    title: str = Field(..., max_length=500)
    description: Optional[str] = None
    severity: str = "medium"
    affected_contacts_count: int = 0
    affected_data_categories: Optional[list[str]] = None


class BreachRead(BaseModel):
    id: uuid.UUID
    title: str
    severity: str
    status: str
    detected_at: datetime
    icasa_notified_at: Optional[datetime]

    class Config:
        from_attributes = True


@app.post("/breaches", response_model=BreachRead, status_code=status.HTTP_201_CREATED)
async def create_breach_record(
    body: BreachCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    breach = DataBreachRecord(
        tenant_id=tenant_id,
        title=body.title,
        description=body.description,
        severity=body.severity,
        affected_contacts_count=body.affected_contacts_count,
        affected_data_categories=body.affected_data_categories,
        detected_at=datetime.now(timezone.utc),
    )
    db.add(breach)
    await db.flush()
    await db.refresh(breach)
    return BreachRead.model_validate(breach)


@app.get("/breaches")
async def list_breaches(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    status: Optional[str] = None,
    severity: Optional[str] = None,
):
    stmt = select(DataBreachRecord).where(DataBreachRecord.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(DataBreachRecord.status == status)
    if severity:
        stmt = stmt.where(DataBreachRecord.severity == severity)
    result = await db.execute(stmt.order_by(desc(DataBreachRecord.detected_at)))
    return [BreachRead.model_validate(b) for b in result.scalars().all()]


@app.post("/breaches/{breach_id}/notify-icasa")
async def notify_icasa(
    breach_id: uuid.UUID,
    icasa_reference: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Mark breach as notified to ICASA."""
    breach = await db.get(DataBreachRecord, breach_id)
    if not breach or breach.tenant_id != tenant_id:
        raise HTTPException(404, "Breach not found")
    breach.status = "notified_icasa"
    breach.icasa_notified_at = datetime.now(timezone.utc)
    breach.icasa_notification_reference = icasa_reference
    await db.flush()
    return {"id": str(breach.id), "icasa_notified": True}


# ===========================================================================
# 5. ICASA REGULATIONS
# ===========================================================================

class RegulationCreate(BaseModel):
    document_type: str
    title: str = Field(..., max_length=500)
    description: Optional[str] = None
    icasa_reference: Optional[str] = None
    source_url: Optional[str] = None
    document_url: Optional[str] = None
    published_date: Optional[str] = None
    effective_date: Optional[str] = None
    key_points: Optional[list[str]] = None
    affected_areas: Optional[list[str]] = None
    impact_level: str = "unknown"


class RegulationRead(BaseModel):
    id: uuid.UUID
    document_type: str
    title: str
    icasa_reference: Optional[str]
    impact_level: str
    is_new: bool
    is_reviewed: bool
    scraped_at: datetime

    class Config:
        from_attributes = True


@app.post("/icasa/regulations", response_model=RegulationRead, status_code=status.HTTP_201_CREATED)
async def create_regulation(
    body: RegulationCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    reg = IcasaRegulation(
        tenant_id=tenant_id,
        document_type=body.document_type,
        title=body.title,
        description=body.description,
        icasa_reference=body.icasa_reference,
        source_url=body.source_url,
        document_url=body.document_url,
        key_points=body.key_points,
        affected_areas=body.affected_areas,
        impact_level=body.impact_level,
    )
    db.add(reg)
    await db.flush()
    await db.refresh(reg)
    return RegulationRead.model_validate(reg)


@app.get("/icasa/regulations")
async def list_regulations(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    document_type: Optional[str] = None,
    is_new: Optional[bool] = None,
    impact_level: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    stmt = select(IcasaRegulation).where(IcasaRegulation.tenant_id == tenant_id)
    if document_type:
        stmt = stmt.where(IcasaRegulation.document_type == document_type)
    if is_new is not None:
        stmt = stmt.where(IcasaRegulation.is_new == is_new)
    if impact_level:
        stmt = stmt.where(IcasaRegulation.impact_level == impact_level)
    result = await db.execute(stmt.order_by(desc(IcasaRegulation.scraped_at)).limit(limit))
    return [RegulationRead.model_validate(r) for r in result.scalars().all()]


@app.post("/icasa/regulations/{regulation_id}/review")
async def review_regulation(
    regulation_id: uuid.UUID,
    impact_assessment: Optional[str] = None,
    required_actions: Optional[list[str]] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    reg = await db.get(IcasaRegulation, regulation_id)
    if not reg or reg.tenant_id != tenant_id:
        raise HTTPException(404, "Regulation not found")
    reg.is_reviewed = True
    reg.is_new = False
    reg.reviewed_at = datetime.now(timezone.utc)
    if impact_assessment:
        reg.impact_assessment = impact_assessment
    if required_actions:
        reg.required_actions = required_actions
    await db.flush()
    return {"id": str(reg.id), "is_reviewed": True}


# ===========================================================================
# 6. ICASA PRODUCT LODGMENT
# ===========================================================================

class LodgmentCreate(BaseModel):
    product_name: str = Field(..., max_length=500)
    product_type: str
    description: Optional[str] = None
    product_id: Optional[uuid.UUID] = None
    supporting_documents: Optional[list[dict]] = None


class LodgmentRead(BaseModel):
    id: uuid.UUID
    product_name: str
    product_type: str
    status: str
    icasa_reference: Optional[str]
    submitted_at: Optional[datetime]

    class Config:
        from_attributes = True


@app.post("/icasa/lodgments", response_model=LodgmentRead, status_code=status.HTTP_201_CREATED)
async def create_lodgment(
    body: LodgmentCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    lodge = IcasaProductLodgment(
        tenant_id=tenant_id,
        product_name=body.product_name,
        product_type=body.product_type,
        description=body.description,
        product_id=body.product_id,
        supporting_documents=body.supporting_documents,
        status="draft",
    )
    db.add(lodge)
    await db.flush()
    await db.refresh(lodge)
    return LodgmentRead.model_validate(lodge)


@app.get("/icasa/lodgments")
async def list_lodgments(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    status: Optional[str] = None,
):
    stmt = select(IcasaProductLodgment).where(IcasaProductLodgment.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(IcasaProductLodgment.status == status)
    result = await db.execute(stmt.order_by(desc(IcasaProductLodgment.created_at)))
    return [LodgmentRead.model_validate(l) for l in result.scalars().all()]


@app.post("/icasa/lodgments/{lodge_id}/submit")
async def submit_lodgment(
    lodge_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    lodge = await db.get(IcasaProductLodgment, lodge_id)
    if not lodge or lodge.tenant_id != tenant_id:
        raise HTTPException(404, "Lodgment not found")
    lodge.status = "submitted"
    lodge.submitted_at = datetime.now(timezone.utc)
    await db.flush()
    return {"id": str(lodge.id), "status": "submitted"}


# ===========================================================================
# 7. SLA MANAGEMENT
# ===========================================================================

class SLACreate(BaseModel):
    name: str = Field(..., max_length=300)
    description: Optional[str] = None
    sla_type: str
    target_value: float
    target_unit: str
    warning_threshold: Optional[float] = None
    breach_threshold: Optional[float] = None
    regulatory_reference: Optional[str] = None
    effective_from: Optional[datetime] = None


class SLARead(BaseModel):
    id: uuid.UUID
    name: str
    sla_type: str
    target_value: float
    target_unit: str
    current_status: str
    current_value: Optional[float]
    is_active: bool

    class Config:
        from_attributes = True


@app.post("/slas", response_model=SLARead, status_code=status.HTTP_201_CREATED)
async def create_sla(
    body: SLACreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    sla = ComplianceSLA(
        tenant_id=tenant_id,
        name=body.name,
        description=body.description,
        sla_type=body.sla_type,
        target_value=body.target_value,
        target_unit=body.target_unit,
        warning_threshold=body.warning_threshold,
        breach_threshold=body.breach_threshold,
        regulatory_reference=body.regulatory_reference,
        effective_from=body.effective_from or datetime.now(timezone.utc),
    )
    db.add(sla)
    await db.flush()
    await db.refresh(sla)
    return SLARead.model_validate(sla)


@app.get("/slas")
async def list_slas(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    sla_type: Optional[str] = None,
    current_status: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    stmt = select(ComplianceSLA).where(ComplianceSLA.tenant_id == tenant_id)
    if sla_type:
        stmt = stmt.where(ComplianceSLA.sla_type == sla_type)
    if current_status:
        stmt = stmt.where(ComplianceSLA.current_status == current_status)
    if is_active is not None:
        stmt = stmt.where(ComplianceSLA.is_active == is_active)
    result = await db.execute(stmt)
    return [SLARead.model_validate(s) for s in result.scalars().all()]


class SLAMeasurementCreate(BaseModel):
    sla_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    period_type: str = "daily"
    actual_value: float
    sample_count: int = 0
    notes: Optional[str] = None


@app.post("/slas/measurements", status_code=status.HTTP_201_CREATED)
async def record_sla_measurement(
    body: SLAMeasurementCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    sla = await db.get(ComplianceSLA, body.sla_id)
    if not sla or sla.tenant_id != tenant_id:
        raise HTTPException(404, "SLA not found")

    deviation = ((body.actual_value - sla.target_value) / sla.target_value * 100) if sla.target_value else 0
    is_breach = False
    if sla.sla_type in ("regulatory", "customer"):
        if sla.target_unit in ("hours", "days"):
            is_breach = body.actual_value > sla.target_value
        elif sla.target_unit == "percent":
            is_breach = body.actual_value < sla.target_value

    measurement = ComplianceSLAMeasurement(
        tenant_id=tenant_id,
        sla_id=body.sla_id,
        period_start=body.period_start,
        period_end=body.period_end,
        period_type=body.period_type,
        actual_value=body.actual_value,
        target_value=sla.target_value,
        is_breach=is_breach,
        deviation_pct=round(deviation, 4) if deviation else None,
        sample_count=body.sample_count,
        notes=body.notes,
    )
    db.add(measurement)

    # Update SLA current status
    sla.current_value = body.actual_value
    if is_breach:
        sla.current_status = "breached"
    elif sla.warning_threshold and abs(deviation) >= sla.warning_threshold:
        sla.current_status = "at_risk"
    else:
        sla.current_status = "met"

    await db.flush()
    return {"id": str(measurement.id), "is_breach": is_breach, "sla_status": sla.current_status}


# ===========================================================================
# 8. ICASA WEB SCRAPER
# ===========================================================================

ICASA_BASE_URL = "https://www.icasa.org.za"


@app.post("/icasa/scrape")
async def trigger_icasa_scrape(
    scrape_type: str = "regulations",
    background_tasks: BackgroundTasks = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Trigger an ICASA website scrape. Runs in background."""
    log = IcasaScrapeLog(
        tenant_id=tenant_id,
        scrape_type=scrape_type,
        source_url=f"{ICASA_BASE_URL}/{scrape_type}",
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(log)
    await db.flush()

    if background_tasks:
        background_tasks.add_task(_scrape_icasa, log.id, scrape_type, tenant_id)

    return {"scrape_id": str(log.id), "status": "running"}


async def _scrape_icasa(log_id: uuid.UUID, scrape_type: str, tenant_id: uuid.UUID):
    """Background task: scrape ICASA website for regulatory changes."""
    from services.compliance.database import get_session as _get_session

    async with _get_session() as session:
        log = await session.get(IcasaScrapeLog, log_id)
        if not log:
            return

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                if scrape_type == "regulations":
                    url = f"{ICASA_BASE_URL}/legislation-and-regulations"
                elif scrape_type == "announcements":
                    url = f"{ICASA_BASE_URL}/news-and-announcements"
                elif scrape_type == "tariffs":
                    url = f"{ICASA_BASE_URL}/tariffs"
                else:
                    url = f"{ICASA_BASE_URL}"

                resp = await client.get(url)
                resp.raise_for_status()

                # In production: parse HTML with BeautifulSoup to extract regulations
                # For now, log the scrape
                content_length = len(resp.text)

                log.status = "success"
                log.completed_at = datetime.now(timezone.utc)
                log.duration_seconds = 0  # Would calculate actual duration
                log.items_found = 1  # Would count actual items parsed
                log.items_new = 0

                # TODO: Parse HTML and create IcasaRegulation records
                # soup = BeautifulSoup(resp.text, 'html.parser')
                # for item in soup.select('.regulation-item'):
                #     reg = IcasaRegulation(...)
                #     session.add(reg)

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            log.completed_at = datetime.now(timezone.utc)
            logger.error(f"ICASA scrape failed: {e}")

        await session.flush()


@app.get("/icasa/scrape-logs")
async def list_scrape_logs(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    scrape_type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
):
    stmt = select(IcasaScrapeLog).where(IcasaScrapeLog.tenant_id == tenant_id)
    if scrape_type:
        stmt = stmt.where(IcasaScrapeLog.scrape_type == scrape_type)
    result = await db.execute(stmt.order_by(desc(IcasaScrapeLog.started_at)).limit(limit))
    logs = result.scalars().all()
    return [{
        "id": str(l.id), "type": l.scrape_type, "status": l.status,
        "items_found": l.items_found, "items_new": l.items_new,
        "started_at": l.started_at.isoformat(),
    } for l in logs]


# ===========================================================================
# 9. DATA RETENTION
# ===========================================================================

class RetentionScheduleCreate(BaseModel):
    data_category: str
    retention_period_months: int
    legal_basis: str
    auto_delete: bool = False
    anonymize_instead: bool = True
    anonymization_method: Optional[str] = "masking"


@app.post("/retention-schedules", status_code=status.HTTP_201_CREATED)
async def create_retention_schedule(
    body: RetentionScheduleCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    schedule = DataRetentionSchedule(
        tenant_id=tenant_id,
        data_category=body.data_category,
        retention_period_months=body.retention_period_months,
        legal_basis=body.legal_basis,
        auto_delete=body.auto_delete,
        anonymize_instead=body.anonymize_instead,
        anonymization_method=body.anonymization_method,
    )
    db.add(schedule)
    await db.flush()
    return {"id": str(schedule.id), "category": body.data_category}


@app.get("/retention-schedules")
async def list_retention_schedules(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(DataRetentionSchedule).where(DataRetentionSchedule.tenant_id == tenant_id)
    )
    schedules = result.scalars().all()
    return [{
        "id": str(s.id), "category": s.data_category,
        "retention_months": s.retention_period_months,
        "legal_basis": s.legal_basis, "auto_delete": s.auto_delete,
    } for s in schedules]


@app.post("/retention-schedules/enforce")
async def enforce_retention(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    background_tasks: BackgroundTasks = None,
):
    """Enforce data retention policies — anonymize or delete expired records."""
    now = datetime.now(timezone.utc)
    schedules = (await db.execute(
        select(DataRetentionSchedule).where(
            DataRetentionSchedule.tenant_id == tenant_id,
            DataRetentionSchedule.is_active.is_(True),
        )
    )).scalars().all()

    total_affected = 0
    for schedule in schedules:
        cutoff = now - timedelta(days=schedule.retention_period_months * 30)
        contacts = (await db.execute(
            select(ComplianceContact).where(
                ComplianceContact.tenant_id == tenant_id,
                ComplianceContact.created_at < cutoff,
                ComplianceContact.is_anonymized.is_(False),
            )
        )).scalars().all()

        for contact in contacts:
            if schedule.anonymize_instead:
                contact.id_number = "ANONYMIZED" if contact.id_number else None
                contact.first_name = "ANONYMIZED" if contact.first_name else None
                contact.last_name = "ANONYMIZED" if contact.last_name else None
                contact.phone_primary = None
                contact.phone_secondary = None
                contact.email = None
                contact.is_anonymized = True
                contact.anonymized_at = now
                contact.anonymization_method = schedule.anonymization_method
            # TODO: auto_delete logic
            total_affected += 1

        schedule.last_enforced_at = now
        schedule.records_affected = total_affected

    await db.flush()
    return {"records_processed": total_affected}


# ===========================================================================
# 10. RICA VERIFICATION (extended)
# ===========================================================================

class RicaSessionCreate(BaseModel):
    contact_id: uuid.UUID
    verification_type: str = "DOCUMENT_VERIFICATION"


class RicaSessionResponse(BaseModel):
    job_id: str
    signature: str
    timestamp: str


@app.post("/rica/sessions", response_model=RicaSessionResponse)
async def create_rica_session(
    body: RicaSessionCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Initialize a RICA verification session."""
    import hashlib, hmac
    job_id = f"RICA-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.now().isoformat()
    api_key = os.getenv("SMILE_ID_API_KEY", "mock_key")
    partner_id = os.getenv("SMILE_ID_PARTNER_ID", "mock_partner")
    message = f"{timestamp}{partner_id}sid_request"
    signature = hmac.new(api_key.encode(), message.encode(), hashlib.sha256).hexdigest()

    verification = RicaVerification(
        tenant_id=tenant_id,
        contact_id=body.contact_id,
        job_id=job_id,
        verification_type=body.verification_type,
        status="pending",
    )
    db.add(verification)
    await db.flush()

    return {"job_id": job_id, "signature": signature, "timestamp": timestamp}


@app.get("/rica/verifications")
async def list_rica_verifications(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    status: Optional[str] = None,
):
    stmt = select(RicaVerification).where(RicaVerification.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(RicaVerification.status == status)
    result = await db.execute(stmt.order_by(desc(RicaVerification.created_at)))
    verifications = result.scalars().all()
    return [{
        "id": str(v.id), "job_id": v.job_id, "status": v.status,
        "verification_type": v.verification_type, "id_number": v.id_number,
        "first_name": v.first_name, "last_name": v.last_name,
        "rica_status": v.icasa_registration_status,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    } for v in verifications]


@app.post("/rica/callback")
async def rica_callback(
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    """Webhook for Smile ID / RICA verification results."""
    payload = await request.json()
    job_id = payload.get("job_id")
    result_code = payload.get("result_code")

    verification = (await db.execute(
        select(RicaVerification).where(RicaVerification.job_id == job_id)
    )).scalar_one_or_none()

    if verification:
        verification.status = "completed" if result_code == "1012" else "failed"
        verification.result_code = result_code
        verification.result_message = payload.get("result_message")
        verification.full_response = payload
        verification.smile_job_id = payload.get("smile_job_id", verification.smile_job_id)

        # Update contact RICA status
        if verification.contact_id:
            contact = await db.get(ComplianceContact, verification.contact_id)
            if contact:
                contact.rica_status = "verified" if result_code == "1012" else "failed"
                contact.rica_verified_at = datetime.now(timezone.utc)
                contact.rica_expires_at = datetime.now(timezone.utc) + timedelta(days=365 * 5)
                # RICA verification valid for 5 years per ICASA

        await db.flush()

    return {"status": "accepted"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8019)
