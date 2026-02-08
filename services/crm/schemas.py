"""Pydantic v2 schemas for the CRM service."""

import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


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


# ---------------------------------------------------------------------------
# Customer schemas
# ---------------------------------------------------------------------------

class CustomerCreate(BaseModel):
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


class CustomerUpdate(BaseModel):
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
    email: str
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
    services: List[Dict[str, Any]] = Field(default_factory=list)
    billing: List[Dict[str, Any]] = Field(default_factory=list)
    support: List[Dict[str, Any]] = Field(default_factory=list)
    network: List[Dict[str, Any]] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    notes_count: int = 0


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

class LeadCreate(BaseModel):
    source: Optional[str] = Field(None, max_length=100)
    first_name: str = Field(..., min_length=1, max_length=120)
    last_name: str = Field(..., min_length=1, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    coverage_area: Optional[str] = Field(None, max_length=255)
    interested_package: Optional[str] = Field(None, max_length=120)


class LeadUpdate(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    coverage_area: Optional[str] = Field(None, max_length=255)
    interested_package: Optional[str] = Field(None, max_length=120)

    @field_validator("status")
    @classmethod
    def check_status(cls, v: Optional[str]) -> Optional[str]:
        allowed = {"new", "contacted", "qualified", "converted", "lost"}
        if v is not None and v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v


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
    field: str  # e.g. "tenure", "spend", "province", "package_type", "payment_method", "churn_risk"
    operator: str  # "eq", "ne", "gt", "gte", "lt", "lte", "in", "contains"
    value: Any


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
