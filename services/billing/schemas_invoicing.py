"""Request/response schemas for the invoicing suite. Client-sent totals are not fields (ignored)."""
from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

SOURCE_TYPES = ("manual", "field_sales", "technician", "termination_fee", "web", "other")
QUOTE_SOURCES = ("field_sales", "technician", "web", "other")
_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
_EMAIL = re.compile(r"^[^@\s<>\"',;]+@[^@\s<>\"',;]+\.[^@\s<>\"',;]+$")


def check_email(value: str) -> str:
    v = (value or "").strip()
    if len(v) > 254 or not _EMAIL.match(v):
        raise ValueError("invalid email address")
    return v


def check_https_url(value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return None
    v = value.strip()
    if not re.match(r"^https?://[^\s<>\"']+$", v) or len(v) > 500:
        raise ValueError("must be an http(s) URL")
    return v


class LineIn(BaseModel):
    line_id: Optional[str] = Field(None, max_length=64)
    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal = Field(default=Decimal("1"), gt=0, le=Decimal("1000000"), decimal_places=3, max_digits=12)
    unit_price: Decimal = Field(ge=0, le=Decimal("1000000000"), decimal_places=2, max_digits=12)
    discount: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2, max_digits=12)
    discount_type: Literal["amount", "percent"] = "amount"
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100, decimal_places=2)
    catalog_item_id: Optional[uuid.UUID] = None


class BillTo(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    email: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=40)
    address: Optional[str] = Field(None, max_length=1000)

    @field_validator("email")
    @classmethod
    def _e(cls, v):
        return check_email(v) if v else None


class ManualInvoiceCreate(BaseModel):
    customer_id: uuid.UUID
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    lines: list[LineIn] = Field(min_length=1, max_length=200)
    notes: Optional[str] = Field(None, max_length=4000)
    terms: Optional[str] = Field(None, max_length=4000)
    po_number: Optional[str] = Field(None, max_length=80)
    source_type: Literal["manual", "field_sales", "technician", "termination_fee", "web", "other"] = "manual"
    created_by: Optional[str] = Field(None, max_length=120)
    template_id: Optional[uuid.UUID] = None
    bill_to: Optional[BillTo] = None


class InvoiceUpdate(BaseModel):
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    lines: Optional[list[LineIn]] = Field(None, min_length=1, max_length=200)
    notes: Optional[str] = Field(None, max_length=4000)
    terms: Optional[str] = Field(None, max_length=4000)
    po_number: Optional[str] = Field(None, max_length=80)
    template_id: Optional[uuid.UUID] = None
    bill_to: Optional[BillTo] = None


class LineOrder(BaseModel):
    order: list[str] = Field(min_length=1, max_length=200, description="line_id values in the new order")


# ── catalog / templates ──────────────────────────────────────────────────────

class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    unit_price_zar: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("1000000000"), decimal_places=2, max_digits=12)
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100, decimal_places=2)
    category: Optional[str] = Field(None, max_length=80)
    active: bool = True


class ItemPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    unit_price_zar: Optional[Decimal] = Field(None, ge=0, le=Decimal("1000000000"), decimal_places=2, max_digits=12)
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100, decimal_places=2)
    category: Optional[str] = Field(None, max_length=80)
    active: Optional[bool] = None


class ShowColumns(BaseModel):
    description: bool = True
    quantity: bool = True
    unit_price: bool = True
    discount: bool = True
    tax: bool = True
    line_total: bool = True


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    is_default: bool = False
    company_name: Optional[str] = Field(None, max_length=200)
    company_address: Optional[str] = Field(None, max_length=1000)
    vat_number: Optional[str] = Field(None, max_length=40)
    logo_url: Optional[str] = None
    accent_colour: str = "#1d4ed8"
    footer: Optional[str] = Field(None, max_length=1000)
    payment_details: Optional[str] = Field(None, max_length=2000)
    default_terms: Optional[str] = Field(None, max_length=4000)
    default_due_days: int = Field(30, ge=0, le=365)
    show_columns: ShowColumns = Field(default_factory=ShowColumns)
    show_payment_details: bool = True
    show_terms: bool = True

    @field_validator("logo_url")
    @classmethod
    def _logo(cls, v):
        return check_https_url(v)

    @field_validator("accent_colour")
    @classmethod
    def _colour(cls, v):
        if not _COLOUR.match(v or ""):
            raise ValueError("accent_colour must be a #rrggbb hex colour")
        return v.lower()


class TemplatePatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    is_default: Optional[bool] = None
    company_name: Optional[str] = Field(None, max_length=200)
    company_address: Optional[str] = Field(None, max_length=1000)
    vat_number: Optional[str] = Field(None, max_length=40)
    logo_url: Optional[str] = None
    accent_colour: Optional[str] = None
    footer: Optional[str] = Field(None, max_length=1000)
    payment_details: Optional[str] = Field(None, max_length=2000)
    default_terms: Optional[str] = Field(None, max_length=4000)
    default_due_days: Optional[int] = Field(None, ge=0, le=365)
    show_columns: Optional[ShowColumns] = None
    show_payment_details: Optional[bool] = None
    show_terms: Optional[bool] = None

    @field_validator("logo_url")
    @classmethod
    def _logo(cls, v):
        return check_https_url(v)

    @field_validator("accent_colour")
    @classmethod
    def _colour(cls, v):
        if v is not None and not _COLOUR.match(v):
            raise ValueError("accent_colour must be a #rrggbb hex colour")
        return v.lower() if v else v


# ── quotes ───────────────────────────────────────────────────────────────────

class QuoteCreate(BaseModel):
    customer_id: Optional[uuid.UUID] = None
    prospect_name: Optional[str] = Field(None, max_length=200)
    prospect_email: Optional[str] = None
    prospect_phone: Optional[str] = Field(None, max_length=40)
    prospect_address: Optional[str] = Field(None, max_length=1000)
    issue_date: Optional[date] = None
    valid_until: Optional[date] = None
    lines: list[LineIn] = Field(min_length=1, max_length=200)
    notes: Optional[str] = Field(None, max_length=4000)
    terms: Optional[str] = Field(None, max_length=4000)
    po_number: Optional[str] = Field(None, max_length=80)
    source: Literal["field_sales", "technician", "web", "other"] = "web"
    created_by: Optional[str] = Field(None, max_length=120)
    template_id: Optional[uuid.UUID] = None

    @field_validator("prospect_email")
    @classmethod
    def _pe(cls, v):
        return check_email(v) if v else None


class QuoteUpdate(BaseModel):
    customer_id: Optional[uuid.UUID] = None
    prospect_name: Optional[str] = Field(None, max_length=200)
    prospect_email: Optional[str] = None
    prospect_phone: Optional[str] = Field(None, max_length=40)
    prospect_address: Optional[str] = Field(None, max_length=1000)
    issue_date: Optional[date] = None
    valid_until: Optional[date] = None
    lines: Optional[list[LineIn]] = Field(None, min_length=1, max_length=200)
    notes: Optional[str] = Field(None, max_length=4000)
    terms: Optional[str] = Field(None, max_length=4000)
    po_number: Optional[str] = Field(None, max_length=80)
    template_id: Optional[uuid.UUID] = None

    @field_validator("prospect_email")
    @classmethod
    def _pe(cls, v):
        return check_email(v) if v else None


class QuoteDecision(BaseModel):
    note: Optional[str] = Field(None, max_length=500)


class QuoteConvert(BaseModel):
    customer_id: Optional[uuid.UUID] = Field(None, description="Required when the quote is for a prospect")
    due_date: Optional[date] = None
    force: bool = Field(False, description="Admin only: convert a quote that is not yet accepted")


# ── delivery / sharing ───────────────────────────────────────────────────────

class EmailRequest(BaseModel):
    to: Optional[list[str]] = Field(None, max_length=5)
    cc: Optional[list[str]] = Field(None, max_length=5)
    subject: Optional[str] = Field(None, max_length=300)
    message: Optional[str] = Field(None, max_length=4000)
    kind: Literal["document", "reminder"] = "document"
    link_expires_in_days: Optional[int] = Field(None, ge=1, le=365)

    @field_validator("to", "cc")
    @classmethod
    def _addrs(cls, v):
        return [check_email(a) for a in v] if v else v


class ShareLinkRequest(BaseModel):
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)


class DeliveryWebhookEvent(BaseModel):
    tenant_id: uuid.UUID
    message_id: str = Field(min_length=1, max_length=255)
    event_type: Literal["delivered", "bounced", "complained", "rejected", "replied", "opened"]
    occurred_at: Optional[str] = Field(None, max_length=40)
    detail: Optional[dict] = None


class ReconcileRequest(BaseModel):
    outcome: Literal["sent", "not_sent"]
    message_id: Optional[str] = Field(None, max_length=255)


class PublicPayRequest(BaseModel):
    amount_zar: Optional[Decimal] = Field(None, gt=0, max_digits=12, decimal_places=2)
