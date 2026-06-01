"""Finance routes — financial periods, revenue recognition, FP&A scenarios."""

import uuid
import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.common.http_client import service_call
from finance.models import FinancePeriod, RevenueRecognition, BudgetScenario

router = APIRouter(prefix="/api/v1/finance", tags=["Finance"])

TAX_RATE = Decimal("0.28")
BASE_INTEREST = Decimal("1800000")


class PeriodCreate(BaseModel):
    period: str = Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    revenue: Decimal = Decimal("0.00")
    cogs: Decimal = Decimal("0.00")
    operating_expenses: Decimal = Decimal("0.00")
    depreciation: Decimal = Decimal("0.00")
    interest: Decimal = BASE_INTEREST
    capex: Decimal = Decimal("0.00")


class PeriodUpdate(BaseModel):
    revenue: Optional[Decimal] = None
    cogs: Optional[Decimal] = None
    operating_expenses: Optional[Decimal] = None
    depreciation: Optional[Decimal] = None
    interest: Optional[Decimal] = None
    capex: Optional[Decimal] = None
    status: Optional[str] = None


class PeriodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    period: str
    revenue: Decimal
    cogs: Decimal
    gross_profit: Decimal
    operating_expenses: Decimal
    ebitda: Decimal
    depreciation: Decimal
    ebit: Decimal
    interest: Decimal
    tax: Decimal
    net_income: Decimal
    capex: Decimal
    free_cash_flow: Decimal
    status: str
    created_at: datetime


def _calculate_derived(revenue, cogs, opex, depreciation, interest, capex):
    gross_profit = revenue - cogs
    ebitda = gross_profit - opex
    ebit = ebitda - depreciation
    taxable = max(Decimal("0"), ebit - interest)
    tax = taxable * TAX_RATE
    net_income = ebit - interest - tax
    free_cash_flow = ebitda - capex - interest - tax
    return gross_profit, ebitda, ebit, tax, net_income, free_cash_flow


@router.post("/periods", response_model=PeriodRead)
async def create_period(body: PeriodCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        # Auto-pull revenue from billing if revenue=0
        revenue = body.revenue
        if revenue == Decimal("0"):
            try:
                billing_data = await service_call("billing", "GET", "/api/reports/revenue?months=1",
                    tenant_id=str(ctx.tenant_id), user_id=str(ctx.user_id), timeout=5.0)
                if billing_data and isinstance(billing_data, list) and len(billing_data) > 0:
                    revenue = Decimal(str(billing_data[0].get("total_invoiced_zar", 0)))
            except Exception:
                revenue = Decimal("48000000")  # fallback to Cell C benchmark
        gross_profit, ebitda, ebit, tax, net_income, fcf = _calculate_derived(
            revenue, body.cogs, body.operating_expenses, body.depreciation, body.interest, body.capex)
        period = FinancePeriod(
            tenant_id=ctx.tenant_id, period=body.period,
            revenue=revenue, cogs=body.cogs, operating_expenses=body.operating_expenses,
            depreciation=body.depreciation, interest=body.interest, capex=body.capex,
            status="draft",
        )
        session.add(period)
        await session.flush()
        await session.refresh(period)
        return PeriodRead.model_validate(period)


@router.get("/periods")
async def list_periods(ctx: AuthContext = Depends(get_auth_context), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    async with session_scope() as session:
        total = await session.scalar(select(func.count()).select_from(select(FinancePeriod).where(FinancePeriod.tenant_id == ctx.tenant_id).subquery()))
        items = (await session.execute(select(FinancePeriod).where(FinancePeriod.tenant_id == ctx.tenant_id).order_by(FinancePeriod.period.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
        return {
            "items": [PeriodRead.model_validate(p) for p in items],
            "total": total or 0, "page": page, "page_size": page_size,
            "pages": max(1, math.ceil((total or 0) / page_size)),
        }


@router.get("/periods/{period_id}", response_model=PeriodRead)
async def get_period(period_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        period = await session.get(FinancePeriod, period_id)
        if not period or period.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Period not found")
        return PeriodRead.model_validate(period)


@router.put("/periods/{period_id}", response_model=PeriodRead)
async def update_period(period_id: uuid.UUID, body: PeriodUpdate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        period = await session.get(FinancePeriod, period_id)
        if not period or period.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Period not found")
        update = body.model_dump(exclude_unset=True)
        for k, v in update.items():
            setattr(period, k, v)
        # Recalculate derived fields
        gp, ebitda, ebit, tax, ni, fcf = _calculate_derived(
            period.revenue, period.cogs, period.operating_expenses,
            period.depreciation, period.interest, period.capex)
        period.gross_profit = gp
        period.ebitda = ebitda
        period.ebit = ebit
        period.tax = tax
        period.net_income = ni
        period.free_cash_flow = fcf
        await session.flush()
        await session.refresh(period)
        return PeriodRead.model_validate(period)


@router.delete("/periods/{period_id}")
async def delete_period(period_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        period = await session.get(FinancePeriod, period_id)
        if not period or period.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Period not found")
        await session.delete(period)
        return {"status": "deleted", "id": str(period_id)}


@router.get("/summary")
async def financial_summary(ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        latest = (await session.execute(select(FinancePeriod).where(FinancePeriod.tenant_id == ctx.tenant_id).order_by(FinancePeriod.period.desc()).limit(1))).scalars().first()
        period_data = PeriodRead.model_validate(latest) if latest else None
    billing_trend = []
    try:
        billing_trend = await service_call("billing", "GET", "/api/reports/revenue?months=3",
            tenant_id=str(ctx.tenant_id), user_id=str(ctx.user_id), timeout=5.0)
    except Exception:
        pass
    return {"current_period": period_data, "billing_trend": billing_trend}


@router.get("/statements")
async def financial_statements(ctx: AuthContext = Depends(get_auth_context)):
    summary = await financial_summary(ctx)
    period = summary.get("current_period")
    if not period:
        raise HTTPException(404, "No financial periods found — create one first via POST /api/v1/finance/periods")
    return {
        "income_statement": [
            {"line": "Revenue", "amount": str(period.revenue)},
            {"line": "Cost of Service", "amount": str(-period.cogs)},
            {"line": "Gross Profit", "amount": str(period.gross_profit)},
            {"line": "Operating Expenses", "amount": str(-period.operating_expenses)},
            {"line": "EBITDA", "amount": str(period.ebitda)},
            {"line": "Depreciation", "amount": str(-period.depreciation)},
            {"line": "EBIT", "amount": str(period.ebit)},
            {"line": "Interest", "amount": str(-period.interest)},
            {"line": "Taxes", "amount": str(-period.tax)},
            {"line": "Net Income", "amount": str(period.net_income)},
        ],
        "cash_flow": [
            {"line": "Operating Cash Flow", "amount": str(period.ebitda)},
            {"line": "Capital Expenditure", "amount": str(-period.capex)},
            {"line": "Interest Paid", "amount": str(-period.interest)},
            {"line": "Free Cash Flow", "amount": str(period.free_cash_flow)},
        ],
        "period": period.period,
    }


class ScenarioRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    revenue_growth_pct: float = 0
    opex_change_pct: float = 0
    capex_change_pct: float = 0


@router.post("/scenarios")
async def create_scenario(body: ScenarioRequest, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        latest = (await session.execute(select(FinancePeriod).where(FinancePeriod.tenant_id == ctx.tenant_id).order_by(FinancePeriod.period.desc()).limit(1))).scalars().first()
        base_revenue = latest.revenue if latest else Decimal("48000000")
        base_opex = latest.operating_expenses if latest else Decimal("30000000")
        base_capex = latest.capex if latest else Decimal("9000000")
    projected = _scenario_calc(base_revenue, base_opex, base_capex,
        body.revenue_growth_pct, body.opex_change_pct, body.capex_change_pct)
    async with session_scope() as session:
        scenario = BudgetScenario(
            tenant_id=ctx.tenant_id, name=body.name, description=body.description,
            revenue_growth_pct=body.revenue_growth_pct, opex_change_pct=body.opex_change_pct,
            capex_change_pct=body.capex_change_pct, projected_data=projected,
            created_by=ctx.user_id,
        )
        session.add(scenario)
        await session.flush()
        await session.refresh(scenario)
        return {"id": str(scenario.id), "name": body.name, "projected": projected}


def _scenario_calc(base_revenue, base_opex, base_capex, rev_growth, opex_change, capex_change):
    import json
    revenue = float(base_revenue) * (1 + rev_growth / 100)
    opex = float(base_opex) * (1 + opex_change / 100)
    capex = float(base_capex) * (1 + capex_change / 100)
    depreciation = 6000000 * (1 + capex_change / 100 * 0.4)
    ebitda = revenue - opex
    ebit = ebitda - depreciation
    taxable = max(0, ebit - float(BASE_INTEREST))
    tax = taxable * float(TAX_RATE)
    fcf = ebitda - capex - float(BASE_INTEREST) - tax
    return {"revenue": round(revenue, 2), "opex": round(opex, 2), "ebitda": round(ebitda, 2),
            "ebit": round(ebit, 2), "free_cash_flow": round(fcf, 2), "tax": round(tax, 2)}


@router.get("/scenarios")
async def list_scenarios(ctx: AuthContext = Depends(get_auth_context), limit: int = Query(50, le=200)):
    async with session_scope() as session:
        items = (await session.execute(select(BudgetScenario).where(BudgetScenario.tenant_id == ctx.tenant_id).order_by(BudgetScenario.created_at.desc()).limit(limit))).scalars().all()
        return [{"id": str(s.id), "name": s.name, "projected": s.projected_data,
                 "revenue_growth_pct": s.revenue_growth_pct, "opex_change_pct": s.opex_change_pct,
                 "capex_change_pct": s.capex_change_pct,
                 "created_at": s.created_at.isoformat() if s.created_at else None} for s in items]
