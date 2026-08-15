"""
Compliance Service — Pydantic Schemas for Request/Response Validation
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, field_validator

# ── Enums ──────────────────────────────────────────────────────────────

class ContractType(str):
    fno = "fno"
    supplier = "supplier"
    customer = "customer"
    employee = "employee"
    partner = "partner"
    service_level = "service_level"
    interconnect = "interconnect"
    infrastructure = "infrastructure"
    maintenance = "maintenance"

class ContractStatus(str):
    draft = "draft"
    active = "active"
    expired = "expired"
    terminated = "terminated"
    suspended = "suspended"

class SlaComparison(str):
    lower_is_worse = "lower_is_worse"
    higher_is_worse = "higher_is_worse"

# ── Contract Schemas ──────────────────────────────────────────────────

class ContractBase(BaseModel):
    contract_type: ContractType
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    contract_type_value: Optional[str] = None
    start_date: Optional[date] = None
    expiry_date: Optional[date] = None
    counterparty: Optional[str] = None
    value: Optional[Decimal] = None
    currency: str = "ZAR"
    status: ContractStatus = ContractStatus.draft
    auto_renew: bool = False
    renewal_notice_days: int = 30
    compliance_category: Optional[str] = None
    compliance_score: Optional[int] = None
    risk_level: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator('contract_type_value', mode='before')
    @classmethod
    def _validate_contract_type(cls, v):
        if isinstance(v, ContractType):
            return v.value
        return v

class ContractCreate(ContractBase):
    tenant_id: str  # will be overridden by auth context
    created_by: Optional[str] = None

class ContractUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    start_date: Optional[date] = None
    expiry_date: Optional[date] = None
    counterparty: Optional[str] = None
    value: Optional[Decimal] = None
    currency: Optional[str] = None
    status: Optional[ContractStatus] = None
    auto_renew: Optional[bool] = None
    renewal_notice_days: Optional[int] = None
    compliance_category: Optional[str] = None
    compliance_score: Optional[int] = None
    risk_level: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class ContractSLAStatus(str):
    active = "active"
    inactive = "inactive"
    suspended = "suspended"

class ContractSLACreate(BaseModel):
    contract_id: int
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    metric_name: str = Field(min_length=1, max_length=100)
    target_value: Decimal
    unit: str = Field(min_length=1, max_length=20)
    comparison: SlaComparison = SlaComparison.lower_is_worse
    measurement_frequency: str = "daily"
    threshold_warning_pct: Optional[float] = None
    threshold_critical_pct: Optional[float] = None
    status: ContractSLAStatus = ContractSLAStatus.active

class SlaMeasurementCreate(BaseModel):
    sla_id: int
    measured_value: Decimal
    measured_at: datetime
    notes: Optional[str] = None

# ── Document Schemas ──────────────────────────────────────────────────

class DocumentType(str):
    contract = "contract"
    tax_return = "tax_return"
    hs_report = "hs_report"
    cipc_filing = "cipc_filing"
    bbbee_certificate = "bbbee_certificate"
    permit = "permit"
    dr_plan = "dr_plan"
    bcp_plan = "bcp_plan"
    financial_statement = "financial_statement"
    invoice = "invoice"
    policy = "policy"
    other = "other"

class DocumentUploadResponse(BaseModel):
    status: str
    document_id: int
    understanding: Dict[str, Any]

class FetchUrlRequest(BaseModel):
    url: HttpUrl
    tenant_id: Optional[str] = None  # overridden by auth
    doc_type_hint: Optional[str] = None
    crawl: bool = False
    max_depth: int = Field(default=2, ge=1, le=5)

class WebIntelIngestRequest(BaseModel):
    url: HttpUrl
    tenant_id: Optional[str] = None
    doc_type_hint: Optional[str] = None
    contract_id: Optional[int] = None

class ReprocessDocumentRequest(BaseModel):
    tenant_id: Optional[str] = None
    doc_type_hint: Optional[str] = None

class LinkDocumentRequest(BaseModel):
    contract_id: int
    tenant_id: Optional[str] = None

# ── ICASA Schemas ──────────────────────────────────────────────────────

class IcasaSubmissionBase(BaseModel):
    submission_type: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    status: str = "draft"
    reference_number: Optional[str] = None
    due_date: Optional[date] = None
    submitted_date: Optional[datetime] = None

class IcasaSubmissionCreate(IcasaSubmissionBase):
    tenant_id: Optional[str] = None

class IcasaScrapeJobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    target_url: HttpUrl
    frequency: str = "daily"
    selectors: Dict[str, str] = {}

class IcasaRegulationChangeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    source_url: HttpUrl
    impact_level: str = "low"
    status: str = "detected"

# ── POPI Schemas ──────────────────────────────────────────────────────

class PopiDataAccessRequestCreate(BaseModel):
    data_subject_id: str = Field(min_length=1)
    full_name: str = Field(min_length=1)
    email: str
    phone: Optional[str] = None
    request_type: str = "access"
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    status: str = "received"
    tenant_id: Optional[str] = None

class PopiConsentRecordCreate(BaseModel):
    data_subject_id: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    consent_given: bool
    consent_method: str = "explicit"
    expiry_date: Optional[date] = None
    tenant_id: Optional[str] = None

# ── RICA Schemas ──────────────────────────────────────────────────────

class RicaVerificationCreate(BaseModel):
    id_number_hash: str = Field(min_length=64, max_length=64)  # salted hash
    full_name: str = Field(min_length=1)
    msisdn: str = Field(min_length=10, max_length=15)
    sim_number: Optional[str] = None
    status: str = "pending"
    expiry_date: Optional[datetime] = None
    tenant_id: Optional[str] = None

# ── Breach Register Schemas ───────────────────────────────────────────

class BreachSeverity(str):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

class BreachStatus(str):
    identified = "identified"
    investigating = "investigating"
    contained = "contained"
    resolved = "resolved"
    closed = "closed"

class BreachCategory(str):
    data_breach = "data_breach"
    security_incident = "security_incident"
    compliance_failure = "compliance_failure"
    service_outage = "service_outage"
    other = "other"

class BreachRegisterCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    severity: BreachSeverity
    category: BreachCategory
    status: BreachStatus = BreachStatus.identified
    identified_date: datetime
    contained_date: Optional[datetime] = None
    resolved_date: Optional[datetime] = None
    icasa_notified: bool = False
    popi_commission_notified: bool = False
    financial_impact: Optional[Decimal] = None
    affected_data_subjects: Optional[int] = None
    root_cause: Optional[str] = None
    remediation_actions: Optional[str] = None
    tenant_id: Optional[str] = None

# ── Funding Schemas ───────────────────────────────────────────────────

class FundingType(str):
    grant = "grant"
    loan = "loan"
    equity = "equity"
    tax_incentive = "tax_incentive"
    other = "other"

class FundingOpportunityCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    funding_type: FundingType
    provider: str = Field(min_length=1)
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    currency: str = "ZAR"
    min_compliance_score: int = 0
    required_bbbee_level: Optional[str] = None
    application_deadline: date
    status: str = "identified"
    source_url: Optional[HttpUrl] = None
    tenant_id: Optional[str] = None

# ── Regulatory (Tax, H&S, CIPC, Bylaw, BBBEE) Schemas ─────────────────

class TaxType(str):
    vat = "vat"
    paye = "paye"
    uif = "uif"
    sdl = "sdl"
    income_tax = "income_tax"
    provisional_tax = "provisional_tax"
    customs = "customs"
    excise = "excise"

class TaxReturnStatus(str):
    pending = "pending"
    submitted = "submitted"
    assessed = "assessed"
    paid = "paid"
    overdue = "overdue"
    disputed = "disputed"

class TaxReturnCreate(BaseModel):
    tax_type: TaxType
    period_start: date
    period_end: date
    amount_due: Optional[Decimal] = None
    amount_paid: Optional[Decimal] = None
    status: TaxReturnStatus = TaxReturnStatus.pending
    reference_number: Optional[str] = None
    tenant_id: Optional[str] = None

class HsIncidentCreate(BaseModel):
    incident_type: str
    description: str
    severity: str
    location: Optional[str] = None
    reported_by: str
    status: str = "open"
    tenant_id: Optional[str] = None

# ── HR Operations Schemas ─────────────────────────────────────────────

class LeaveType(str):
    annual = "annual"
    sick = "sick"
    maternity = "maternity"
    paternity = "paternity"
    study = "study"
    unpaid = "unpaid"

class LeaveRequestCreate(BaseModel):
    employee_id: str
    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: Optional[str] = None
    status: str = "pending"
    tenant_id: Optional[str] = None

# ── Operations Schemas ────────────────────────────────────────────────

class DrPlanCreate(BaseModel):
    name: str
    description: Optional[str] = None
    rto_hours: int
    rpo_hours: int
    status: str = "draft"
    tenant_id: Optional[str] = None

# ── Pagination ────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def create(cls, items: List[Any], total: int, page: int, page_size: int) -> "PaginatedResponse":
        pages = max(1, (total + page_size - 1) // page_size)
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)