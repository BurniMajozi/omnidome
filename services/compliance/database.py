"""
OmniDome Compliance Service v2 — Database Models
Covers: Tax, H&S, CIPC, Bylaw, BBBEE, Leave, Vehicles, Foreign Workers,
        Travel, DR/BCP, Document Understanding, e-Services Gateway,
        Compliance Scoring, Contract Management, SLA, ICASA, POPI, RICA,
        Funding Opportunities
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, Float, ForeignKey,
    Index, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


# ── Enums ──────────────────────────────────────────────────────────────

class ContractType(enum.Enum):
    fno = "fno"
    supplier = "supplier"
    customer = "customer"
    employee = "employee"
    partner = "partner"
    service_level = "service_level"
    interconnect = "interconnect"
    infrastructure = "infrastructure"
    maintenance = "maintenance"


class ContractStatus(enum.Enum):
    draft = "draft"
    active = "active"
    expired = "expired"
    terminated = "terminated"
    suspended = "suspended"


class TaxType(enum.Enum):
    vat = "vat"
    paye = "paye"
    uif = "uif"
    sdl = "sdl"
    income_tax = "income_tax"
    provisional_tax = "provisional_tax"
    customs = "customs"
    excise = "excise"


class TaxReturnStatus(enum.Enum):
    pending = "pending"
    submitted = "submitted"
    assessed = "assessed"
    paid = "paid"
    overdue = "overdue"
    disputed = "disputed"


class HsIncidentType(enum.Enum):
    injury = "injury"
    illness = "illness"
    near_miss = "near_miss"
    fatality = "fatality"
    property_damage = "property_damage"
    environmental = "environmental"


class HsSeverity(enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class BbbeeLevel(enum.Enum):
    level_1 = "level_1"
    level_2 = "level_2"
    level_3 = "level_3"
    level_4 = "level_4"
    level_5 = "level_5"
    level_6 = "level_6"
    level_7 = "level_7"
    level_8 = "level_8"
    non_compliant = "non_compliant"


class LeaveType(enum.Enum):
    annual = "annual"
    sick = "sick"
    family_responsibility = "family_responsibility"
    maternity = "maternity"
    parental = "parental"
    study = "study"
    unpaid = "unpaid"


class LeaveStatus(enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"
    taken = "taken"


class VehicleStatus(enum.Enum):
    active = "active"
    suspended = "suspended"
    scrapped = "scrapped"
    sold = "sold"


class PermitType(enum.Enum):
    general_work = "general_work"
    critical_skills = "critical_skills"
    intra_company = "intra_company"
    corporate = "corporate"
    study = "study"
    spousal = "spousal"
    refugee = "refugee"


class PermitStatus(enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
    revoked = "revoked"


class VisaType(enum.Enum):
    tourist = "tourist"
    business = "business"
    transit = "transit"
    diplomatic = "diplomatic"
    work = "work"
    study = "study"


class VisaStatus(enum.Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


class DrBcpStatus(enum.Enum):
    draft = "draft"
    in_review = "in_review"
    approved = "approved"
    tested = "tested"
    failed = "failed"
    archived = "archived"


class ComplianceCategory(enum.Enum):
    tax = "tax"
    health_safety = "health_safety"
    cipc = "cipc"
    bylaw = "bylaw"
    bbbee = "bbbee"
    leave = "leave"
    vehicle = "vehicle"
    foreign_worker = "foreign_worker"
    travel = "travel"
    dr_bcp = "dr_bcp"
    contract = "contract"
    sla = "sla"
    icasa = "icasa"
    popi = "popi"
    rica = "rica"


class ComplianceStatus(enum.Enum):
    compliant = "compliant"
    non_compliant = "non_compliant"
    at_risk = "at_risk"
    pending_review = "pending_review"
    exempt = "exempt"


class EservicePlatform(enum.Enum):
    sars_efiling = "sars_efiling"
    sars_easyfile = "sars_easyfile"
    cipc = "cipc"
    dti = "dti"
    eservices_gov = "eservices_gov"
    dol = "dol"
    dha = "dha"
    natis = "natis"
    bbbee_commission = "bbbee_commission"
    municipal = "municipal"


class EserviceSubmissionStatus(enum.Enum):
    draft = "draft"
    submitted = "submitted"
    acknowledged = "acknowledged"
    approved = "approved"
    rejected = "rejected"
    error = "error"


class DocumentType(enum.Enum):
    contract = "contract"
    tax_return = "tax_return"
    hs_report = "hs_report"
    cipc_filing = "cipc_filing"
    bbbee_certificate = "bbbee_certificate"
    permit = "permit"
    visa = "visa"
    dr_plan = "dr_plan"
    bcp_plan = "bcp_plan"
    financial_statement = "financial_statement"
    invoice = "invoice"
    policy = "policy"
    other = "other"


# ── 1. Contract Management ─────────────────────────────────────────────

class Contract(Base):
    __tablename__ = "compliance_contracts"
    __table_args__ = (
        Index("ix_contract_type_status", "contract_type", "status"),
        Index("ix_contract_expiry", "expiry_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    contract_number = Column(String(100), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    contract_type = Column(Enum(ContractType), nullable=False)
    status = Column(Enum(ContractStatus), default=ContractStatus.draft, nullable=False)

    counterparty_name = Column(String(300), nullable=False)
    counterparty_registration = Column(String(100))
    counterparty_contact = Column(String(200))
    counterparty_email = Column(String(200))

    effective_date = Column(Date, nullable=False)
    expiry_date = Column(Date)
    renewal_date = Column(Date)
    auto_renew = Column(Boolean, default=False)
    renewal_notice_days = Column(Integer, default=30)

    value_zar = Column(Numeric(15, 2))
    payment_terms = Column(String(200))
    currency = Column(String(3), default="ZAR")

    compliance_score = Column(Float, default=0.0)
    risk_rating = Column(String(20), default="medium")

    parent_contract_id = Column(Integer, ForeignKey("compliance_contracts.id"))
    parent = relationship("Contract", remote_side=[id], backref="amendments")

    notes = Column(Text)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)

    slas = relationship("ContractSLA", back_populates="contract", cascade="all, delete-orphan")
    documents = relationship("ComplianceDocument", back_populates="contract", cascade="all, delete-orphan")
    audit_logs = relationship("ContractAuditLog", back_populates="contract", cascade="all, delete-orphan")
    icasa_submissions = relationship("IcasaSubmission", back_populates="contract")
    popi_requests = relationship("PopiDataAccessRequest", back_populates="contract")


# ── 2. Contract SLA ────────────────────────────────────────────────────

class ContractSLA(Base):
    __tablename__ = "compliance_contract_slas"
    __table_args__ = (Index("ix_contract_sla_contract", "contract_id"),)

    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("compliance_contracts.id"), nullable=False)
    name = Column(String(200), nullable=False)
    metric = Column(String(100), nullable=False)
    target_value = Column(Numeric(10, 4), nullable=False)
    unit = Column(String(50))
    measurement_frequency = Column(String(50), default="monthly")
    penalty_type = Column(String(50))
    penalty_amount = Column(Numeric(12, 2))
    effective_date = Column(Date, nullable=False)
    expiry_date = Column(Date)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)

    contract = relationship("Contract", back_populates="slas")
    measurements = relationship("SlaMeasurement", back_populates="sla", cascade="all, delete-orphan")


class SlaMeasurement(Base):
    __tablename__ = "compliance_sla_measurements"

    id = Column(Integer, primary_key=True, index=True)
    sla_id = Column(Integer, ForeignKey("compliance_contract_slas.id"), nullable=False)
    measured_value = Column(Numeric(10, 4), nullable=False)
    is_breach = Column(Boolean, default=False)
    breach_severity = Column(String(20))
    measured_at = Column(DateTime, default=func.now(), nullable=False)
    notes = Column(Text)
    tenant_id = Column(String(100), nullable=False, index=True)

    sla = relationship("ContractSLA", back_populates="measurements")


# ── 3. Tax Compliance ──────────────────────────────────────────────────

class TaxRegistration(Base):
    __tablename__ = "compliance_tax_registrations"
    __table_args__ = (Index("ix_tax_reg_tenant_type", "tenant_id", "tax_type"),)

    id = Column(Integer, primary_key=True, index=True)
    tax_type = Column(Enum(TaxType), nullable=False)
    registration_number = Column(String(100), nullable=False)
    status = Column(String(50), default="active")
    registered_date = Column(Date)
    last_filed = Column(Date)
    next_due = Column(Date)
    sars_reference = Column(String(100))
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


class TaxReturn(Base):
    __tablename__ = "compliance_tax_returns"
    __table_args__ = (
        Index("ix_tax_return_period", "tax_type", "period_start", "period_end"),
        Index("ix_tax_return_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tax_type = Column(Enum(TaxType), nullable=False)
    registration_id = Column(Integer, ForeignKey("compliance_tax_registrations.id"))
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    status = Column(Enum(TaxReturnStatus), default=TaxReturnStatus.pending, nullable=False)
    amount_payable = Column(Numeric(15, 2))
    amount_refund = Column(Numeric(15, 2))
    submission_date = Column(Date)
    sars_assessment_date = Column(Date)
    payment_date = Column(Date)
    sars_reference = Column(String(100))
    filing_reference = Column(String(100))
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 4. Health & Safety ─────────────────────────────────────────────────

class HsRiskAssessment(Base):
    __tablename__ = "compliance_hs_risk_assessments"
    __table_args__ = (Index("ix_hs_risk_status", "status"),)

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(300), nullable=False)
    location = Column(String(300))
    assessor = Column(String(200))
    assessment_date = Column(Date, nullable=False)
    review_date = Column(Date)
    status = Column(String(50), default="active")
    overall_risk_score = Column(Float)
    findings = Column(Text)
    recommendations = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


class HsIncident(Base):
    __tablename__ = "compliance_hs_incidents"
    __table_args__ = (
        Index("ix_hs_incident_date", "incident_date"),
        Index("ix_hs_incident_severity", "severity"),
    )

    id = Column(Integer, primary_key=True, index=True)
    incident_number = Column(String(100), unique=True, nullable=False)
    incident_type = Column(Enum(HsIncidentType), nullable=False)
    severity = Column(Enum(HsSeverity), nullable=False)
    incident_date = Column(DateTime, nullable=False)
    reported_date = Column(DateTime, default=func.now())
    location = Column(String(300))
    description = Column(Text, nullable=False)
    root_cause = Column(Text)
    corrective_action = Column(Text)
    preventive_action = Column(Text)
    persons_involved = Column(Text)
    coida_reported = Column(Boolean, default=False)
    coida_reference = Column(String(100))
    status = Column(String(50), default="open")
    closed_date = Column(DateTime)
    risk_assessment_id = Column(Integer, ForeignKey("compliance_hs_risk_assessments.id"))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 5. CIPC Compliance ─────────────────────────────────────────────────

class CipcFiling(Base):
    __tablename__ = "compliance_cipc_filings"
    __table_args__ = (
        Index("ix_cipc_filing_year", "financial_year_end"),
        Index("ix_cipc_filing_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    filing_type = Column(String(100), nullable=False)
    financial_year_end = Column(Date, nullable=False)
    status = Column(String(50), default="pending")
    due_date = Column(Date, nullable=False)
    filed_date = Column(Date)
    cipc_reference = Column(String(100))
    fee_amount = Column(Numeric(12, 2))
    fee_paid = Column(Boolean, default=False)
    confirmation_number = Column(String(100))
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 6. Bylaw Compliance ────────────────────────────────────────────────

class BylawObligation(Base):
    __tablename__ = "compliance_bylaw_obligations"
    __table_args__ = (
        Index("ix_bylaw_municipality", "municipality"),
        Index("ix_bylaw_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    municipality = Column(String(200), nullable=False)
    bylaw_reference = Column(String(200), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    category = Column(String(100))
    status = Column(Enum(ComplianceStatus), default=ComplianceStatus.pending_review)
    compliance_date = Column(Date)
    next_review_date = Column(Date)
    responsible_person = Column(String(200))
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 7. BBBEE Compliance ────────────────────────────────────────────────

class BbbeeScorecard(Base):
    __tablename__ = "compliance_bbbee_scorecards"
    __table_args__ = (
        Index("ix_bbbee_scorecard_year", "financial_year"),
        Index("ix_bbbee_scorecard_level", "overall_level"),
    )

    id = Column(Integer, primary_key=True, index=True)
    financial_year = Column(String(20), nullable=False)
    overall_level = Column(Enum(BbbeeLevel), nullable=False)
    overall_score = Column(Numeric(6, 2), nullable=False)

    ownership_score = Column(Numeric(6, 2), default=0)
    management_control_score = Column(Numeric(6, 2), default=0)
    skills_development_score = Column(Numeric(6, 2), default=0)
    enterprise_supplier_dev_score = Column(Numeric(6, 2), default=0)
    socio_economic_dev_score = Column(Numeric(6, 2), default=0)

    black_ownership_pct = Column(Numeric(5, 2))
    black_female_ownership_pct = Column(Numeric(5, 2))
    black_youth_ownership_pct = Column(Numeric(5, 2))
    black_disabled_ownership_pct = Column(Numeric(5, 2))

    certificate_number = Column(String(100))
    certificate_issue_date = Column(Date)
    certificate_expiry_date = Column(Date)
    verification_agency = Column(String(200))
    verification_agency_reference = Column(String(100))
    is_verified = Column(Boolean, default=False)
    status = Column(String(50), default="draft")
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 8. Leave Management ────────────────────────────────────────────────

class LeaveApplication(Base):
    __tablename__ = "compliance_leave_applications"
    __table_args__ = (
        Index("ix_leave_employee", "employee_id"),
        Index("ix_leave_status", "status"),
        Index("ix_leave_dates", "start_date", "end_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(100), nullable=False, index=True)
    employee_name = Column(String(200), nullable=False)
    leave_type = Column(Enum(LeaveType), nullable=False)
    status = Column(Enum(LeaveStatus), default=LeaveStatus.pending, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    days_requested = Column(Numeric(5, 1), nullable=False)
    days_approved = Column(Numeric(5, 1))
    reason = Column(Text)
    approver_id = Column(String(100))
    approver_name = Column(String(200))
    approved_date = Column(DateTime)
    rejection_reason = Column(Text)
    half_day = Column(Boolean, default=False)
    half_day_am = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


class LeaveBalance(Base):
    __tablename__ = "compliance_leave_balances"
    __table_args__ = (
        UniqueConstraint("employee_id", "leave_type", "year", name="uq_leave_balance"),
    )

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(100), nullable=False, index=True)
    leave_type = Column(Enum(LeaveType), nullable=False)
    year = Column(Integer, nullable=False)
    entitlement_days = Column(Numeric(5, 1), nullable=False)
    carried_over_days = Column(Numeric(5, 1), default=0)
    taken_days = Column(Numeric(5, 1), default=0)
    pending_days = Column(Numeric(5, 1), default=0)
    available_days = Column(Numeric(5, 1), default=0)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 9. Vehicle Registration ────────────────────────────────────────────

class VehicleRegistration(Base):
    __tablename__ = "compliance_vehicle_registrations"
    __table_args__ = (
        Index("ix_vehicle_reg_number", "registration_number"),
        Index("ix_vehicle_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    registration_number = Column(String(50), unique=True, nullable=False)
    vin = Column(String(50))
    engine_number = Column(String(50))
    make = Column(String(100))
    model = Column(String(100))
    year = Column(Integer)
    color = Column(String(50))
    vehicle_type = Column(String(50))
    status = Column(Enum(VehicleStatus), default=VehicleStatus.active)
    license_expiry = Column(Date)
    license_renewed_date = Column(Date)
    roadworthy_expiry = Column(Date)
    insurance_expiry = Column(Date)
    insurance_provider = Column(String(200))
    assigned_driver = Column(String(200))
    assigned_employee_id = Column(String(100))
    natis_reference = Column(String(100))
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 10. Foreign Worker Permits ─────────────────────────────────────────

class ForeignWorkerPermit(Base):
    __tablename__ = "compliance_foreign_worker_permits"
    __table_args__ = (
        Index("ix_fwp_employee", "employee_id"),
        Index("ix_fwp_status", "status"),
        Index("ix_fwp_expiry", "expiry_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(100), nullable=False, index=True)
    employee_name = Column(String(200), nullable=False)
    nationality = Column(String(100), nullable=False)
    passport_number = Column(String(100))
    permit_type = Column(Enum(PermitType), nullable=False)
    permit_number = Column(String(100))
    status = Column(Enum(PermitStatus), default=PermitStatus.pending)
    issue_date = Column(Date)
    expiry_date = Column(Date)
    dha_reference = Column(String(100))
    critical_skill_area = Column(String(200))
    job_title = Column(String(200))
    employer_name = Column(String(200))
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 11. Travel Readiness ───────────────────────────────────────────────

class TravelReadiness(Base):
    __tablename__ = "compliance_travel_readiness"
    __table_args__ = (
        Index("ix_travel_employee", "employee_id"),
        Index("ix_travel_destination", "destination_country"),
    )

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(100), nullable=False, index=True)
    employee_name = Column(String(200), nullable=False)
    destination_country = Column(String(100), nullable=False)
    destination_city = Column(String(100))
    purpose = Column(Text)
    departure_date = Column(Date)
    return_date = Column(Date)
    visa_type = Column(Enum(VisaType))
    visa_status = Column(Enum(VisaStatus), default=VisaStatus.not_started)
    visa_reference = Column(String(100))
    visa_expiry = Column(Date)
    passport_number = Column(String(100))
    passport_expiry = Column(Date)
    travel_insurance_provider = Column(String(200))
    travel_insurance_policy = Column(String(100))
    travel_insurance_expiry = Column(Date)
    vaccinations_required = Column(Text)
    vaccinations_completed = Column(Text)
    risk_assessment_done = Column(Boolean, default=False)
    emergency_contact = Column(String(200))
    overall_status = Column(String(50), default="pending")
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 12. DR/BCP ─────────────────────────────────────────────────────────

class DrBcpPlan(Base):
    __tablename__ = "compliance_dr_bcp_plans"
    __table_args__ = (
        Index("ix_dr_bcp_status", "status"),
        Index("ix_dr_bcp_type", "plan_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    plan_name = Column(String(300), nullable=False)
    plan_type = Column(String(50), nullable=False)
    status = Column(Enum(DrBcpStatus), default=DrBcpStatus.draft)
    version = Column(String(20), default="1.0")
    owner = Column(String(200))
    scope = Column(Text)
    objectives = Column(Text)
    risk_assessment = Column(Text)
    impact_analysis = Column(Text)
    recovery_strategy = Column(Text)
    rto_hours = Column(Numeric(6, 2))
    rpo_hours = Column(Numeric(6, 2))
    communication_plan = Column(Text)
    escalation_matrix = Column(Text)
    vendor_contacts = Column(Text)
    last_test_date = Column(Date)
    next_test_date = Column(Date)
    test_results = Column(Text)
    gaps_identified = Column(Text)
    remediation_plan = Column(Text)
    approved_by = Column(String(200))
    approved_date = Column(Date)
    review_frequency_months = Column(Integer, default=12)
    next_review_date = Column(Date)
    document_path = Column(String(500))
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


class DrBcpAssessment(Base):
    __tablename__ = "compliance_dr_bcp_assessments"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("compliance_dr_bcp_plans.id"), nullable=False)
    assessment_date = Column(Date, nullable=False)
    assessor = Column(String(200))
    readiness_score = Column(Float)
    infrastructure_score = Column(Float)
    data_protection_score = Column(Float)
    communication_score = Column(Float)
    staff_awareness_score = Column(Float)
    vendor_readiness_score = Column(Float)
    overall_rating = Column(String(20))
    findings = Column(Text)
    recommendations = Column(Text)
    action_items = Column(Text)
    next_assessment_date = Column(Date)
    created_at = Column(DateTime, default=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 13. Compliance Scoring & Obligations ───────────────────────────────

class ComplianceScore(Base):
    __tablename__ = "compliance_scores"
    __table_args__ = (Index("ix_cs_tenant_date", "tenant_id", "calculated_at"),)

    id = Column(Integer, primary_key=True, index=True)
    category = Column(Enum(ComplianceCategory), nullable=False)
    score = Column(Float, nullable=False)
    weight = Column(Float, default=1.0)
    status = Column(Enum(ComplianceStatus), nullable=False)
    issues_count = Column(Integer, default=0)
    critical_issues = Column(Integer, default=0)
    details = Column(Text)
    calculated_at = Column(DateTime, default=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


class ComplianceObligation(Base):
    __tablename__ = "compliance_obligations"
    __table_args__ = (
        Index("ix_obligation_category", "category"),
        Index("ix_obligation_due", "due_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    category = Column(Enum(ComplianceCategory), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    regulatory_reference = Column(String(300))
    frequency = Column(String(50))
    due_date = Column(Date)
    status = Column(Enum(ComplianceStatus), default=ComplianceStatus.pending_review)
    responsible_person = Column(String(200))
    responsible_department = Column(String(200))
    evidence_required = Column(Text)
    evidence_provided = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 14. e-Services Gateway ─────────────────────────────────────────────

class EserviceSubmission(Base):
    __tablename__ = "compliance_eservice_submissions"
    __table_args__ = (
        Index("ix_eservice_platform", "platform"),
        Index("ix_eservice_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(Enum(EservicePlatform), nullable=False)
    form_name = Column(String(300), nullable=False)
    form_reference = Column(String(200))
    status = Column(Enum(EserviceSubmissionStatus), default=EserviceSubmissionStatus.draft)
    submission_data = Column(Text)
    response_data = Column(Text)
    submission_date = Column(DateTime)
    response_date = Column(DateTime)
    reference_number = Column(String(200))
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    obligation_id = Column(Integer, ForeignKey("compliance_obligations.id"))
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 15. Document Understanding ─────────────────────────────────────────

class ComplianceDocument(Base):
    __tablename__ = "compliance_documents"
    __table_args__ = (
        Index("ix_compliance_doc_type", "document_type"),
        Index("ix_compliance_doc_contract", "contract_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    document_type = Column(Enum(DocumentType), nullable=False)
    file_path = Column(String(500))
    file_size = Column(Integer)
    mime_type = Column(String(100))
    contract_id = Column(Integer, ForeignKey("compliance_contracts.id"))
    ocr_text = Column(Text)
    extracted_data = Column(Text)
    financial_summary = Column(Text)
    tags = Column(String(500))
    version = Column(String(20), default="1.0")
    is_confidential = Column(Boolean, default=False)
    uploaded_by = Column(String(200))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)

    contract = relationship("Contract", back_populates="documents")


# ── 16. Financial Scenario Planning ────────────────────────────────────

class FinancialScenario(Base):
    __tablename__ = "compliance_financial_scenarios"
    __table_args__ = (Index("ix_fs_type", "scenario_type"),)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(300), nullable=False)
    scenario_type = Column(String(100), nullable=False)
    description = Column(Text)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    assumptions = Column(Text)
    revenue_projections = Column(Text)
    expense_projections = Column(Text)
    cash_flow_projections = Column(Text)
    compliance_cost_impact = Column(Numeric(15, 2))
    funding_eligibility = Column(Text)
    funding_opportunities = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 17. ICASA ──────────────────────────────────────────────────────────

class IcasaSubmission(Base):
    __tablename__ = "compliance_icasa_submissions"
    __table_args__ = (
        Index("ix_icasa_sub_type", "submission_type"),
        Index("ix_icasa_sub_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    submission_type = Column(String(100), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    contract_id = Column(Integer, ForeignKey("compliance_contracts.id"))
    status = Column(String(50), default="draft")
    icasa_reference = Column(String(100))
    submission_date = Column(Date)
    response_date = Column(Date)
    approval_date = Column(Date)
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)

    contract = relationship("Contract", back_populates="icasa_submissions")


class IcasaScrapeJob(Base):
    __tablename__ = "compliance_icasa_scrape_jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_name = Column(String(200), nullable=False)
    source_url = Column(String(500), nullable=False)
    status = Column(String(50), default="pending")
    last_run = Column(DateTime)
    next_run = Column(DateTime)
    changes_detected = Column(Integer, default=0)
    last_changes = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


class IcasaRegulationChange(Base):
    __tablename__ = "compliance_icasa_regulation_changes"

    id = Column(Integer, primary_key=True, index=True)
    scrape_job_id = Column(Integer, ForeignKey("compliance_icasa_scrape_jobs.id"))
    title = Column(String(500), nullable=False)
    description = Column(Text)
    regulation_reference = Column(String(200))
    change_type = Column(String(100))
    effective_date = Column(Date)
    impact_level = Column(String(20))
    impact_assessment = Column(Text)
    action_required = Column(Text)
    action_taken = Column(Text)
    status = Column(String(50), default="identified")
    detected_at = Column(DateTime, default=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 18. POPI Act ───────────────────────────────────────────────────────

class PopiDataAccessRequest(Base):
    __tablename__ = "compliance_popi_dsar"
    __table_args__ = (
        Index("ix_popi_dsar_status", "status"),
        Index("ix_popi_dsar_due", "due_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    request_reference = Column(String(100), unique=True, nullable=False)
    data_subject_name = Column(String(200), nullable=False)
    data_subject_email = Column(String(200))
    data_subject_phone = Column(String(50))
    request_type = Column(String(100), nullable=False)
    description = Column(Text)
    contract_id = Column(Integer, ForeignKey("compliance_contracts.id"))
    status = Column(String(50), default="received")
    received_date = Column(DateTime, default=func.now())
    due_date = Column(DateTime, nullable=False)
    completed_date = Column(DateTime)
    response_sent = Column(Boolean, default=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)

    contract = relationship("Contract", back_populates="popi_requests")


class PopiAnonymizationLog(Base):
    __tablename__ = "compliance_popi_anonymization_logs"

    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String(100), nullable=False)
    record_id = Column(Integer, nullable=False)
    field_name = Column(String(100), nullable=False)
    anonymization_method = Column(String(100))
    reason = Column(Text)
    performed_at = Column(DateTime, default=func.now())
    performed_by = Column(String(200))
    tenant_id = Column(String(100), nullable=False, index=True)


class PopiConsentRecord(Base):
    __tablename__ = "compliance_popi_consent_records"

    id = Column(Integer, primary_key=True, index=True)
    data_subject_id = Column(String(100), nullable=False)
    data_subject_name = Column(String(200))
    purpose = Column(Text, nullable=False)
    consent_given = Column(Boolean, nullable=False)
    consent_date = Column(DateTime, nullable=False)
    consent_method = Column(String(100))
    withdrawal_date = Column(DateTime)
    expiry_date = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 19. RICA ───────────────────────────────────────────────────────────

class RicaVerification(Base):
    __tablename__ = "compliance_rica_verifications"
    __table_args__ = (
        Index("ix_rica_id_hash", "id_number_hash"),
        Index("ix_rica_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    id_number_hash = Column(String(128), nullable=False, index=True)
    id_type = Column(String(50), nullable=False)
    full_name = Column(String(200))
    status = Column(String(50), default="pending")
    verification_date = Column(DateTime)
    expiry_date = Column(DateTime)
    source = Column(String(100))
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 20. Contract Audit Log ─────────────────────────────────────────────

class ContractAuditLog(Base):
    __tablename__ = "compliance_contract_audit_logs"
    __table_args__ = (
        Index("ix_audit_contract", "contract_id"),
        Index("ix_audit_created", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("compliance_contracts.id"), nullable=False)
    action = Column(String(100), nullable=False)
    field_name = Column(String(100))
    old_value = Column(Text)
    new_value = Column(Text)
    performed_by = Column(String(200))
    performed_at = Column(DateTime, default=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)

    contract = relationship("Contract", back_populates="audit_logs")


# ── 21. Breach Register ────────────────────────────────────────────────

class BreachRegister(Base):
    __tablename__ = "compliance_breach_register"
    __table_args__ = (
        Index("ix_breach_severity", "severity"),
        Index("ix_breach_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    breach_number = Column(String(100), unique=True, nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(Enum(ComplianceCategory), nullable=False)
    severity = Column(String(20), nullable=False)
    status = Column(String(50), default="identified")
    identified_date = Column(DateTime, default=func.now())
    reported_date = Column(DateTime)
    resolved_date = Column(DateTime)
    root_cause = Column(Text)
    corrective_action = Column(Text)
    icasa_notified = Column(Boolean, default=False)
    icasa_notification_date = Column(DateTime)
    icasa_reference = Column(String(100))
    popi_commission_notified = Column(Boolean, default=False)
    popi_notification_date = Column(DateTime)
    financial_impact = Column(Numeric(15, 2))
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)


# ── 22. Funding Opportunities ──────────────────────────────────────────

class FundingOpportunity(Base):
    __tablename__ = "compliance_funding_opportunities"
    __table_args__ = (
        Index("ix_funding_status", "status"),
        Index("ix_funding_deadline", "application_deadline"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(500), nullable=False)
    description = Column(Text)
    source = Column(String(300))
    source_url = Column(String(500))
    funding_type = Column(String(100))
    min_compliance_score = Column(Float)
    max_funding_amount = Column(Numeric(15, 2))
    currency = Column(String(3), default="ZAR")
    eligibility_criteria = Column(Text)
    required_bbbee_level = Column(Enum(BbbeeLevel))
    application_deadline = Column(Date)
    status = Column(String(50), default="identified")
    applied_date = Column(Date)
    approval_date = Column(Date)
    amount_awarded = Column(Numeric(15, 2))
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tenant_id = Column(String(100), nullable=False, index=True)
