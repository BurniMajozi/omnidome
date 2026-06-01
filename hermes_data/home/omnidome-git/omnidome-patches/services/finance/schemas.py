"""Pydantic v2 schemas for the Finance Service."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Financial Period Schemas ──────────────────────────────────────────────

class FinancialPeriodCreate(BaseModel):
    period: str = Field(..., min_length=1, max_length=20, description="Period identifier, e.g. 2024-Q1 or 2024-01")
    revenue: float = 0
    cogs: float = 0
    operating_expenses: float = 0


class FinancialPeriodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    period: str
    revenue: float
    cogs: float
    gross_profit: float
    operating_expenses: float
    ebitda: float
    net_income: float
    cash_flow: float
    data: Dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime


class FinancialPeriodUpdate(BaseModel):
    revenue: Optional[float] = None
    cogs: Optional[float] = None
    operating_expenses: Optional[float] = None
    data: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


# ── Summary Schemas ───────────────────────────────────────────────────────

class FinanceSummary(BaseModel):
    period: str
    revenue: float
    gross_profit: float
    operating_expenses: float
    ebitda: float
    net_income: float
    cash_flow: float
    status: str


class RevenueRecognitionItem(BaseModel):
    period: str
    recognized_revenue: float
    deferred_revenue: float
    source: str


class RevenueRecognitionSchedule(BaseModel):
    items: List[RevenueRecognitionItem]
    total_recognized: float = 0
    total_deferred: float = 0


class CashFlowStatement(BaseModel):
    period: str
    operating_cash_flow: float = 0
    investing_cash_flow: float = 0
    financing_cash_flow: float = 0
    net_cash_flow: float = 0


# ── Pagination ────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int
