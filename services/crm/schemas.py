"""Pydantic v2 schemas for the CRM service."""

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from services.crm.normalize import normalize_status

# Fields a client may never set through a create/update body: they belong to the server
# (tenant scoping, ownership, audit timestamps, lifecycle / conversion state).
PROTECTED_FIELDS = frozenset({
    "id", "tenant_id", "owner_id", "created_at", "updated_at", "account_number", "rica_verified",
    "converted_customer_id", "converted_at", "lifecycle_stage", "current_stage", "lifecycle",
    "phone_normalized", "company_id",
})


class _NoMassAssignment(BaseModel):
    """Rejects (422) bodies that try to set server-owned fields; other unknown keys are ignored."""

    @model_validator(mode="before")
    @classmethod
    def _reject_protected(cls, data):
        if isinstance(data, dict):
            bad = sorted(PROTECTED_FIELDS.intersection(data.keys()))
            if bad:
                raise ValueError(f"fields not settable by clients: {', '.join(bad)}")
        return data


# ---------------------------------------------------------------------------
# SA ID validation helper
# ---------------------------------------------------------------------------

def validate_sa_id_number(value: Optional[str]) -> Optional[str]:
    """Validate a South African 13-digit ID number using Luhn check."""
    if value is None:
        return value
    cleaned = value.strip()
    if not re.fullmatch(r"\d{13}", cleaned):
        raise ValueError("SA ID number must be exactly 13 digits")

    digits = [int(d) for d in cleaned]
    # Luhn algorithm on the first 12 digits; 13th is the check digit
    odd_sum = sum(digits[i] for i in range(0, 12, 2))
    even_concat = "".join(str(digits[i]) for i in range(1, 12, 2))
    even_doubled = int(even_concat) * 2
    even_sum = sum(int(d) for d in str(even_doubled))
    total = odd_sum + even_sum
    check = (10 - (total % 10)) % 10
    if check != digits[12]:
        raise ValueError("SA ID number failed Luhn check")
    return cleaned


# ---------------------------------------------------------------------------
# Province enum
# ---------------------------------------------------------------------------

SA_PROVINCE_CHOICES = [
    "eastern_cape",
    "free_state",
    "gauteng",
    "kwazulu_natal",
    "limpopo",
    "mpumalanga",
    "north_west",
    "northern_cape",
    "western_cape",
]


CUSTOMER_STATUS_CHOICES = ["active", "suspended", "churned"]
SEGMENT_FIELDS = frozenset({"province", "status", "email"})
SEGMENT_OPERATORS = frozenset({"eq", "ne", "gt", "gte", "lt", "lte", "in", "contains"})


# ---------------------------------------------------------------------------
# Customer schemas
# ---------------------------------------------------------------------------

class CustomerCreate(_NoMassAssignment):
    first_name: str = Field(..., min_length=1, max_length=120)
    last_name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    id_number: Optional[str] = Field(None, max_length=13)
    address: Optional[str] = None
    province: Optional[str] = None

    @field_validator("id_number")
    @classmethod
    def check_sa_id(cls, v: Optional[str]) -> Optional[str]:
        return validate_sa_id_number(v)

    @field_validator("province")
    @classmethod
    def check_province(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SA_PROVINCE_CHOICES:
            raise ValueError(f"province must be one of {SA_PROVINCE_CHOICES}")
        return v


class CustomerUpdate(_NoMassAssignment):
    first_name: Optional[str] = Field(None, min_length=1, max_length=120)
    last_name: Optional[str] = Field(None, min_length=1, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    id_number: Optional[str] = Field(None, max_length=13)
    address: Optional[str] = None
    province: Optional[str] = None
    status: Optional[str] = None

    @field_validator("id_number")
    @classmethod
    def check_sa_id(cls, v: Optional[str]) -> Optional[str]:
        return validate_sa_id_number(v)

    @field_validator("province")
    @classmethod
    def check_province(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SA_PROVINCE_CHOICES:
            raise ValueError(f"province must be one of {SA_PROVINCE_CHOICES}")
        return v

    @field_validator("status")
    @classmethod
    def check_status(cls, v: Optional[str]) -> Optional[str]:
        allowed = {"active", "suspended", "churned"}
        if v is not None and v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    id_number: Optional[str] = None
    address: Optional[str] = None
    province: Optional[str] = None
    account_number: Optional[str] = None
    status: str
    rica_verified: bool
    created_at: datetime
    updated_at: datetime


class Customer360(CustomerRead):
    """Extended customer view aggregating cross-service data."""
    # null = that upstream service failed or timed out (see section_errors); [] = it answered "none".
    services: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    billing: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    support: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    network: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    notes_count: int = 0
    lifecycle_data: Optional[Dict[str, Any]] = None
    partial: bool = False
    section_errors: Dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Note / Tag schemas
# ---------------------------------------------------------------------------

class NoteCreate(BaseModel):
    content: str = Field(..., min_length=1)


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    author_id: uuid.UUID
    content: str
    created_at: datetime


class TagCreate(BaseModel):
    tag: str = Field(..., min_length=1, max_length=60)


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    tag: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Lead schemas
# ---------------------------------------------------------------------------

class LeadCreate(_NoMassAssignment):
    source: Optional[str] = Field(None, max_length=100)
    first_name: str = Field(..., min_length=1, max_length=120)
    last_name: str = Field(..., min_length=1, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    coverage_area: Optional[str] = Field(None, max_length=255)
    interested_package: Optional[str] = Field(None, max_length=120)


class LeadUpdate(_NoMassAssignment):
    status: Optional[str] = None
    assigned_to: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    coverage_area: Optional[str] = Field(None, max_length=255)
    interested_package: Optional[str] = Field(None, max_length=120)

    @field_validator("status")
    @classmethod
    def check_status(cls, v: Optional[str]) -> Optional[str]:
        return normalize_status(v)  # upper-case, validated against the sales vocabulary


class LeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    source: Optional[str] = None
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    coverage_area: Optional[str] = None
    interested_package: Optional[str] = None
    status: str
    assigned_to: Optional[uuid.UUID] = None
    coverage_check_result: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    converted_customer_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Segment schemas
# ---------------------------------------------------------------------------

class SegmentRule(BaseModel):
    """A single segment filter rule."""
    field: str  # one of SEGMENT_FIELDS (the columns the segment engine can filter on)
    operator: str  # "eq", "ne", "gt", "gte", "lt", "lte", "in", "contains"
    value: Any

    @model_validator(mode="after")
    def _check_rule(self):
        if self.field not in SEGMENT_FIELDS:
            raise ValueError(f"field must be one of {sorted(SEGMENT_FIELDS)}")
        if self.operator not in SEGMENT_OPERATORS:
            raise ValueError(f"operator must be one of {sorted(SEGMENT_OPERATORS)}")
        scalar = (str, int, float)
        if self.operator == "in":
            if not isinstance(self.value, list) or not 1 <= len(self.value) <= 100                     or not all(isinstance(v, scalar) and not isinstance(v, bool) for v in self.value):
                raise ValueError("'in' needs a list of 1-100 strings/numbers")
            values = self.value
        else:
            if not isinstance(self.value, scalar) or isinstance(self.value, bool):
                raise ValueError("value must be a string or number")
            values = [self.value]
        if self.operator == "contains" and (not isinstance(self.value, str) or not 1 <= len(self.value) <= 100):
            raise ValueError("'contains' needs a string of 1-100 characters")
        if any(isinstance(v, str) and len(v) > 255 for v in values):
            raise ValueError("value too long")
        enum_values = {"status": CUSTOMER_STATUS_CHOICES, "province": SA_PROVINCE_CHOICES}.get(self.field)
        if enum_values and self.operator in {"eq", "ne", "in"} and any(v not in enum_values for v in values):
            raise ValueError(f"{self.field} must be one of {enum_values}")
        return self


class SegmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    rules: List[SegmentRule] = Field(..., min_length=1)
    auto_refresh: bool = False


class SegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: Optional[str] = None
    rules: Any
    auto_refresh: bool
    customer_count: int = 0
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Timeline schemas
# ---------------------------------------------------------------------------

class TimelineEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    summary: str
    details: Optional[Dict[str, Any]] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Pagination wrapper
# ---------------------------------------------------------------------------

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int


# ---------------------------------------------------------------------------
# Customer 360 View Schemas — Four Tabs
# ---------------------------------------------------------------------------

# ── Tab 1: Customer Details ──

class PropertyAddress(BaseModel):
    id: uuid.UUID
    name: Optional[str] = None
    line1: str
    line2: Optional[str] = None
    city: str
    province: Optional[str] = None
    postal_code: str
    property_type: str
    is_active: bool


class PropertyAccountInfo(BaseModel):
    id: uuid.UUID
    account_number: str
    relationship_type: str
    is_primary: bool
    is_active: bool
    activated_at: Optional[datetime] = None
    company_id: Optional[uuid.UUID] = None


class ServiceAddressInfo(BaseModel):
    id: uuid.UUID
    address_type: str
    line1: str
    city: str
    postal_code: str
    is_primary: bool


class BillingAccountInfo(BaseModel):
    id: uuid.UUID
    account_number: str
    account_name: Optional[str] = None
    billing_email: Optional[str] = None
    payment_terms: Optional[str] = None
    credit_limit_zar: Optional[Decimal] = None
    status: str
    dunning_stage: Optional[str] = None


class SubscriptionInfo(BaseModel):
    id: uuid.UUID
    plan: str
    segment: Optional[str] = None
    status: str
    billing_interval: str
    base_price_zar: Decimal
    property_id: Optional[uuid.UUID] = None


class PaymentMethodInfo(BaseModel):
    id: uuid.UUID
    method_type: str
    last_four: Optional[str] = None
    card_brand: Optional[str] = None
    is_default: bool
    is_active: bool


class HandoverHistoryItem(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    from_customer_id: uuid.UUID
    to_customer_id: uuid.UUID
    status: str
    trigger: str
    completed_at: Optional[datetime] = None


class CustomerDetailsResponse(BaseModel):
    """Tab 1: Customer Details — identity, properties, billing, subscriptions."""
    customer: CustomerRead
    company: Optional[Dict[str, Any]] = None
    # A section that could not be read is null and named in section_errors (partial=true).
    properties: Optional[List[PropertyAddress]] = Field(default_factory=list)
    property_accounts: Optional[List[PropertyAccountInfo]] = Field(default_factory=list)
    service_addresses: Optional[List[ServiceAddressInfo]] = Field(default_factory=list)
    billing_account: Optional[BillingAccountInfo] = None
    subscriptions: Optional[List[SubscriptionInfo]] = Field(default_factory=list)
    payment_methods: Optional[List[PaymentMethodInfo]] = Field(default_factory=list)
    handover_history: Optional[List[HandoverHistoryItem]] = Field(default_factory=list)
    partial: bool = False
    section_errors: Dict[str, str] = Field(default_factory=dict)


# ── Tab 2: Customer Experience (CX) ──

class OrderSummary(BaseModel):
    id: uuid.UUID
    order_number: str
    status: str
    total_zar: Decimal
    payment_status: str
    confirmed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class DeliverySummary(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    courier: Optional[str] = None
    tracking_number: Optional[str] = None
    status: Optional[str] = None
    scheduled_date: Optional[datetime] = None
    delivered_at: Optional[datetime] = None


class TechnicianVisitSummary(BaseModel):
    id: uuid.UUID
    visit_type: str
    status: str
    scheduled_date: datetime
    technician_name: Optional[str] = None
    customer_rating: Optional[int] = None


class SupportTicketSummary(BaseModel):
    id: uuid.UUID
    subject: str
    priority: str
    status: str
    category: Optional[str] = None
    is_fcr: bool
    created_at: datetime
    resolved_at: Optional[datetime] = None


class ActivityTimelineItem(BaseModel):
    id: uuid.UUID
    event_type: str
    event_category: str
    summary: str
    source_service: str
    created_at: datetime


class CXSummary(BaseModel):
    total_orders: Optional[int] = 0
    open_tickets: Optional[int] = 0
    avg_technician_rating: Optional[float] = None
    last_interaction: Optional[datetime] = None
    lifecycle_stage: Optional[str] = None


class CXResponse(BaseModel):
    """Tab 2: Customer Experience — orders, deliveries, visits, tickets, timeline."""
    orders: Optional[List[OrderSummary]] = Field(default_factory=list)
    deliveries: Optional[List[DeliverySummary]] = Field(default_factory=list)
    technician_visits: Optional[List[TechnicianVisitSummary]] = Field(default_factory=list)
    support_tickets: Optional[List[SupportTicketSummary]] = Field(default_factory=list)
    activity_timeline: Optional[List[ActivityTimelineItem]] = Field(default_factory=list)
    nps_score: Optional[int] = None
    cx_summary: CXSummary = Field(default_factory=CXSummary)
    partial: bool = False
    section_errors: Dict[str, str] = Field(default_factory=dict)


# ── Tab 3: CRM ──

class DealSummary(BaseModel):
    id: uuid.UUID
    name: str
    value_zar: Decimal
    status: str
    stage_name: Optional[str] = None
    probability: Optional[int] = None
    close_date: Optional[datetime] = None


class QuoteSummary(BaseModel):
    id: uuid.UUID
    total_monthly: Decimal
    total_once_off: Decimal
    term_months: int
    status: str
    valid_until: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None


class CommissionSummary(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    amount_zar: Decimal
    rate_percent: Optional[Decimal] = None
    status: str


class LifecycleInfo(BaseModel):
    current_stage: str
    health_score: int
    is_at_risk: bool
    churn_probability: Optional[Decimal] = None
    monthly_recurring_revenue: Decimal
    first_contact_at: Optional[datetime] = None
    converted_at: Optional[datetime] = None
    last_payment_at: Optional[datetime] = None


class CRMSummary(BaseModel):
    total_deals_value: Decimal = Decimal("0")
    active_deals: int = 0
    won_deals: int = 0
    lost_deals: int = 0
    quotes_sent: int = 0
    quotes_accepted: int = 0


class CRMResponse(BaseModel):
    """Tab 3: CRM — sales pipeline, deals, quotes, commissions, lifecycle."""
    lead: Optional[Dict[str, Any]] = None
    deals: Optional[List[DealSummary]] = Field(default_factory=list)
    quotes: Optional[List[QuoteSummary]] = Field(default_factory=list)
    commissions: Optional[List[CommissionSummary]] = Field(default_factory=list)
    segments: List[Dict[str, Any]] = Field(default_factory=list)
    tags: Optional[List[str]] = Field(default_factory=list)
    notes: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    lifecycle: Optional[LifecycleInfo] = None
    crm_summary: CRMSummary = Field(default_factory=CRMSummary)
    partial: bool = False
    section_errors: Dict[str, str] = Field(default_factory=dict)


# ── Tab 4: Customer Value Management (CVM) ──

class FinancialSummary(BaseModel):
    # None = not available (section failed / nothing to measure); never a made-up default.
    mrr: Optional[Decimal] = None
    arr: Optional[Decimal] = None
    ltv: Optional[Decimal] = None
    outstanding_balance: Optional[Decimal] = None
    payment_reliability_pct: Optional[float] = None
    total_invoices: Optional[int] = None
    paid_invoices: Optional[int] = None
    overdue_invoices: Optional[int] = None


class InvoiceSummary(BaseModel):
    id: uuid.UUID
    number: str
    status: str
    total_zar: Decimal
    amount_paid_zar: Decimal
    due_date: datetime
    created_at: datetime


class PaymentSummary(BaseModel):
    id: uuid.UUID
    amount_zar: Decimal
    method: str
    status: str
    created_at: datetime


class ChurnPredictionInfo(BaseModel):
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None
    churn_probability: Optional[float] = None
    nps_score: Optional[float] = None
    predicted_at: Optional[datetime] = None


class HealthInfo(BaseModel):
    score: Optional[int] = None
    is_at_risk: bool = False
    risk_reason: Optional[str] = None
    monthly_recurring_revenue: Decimal = Decimal("0")
    first_payment_at: Optional[datetime] = None
    last_payment_at: Optional[datetime] = None


class CVMSummary(BaseModel):
    customer_tier: str = "NOT_ASSESSED"
    value_segment: str = "NOT_ASSESSED"
    risk_segment: str = "UNKNOWN"
    recommended_action: Optional[str] = None


class CVMResponse(BaseModel):
    """Tab 4: Customer Value Management — financial, churn, health, usage."""
    financial_summary: Optional[FinancialSummary] = None
    invoices: Optional[List[InvoiceSummary]] = Field(default_factory=list)
    payments: Optional[List[PaymentSummary]] = Field(default_factory=list)
    churn_prediction: Optional[ChurnPredictionInfo] = None
    health: Optional[HealthInfo] = None
    usage_summary: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    cvm_summary: Optional[CVMSummary] = None
    partial: bool = False
    section_errors: Dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Company (B2B Account) schemas
# ---------------------------------------------------------------------------

class CompanyCreate(_NoMassAssignment):
    name: str = Field(..., min_length=1, max_length=255)
    registration_number: Optional[str] = Field(None, max_length=50)
    tax_id: Optional[str] = Field(None, max_length=50)
    industry: Optional[str] = Field(None, max_length=100)
    contact_person: Optional[str] = Field(None, max_length=200)
    email: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = None
    billing_email: Optional[str] = None
    payment_terms: Optional[str] = Field(None, max_length=50)
    credit_limit_zar: Optional[Decimal] = None
    notes: Optional[str] = None


class CompanyUpdate(_NoMassAssignment):
    name: Optional[str] = Field(None, max_length=255)
    registration_number: Optional[str] = None
    tax_id: Optional[str] = None
    industry: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    billing_email: Optional[str] = None
    payment_terms: Optional[str] = None
    credit_limit_zar: Optional[Decimal] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    registration_number: Optional[str] = None
    tax_id: Optional[str] = None
    industry: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    billing_email: Optional[str] = None
    payment_terms: Optional[str] = None
    credit_limit_zar: Optional[Decimal] = None
    is_active: bool = True
    notes: Optional[str] = None
    members_count: int = 0
    created_at: datetime
    updated_at: datetime

