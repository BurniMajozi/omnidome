"""Pydantic schemas for the HR Service."""

import uuid
from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Employee Schemas ──────────────────────────────────────────────────────

class EmployeeCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., max_length=255)
    phone: Optional[str] = None
    department: str = "Unassigned"
    role: str = Field(..., min_length=1, max_length=100)
    manager_id: Optional[uuid.UUID] = None
    status: str = "active"
    hire_date: date
    salary_band: Optional[str] = None


class EmployeeUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    role: Optional[str] = None
    manager_id: Optional[uuid.UUID] = None
    status: Optional[str] = None
    hire_date: Optional[date] = None
    salary_band: Optional[str] = None


class EmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    first_name: str
    last_name: str
    email: str
    phone: Optional[str]
    employee_number: str
    department: str
    role: str
    manager_id: Optional[uuid.UUID]
    status: str
    hire_date: date
    salary_band: Optional[str]
    created_at: datetime
    updated_at: datetime


class EmployeeWithManager(EmployeeRead):
    manager: Optional["EmployeeRead"] = None


class DirectReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    last_name: str
    email: str
    employee_number: str
    department: str
    role: str
    status: str


# ── Department Schemas ────────────────────────────────────────────────────

class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = None
    head_id: Optional[uuid.UUID] = None


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    head_id: Optional[uuid.UUID] = None


class DepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: Optional[str]
    head_id: Optional[uuid.UUID]
    created_at: datetime


class DepartmentWithCount(DepartmentRead):
    employee_count: int = 0


# ── Leave Request Schemas ─────────────────────────────────────────────────

class LeaveRequestCreate(BaseModel):
    employee_id: uuid.UUID
    leave_type: str
    start_date: date
    end_date: date
    reason: Optional[str] = None


class LeaveRequestUpdate(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None
    reason: Optional[str] = None


class LeaveRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    leave_type: str
    start_date: date
    end_date: date
    status: str
    approved_by: Optional[uuid.UUID]
    reason: Optional[str]
    created_at: datetime
    updated_at: datetime


class LeaveBalance(BaseModel):
    employee_id: uuid.UUID
    annual_entitled: int = 21
    annual_used: int = 0
    annual_remaining: int = 21
    sick_entitled: int = 10
    sick_used: int = 0
    sick_remaining: int = 10
    family_entitled: int = 5
    family_used: int = 0
    family_remaining: int = 5
    unpaid_used: int = 0


# ── Performance Review Schemas ────────────────────────────────────────────

class PerformanceReviewCreate(BaseModel):
    employee_id: uuid.UUID
    review_period: str = Field(..., min_length=1, max_length=50)
    rating: Optional[str] = None
    goals: Optional[str] = None
    achievements: Optional[str] = None
    reviewer_id: Optional[uuid.UUID] = None


class PerformanceReviewUpdate(BaseModel):
    review_period: Optional[str] = None
    rating: Optional[str] = None
    goals: Optional[str] = None
    achievements: Optional[str] = None
    reviewer_id: Optional[uuid.UUID] = None
    status: Optional[str] = None


class PerformanceReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    review_period: str
    rating: Optional[str]
    goals: Optional[str]
    achievements: Optional[str]
    reviewer_id: Optional[uuid.UUID]
    status: str
    created_at: datetime
    updated_at: datetime


class PerformanceSummary(BaseModel):
    employee_id: uuid.UUID
    review_count: int = 0
    average_rating: Optional[str] = None
    latest_rating: Optional[str] = None
    latest_review_period: Optional[str] = None


# ── Paginated Response ────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int
