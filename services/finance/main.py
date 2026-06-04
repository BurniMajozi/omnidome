"""OmniDome Finance Service - GAAP-aligned financials, FP&A, and audit trail.

Port: 8015
"""

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional
import uuid

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.entitlements import EntitlementGuard
from services.common.auth import get_current_tenant_id
from services.finance.database import get_session, init_tables, FinancialRecord, BudgetScenario

logger = logging.getLogger("finance")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(
    title="OmniDome Finance Service",
    version="1.0.0",
    description="GAAP-aligned statements, revenue recognition, and scenario planning for ISPs.",
)

guard = EntitlementGuard(module_id="finance")


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    await init_tables()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


# ── Pydantic models ───────────────────────────────────────────────────

class ScenarioRequest(BaseModel):
    revenue_growth_pct: float = Field(0, description="Revenue growth percentage")
    opex_change_pct: float = Field(0, description="Operating expense change percentage")
    capex_change_pct: float = Field(0, description="Capital expenditure change percentage")


class ScenarioResponse(BaseModel):
    revenue: float
    opex: float
    ebita: float
    ebit: float
    free_cash_flow: float


class FinancialRecordCreate(BaseModel):
    record_type: str = Field(..., description="REVENUE, OPEX, CAPEX, INTEREST, TAX")
    description: Optional[str] = None
    amount: float
    period: Optional[str] = None


class FinancialRecordResponse(BaseModel):
    id: str
    tenant_id: str
    record_type: str
    description: Optional[str]
    amount: float
    period: Optional[str]
    created_at: str
    updated_at: str


# ── Base values for scenario calculations ─────────────────────────────

BASE_REVENUE = 48_000_000
BASE_OPEX = 30_000_000
BASE_DEPRECIATION = 6_000_000
BASE_INTEREST = 1_800_000
BASE_CAPEX = 9_000_000
TAX_RATE = 0.28


def _scenario_calc(payload: ScenarioRequest) -> ScenarioResponse:
    revenue = BASE_REVENUE * (1 + payload.revenue_growth_pct / 100)
    opex = BASE_OPEX * (1 + payload.opex_change_pct / 100)
    capex = BASE_CAPEX * (1 + payload.capex_change_pct / 100)
    depreciation = BASE_DEPRECIATION * (1 + (payload.capex_change_pct / 100) * 0.4)
    ebita = revenue - opex
    ebit = ebita - depreciation
    taxable = max(0, ebit - BASE_INTEREST)
    tax = taxable * TAX_RATE
    free_cash_flow = ebita - capex - BASE_INTEREST - tax
    return ScenarioResponse(
        revenue=round(revenue, 2),
        opex=round(opex, 2),
        ebita=round(ebita, 2),
        ebit=round(ebit, 2),
        free_cash_flow=round(free_cash_flow, 2),
    )


def _record_to_dict(record: FinancialRecord) -> dict:
    return {
        "id": str(record.id),
        "tenant_id": str(record.tenant_id),
        "record_type": record.record_type,
        "description": record.description,
        "amount": float(record.amount) if record.amount is not None else None,
        "period": record.period,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _scenario_to_dict(scenario: BudgetScenario) -> dict:
    return {
        "id": str(scenario.id),
        "tenant_id": str(scenario.tenant_id),
        "name": scenario.name,
        "revenue_growth_pct": float(scenario.revenue_growth_pct) if scenario.revenue_growth_pct is not None else None,
        "opex_change_pct": float(scenario.opex_change_pct) if scenario.opex_change_pct is not None else None,
        "capex_change_pct": float(scenario.capex_change_pct) if scenario.capex_change_pct is not None else None,
        "result_revenue": float(scenario.result_revenue) if scenario.result_revenue is not None else None,
        "result_opex": float(scenario.result_opex) if scenario.result_opex is not None else None,
        "result_ebita": float(scenario.result_ebita) if scenario.result_ebita is not None else None,
        "result_ebit": float(scenario.result_ebit) if scenario.result_ebit is not None else None,
        "result_fcf": float(scenario.result_fcf) if scenario.result_fcf is not None else None,
        "created_at": scenario.created_at.isoformat() if scenario.created_at else None,
        "updated_at": scenario.updated_at.isoformat() if scenario.updated_at else None,
    }


async def _ensure_sample_data(tenant_id: uuid.UUID, db: AsyncSession) -> None:
    """Seed sample financial records and a budget scenario if tenant has none."""
    result = await db.execute(
        select(func.count(FinancialRecord.id)).where(FinancialRecord.tenant_id == tenant_id)
    )
    count = result.scalar()

    if count == 0:
        sample_records = [
            FinancialRecord(
                tenant_id=tenant_id,
                record_type="REVENUE",
                description="Total revenue for period",
                amount=48_000_000,
                period="FY2026-Q1",
            ),
            FinancialRecord(
                tenant_id=tenant_id,
                record_type="OPEX",
                description="Total operating expenses",
                amount=30_000_000,
                period="FY2026-Q1",
            ),
            FinancialRecord(
                tenant_id=tenant_id,
                record_type="CAPEX",
                description="Capital expenditure",
                amount=9_000_000,
                period="FY2026-Q1",
            ),
            FinancialRecord(
                tenant_id=tenant_id,
                record_type="INTEREST",
                description="Interest expense",
                amount=1_800_000,
                period="FY2026-Q1",
            ),
            FinancialRecord(
                tenant_id=tenant_id,
                record_type="TAX",
                description="Income tax expense",
                amount=2_856_000,
                period="FY2026-Q1",
            ),
        ]
        for rec in sample_records:
            db.add(rec)

        sample_scenario = BudgetScenario(
            tenant_id=tenant_id,
            name="Base Case FY2026",
            revenue_growth_pct=0,
            opex_change_pct=0,
            capex_change_pct=0,
            result_revenue=48_000_000,
            result_opex=30_000_000,
            result_ebita=18_000_000,
            result_ebit=12_000_000,
            result_fcf=7_800_000,
        )
        db.add(sample_scenario)
        await db.flush()


# ── Health ────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "finance"}


# ── Overview ──────────────────────────────────────────────────────────

@app.get("/overview")
async def overview(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    await _ensure_sample_data(tenant_id, db)

    # Compute KPIs from DB records
    rev_result = await db.execute(
        select(func.sum(FinancialRecord.amount)).where(
            FinancialRecord.tenant_id == tenant_id,
            FinancialRecord.record_type == "REVENUE",
        )
    )
    revenue = float(rev_result.scalar() or 0)

    opex_result = await db.execute(
        select(func.sum(FinancialRecord.amount)).where(
            FinancialRecord.tenant_id == tenant_id,
            FinancialRecord.record_type == "OPEX",
        )
    )
    opex = float(opex_result.scalar() or 0)

    ebita = revenue - opex

    capex_result = await db.execute(
        select(func.sum(FinancialRecord.amount)).where(
            FinancialRecord.tenant_id == tenant_id,
            FinancialRecord.record_type == "CAPEX",
        )
    )
    capex = float(capex_result.scalar() or 0)

    interest_result = await db.execute(
        select(func.sum(FinancialRecord.amount)).where(
            FinancialRecord.tenant_id == tenant_id,
            FinancialRecord.record_type == "INTEREST",
        )
    )
    interest = float(interest_result.scalar() or 0)

    depreciation = BASE_DEPRECIATION
    ebit = ebita - depreciation
    taxable = max(0, ebit - interest)
    tax = taxable * TAX_RATE
    free_cash_flow = ebita - capex - interest - tax

    return {
        "tenant_id": str(tenant_id),
        "currency": "ZAR",
        "kpis": {
            "ebita": round(ebita, 2),
            "ebit": round(ebit, 2),
            "free_cash_flow": round(free_cash_flow, 2),
            "dso_days": 31,
        },
        "period": "FY2026 YTD",
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


# ── Statements ────────────────────────────────────────────────────────

@app.get("/statements")
async def statements(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> Dict[str, List[Dict[str, str]]]:
    await _ensure_sample_data(tenant_id, db)

    rev_result = await db.execute(
        select(func.sum(FinancialRecord.amount)).where(
            FinancialRecord.tenant_id == tenant_id,
            FinancialRecord.record_type == "REVENUE",
        )
    )
    revenue = float(rev_result.scalar() or 0)

    opex_result = await db.execute(
        select(func.sum(FinancialRecord.amount)).where(
            FinancialRecord.tenant_id == tenant_id,
            FinancialRecord.record_type == "OPEX",
        )
    )
    opex = float(opex_result.scalar() or 0)

    capex_result = await db.execute(
        select(func.sum(FinancialRecord.amount)).where(
            FinancialRecord.tenant_id == tenant_id,
            FinancialRecord.record_type == "CAPEX",
        )
    )
    capex = float(capex_result.scalar() or 0)

    interest_result = await db.execute(
        select(func.sum(FinancialRecord.amount)).where(
            FinancialRecord.tenant_id == tenant_id,
            FinancialRecord.record_type == "INTEREST",
        )
    )
    interest = float(interest_result.scalar() or 0)

    tax_result = await db.execute(
        select(func.sum(FinancialRecord.amount)).where(
            FinancialRecord.tenant_id == tenant_id,
            FinancialRecord.record_type == "TAX",
        )
    )
    tax = float(tax_result.scalar() or 0)

    cost_of_service = opex * 0.47  # approximate split
    gross_profit = revenue - cost_of_service
    operating_expenses = opex - cost_of_service
    ebita = revenue - opex
    depreciation = BASE_DEPRECIATION
    ebit = ebita - depreciation
    net_income = ebit - interest - tax

    return {
        "income_statement": [
            {"line": "Revenue", "amount": str(revenue)},
            {"line": "Cost of Service", "amount": str(round(-cost_of_service, 2))},
            {"line": "Gross Profit", "amount": str(round(gross_profit, 2))},
            {"line": "Operating Expenses", "amount": str(round(-operating_expenses, 2))},
            {"line": "EBITA", "amount": str(round(ebita, 2))},
            {"line": "Depreciation & Amortization", "amount": str(round(-depreciation, 2))},
            {"line": "EBIT", "amount": str(round(ebit, 2))},
            {"line": "Interest", "amount": str(round(-interest, 2))},
            {"line": "Taxes", "amount": str(round(-tax, 2))},
            {"line": "Net Income", "amount": str(round(net_income, 2))},
        ],
        "balance_sheet": [
            {"line": "Cash", "amount": "8200000"},
            {"line": "Accounts Receivable", "amount": "6400000"},
            {"line": "PP&E", "amount": "42000000"},
            {"line": "Total Assets", "amount": "56600000"},
            {"line": "Accounts Payable", "amount": "5400000"},
            {"line": "Deferred Revenue", "amount": "6200000"},
            {"line": "Long-Term Debt", "amount": "18000000"},
            {"line": "Equity", "amount": "27000000"},
            {"line": "Total Liabilities & Equity", "amount": "56600000"},
        ],
        "cash_flow": [
            {"line": "Operating Cash Flow", "amount": str(round(ebita + depreciation, 2))},
            {"line": "Investing Cash Flow", "amount": str(round(-capex, 2))},
            {"line": "Financing Cash Flow", "amount": str(round(-interest, 2))},
            {"line": "Net Change in Cash", "amount": str(round(ebita + depreciation - capex - interest, 2))},
        ],
    }


# ── Scenario ──────────────────────────────────────────────────────────

@app.post("/scenario", response_model=ScenarioResponse)
async def scenario(
    payload: ScenarioRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = _scenario_calc(payload)

    # Save scenario to DB
    scenario_record = BudgetScenario(
        tenant_id=tenant_id,
        name=f"Scenario {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
        revenue_growth_pct=payload.revenue_growth_pct,
        opex_change_pct=payload.opex_change_pct,
        capex_change_pct=payload.capex_change_pct,
        result_revenue=result.revenue,
        result_opex=result.opex,
        result_ebita=result.ebita,
        result_ebit=result.ebit,
        result_fcf=result.free_cash_flow,
    )
    db.add(scenario_record)

    return result


# ── Financial Records CRUD ────────────────────────────────────────────

@app.post("/records", response_model=FinancialRecordResponse)
async def create_record(
    payload: FinancialRecordCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    record = FinancialRecord(
        tenant_id=tenant_id,
        record_type=payload.record_type,
        description=payload.description,
        amount=payload.amount,
        period=payload.period,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return _record_to_dict(record)


@app.get("/records", response_model=List[FinancialRecordResponse])
async def list_records(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    await _ensure_sample_data(tenant_id, db)

    result = await db.execute(
        select(FinancialRecord)
        .where(FinancialRecord.tenant_id == tenant_id)
        .order_by(desc(FinancialRecord.created_at))
    )
    records = result.scalars().all()
    return [_record_to_dict(r) for r in records]


# ── Budget Scenarios CRUD ─────────────────────────────────────────────

@app.get("/scenarios")
async def list_scenarios(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    await _ensure_sample_data(tenant_id, db)

    result = await db.execute(
        select(BudgetScenario)
        .where(BudgetScenario.tenant_id == tenant_id)
        .order_by(desc(BudgetScenario.created_at))
    )
    scenarios = result.scalars().all()
    return [_scenario_to_dict(s) for s in scenarios]


@app.delete("/scenarios/{scenario_id}")
async def delete_scenario(
    scenario_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(BudgetScenario).where(
            BudgetScenario.id == scenario_id,
            BudgetScenario.tenant_id == tenant_id,
        )
    )
    scenario = result.scalar_one_or_none()
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    await db.delete(scenario)
    return {"status": "deleted", "id": str(scenario_id)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8015)
