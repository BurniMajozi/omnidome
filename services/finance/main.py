"""OmniDome Finance Service - GAAP-aligned financials, FP&A, and audit trail.

Port: 8015
"""

import logging
import os
from datetime import datetime
from typing import Dict, List
import uuid

from fastapi import FastAPI, Depends
from pydantic import BaseModel, Field

from services.common.entitlements import EntitlementGuard
from services.common.auth import get_current_tenant_id

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


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


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


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "finance"}


@app.get("/overview")
async def overview(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return {
        "tenant_id": str(tenant_id),
        "currency": "ZAR",
        "kpis": {
            "ebita": 18_000_000,
            "ebit": 12_000_000,
            "free_cash_flow": 7_800_000,
            "dso_days": 31,
        },
        "period": "FY2026 YTD",
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/statements")
async def statements() -> Dict[str, List[Dict[str, str]]]:
    return {
        "income_statement": [
            {"line": "Revenue", "amount": "48000000"},
            {"line": "Cost of Service", "amount": "-14000000"},
            {"line": "Gross Profit", "amount": "34000000"},
            {"line": "Operating Expenses", "amount": "-16000000"},
            {"line": "EBITA", "amount": "18000000"},
            {"line": "Depreciation & Amortization", "amount": "-6000000"},
            {"line": "EBIT", "amount": "12000000"},
            {"line": "Interest", "amount": "-1800000"},
            {"line": "Taxes", "amount": "-2856000"},
            {"line": "Net Income", "amount": "9344000"},
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
            {"line": "Operating Cash Flow", "amount": "15600000"},
            {"line": "Investing Cash Flow", "amount": "-9000000"},
            {"line": "Financing Cash Flow", "amount": "-2100000"},
            {"line": "Net Change in Cash", "amount": "3600000"},
        ],
    }


@app.post("/scenario", response_model=ScenarioResponse)
async def scenario(payload: ScenarioRequest):
    return _scenario_calc(payload)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8015)
