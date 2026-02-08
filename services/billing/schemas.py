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
    number: str
    status: str
    subtotal_zar: Decimal
    vat_zar: Decimal
    total_zar: Decimal
    amount_paid_zar: Decimal
    due_date: date
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
