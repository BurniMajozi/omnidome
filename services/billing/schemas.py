"""Pydantic v2 schemas for the Billing service."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


VAT_RATE = Decimal("0.15")  # South African VAT = 15%


# ---------------------------------------------------------------------------
# Line item (embedded in invoice JSONB)
# ---------------------------------------------------------------------------

class LineItem(BaseModel):
    description: str
    quantity: int = 1
    unit_price_zar: Decimal = Field(..., ge=0)
    total_zar: Optional[Decimal] = None

    def compute_total(self) -> Decimal:
        return self.unit_price_zar * self.quantity


# ---------------------------------------------------------------------------
# Invoice schemas
# ---------------------------------------------------------------------------

class InvoiceGenerateRequest(BaseModel):
    """Trigger batch invoice generation for a billing period."""
    billing_date: date = Field(default_factory=date.today)
    customer_ids: Optional[List[uuid.UUID]] = Field(
        None, description="Limit to specific customers; omit for all active customers"
    )


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    subscription_id: Optional[uuid.UUID] = None
    number: str
    status: str
    subtotal_zar: Decimal
    vat_zar: Decimal
    total_zar: Decimal
    amount_paid_zar: Decimal
    due_date: date
    billing_period_start: Optional[date] = None
    billing_period_end: Optional[date] = None
    line_items: Optional[List[Dict[str, Any]]] = None
    notes: Optional[str] = None
    credit_note_of: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class InvoiceSendRequest(BaseModel):
    channel: str = Field("email", pattern="^(email|sms|both)$")


class CreditNoteRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    line_items: Optional[List[LineItem]] = Field(
        None, description="Override line items; omit to clone original"
    )


# ---------------------------------------------------------------------------
# Payment schemas
# ---------------------------------------------------------------------------

class PaymentCreate(BaseModel):
    invoice_id: uuid.UUID
    amount_zar: Decimal = Field(..., gt=0)
    method: str
    reference: Optional[str] = None

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        allowed = {"manual", "eft", "card", "debit_order"}
        if v not in allowed:
            raise ValueError(f"method must be one of {allowed}")
        return v


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    invoice_id: uuid.UUID
    customer_id: uuid.UUID
    amount_zar: Decimal
    method: str
    reference: Optional[str] = None
    paystack_ref: Optional[str] = None
    status: str
    created_at: datetime


class PaystackInitializeRequest(BaseModel):
    invoice_id: uuid.UUID
    email: str
    amount_zar: Optional[Decimal] = Field(None, description="Defaults to outstanding balance")
    callback_url: Optional[str] = None


class PaystackInitializeResponse(BaseModel):
    authorization_url: str
    access_code: str
    reference: str


class PaystackVerifyResponse(BaseModel):
    reference: str
    status: str
    amount_zar: Decimal
    paid_at: Optional[datetime] = None
    channel: Optional[str] = None


# ---------------------------------------------------------------------------
# Collections / Dunning schemas
# ---------------------------------------------------------------------------

class CollectionsQueueItem(BaseModel):
    customer_id: uuid.UUID
    customer_name: Optional[str] = None
    total_overdue_zar: Decimal
    oldest_overdue_date: date
    days_overdue: int
    invoice_count: int
    dunning_stage: str


class ArrangementCreate(BaseModel):
    total_owed_zar: Decimal = Field(..., gt=0)
    installment_zar: Decimal = Field(..., gt=0)
    installments_count: int = Field(..., ge=2, le=24)
    first_due_date: date
    notes: Optional[str] = None


class ArrangementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    total_owed_zar: Decimal
    installment_zar: Decimal
    installments_count: int
    installments_paid: int
    status: str
    next_due_date: date
    notes: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Report schemas
# ---------------------------------------------------------------------------

class RevenueReportItem(BaseModel):
    period: str
    total_invoiced_zar: Decimal
    total_paid_zar: Decimal
    total_outstanding_zar: Decimal


class AgingBucket(BaseModel):
    bucket: str  # "current", "30_days", "60_days", "90_days_plus"
    count: int
    total_zar: Decimal


class CollectionsReportItem(BaseModel):
    period: str
    total_overdue_zar: Decimal
    total_collected_zar: Decimal
    collection_rate: Decimal
    suspensions: int
    arrangements: int


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int


# ---------------------------------------------------------------------------
# Dunning action read
# ---------------------------------------------------------------------------

class DunningActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    customer_id: uuid.UUID
    action_type: str
    scheduled_at: datetime
    executed_at: Optional[datetime] = None
    result: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Billing Account schemas
# ---------------------------------------------------------------------------

class BillingAccountCreate(BaseModel):
    customer_id: Optional[uuid.UUID] = None
    company_id: Optional[uuid.UUID] = None
    account_number: str
    account_name: Optional[str] = None
    billing_email: Optional[str] = None
    payment_method: Optional[str] = None
    payment_terms: Optional[str] = None
    credit_limit_zar: Optional[Decimal] = None
    auto_debit: bool = False


class BillingAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: Optional[uuid.UUID] = None
    company_id: Optional[uuid.UUID] = None
    account_number: str
    account_name: Optional[str] = None
    billing_email: Optional[str] = None
    payment_method: Optional[str] = None
    payment_terms: Optional[str] = None
    credit_limit_zar: Optional[Decimal] = None
    auto_debit: bool
    status: str
    dunning_stage: Optional[str] = None
    last_dunning_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Subscription Transfer schemas
# ---------------------------------------------------------------------------

class SubscriptionTransferCreate(BaseModel):
    subscription_id: uuid.UUID
    property_id: Optional[uuid.UUID] = None
    from_customer_id: uuid.UUID
    to_customer_id: uuid.UUID
    from_billing_account_id: Optional[uuid.UUID] = None
    to_billing_account_id: Optional[uuid.UUID] = None
    trigger: str = "tenant_move_out"
    transfer_date: date = Field(default_factory=date.today)
    equipment_transfers: bool = True
    equipment_condition: Optional[str] = None
    equipment_notes: Optional[str] = None
    deposit_transfer_zar: Optional[Decimal] = None
    initiated_by: Optional[uuid.UUID] = None
    initiated_by_type: Optional[str] = None
    notes: Optional[str] = None


class SubscriptionTransferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    subscription_id: uuid.UUID
    property_id: Optional[uuid.UUID] = None
    from_customer_id: uuid.UUID
    to_customer_id: uuid.UUID
    from_billing_account_id: Optional[uuid.UUID] = None
    to_billing_account_id: Optional[uuid.UUID] = None
    status: str
    trigger: str
    transfer_date: date
    from_prorated_amount_zar: Decimal
    to_prorated_amount_zar: Decimal
    equipment_transfers: bool
    equipment_condition: Optional[str] = None
    equipment_notes: Optional[str] = None
    deposit_transfer_zar: Optional[Decimal] = None
    outstanding_balance_zar: Decimal
    settlement_invoice_id: Optional[uuid.UUID] = None
    fno_service_reference: Optional[str] = None
    initiated_by: Optional[uuid.UUID] = None
    initiated_by_type: Optional[str] = None
    requested_at: datetime
    approved_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TransferApprovalRequest(BaseModel):
    approved: bool
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Subscription schemas
# ---------------------------------------------------------------------------

class CreateSubscriptionRequest(BaseModel):
    customer_id: uuid.UUID
    billing_account_id: Optional[uuid.UUID] = None
    property_id: Optional[uuid.UUID] = None
    plan: str
    segment: Optional[str] = None
    billing_interval: str = "monthly"
    base_price_zar: Decimal = Field(..., gt=0)
    segment_pricing: Optional[Dict[str, float]] = None
    billing_anchor: Optional[date] = None
    trial_days: int = Field(0, ge=0, le=365)

    @field_validator("billing_interval")
    @classmethod
    def validate_interval(cls, v: str) -> str:
        allowed = {"monthly", "quarterly", "semi_annual", "annual"}
        if v not in allowed:
            raise ValueError(f"billing_interval must be one of {allowed}")
        return v


class ProratedSubscriptionRequest(BaseModel):
    customer_id: uuid.UUID
    plan: str
    start_date: date
    billing_anchor: date
    segment: Optional[str] = None
    billing_interval: str = "monthly"
    base_price_zar: Decimal = Field(..., gt=0)
    segment_pricing: Optional[Dict[str, float]] = None


class RecordUsageRequest(BaseModel):
    metric: str = Field(..., min_length=1, max_length=100)
    quantity: Decimal = Field(..., ge=0)
    unit_price_zar: Decimal = Field(..., ge=0)
    description: Optional[str] = None


class SubscriptionUsageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subscription_id: uuid.UUID
    metric: str
    quantity: Decimal
    unit_price_zar: Decimal
    recorded_at: datetime
    billed_invoice_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    created_at: datetime


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    billing_account_id: Optional[uuid.UUID] = None
    property_id: Optional[uuid.UUID] = None
    plan: str
    segment: Optional[str] = None
    status: str
    billing_interval: str
    base_price_zar: Decimal
    segment_pricing: Optional[Dict[str, Any]] = None
    billing_anchor: date
    current_period_start: Optional[date] = None
    current_period_end: Optional[date] = None
    trial_ends_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_at_period_end: bool
    metadata_: Optional[Dict[str, Any]] = Field(None, alias="metadata")
    created_at: datetime
    updated_at: datetime


class ProrationResponse(BaseModel):
    prorated_amount_zar: Decimal
    days_remaining: int
    days_in_month: int
    full_price_zar: Decimal
    billing_period_start: date
    billing_period_end: date


class InvoicePreviewResponse(BaseModel):
    subscription_id: uuid.UUID
    customer_id: uuid.UUID
    plan: str
    segment: Optional[str] = None
    recurring_amount_zar: Decimal
    usage_amount_zar: Decimal
    subtotal_zar: Decimal
    vat_zar: Decimal
    total_zar: Decimal
    billing_period_start: date
    billing_period_end: date
    line_items: List[Dict[str, Any]]
    unbilled_usage: List[SubscriptionUsageRead]
    is_in_trial: bool
    trial_ends_at: Optional[datetime] = None
