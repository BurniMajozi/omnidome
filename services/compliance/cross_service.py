"""Compliance Cross-Service Connectors.

Connects OmniDome Compliance to Sales/CRM contracts, fleet and H&S, finance/statutory,
call-centre POPIA, RICA and the orchestrator.

HONESTY RULES (owner decision, 2026-10):
  * Reads return only what is in the database (or the real payroll tables); a value
    that is not available is null, never a made-up default. Nothing is seeded on read.
  * This service never files anything with SARS / the Department of Labour and never
    stores their credentials. EMP201 is prepared as a working paper
    (POST /statutory/emp201/prepare) and a human records the real PRN afterwards
    (POST /statutory/emp201/{id}/mark-filed). The old "file / submit / certificate"
    endpoints answer 501.
"""

import json
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_session as get_db
from services.compliance import sa_calendar, scoring, statutory
from services.compliance.access import member_ctx, sensitive_ctx, tenant_str, write_ctx
from services.compliance.access import filing_ctx
from services.compliance.routes import statutory as statutory_routes
from services.compliance.routes.statutory import MarkFiledIn, PrepareIn, fetch_period_aggregate

logger = logging.getLogger("compliance.cross_service")

router = APIRouter(prefix="/cross-service", tags=["Compliance Cross-Service Connectors"])

NOT_AUTOMATED = (
    "This service does not file with SARS or the Department of Labour and holds no credentials for them. "
    "Prepare the working paper with POST /api/v1/statutory/emp201/prepare, file manually on eFiling / uFiling, "
    "then record the real PRN/receipt with POST /api/v1/statutory/emp201/{id}/mark-filed."
)


def _to_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _num(value) -> Optional[float]:
    return None if value is None else float(value)


# ═══════════════════════════════════════════════════════════════════════════
# 1. SALES & COMMERCIAL CONTRACTS CONNECTOR
# ═══════════════════════════════════════════════════════════════════════════

class ContractSlaItem(BaseModel):
    contract_id: int
    contract_number: str
    title: str
    counterparty: str
    contract_type: str
    status: str
    annual_value_zar: Optional[float] = None
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    days_to_expiry: Optional[int] = None
    uptime_sla_pct: Optional[float] = None       # average of recorded uptime/availability measurements
    mttr_target_hours: Optional[float] = None    # target of the contract's MTTR SLA, when one exists
    fica_status: str = "NOT_CHECKED"


class SalesContractsSlaResponse(BaseModel):
    total_contracts: int
    active_contracts_count: int
    total_portfolio_value_zar: float
    expiring_soon_count: int  # within 90 days
    average_sla_uptime_pct: Optional[float] = None
    fica_verified_pct: Optional[float] = None
    contracts: List[ContractSlaItem]


@router.get("/sales/contracts-sla", response_model=SalesContractsSlaResponse)
async def get_sales_contracts_sla(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    """The tenant's own contracts with SLA figures taken from recorded SLA measurements. Empty when none."""
    tid = tenant_str(ctx)
    rows = (await db.execute(
        text("""
            SELECT c.id, c.contract_number, c.title, c.counterparty_name, c.contract_type,
                   c.status, c.value_zar, c.effective_date, c.expiry_date
            FROM compliance_contracts c
            WHERE c.tenant_id = :tid
            ORDER BY c.value_zar DESC NULLS LAST
        """),
        {"tid": tid},
    )).fetchall()

    uptime = {
        r[0]: _num(r[1]) for r in (await db.execute(
            text("""
                SELECT s.contract_id, avg(m.measured_value)
                FROM compliance_sla_measurements m
                JOIN compliance_contract_slas s ON s.id = m.sla_id
                WHERE m.tenant_id = :tid AND s.tenant_id = :tid
                  AND (lower(s.metric) LIKE '%uptime%' OR lower(s.metric) LIKE '%availab%')
                GROUP BY s.contract_id
            """),
            {"tid": tid},
        )).fetchall()
    }
    mttr = {
        r[0]: _num(r[1]) for r in (await db.execute(
            text("""
                SELECT s.contract_id, max(s.target_value)
                FROM compliance_contract_slas s
                WHERE s.tenant_id = :tid AND lower(s.metric) LIKE '%mttr%'
                GROUP BY s.contract_id
            """),
            {"tid": tid},
        )).fetchall()
    }

    today = sa_calendar.sast_today()
    items: List[ContractSlaItem] = []
    for r in rows:
        exp = _to_date(r[8])
        eff = _to_date(r[7])
        items.append(ContractSlaItem(
            contract_id=r[0], contract_number=r[1], title=r[2], counterparty=r[3],
            contract_type=str(r[4]), status=str(r[5]), annual_value_zar=_num(r[6]),
            effective_date=str(eff) if eff else None,
            expiry_date=str(exp) if exp else None,
            days_to_expiry=(exp - today).days if exp else None,
            uptime_sla_pct=uptime.get(r[0]),
            mttr_target_hours=mttr.get(r[0]),
        ))

    measured = [i.uptime_sla_pct for i in items if i.uptime_sla_pct is not None]
    return SalesContractsSlaResponse(
        total_contracts=len(items),
        active_contracts_count=sum(1 for i in items if i.status.lower() in {"active", "signed", "in_force"}),
        total_portfolio_value_zar=round(sum(i.annual_value_zar or 0.0 for i in items), 2),
        expiring_soon_count=sum(1 for i in items if i.days_to_expiry is not None and 0 < i.days_to_expiry <= 90),
        average_sla_uptime_pct=round(sum(measured) / len(measured), 2) if measured else None,
        fica_verified_pct=None,
        contracts=items,
    )


class VetCustomerFicaRequest(BaseModel):
    company_name: str
    registration_number: str
    vat_number: Optional[str] = None
    director_name: str
    director_id_number: str
    physical_address: Optional[str] = None
    contact_email: Optional[str] = None


@router.post("/sales/vet-customer-fica")
async def vet_customer_fica(data: VetCustomerFicaRequest, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    """FORMAT checks on the CIPC registration number and the director's SA ID number, recorded as a
    document. This is NOT a FICA/AML verification: no CIPC, sanctions or ID-registry lookup is made."""
    reg = data.registration_number.strip()
    is_valid_format = len(reg) >= 10 and "/" in reg
    id_num = data.director_id_number.strip().replace(" ", "")
    is_valid_id = len(id_num) == 13 and id_num.isdigit()

    if not is_valid_format:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid CIPC Registration format. Required format: YYYY/NNNNNN/07 (e.g. 2021/489201/07)",
        )

    check_id = f"FICA-{uuid.uuid4().hex[:8].upper()}"
    status_result = "FORMAT_CHECKED_PENDING_MANUAL_REVIEW" if is_valid_id else "ID_FORMAT_INVALID_PENDING_MANUAL_REVIEW"
    meta = json.dumps({
        "company": data.company_name, "reg": data.registration_number, "director": data.director_name,
        "status": status_result, "checks": "format_only",
    })
    await db.execute(
        text("""
            INSERT INTO compliance_documents
                (tenant_id, document_type, title, mime_type, tags, extracted_data, uploaded_by, created_at, updated_at)
            VALUES
                (:tid, 'policy', :title, 'application/json', 'fica,vetting,format-only', :meta, :by, now(), now())
        """),
        {"tid": tenant_str(ctx), "title": f"FICA format check: {data.company_name} ({data.registration_number})",
         "meta": meta, "by": str(ctx.user_id)},
    )
    await db.flush()

    return {
        "status": "recorded",
        "check_reference": check_id,
        "verification_status": status_result,
        "company_name": data.company_name,
        "registration_number": data.registration_number,
        "director_id_format_valid": is_valid_id,
        "aml_sanctions_clear": None,
        "cipc_registered": None,
        "checks_performed": ["registration_number_format", "sa_id_number_format"],
        "checks_not_performed": ["CIPC lookup", "AML / sanctions screening", "ID registry verification"],
        "timestamp": datetime.utcnow().isoformat(),
        "message": "Format checks recorded. A manual FICA / CIPC / sanctions review is still required.",
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. FIELD TECHNICIANS & FLEET SAFETY CONNECTOR
# ═══════════════════════════════════════════════════════════════════════════

class FleetVehicleItem(BaseModel):
    id: int
    registration_number: str
    vehicle_type: Optional[str] = None
    assigned_technician_name: Optional[str] = None
    make_model: Optional[str] = None
    license_disc_expiry: Optional[str] = None
    days_to_license_expiry: Optional[int] = None
    roadworthy_status: str
    tracking_unit_active: Optional[bool] = None
    last_safety_inspection: Optional[str] = None


class SafetyIncidentItem(BaseModel):
    id: int
    incident_number: str
    incident_type: str
    severity: str
    incident_date: Optional[str] = None
    description: Optional[str] = None
    status: str
    coida_reported: bool


class TechnicianSafetyAuditResponse(BaseModel):
    total_fleet_vehicles: int
    roadworthy_compliant_count: int
    expiring_license_discs_30d: int
    zero_incident_streak_days: Optional[int] = None
    coida_reportable_accidents_ytd: int
    working_at_heights_certified_count: Optional[int] = None
    optical_laser_safety_certified_count: Optional[int] = None
    vehicles: List[FleetVehicleItem]
    recent_incidents: List[SafetyIncidentItem]


@router.get("/technicians/fleet-safety", response_model=TechnicianSafetyAuditResponse)
async def get_technician_fleet_safety(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    """The tenant's vehicles and H&S incidents exactly as recorded. Empty when none."""
    tid = tenant_str(ctx)
    v_rows = (await db.execute(
        text("""
            SELECT id, registration_number, vehicle_type, make, model,
                   license_expiry, roadworthy_expiry, assigned_driver
            FROM compliance_vehicle_registrations
            WHERE tenant_id = :tid
            ORDER BY registration_number
        """),
        {"tid": tid},
    )).fetchall()

    today = sa_calendar.sast_today()
    fleet: List[FleetVehicleItem] = []
    for r in v_rows:
        lic = _to_date(r[5])
        rw = _to_date(r[6])
        make_model = " ".join(p for p in (r[3], r[4]) if p) or None
        fleet.append(FleetVehicleItem(
            id=r[0], registration_number=r[1], vehicle_type=r[2],
            assigned_technician_name=r[7], make_model=make_model,
            license_disc_expiry=str(lic) if lic else None,
            days_to_license_expiry=(lic - today).days if lic else None,
            roadworthy_status=("UNKNOWN" if rw is None else "COMPLIANT" if rw >= today else "EXPIRED"),
        ))

    inc_rows = (await db.execute(
        text("""
            SELECT id, incident_number, incident_type, severity, incident_date, description, status, coida_reported
            FROM compliance_hs_incidents
            WHERE tenant_id = :tid
            ORDER BY incident_date DESC
            LIMIT 5
        """),
        {"tid": tid},
    )).fetchall()
    incidents = [
        SafetyIncidentItem(
            id=ir[0], incident_number=ir[1], incident_type=str(ir[2]), severity=str(ir[3]),
            incident_date=str(ir[4])[:10] if ir[4] else None, description=ir[5],
            status=str(ir[6]), coida_reported=bool(ir[7]),
        )
        for ir in inc_rows
    ]

    last_incident = _to_date(inc_rows[0][4]) if inc_rows else None
    ytd = (await db.execute(
        text("""
            SELECT count(*) FROM compliance_hs_incidents
            WHERE tenant_id = :tid AND coida_reported = true AND incident_date >= :jan1
        """),
        {"tid": tid, "jan1": datetime(today.year, 1, 1)},
    )).scalar() or 0

    return TechnicianSafetyAuditResponse(
        total_fleet_vehicles=len(fleet),
        roadworthy_compliant_count=sum(1 for v in fleet if v.roadworthy_status == "COMPLIANT"),
        expiring_license_discs_30d=sum(
            1 for v in fleet if v.days_to_license_expiry is not None and 0 <= v.days_to_license_expiry <= 30
        ),
        # A streak can only be stated when incidents are actually being recorded.
        zero_incident_streak_days=(today - last_incident).days if last_incident else None,
        coida_reportable_accidents_ytd=int(ytd),
        vehicles=fleet,
        recent_incidents=incidents,
    )


class LogHsIncidentRequest(BaseModel):
    incident_type: str  # injury, illness, near_miss, property_damage
    severity: str  # low, medium, high, critical
    description: str
    incident_date: Optional[str] = None
    employee_involved: Optional[str] = None
    location: Optional[str] = None


@router.post("/technicians/incident-log")
async def log_technician_incident(data: LogHsIncidentRequest, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    inc_dt = datetime.utcnow()
    if data.incident_date:
        try:
            inc_dt = datetime.strptime(data.incident_date[:10], "%Y-%m-%d")
        except ValueError:
            pass

    inc_num = f"INC-{uuid.uuid4().hex[:6].upper()}"
    coida = data.severity.lower() in {"high", "critical"}

    await db.execute(
        text("""
            INSERT INTO compliance_hs_incidents
                (tenant_id, incident_number, incident_type, severity, incident_date, description, location,
                 status, coida_reported, created_at, updated_at)
            VALUES
                (:tid, :num, CAST(:itype AS hsincidenttype), CAST(:sev AS hsseverity), :idate, :desc, :loc,
                 'investigating', false, now(), now())
        """),
        {
            "tid": tenant_str(ctx), "num": inc_num,
            "itype": data.incident_type.lower(), "sev": data.severity.lower(),
            "idate": inc_dt, "loc": data.location,
            "desc": f"[{data.employee_involved or 'Field Staff'}] {data.description}",
        },
    )
    await db.flush()

    return {
        "status": "logged",
        "incident_number": inc_num,
        # coida_reported stays false until a person actually reports to the Compensation Fund.
        "coida_reporting_required": coida,
        "coida_reported": False,
        "statutory_form": "W.Cl.2 (Notice of Accident and Claim for Compensation)" if coida else "Internal Record Only",
        "message": f"Incident {inc_num} recorded in the register.",
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. FINANCE & STATUTORY TREASURY CONNECTOR
# ═══════════════════════════════════════════════════════════════════════════

class StatutoryTaxObligation(BaseModel):
    tax_type: str
    period: str
    due_date: Optional[str] = None
    status: str
    amount_payable_zar: Optional[float] = None
    reference_number: Optional[str] = None


class StatutoryStatusResponse(BaseModel):
    cipc_annual_returns_status: Optional[str] = None
    cipc_next_filing_deadline: Optional[str] = None
    sars_tax_clearance_status: Optional[str] = None
    sars_pin_expiry: Optional[str] = None
    bbbee_contributor_level: Optional[str] = None
    bbbee_procurement_recognition_pct: Optional[int] = None
    bbbee_valid_until: Optional[str] = None
    popia_statutory_liability_mitigation_score_pct: Optional[float] = None
    tax_obligations: List[StatutoryTaxObligation]


@router.get("/finance/statutory-status", response_model=StatutoryStatusResponse)
async def get_finance_statutory_status(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    """CIPC, B-BBEE and tax-return status exactly as recorded for this tenant; null where nothing is recorded."""
    tid = tenant_str(ctx)
    t_rows = (await db.execute(
        text("""
            SELECT tax_type, period_start, period_end, status, amount_payable, sars_reference
            FROM compliance_tax_returns
            WHERE tenant_id = :tid
            ORDER BY period_end DESC
            LIMIT 4
        """),
        {"tid": tid},
    )).fetchall()

    obligations: List[StatutoryTaxObligation] = []
    for tr in t_rows:
        t_type = str(tr[0]).lower()
        p_end = _to_date(tr[2])
        due = None
        if t_type == "paye" and p_end:
            due = str(sa_calendar.emp201_due_date(p_end.strftime("%Y-%m"))[0])
        obligations.append(StatutoryTaxObligation(
            tax_type="VAT201 (Value-Added Tax)" if t_type == "vat" else
                     "EMP201 (PAYE/UIF/SDL)" if t_type == "paye" else t_type.upper(),
            period=p_end.strftime("%Y-%m") if p_end else "",
            due_date=due, status=str(tr[3]).upper(), amount_payable_zar=_num(tr[4]), reference_number=tr[5],
        ))

    cipc = (await db.execute(
        text("""
            SELECT status, due_date FROM compliance_cipc_filings
            WHERE tenant_id = :tid AND lower(coalesce(status, '')) <> 'filed'
            ORDER BY due_date ASC LIMIT 1
        """),
        {"tid": tid},
    )).fetchone()
    bbbee = (await db.execute(
        text("""
            SELECT overall_level, certificate_expiry_date FROM compliance_bbbee_scorecards
            WHERE tenant_id = :tid ORDER BY id DESC LIMIT 1
        """),
        {"tid": tid},
    )).fetchone()

    return StatutoryStatusResponse(
        cipc_annual_returns_status=str(cipc[0]).upper() if cipc else None,
        cipc_next_filing_deadline=str(_to_date(cipc[1])) if cipc and cipc[1] else None,
        bbbee_contributor_level=str(bbbee[0]) if bbbee else None,
        bbbee_valid_until=str(_to_date(bbbee[1])) if bbbee and bbbee[1] else None,
        tax_obligations=obligations,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. CALL CENTER & POPIA CONSENT CONNECTOR
# ═══════════════════════════════════════════════════════════════════════════

class DsarItem(BaseModel):
    id: int
    request_number: str
    request_type: str
    requester_name: str
    requester_email: Optional[str] = None
    status: str
    received_date: Optional[str] = None
    due_date: Optional[str] = None
    days_remaining: Optional[int] = None


class PopiaAuditResponse(BaseModel):
    voice_recording_consent_rate_pct: Optional[float] = None
    total_calls_monitored_month: Optional[int] = None
    active_dsar_requests_count: int
    overdue_dsar_count: int
    registered_information_officer: Optional[str] = None
    regulator_registration_number: Optional[str] = None
    open_data_breaches_count: int
    requests: List[DsarItem]


@router.get("/call-center/popia-audit", response_model=PopiaAuditResponse)
async def get_call_center_popia_audit(ctx: AuthContext = Depends(sensitive_ctx), db: AsyncSession = Depends(get_db)):
    """The tenant's DSAR register and open breaches. Call-recording consent rates and the Information
    Officer registration are not tracked here and are returned as null."""
    tid = tenant_str(ctx)
    rows = (await db.execute(
        text("""
            SELECT id, request_reference, request_type, data_subject_name, data_subject_email, status, received_date, due_date
            FROM compliance_popi_dsar
            WHERE tenant_id = :tid
            ORDER BY received_date DESC
        """),
        {"tid": tid},
    )).fetchall()

    today = sa_calendar.sast_today()
    dsars: List[DsarItem] = []
    for r in rows:
        due = _to_date(r[7])
        rec = _to_date(r[6])
        dsars.append(DsarItem(
            id=r[0], request_number=r[1], request_type=str(r[2]), requester_name=r[3], requester_email=r[4],
            status=str(r[5]), received_date=str(rec) if rec else None, due_date=str(due) if due else None,
            days_remaining=(due - today).days if due else None,
        ))

    open_breaches = (await db.execute(
        text("SELECT count(*) FROM compliance_breach_register WHERE tenant_id = :tid AND status NOT IN ('resolved', 'closed')"),
        {"tid": tid},
    )).scalar() or 0

    return PopiaAuditResponse(
        active_dsar_requests_count=sum(1 for d in dsars if d.status != "completed"),
        overdue_dsar_count=sum(1 for d in dsars if d.status != "completed" and d.days_remaining is not None and d.days_remaining < 0),
        open_data_breaches_count=int(open_breaches),
        requests=dsars,
    )


class CreateDsarRequest(BaseModel):
    request_type: str  # access, deletion, rectification, objection
    requester_name: str
    requester_email: str
    requester_phone: Optional[str] = None
    description: str


@router.post("/call-center/dsar-log")
async def log_call_center_dsar(data: CreateDsarRequest, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    """Register a POPIA Data Subject Access Request and start the 30-day clock."""
    req_num = f"DSAR-{uuid.uuid4().hex[:8].upper()}"
    rec_date = datetime.utcnow()
    due_date = rec_date + timedelta(days=30)

    await db.execute(
        text("""
            INSERT INTO compliance_popi_dsar
                (tenant_id, request_reference, request_type, data_subject_name, data_subject_email, data_subject_phone,
                 description, status, received_date, due_date, created_at, updated_at)
            VALUES
                (:tid, :num, :rtype, :name, :email, :phone, :desc, 'received', :rec, :due, now(), now())
        """),
        {
            "tid": tenant_str(ctx), "num": req_num, "rtype": data.request_type.lower(),
            "name": data.requester_name, "email": data.requester_email, "phone": data.requester_phone or "",
            "desc": data.description, "rec": rec_date, "due": due_date,
        },
    )
    await db.flush()

    return {
        "status": "registered",
        "request_number": req_num,
        "statutory_response_deadline": str(due_date),
        "days_allowed": 30,
        "message": f"POPIA request {req_num} registered. Response deadline: {due_date.date()}.",
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. RICA SUBSCRIBER VERIFICATION CONNECTOR
# ═══════════════════════════════════════════════════════════════════════════

class RicaSubscriberAuditResponse(BaseModel):
    total_active_subscribers: Optional[int] = None
    verified_subscribers_count: int
    verified_pct: Optional[float] = None
    unverified_quarantine_count: Optional[int] = None
    recorded_verifications: int
    sa_smart_id_verified_count: Optional[int] = None
    foreign_passport_permit_count: Optional[int] = None
    green_barcode_book_count: Optional[int] = None
    biometric_smileid_verified_pct: Optional[float] = None
    average_audit_latency_ms: Optional[int] = None


@router.get("/rica/subscriber-audit", response_model=RicaSubscriberAuditResponse)
async def get_rica_subscriber_audit(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    """Counts of this tenant's recorded RICA verifications. The subscriber base lives in other services,
    so verified_pct / quarantine counts are null rather than guessed."""
    row = (await db.execute(
        text("""
            SELECT count(*), count(*) FILTER (WHERE status = 'verified')
            FROM compliance_rica_verifications WHERE tenant_id = :tid
        """),
        {"tid": tenant_str(ctx)},
    )).fetchone()
    return RicaSubscriberAuditResponse(
        verified_subscribers_count=int(row[1] or 0),
        recorded_verifications=int(row[0] or 0),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6. EXECUTIVE COMPLIANCE COPILOT & ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════

class ComplianceAlertItem(BaseModel):
    id: str
    category: str
    severity: str
    title: str
    description: str
    deadline: Optional[str] = None
    recommended_action: str


class ExecutiveSummaryResponse(BaseModel):
    overall_compliance_score: Optional[int] = None
    audit_readiness_level: str  # NOT_ASSESSED when there is no scoring data
    critical_statutory_deadlines_30d: int
    pillars_assessed_count: int
    icasa_regulatory_alerts_count: int
    alerts: List[ComplianceAlertItem]


@router.get("/orchestrator/executive-summary", response_model=ExecutiveSummaryResponse)
async def get_orchestrator_executive_summary(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    """Alerts derived from THIS tenant's real records (expiring contracts, licence discs, overdue DSARs,
    open breaches, overdue tax). No records means no alerts and a null score."""
    from services.compliance import crud
    from services.compliance.database import ComplianceScore

    tid = tenant_str(ctx)
    today = sa_calendar.sast_today()
    alerts: List[ComplianceAlertItem] = []

    async def scalar(sql: str, **params):
        return (await db.execute(text(sql), {"tid": tid, **params})).scalar() or 0

    expiring = await scalar(
        "SELECT count(*) FROM compliance_contracts WHERE tenant_id = :tid AND status = 'active' "
        "AND expiry_date IS NOT NULL AND expiry_date BETWEEN :d0 AND :d1", d0=today, d1=today + timedelta(days=90))
    if expiring:
        alerts.append(ComplianceAlertItem(
            id="contracts-expiring", category="COMMERCIAL_CONTRACTS", severity="medium",
            title=f"{expiring} active contract(s) expire within 90 days",
            description="Review renewal or termination terms for the contracts listed under Contracts.",
            deadline=str(today + timedelta(days=90)), recommended_action="Open Contracts and review the expiring list."))
    discs = await scalar(
        "SELECT count(*) FROM compliance_vehicle_registrations WHERE tenant_id = :tid AND status = 'active' "
        "AND license_expiry IS NOT NULL AND license_expiry <= :d1", d1=today + timedelta(days=30))
    if discs:
        alerts.append(ComplianceAlertItem(
            id="fleet-discs", category="FLEET_SAFETY", severity="low",
            title=f"{discs} vehicle licence disc(s) expired or expiring within 30 days",
            description="Licence discs due for renewal.", deadline=str(today + timedelta(days=30)),
            recommended_action="Renew the licence discs."))
    overdue_dsar = await scalar(
        "SELECT count(*) FROM compliance_popi_dsar WHERE tenant_id = :tid AND status <> 'completed' AND due_date < :now",
        now=datetime.utcnow())
    if overdue_dsar:
        alerts.append(ComplianceAlertItem(
            id="dsar-overdue", category="POPIA_PRIVACY", severity="high",
            title=f"{overdue_dsar} DSAR(s) past the 30-day deadline",
            description="Data subject requests are overdue.", deadline=None,
            recommended_action="Complete or escalate the overdue requests."))
    open_breaches = await scalar(
        "SELECT count(*) FROM compliance_breach_register WHERE tenant_id = :tid AND status IN ('identified', 'investigating')")
    if open_breaches:
        alerts.append(ComplianceAlertItem(
            id="breaches-open", category="POPIA_PRIVACY", severity="high",
            title=f"{open_breaches} open breach(es) in the register",
            description="Breaches still identified or under investigation.", deadline=None,
            recommended_action="Review notification duties to the Information Regulator / ICASA."))
    tax_overdue = await scalar(
        "SELECT count(*) FROM compliance_tax_returns WHERE tenant_id = :tid AND status = 'overdue'")
    if tax_overdue:
        alerts.append(ComplianceAlertItem(
            id="tax-overdue", category="STATUTORY_TAX", severity="high",
            title=f"{tax_overdue} tax return(s) marked overdue", description="Overdue returns in the tax register.",
            deadline=None, recommended_action="File on SARS eFiling and record the reference."))

    rows = await crud.list_rows(db, ctx, ComplianceScore, order_by=ComplianceScore.calculated_at.desc())
    latest = scoring.latest_per_category(rows)
    overall = scoring.overall_score(latest)
    readiness = (
        "NOT_ASSESSED" if overall is None
        else "AUDIT_READY" if overall >= 90 and not any(a.severity == "high" for a in alerts)
        else "MINOR_ATTENTION" if overall >= 70 else "CRITICAL_GAPS"
    )
    icasa_open = await scalar(
        "SELECT count(*) FROM compliance_icasa_regulation_changes WHERE tenant_id = :tid AND status = 'identified'")

    return ExecutiveSummaryResponse(
        overall_compliance_score=overall,
        audit_readiness_level=readiness,
        critical_statutory_deadlines_30d=sum(1 for a in alerts if a.severity == "high"),
        pillars_assessed_count=len(latest),
        icasa_regulatory_alerts_count=int(icasa_open),
        alerts=alerts,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7. STATUTORY PAYE, UIF ADMINISTRATION & LABOUR COMPLIANCE
# ═══════════════════════════════════════════════════════════════════════════

class Emp201ReturnItem(BaseModel):
    id: Optional[int] = None
    period: str
    due_date: Optional[str] = None
    paye_zar: Optional[float] = None
    uif_zar: Optional[float] = None
    sdl_zar: Optional[float] = None
    total_payable_zar: Optional[float] = None
    status: str
    prn: Optional[str] = None
    submission_date: Optional[str] = None
    sars_receipt_number: Optional[str] = None


class StatutoryPayrollSummaryResponse(BaseModel):
    period: str
    data_source: str
    rates_verified: bool = False
    rates: dict
    total_employees: Optional[int] = None
    gross_remuneration_zar: Optional[float] = None
    paye_withheld_zar: Optional[float] = None
    uif_employee_zar: Optional[float] = None
    uif_employer_zar: Optional[float] = None
    sdl_zar: Optional[float] = None
    total_emp201_liability_zar: Optional[float] = None
    net_salaries_disbursed_zar: Optional[float] = None
    due_date: Optional[str] = None
    due_date_note: Optional[str] = None
    sars_tcc_pin: Optional[str] = None
    sars_tcc_status: Optional[str] = None
    sars_prn: Optional[str] = None
    emp501_reconciliation_status: str = "NOT_AVAILABLE"
    emp501_variance_zar: Optional[float] = None
    recent_emp201_returns: List[Emp201ReturnItem]


class FileEmp201Request(BaseModel):
    period: str
    amount_paye: Optional[float] = None
    amount_uif: Optional[float] = None
    amount_sdl: Optional[float] = None
    payment_method: Optional[str] = None
    notes: Optional[str] = None


class UifDeclarationItem(BaseModel):
    employee_id: str
    employee_code: Optional[str] = None
    full_name: str
    id_number: Optional[str] = None
    id_number_missing: bool
    tax_number: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    gross_remuneration_zar: Optional[float] = None
    uif_remuneration_zar: Optional[float] = None
    hours_worked_month: Optional[int] = None
    employee_uif_zar: Optional[float] = None
    employer_uif_zar: Optional[float] = None
    total_uif_zar: Optional[float] = None
    employment_status: Optional[str] = None
    uif_declaration_status: str


class UifDeclarationsResponse(BaseModel):
    period: str
    uif_employer_reference: Optional[str] = None
    total_contributors: int
    total_monthly_remittance_zar: Optional[float] = None
    ufiling_batch_reference: Optional[str] = None
    ufiling_status: str
    last_submission_date: Optional[str] = None
    rates_verified: bool = False
    employees: List[UifDeclarationItem]


class SubmitUifRequest(BaseModel):
    period: str
    declarer_name: str
    notes: Optional[str] = None


class IssueUi27Request(BaseModel):
    employee_id: str
    reason_for_claim: str
    last_day_worked: str


class LaborAuditFinding(BaseModel):
    standard: str
    category: str
    compliant: Optional[bool] = None
    status_label: str
    details: str
    remediation: Optional[str] = None


class LaborComplianceAuditResponse(BaseModel):
    overall_labor_score: Optional[float] = None
    bcea_readiness_status: str
    normal_hours_compliant_pct: Optional[float] = None
    overtime_compliant_pct: Optional[float] = None
    mandatory_leave_accrual_compliant_pct: Optional[float] = None
    psira_security_grading_compliant_pct: Optional[float] = None
    total_active_staff: int
    psira_registered_officers: Optional[int] = None
    audit_findings: List[LaborAuditFinding]


def _valid_period(period: Optional[str]) -> str:
    cur = period or sa_calendar.sast_today().strftime("%Y-%m")
    try:
        sa_calendar.parse_period(cur)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return cur


@router.get("/payroll-statutory/summary", response_model=StatutoryPayrollSummaryResponse)
async def get_payroll_statutory_summary(
    period: Optional[str] = Query(None, description="YYYY-MM; defaults to the current SAST month"),
    ctx: AuthContext = Depends(sensitive_ctx),
    db: AsyncSession = Depends(get_db),
):
    """EMP201 figures for ONE period from real PAID / PARTIALLY_PAID payroll runs.
    No paid payroll for the period => every figure is null (nothing is estimated or substituted)."""
    cur = _valid_period(period)
    tid = tenant_str(ctx)
    fig = await fetch_period_aggregate(db, tid, cur)
    due, due_note = sa_calendar.emp201_due_date(cur)
    rates = statutory.load_rates()

    wps = (await db.execute(
        text("""
            SELECT id, period, due_date, paye, uif_employee, uif_employer, sdl, total_liability,
                   status, prn, filed_at, receipt_reference
            FROM compliance_emp201_workpapers
            WHERE tenant_id = :tid ORDER BY period DESC LIMIT 6
        """),
        {"tid": tid},
    )).fetchall()
    recent = [
        Emp201ReturnItem(
            id=w[0], period=w[1], due_date=str(_to_date(w[2])) if w[2] else None,
            paye_zar=_num(w[3]),
            uif_zar=None if w[4] is None and w[5] is None else round((_num(w[4]) or 0) + (_num(w[5]) or 0), 2),
            sdl_zar=_num(w[6]), total_payable_zar=_num(w[7]), status=str(w[8]),
            prn=w[9], submission_date=str(_to_date(w[10])) if w[10] else None, sars_receipt_number=w[11],
        )
        for w in wps
    ]
    current_prn = next((w[9] for w in wps if w[1] == cur and w[9]), None)

    return StatutoryPayrollSummaryResponse(
        period=cur,
        data_source="payslips of PAID/PARTIALLY_PAID payroll runs for the period",
        rates_verified=False,
        rates=rates.as_dict(),
        total_employees=fig["employee_count"],
        gross_remuneration_zar=fig["gross_remuneration"],
        paye_withheld_zar=fig["paye"],
        uif_employee_zar=fig["uif_employee"],
        uif_employer_zar=fig["uif_employer"],
        sdl_zar=fig["sdl"],
        total_emp201_liability_zar=fig["total_liability"],
        net_salaries_disbursed_zar=fig["net_pay"],
        due_date=str(due), due_date_note=due_note,
        sars_prn=current_prn,
        recent_emp201_returns=recent,
    )


@router.post("/payroll-statutory/emp201/file")
async def file_emp201_declaration(data: FileEmp201Request, ctx: AuthContext = Depends(sensitive_ctx)):
    """Removed: this used to record a 'paid' return with an invented PRN and receipt without contacting SARS."""
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=NOT_AUTOMATED)


# Aliases of /statutory/emp201/... under the path the web frontend calls.
@router.post("/payroll-statutory/emp201/prepare")
async def prepare_emp201_alias(body: PrepareIn, ctx: AuthContext = Depends(sensitive_ctx), db: AsyncSession = Depends(get_db)):
    """Build the EMP201 working paper from real paid payroll (status PREPARED_NOT_FILED). Files nothing."""
    return await statutory_routes.prepare_emp201(body, ctx, db)


@router.post("/payroll-statutory/emp201/{workpaper_id}/mark-filed")
async def mark_emp201_filed_alias(workpaper_id: int, body: MarkFiledIn, ctx: AuthContext = Depends(filing_ctx), db: AsyncSession = Depends(get_db)):
    """hr/finance admin records the REAL PRN/receipt copied from SARS eFiling."""
    return await statutory_routes.mark_emp201_filed(workpaper_id, body, ctx, db)


@router.get("/payroll-statutory/uif/declarations", response_model=UifDeclarationsResponse)
async def get_uif_declarations(
    period: Optional[str] = Query(None),
    ctx: AuthContext = Depends(sensitive_ctx),  # employee ID and tax numbers
    db: AsyncSession = Depends(get_db),
):
    """UI-19 working data per employee from real payslips of the period. Missing ID numbers are reported
    as missing (null) and flagged; employees without a payslip in the period have null amounts."""
    cur = _valid_period(period)
    tid = tenant_str(ctx)
    rates = statutory.load_rates()
    rows = (await db.execute(
        text("""
            SELECT e.id, e.employee_id, e.full_name, e.department, e.job_title, e.id_number, e.tax_number, e.status,
                   p.gross, p.uif, p.uif_employer
            FROM employees e
            LEFT JOIN (
                SELECT ps.employee_id, sum(ps.gross) AS gross, sum(ps.uif) AS uif, sum(ps.uif_employer) AS uif_employer
                FROM payslips ps
                JOIN payroll_runs r ON r.id = ps.run_id
                WHERE ps.tenant_id = :tid AND r.tenant_id = :tid AND r.period = :period
                  AND r.status IN ('PAID', 'PARTIALLY_PAID')
                GROUP BY ps.employee_id
            ) p ON p.employee_id = e.id
            WHERE e.tenant_id = :tid
            ORDER BY e.full_name
        """),
        {"tid": tid, "period": cur},
    )).fetchall()

    items: List[UifDeclarationItem] = []
    total = 0.0
    any_amount = False
    for r in rows:
        gross = _num(r[8])
        id_number = (r[5] or "").strip() or None
        emp_uif = _num(r[9])
        co_uif = _num(r[10])
        if gross is None:
            decl = "NO_PAYSLIP_FOR_PERIOD"
        elif id_number is None:
            decl = "INCOMPLETE_ID_NUMBER_MISSING"
        else:
            decl = "READY_TO_DECLARE_MANUALLY"
        tot = None if emp_uif is None and co_uif is None else round((emp_uif or 0) + (co_uif or 0), 2)
        if tot is not None:
            total += tot
            any_amount = True
        items.append(UifDeclarationItem(
            employee_id=str(r[0]), employee_code=r[1], full_name=r[2], department=r[3], job_title=r[4],
            id_number=id_number, id_number_missing=id_number is None, tax_number=(r[6] or None),
            gross_remuneration_zar=gross,
            uif_remuneration_zar=None if gross is None else min(gross, rates.uif_monthly_ceiling),
            employee_uif_zar=emp_uif, employer_uif_zar=co_uif, total_uif_zar=tot,
            employment_status=r[7], uif_declaration_status=decl,
        ))

    return UifDeclarationsResponse(
        period=cur,
        total_contributors=sum(1 for i in items if i.total_uif_zar is not None),
        total_monthly_remittance_zar=round(total, 2) if any_amount else None,
        ufiling_status="NOT_SUBMITTED_BY_THIS_SERVICE",
        rates_verified=False,
        employees=items,
    )


@router.post("/payroll-statutory/uif/submit")
async def submit_uif_declaration(data: SubmitUifRequest, ctx: AuthContext = Depends(sensitive_ctx)):
    """Removed: this used to return an invented batch reference and acknowledgment without contacting uFiling."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="This service does not submit UI-19 declarations to the Department of Employment and Labour. "
               "Download the declaration data and submit it manually on uFiling.",
    )


@router.post("/payroll-statutory/uif/ui27-certificate")
async def issue_ui27_certificate(data: IssueUi27Request, ctx: AuthContext = Depends(sensitive_ctx)):
    """Removed: certificates were generated with an invented employer UIF reference and signatory."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="UI-2.7 certificates are not issued by this service; complete the form with the employer's real UIF reference.",
    )


@router.get("/payroll-statutory/labor-audit", response_model=LaborComplianceAuditResponse)
async def get_labor_compliance_audit(ctx: AuthContext = Depends(sensitive_ctx), db: AsyncSession = Depends(get_db)):
    """Headcount from the employee register. BCEA / PSIRA / COIDA conformance cannot be assessed from the
    data this service holds, so every check is reported as not assessed rather than 'compliant'."""
    total_staff = (await db.execute(
        text("SELECT count(*) FROM employees WHERE tenant_id = :tid AND coalesce(status, 'ACTIVE') = 'ACTIVE'"),
        {"tid": tenant_str(ctx)},
    )).scalar() or 0

    def finding(standard: str, category: str, needs: str) -> LaborAuditFinding:
        return LaborAuditFinding(
            standard=standard, category=category, compliant=None, status_label="Not assessed",
            details=f"No data is connected to assess this. Needs: {needs}.",
            remediation="Provide the evidence or connect the data source, then record the outcome as an obligation.",
        )

    return LaborComplianceAuditResponse(
        bcea_readiness_status="NOT_ASSESSED",
        total_active_staff=int(total_staff),
        audit_findings=[
            finding("BCEA Section 9 (Ordinary Hours of Work)", "WORKING_HOURS", "contracted/worked hours per employee"),
            finding("BCEA Section 10 (Overtime)", "OVERTIME", "overtime hours and rates paid"),
            finding("BCEA Section 20 (Annual Leave)", "ANNUAL_LEAVE", "leave accrual and balances"),
            finding("BCEA Section 14 (Meal Intervals & Daily Rest)", "REST_PERIODS", "shift and rest records"),
            finding("PSIRA Act (Security Service Provider Registration)", "PSIRA_GUARDING", "PSIRA registration of any guarding staff"),
            finding("COIDA (Compensation for Occupational Injuries and Diseases)", "WORKPLACE_INJURY", "Return of Earnings and Letter of Good Standing"),
        ],
    )
