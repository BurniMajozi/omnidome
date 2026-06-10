"""Compliance Service (port 8019) — Contract Management, SLA, ICASA, POPI, RICA.

Central entity: Contract — all contracts (FNO, supplier, customer, employee, partner).
SLAs, ICASA lodgments, POPI data requests, and RICA verifications are all linked to contracts.
"""

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import get_current_tenant_id
from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
from services.compliance.database import (
    Base, Contract, ContractAuditLog, ContractDocument, ContractSLA,
    ContractSLAMeasurement, DataBreachRecord, IcasaLodgment, IcasaRegulation,
    IcasaScrapeLog, PopiDataRequest, RicaVerification,
    get_session, init_tables,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="OmniDome Compliance Service", version="2.0.0")
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
# 1. CONTRACT MANAGEMENT
# ===========================================================================

class ContractCreate(BaseModel):
    contract_number: str = Field(..., max_length=100)
    contract_type: str
    title: str = Field(..., max_length=500)
    description: Optional[str] = None
    priority: str = "medium"
    counterparty_name: str = Field(..., max_length=300)
    counterparty_registration: Optional[str] = None
    counterparty_contact_person: Optional[str] = None
    counterparty_email: Optional[str] = None
    counterparty_phone: Optional[str] = None
    internal_owner_id: Optional[uuid.UUID] = None
    internal_department: Optional[str] = None
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    renewal_date: Optional[str] = None
    termination_notice_days: int = 30
    auto_renew: bool = False
    contract_value_zar: Optional[float] = None
    payment_terms: Optional[str] = None
    icasa_registration_required: bool = False
    rica_data_retention_required: bool = True
    rica_retention_years: int = 5


class ContractUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    counterparty_name: Optional[str] = None
    counterparty_contact_person: Optional[str] = None
    counterparty_email: Optional[str] = None
    counterparty_phone: Optional[str] = None
    internal_owner_id: Optional[uuid.UUID] = None
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    contract_value_zar: Optional[float] = None
    internal_notes: Optional[str] = None


def _contract_to_dict(c: Contract) -> dict:
    return {
        "id": str(c.id), "contract_number": c.contract_number,
        "contract_type": c.contract_type, "title": c.title,
        "status": c.status, "priority": c.priority,
        "counterparty_name": c.counterparty_name,
        "effective_date": c.effective_date.isoformat() if c.effective_date else None,
        "expiry_date": c.expiry_date.isoformat() if c.expiry_date else None,
        "contract_value_zar": float(c.contract_value_zar) if c.contract_value_zar else None,
        "icasa_compliance_status": c.icasa_compliance_status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@app.post("/contracts", status_code=status.HTTP_201_CREATED)
async def create_contract(
    body: ContractCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Create a new contract (FNO, supplier, customer, employee, partner, etc.)."""
    from datetime import date as date_type
    contract = Contract(
        tenant_id=tenant_id,
        contract_number=body.contract_number,
        contract_type=body.contract_type,
        title=body.title,
        description=body.description,
        priority=body.priority,
        counterparty_name=body.counterparty_name,
        counterparty_registration=body.counterparty_registration,
        counterparty_contact_person=body.counterparty_contact_person,
        counterparty_email=body.counterparty_email,
        counterparty_phone=body.counterparty_phone,
        internal_owner_id=body.internal_owner_id,
        internal_department=body.internal_department,
        effective_date=date_type.fromisoformat(body.effective_date) if body.effective_date else None,
        expiry_date=date_type.fromisoformat(body.expiry_date) if body.expiry_date else None,
        renewal_date=date_type.fromisoformat(body.renewal_date) if body.renewal_date else None,
        termination_notice_days=body.termination_notice_days,
        auto_renew=body.auto_renew,
        contract_value_zar=body.contract_value_zar,
        payment_terms=body.payment_terms,
        icasa_registration_required=body.icasa_registration_required,
        rica_data_retention_required=body.rica_data_retention_required,
        rica_retention_years=body.rica_retention_years,
    )
    db.add(contract)
    await db.flush()

    # Audit log
    audit = ContractAuditLog(
        tenant_id=tenant_id, contract_id=contract.id,
        action="created", notes=f"Contract {body.contract_number} created",
    )
    db.add(audit)
    await db.flush()
    await db.refresh(contract)
    return _contract_to_dict(contract)


@app.get("/contracts")
async def list_contracts(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    contract_type: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    counterparty_name: Optional[str] = None,
    icasa_compliance: Optional[str] = None,
    expiring_before: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    stmt = select(Contract).where(Contract.tenant_id == tenant_id)
    if contract_type:
        stmt = stmt.where(Contract.contract_type == contract_type)
    if status:
        stmt = stmt.where(Contract.status == status)
    if priority:
        stmt = stmt.where(Contract.priority == priority)
    if counterparty_name:
        stmt = stmt.where(Contract.counterparty_name.ilike(f"%{counterparty_name}%"))
    if icasa_compliance:
        stmt = stmt.where(Contract.icasa_compliance_status == icasa_compliance)
    if expiring_before:
        from datetime import date as date_type
        stmt = stmt.where(Contract.expiry_date <= date_type.fromisoformat(expiring_before))

    total = (await db.execute(select(func.count(Contract.id)).where(
        Contract.tenant_id == tenant_id
    ))).scalar() or 0
    stmt = stmt.order_by(desc(Contract.created_at)).offset((page - 1) * page_size).limit(page_size)
    contracts = (await db.execute(stmt)).scalars().all()
    return {"items": [_contract_to_dict(c) for c in contracts], "total": total, "page": page, "page_size": page_size}


@app.get("/contracts/{contract_id}")
async def get_contract(
    contract_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    contract = await db.get(Contract, contract_id)
    if not contract or contract.tenant_id != tenant_id:
        raise HTTPException(404, "Contract not found")

    # Load related data
    slas = (await db.execute(select(ContractSLA).where(ContractSLA.contract_id == contract_id))).scalars().all()
    documents = (await db.execute(select(ContractDocument).where(ContractDocument.contract_id == contract_id))).scalars().all()
    audit_logs = (await db.execute(
        select(ContractAuditLog).where(ContractAuditLog.contract_id == contract_id)
        .order_by(desc(ContractAuditLog.created_at)).limit(20)
    )).scalars().all()

    result = _contract_to_dict(contract)
    result["slas"] = [{"id": str(s.id), "name": s.name, "target": s.target_value, "unit": s.target_unit, "status": s.current_status} for s in slas]
    result["documents"] = [{"id": str(d.id), "type": d.document_type, "name": d.name} for d in documents]
    result["audit_log"] = [{"action": a.action, "field": a.field_changed, "at": a.created_at.isoformat()} for a in audit_logs]
    return result


@app.put("/contracts/{contract_id}")
async def update_contract(
    contract_id: uuid.UUID,
    body: ContractUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    contract = await db.get(Contract, contract_id)
    if not contract or contract.tenant_id != tenant_id:
        raise HTTPException(404, "Contract not found")

    changes = []
    for field, value in body.model_dump(exclude_unset=True).items():
        old = getattr(contract, field, None)
        if old != value:
            changes.append((field, str(old), str(value)))
            setattr(contract, field, value)

    # Audit log for changes
    for field, old_val, new_val in changes:
        db.add(ContractAuditLog(
            tenant_id=tenant_id, contract_id=contract_id,
            action="updated", field_changed=field,
            old_value=old_val, new_value=new_val,
        ))

    await db.flush()
    return _contract_to_dict(contract)


@app.post("/contracts/{contract_id}/terminate")
async def terminate_contract(
    contract_id: uuid.UUID,
    reason: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    contract = await db.get(Contract, contract_id)
    if not contract or contract.tenant_id != tenant_id:
        raise HTTPException(404, "Contract not found")
    contract.status = "terminated"
    contract.termination_reason = reason
    db.add(ContractAuditLog(
        tenant_id=tenant_id, contract_id=contract_id,
        action="terminated", notes=reason,
    ))
    await db.flush()
    return {"id": str(contract.id), "status": "terminated"}


# ===========================================================================
# 2. CONTRACT SLAs
# ===========================================================================

class SLACreate(BaseModel):
    contract_id: uuid.UUID
    name: str = Field(..., max_length=300)
    description: Optional[str] = None
    sla_type: str
    target_value: float
    target_unit: str
    warning_threshold_pct: Optional[float] = None
    breach_threshold_pct: Optional[float] = None
    penalty_clause: Optional[str] = None
    penalty_amount_zar: Optional[float] = None
    effective_from: Optional[datetime] = None


@app.post("/contracts/slas", status_code=status.HTTP_201_CREATED)
async def create_contract_sla(
    body: SLACreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    sla = ContractSLA(
        tenant_id=tenant_id,
        contract_id=body.contract_id,
        name=body.name,
        description=body.description,
        sla_type=body.sla_type,
        target_value=body.target_value,
        target_unit=body.target_unit,
        warning_threshold_pct=body.warning_threshold_pct,
        breach_threshold_pct=body.breach_threshold_pct,
        penalty_clause=body.penalty_clause,
        penalty_amount_zar=body.penalty_amount_zar,
        effective_from=body.effective_from or datetime.now(timezone.utc),
    )
    db.add(sla)
    await db.flush()
    await db.refresh(sla)
    return {"id": str(sla.id), "name": sla.name, "target": sla.target_value, "unit": sla.target_unit}


@app.post("/contracts/slas/measurements", status_code=status.HTTP_201_CREATED)
async def record_sla_measurement(
    sla_id: uuid.UUID,
    period_start: datetime,
    period_end: datetime,
    period_type: str = "daily",
    actual_value: float = 0,
    sample_count: int = 0,
    notes: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    sla = await db.get(ContractSLA, sla_id)
    if not sla or sla.tenant_id != tenant_id:
        raise HTTPException(404, "SLA not found")

    deviation = ((actual_value - sla.target_value) / sla.target_value * 100) if sla.target_value else 0
    is_breach = False
    if sla.target_unit in ("hours", "days", "minutes"):
        is_breach = actual_value > sla.target_value
    elif sla.target_unit == "percent":
        is_breach = actual_value < sla.target_value

    measurement = ContractSLAMeasurement(
        tenant_id=tenant_id, sla_id=sla_id,
        period_start=period_start, period_end=period_end,
        period_type=period_type, actual_value=actual_value,
        target_value=sla.target_value, is_breach=is_breach,
        deviation_pct=round(deviation, 4) if deviation else None,
        sample_count=sample_count, notes=notes,
    )
    db.add(measurement)

    sla.current_value = actual_value
    sla.current_status = "breached" if is_breach else ("at_risk" if sla.warning_threshold_pct and abs(deviation) >= sla.warning_threshold_pct else "met")

    # Audit log
    db.add(ContractAuditLog(
        tenant_id=tenant_id, contract_id=sla.contract_id,
        action="sla_breach" if is_breach else "sla_measurement",
        notes=f"SLA {sla.name}: {actual_value}{sla.target_unit} (target: {sla.target_value})",
    ))
    await db.flush()
    return {"id": str(measurement.id), "is_breach": is_breach, "sla_status": sla.current_status}


@app.get("/contracts/{contract_id}/slas")
async def list_contract_slas(
    contract_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(ContractSLA).where(ContractSLA.contract_id == contract_id, ContractSLA.tenant_id == tenant_id)
    )
    slas = result.scalars().all()
    return [{"id": str(s.id), "name": s.name, "type": s.sla_type, "target": s.target_value, "unit": s.target_unit, "status": s.current_status, "current_value": s.current_value} for s in slas]


# ===========================================================================
# 3. ICASA PRODUCT LODGMENT
# ===========================================================================

class LodgmentCreate(BaseModel):
    contract_id: Optional[uuid.UUID] = None
    product_name: str = Field(..., max_length=500)
    product_type: str
    description: Optional[str] = None
    product_id: Optional[uuid.UUID] = None
    supporting_documents: Optional[list[dict]] = None


@app.post("/icasa/lodgments", status_code=status.HTTP_201_CREATED)
async def create_lodgment(
    body: LodgmentCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    lodge = IcasaLodgment(
        tenant_id=tenant_id, contract_id=body.contract_id,
        product_name=body.product_name, product_type=body.product_type,
        description=body.description, product_id=body.product_id,
        supporting_documents=body.supporting_documents, status="draft",
    )
    db.add(lodge)
    await db.flush()
    await db.refresh(lodge)
    return {"id": str(lodge.id), "product_name": lodge.product_name, "status": lodge.status}


@app.get("/icasa/lodgments")
async def list_lodgments(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    status: Optional[str] = None,
    contract_id: Optional[uuid.UUID] = None,
):
    stmt = select(IcasaLodgment).where(IcasaLodgment.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(IcasaLodgment.status == status)
    if contract_id:
        stmt = stmt.where(IcasaLodgment.contract_id == contract_id)
    result = await db.execute(stmt.order_by(desc(IcasaLodgment.created_at)))
    return [{"id": str(l.id), "product": l.product_name, "type": l.product_type, "status": l.status, "icasa_ref": l.icasa_reference} for l in result.scalars().all()]


@app.post("/icasa/lodgments/{lodge_id}/submit")
async def submit_lodgment(
    lodge_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    lodge = await db.get(IcasaLodgment, lodge_id)
    if not lodge or lodge.tenant_id != tenant_id:
        raise HTTPException(404, "Lodgment not found")
    lodge.status = "submitted"
    lodge.submitted_at = datetime.now(timezone.utc)
    await db.flush()
    return {"id": str(lodge.id), "status": "submitted"}


# ===========================================================================
# 4. ICASA REGULATIONS
# ===========================================================================

class RegulationCreate(BaseModel):
    document_type: str
    title: str = Field(..., max_length=500)
    description: Optional[str] = None
    icasa_reference: Optional[str] = None
    source_url: Optional[str] = None
    document_url: Optional[str] = None
    key_points: Optional[list[str]] = None
    affected_areas: Optional[list[str]] = None
    impact_level: str = "unknown"


@app.post("/icasa/regulations", status_code=status.HTTP_201_CREATED)
async def create_regulation(
    body: RegulationCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    reg = IcasaRegulation(
        tenant_id=tenant_id, document_type=body.document_type,
        title=body.title, description=body.description,
        icasa_reference=body.icasa_reference, source_url=body.source_url,
        document_url=body.document_url, key_points=body.key_points,
        affected_areas=body.affected_areas, impact_level=body.impact_level,
    )
    db.add(reg)
    await db.flush()
    await db.refresh(reg)
    return {"id": str(reg.id), "title": reg.title, "impact": reg.impact_level}


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
    return [{"id": str(r.id), "type": r.document_type, "title": r.title, "impact": r.impact_level, "is_new": r.is_new} for r in result.scalars().all()]


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
# 5. ICASA WEB SCRAPER
# ===========================================================================

ICASA_BASE_URL = "https://www.icasa.org.za"


@app.post("/icasa/scrape")
async def trigger_icasa_scrape(
    scrape_type: str = "regulations",
    background_tasks: BackgroundTasks = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Trigger ICASA website scrape for regulatory changes."""
    log = IcasaScrapeLog(
        tenant_id=tenant_id, scrape_type=scrape_type,
        source_url=f"{ICASA_BASE_URL}/{scrape_type}",
        status="running", started_at=datetime.now(timezone.utc),
    )
    db.add(log)
    await db.flush()

    if background_tasks:
        background_tasks.add_task(_scrape_icasa, log.id, scrape_type, tenant_id)

    return {"scrape_id": str(log.id), "status": "running"}


async def _scrape_icasa(log_id: uuid.UUID, scrape_type: str, tenant_id: uuid.UUID):
    """Background task: scrape ICASA website."""
    from services.compliance.database import get_session as _get_session
    async with _get_session() as session:
        log = await session.get(IcasaScrapeLog, log_id)
        if not log:
            return
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                url = f"{ICASA_BASE_URL}/{scrape_type}"
                resp = await client.get(url)
                resp.raise_for_status()
                # TODO: Parse HTML with BeautifulSoup to extract regulations
                log.status = "success"
                log.items_found = 1
        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            logger.error(f"ICASA scrape failed: {e}")
        log.completed_at = datetime.now(timezone.utc)
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
    return [{"id": str(l.id), "type": l.scrape_type, "status": l.status, "items": l.items_found, "started": l.started_at.isoformat()} for l in result.scalars().all()]


# ===========================================================================
# 6. POPI DATA SUBJECT ACCESS REQUESTS
# ===========================================================================

class PopiRequestCreate(BaseModel):
    contract_id: Optional[uuid.UUID] = None
    requested_by_customer_id: Optional[uuid.UUID] = None
    requested_by_email: Optional[str] = None
    request_type: str
    description: Optional[str] = None
    requested_data_categories: Optional[list[str]] = None


@app.post("/popi-requests", status_code=status.HTTP_201_CREATED)
async def create_popi_request(
    body: PopiRequestCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    now = datetime.now(timezone.utc)
    request = PopiDataRequest(
        tenant_id=tenant_id, contract_id=body.contract_id,
        requested_by_customer_id=body.requested_by_customer_id,
        requested_by_email=body.requested_by_email,
        request_type=body.request_type, description=body.description,
        requested_data_categories=body.requested_data_categories,
        submitted_at=now, due_date=now + timedelta(days=30),
    )
    db.add(request)
    await db.flush()
    await db.refresh(request)
    return {"id": str(request.id), "status": request.status, "due_date": request.due_date.isoformat()}


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
    return [{"id": str(r.id), "type": r.request_type, "status": r.status, "due": r.due_date.isoformat()} for r in result.scalars().all()]


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
# 7. DATA BREACH REGISTER
# ===========================================================================

class BreachCreate(BaseModel):
    contract_id: Optional[uuid.UUID] = None
    title: str = Field(..., max_length=500)
    description: Optional[str] = None
    severity: str = "medium"
    affected_data_subjects_count: int = 0
    affected_data_categories: Optional[list[str]] = None


@app.post("/breaches", status_code=status.HTTP_201_CREATED)
async def create_breach(
    body: BreachCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    breach = DataBreachRecord(
        tenant_id=tenant_id, contract_id=body.contract_id,
        title=body.title, description=body.description,
        severity=body.severity,
        affected_data_subjects_count=body.affected_data_subjects_count,
        affected_data_categories=body.affected_data_categories,
        detected_at=datetime.now(timezone.utc),
    )
    db.add(breach)
    await db.flush()
    await db.refresh(breach)
    return {"id": str(breach.id), "status": breach.status}


@app.get("/breaches")
async def list_breaches(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    status: Optional[str] = None,
):
    stmt = select(DataBreachRecord).where(DataBreachRecord.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(DataBreachRecord.status == status)
    result = await db.execute(stmt.order_by(desc(DataBreachRecord.detected_at)))
    return [{"id": str(b.id), "title": b.title, "severity": b.severity, "status": b.status} for b in result.scalars().all()]


@app.post("/breaches/{breach_id}/notify-icasa")
async def notify_icasa_breach(
    breach_id: uuid.UUID,
    icasa_reference: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    breach = await db.get(DataBreachRecord, breach_id)
    if not breach or breach.tenant_id != tenant_id:
        raise HTTPException(404, "Breach not found")
    breach.status = "notified_icasa"
    breach.icasa_notified_at = datetime.now(timezone.utc)
    breach.icasa_notification_reference = icasa_reference
    await db.flush()
    return {"id": str(breach.id), "icasa_notified": True}


# ===========================================================================
# 8. RICA VERIFICATION
# ===========================================================================

class RicaSessionCreate(BaseModel):
    contract_id: Optional[uuid.UUID] = None
    customer_id: Optional[uuid.UUID] = None
    verification_type: str = "DOCUMENT_VERIFICATION"


@app.post("/rica/sessions", status_code=status.HTTP_201_CREATED)
async def create_rica_session(
    body: RicaSessionCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    import hashlib, hmac
    job_id = f"RICA-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.now().isoformat()
    api_key = os.getenv("SMILE_ID_API_KEY", "mock_key")
    partner_id = os.getenv("SMILE_ID_PARTNER_ID", "mock_partner")
    message = f"{timestamp}{partner_id}sid_request"
    signature = hmac.new(api_key.encode(), message.encode(), hashlib.sha256).hexdigest()

    verification = RicaVerification(
        tenant_id=tenant_id, contract_id=body.contract_id,
        customer_id=body.customer_id, job_id=job_id,
        verification_type=body.verification_type, status="pending",
    )
    db.add(verification)
    await db.flush()
    return {"job_id": job_id, "signature": signature, "timestamp": timestamp}


@app.get("/rica/verifications")
async def list_rica_verifications(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    status: Optional[str] = None,
    contract_id: Optional[uuid.UUID] = None,
):
    stmt = select(RicaVerification).where(RicaVerification.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(RicaVerification.status == status)
    if contract_id:
        stmt = stmt.where(RicaVerification.contract_id == contract_id)
    result = await db.execute(stmt.order_by(desc(RicaVerification.created_at)))
    return [{"id": str(v.id), "job_id": v.job_id, "status": v.status, "id_number": v.id_number, "first_name": v.first_name, "last_name": v.last_name} for v in result.scalars().all()]


@app.post("/rica/callback")
async def rica_callback(
    request: Request,
    db: AsyncSession = Depends(get_session),
):
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
        await db.flush()
    return {"status": "accepted"}


# ===========================================================================
# 9. CONTRACT DOCUMENTS
# ===========================================================================

class DocumentUpload(BaseModel):
    contract_id: uuid.UUID
    document_type: str
    name: str = Field(..., max_length=300)
    description: Optional[str] = None
    file_path: str
    file_size_bytes: Optional[int] = None


@app.post("/contracts/documents", status_code=status.HTTP_201_CREATED)
async def add_contract_document(
    body: DocumentUpload,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    doc = ContractDocument(
        tenant_id=tenant_id, contract_id=body.contract_id,
        document_type=body.document_type, name=body.name,
        description=body.description, file_path=body.file_path,
        file_size_bytes=body.file_size_bytes,
    )
    db.add(doc)
    await db.flush()
    return {"id": str(doc.id), "name": doc.name, "type": doc.document_type}


@app.get("/contracts/{contract_id}/documents")
async def list_contract_documents(
    contract_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(ContractDocument).where(ContractDocument.contract_id == contract_id, ContractDocument.tenant_id == tenant_id)
    )
    return [{"id": str(d.id), "type": d.document_type, "name": d.name, "uploaded": d.uploaded_at.isoformat()} for d in result.scalars().all()]


# ===========================================================================
# 10. CONTRACT AUDIT LOG
# ===========================================================================

@app.get("/contracts/{contract_id}/audit-log")
async def get_contract_audit_log(
    contract_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    limit: int = Query(50, ge=1, le=500),
):
    result = await db.execute(
        select(ContractAuditLog).where(
            ContractAuditLog.contract_id == contract_id,
            ContractAuditLog.tenant_id == tenant_id,
        ).order_by(desc(ContractAuditLog.created_at)).limit(limit)
    )
    logs = result.scalars().all()
    return [{"action": l.action, "field": l.field_changed, "old": l.old_value, "new": l.new_value, "at": l.created_at.isoformat()} for l in logs]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8019)
