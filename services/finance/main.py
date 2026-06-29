"""OmniDome Finance Service — GAAP-aligned financials, GL, and billing integration.

Port: 8015

Features:
    - GL Journal Entries (double-entry)
    - Trial Balance
    - Cash Flow Statement (direct method)
    - Income Statement & Balance Sheet (from GL)
    - Billing service integration (invoice → GL sync)
    - Budget Scenarios (what-if)
"""

import logging
import os
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Optional
import uuid

import httpx
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func, and_
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
from services.common.auth import get_current_tenant_id
from services.finance.database import (
    get_session, init_tables,
    JournalEntry, JournalEntryLine,
    FinancialRecord, BudgetScenario,
    next_journal_reference,
    RevenueContract, ExpenseReceipt, ApprovalRequest, FinancePurchaseOrder,
    FixedAsset, RecurringPayment, BankStatementItem,
)

logger = logging.getLogger("finance")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(
    title="OmniDome Finance Service",
    version="2.0.0",
    description="GAAP-aligned GL, trial balance, cash flow, and billing integration for ISPs.",
)

guard = EntitlementGuard(module_id="finance")

configure_production(app)

# ── Billing service URL for cross-service integration ──────────────────
BILLING_SERVICE_URL = os.getenv("BILLING_SERVICE_URL", "http://billing:8003")


# ── Pydantic models ────────────────────────────────────────────────────

class JournalLineInput(BaseModel):
    account_code: str = Field(..., description="Chart of accounts code, e.g. 4100")
    account_name: str = Field(..., description="Account name, e.g. Revenue - FTTH")
    description: Optional[str] = None
    debit: float = Field(0, ge=0)
    credit: float = Field(0, ge=0)


class JournalEntryCreate(BaseModel):
    entry_date: date = Field(default_factory=date.today)
    reference: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = Field(None, description="BILLING, MANUAL, PAYROLL, ADJUSTMENT")
    source_id: Optional[str] = None
    lines: List[JournalLineInput] = Field(..., min_length=2)


class JournalEntryResponse(BaseModel):
    id: str
    tenant_id: str
    entry_date: str
    reference: Optional[str]
    description: Optional[str]
    source: Optional[str]
    source_id: Optional[str]
    is_posted: bool
    total_debit: float
    total_credit: float
    lines: List[dict]
    created_at: str


class TrialBalanceItem(BaseModel):
    account_code: str
    account_name: str
    debit_total: float
    credit_total: float
    balance: float  # positive = debit balance, negative = credit balance


class CashFlowItem(BaseModel):
    category: str  # OPERATING, INVESTING, FINANCING
    line: str
    amount: float


class ScenarioRequest(BaseModel):
    revenue_growth_pct: float = 0
    opex_change_pct: float = 0
    capex_change_pct: float = 0


class ScenarioResponse(BaseModel):
    revenue: float
    opex: float
    ebita: float
    ebit: float
    free_cash_flow: float


class FinancialRecordCreate(BaseModel):
    record_type: str
    description: Optional[str] = None
    amount: float
    period: Optional[str] = None


# ── Chart of Accounts (SA ISP) ─────────────────────────────────────────

CHART_OF_ACCOUNTS = {
    # Assets (1xxx)
    "1000": "Cash & Bank",
    "1100": "Accounts Receivable",
    "1200": "Inventory",
    "1500": "PP&E - Network Infrastructure",
    "1510": "PP&E - Equipment",
    "1600": "Accumulated Depreciation",
    # Liabilities (2xxx)
    "2000": "Accounts Payable",
    "2100": "Accrued Expenses",
    "2200": "Deferred Revenue",
    "2500": "Long-Term Debt",
    "2600": "Tax Payable",
    # Equity (3xxx)
    "3000": "Share Capital",
    "3100": "Retained Earnings",
    # Revenue (4xxx)
    "4000": "Revenue - FTTH Subscriptions",
    "4100": "Revenue - Installation Fees",
    "4200": "Revenue - Equipment Sales",
    "4900": "Other Revenue",
    # Cost of Service (5xxx)
    "5000": "Cost of Service - FNO Access",
    "5100": "Cost of Service - Equipment COGS",
    # Operating Expenses (6xxx)
    "6000": "Salaries & Wages",
    "6100": "Rent & Facilities",
    "6200": "Marketing & Advertising",
    "6300": "Software & Licenses",
    "6400": "Depreciation & Amortization",
    "6500": "Bad Debt Expense",
    "6900": "General & Administrative",
    # Other (7xxx-9xxx)
    "7000": "Interest Income",
    "8000": "Interest Expense",
    "9000": "Income Tax Expense",
}

# Account type classification for financial statements
ACCOUNT_TYPE_MAP = {}
for code, name in CHART_OF_ACCOUNTS.items():
    prefix = code[0]
    if prefix == "1":
        ACCOUNT_TYPE_MAP[code] = "ASSET"
    elif prefix == "2":
        ACCOUNT_TYPE_MAP[code] = "LIABILITY"
    elif prefix == "3":
        ACCOUNT_TYPE_MAP[code] = "EQUITY"
    elif prefix == "4" or prefix == "7":
        ACCOUNT_TYPE_MAP[code] = "REVENUE"
    else:
        ACCOUNT_TYPE_MAP[code] = "EXPENSE"

# Cash flow classification
CASH_FLOW_MAP = {
    "1000": "OPERATING",  # Cash changes classified by the transaction type
}
# Default: operating for revenue/expense, investing for PPE, financing for debt/equity
def _cash_flow_category(account_code: str) -> str:
    """Classify an account code into a cash flow category."""
    prefix = account_code[0]
    if prefix == "1":
        if account_code in ("1500", "1510", "1600"):
            return "INVESTING"
        return "OPERATING"
    if prefix == "2":
        if account_code == "2500":
            return "FINANCING"
        return "OPERATING"
    if prefix == "3":
        return "FINANCING"
    if prefix in ("4", "5", "6", "7", "8", "9"):
        return "OPERATING"
    return "OPERATING"


# ── App setup ──────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    await init_tables()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


# ── Helpers ────────────────────────────────────────────────────────────

def _entry_to_dict(entry: JournalEntry, lines: list[JournalEntryLine]) -> dict:
    total_debit = sum(float(l.debit or 0) for l in lines)
    total_credit = sum(float(l.credit or 0) for l in lines)
    return {
        "id": str(entry.id),
        "tenant_id": str(entry.tenant_id),
        "entry_date": entry.entry_date.isoformat() if entry.entry_date else None,
        "reference": entry.reference,
        "description": entry.description,
        "source": entry.source,
        "source_id": entry.source_id,
        "is_posted": entry.is_posted,
        "total_debit": round(total_debit, 2),
        "total_credit": round(total_credit, 2),
        "lines": [
            {
                "id": str(l.id),
                "account_code": l.account_code,
                "account_name": l.account_name,
                "description": l.description,
                "debit": float(l.debit or 0),
                "credit": float(l.credit or 0),
            }
            for l in lines
        ],
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


async def _ensure_sample_data(tenant_id: uuid.UUID, db: AsyncSession) -> None:
    """Seed sample GL entries if tenant has no journal entries."""
    result = await db.execute(
        select(func.count(JournalEntry.id)).where(
            JournalEntry.tenant_id == tenant_id
        )
    )
    if result.scalar() > 0:
        return

    # Sample: Revenue recognition for monthly subscriptions
    sample_entries = [
        {
            "entry_date": date(2026, 4, 1),
            "reference": "JE-2026-001",
            "description": "Monthly subscription revenue recognition",
            "source": "BILLING",
            "lines": [
                JournalLineInput(account_code="1100", account_name="Accounts Receivable",
                                 debit=48_000_000, credit=0,
                                 description="AR from monthly invoices"),
                JournalLineInput(account_code="4000", account_name="Revenue - FTTH Subscriptions",
                                 debit=0, credit=48_000_000,
                                 description="Revenue recognized"),
            ],
        },
        {
            "entry_date": date(2026, 4, 1),
            "reference": "JE-2026-002",
            "description": "FNO access cost recognition",
            "source": "BILLING",
            "lines": [
                JournalLineInput(account_code="5000", account_name="Cost of Service - FNO Access",
                                 debit=14_000_000, credit=0,
                                 description="FNO wholesale access fees"),
                JournalLineInput(account_code="2000", account_name="Accounts Payable",
                                 debit=0, credit=14_000_000,
                                 description="AP to FNOs"),
            ],
        },
        {
            "entry_date": date(2026, 4, 1),
            "reference": "JE-2026-003",
            "description": "Salaries and wages",
            "source": "PAYROLL",
            "lines": [
                JournalLineInput(account_code="6000", account_name="Salaries & Wages",
                                 debit=8_000_000, credit=0,
                                 description="Monthly payroll"),
                JournalLineInput(account_code="1000", account_name="Cash & Bank",
                                 debit=0, credit=8_000_000,
                                 description="Cash disbursement"),
            ],
        },
        {
            "entry_date": date(2026, 4, 1),
            "reference": "JE-2026-004",
            "description": "Depreciation - network infrastructure",
            "source": "ADJUSTMENT",
            "lines": [
                JournalLineInput(account_code="6400", account_name="Depreciation & Amortization",
                                 debit=500_000, credit=0,
                                 description="Monthly depreciation"),
                JournalLineInput(account_code="1600", account_name="Accumulated Depreciation",
                                 debit=0, credit=500_000,
                                 description="Accumulated depreciation"),
            ],
        },
        {
            "entry_date": date(2026, 4, 1),
            "reference": "JE-2026-005",
            "description": "Interest expense on long-term debt",
            "source": "ADJUSTMENT",
            "lines": [
                JournalLineInput(account_code="8000", account_name="Interest Expense",
                                 debit=150_000, credit=0,
                                 description="Monthly interest"),
                JournalLineInput(account_code="1000", account_name="Cash & Bank",
                                 debit=0, credit=150_000,
                                 description="Interest payment"),
            ],
        },
        {
            "entry_date": date(2026, 4, 1),
            "reference": "JE-2026-006",
            "description": "Income tax provision",
            "source": "ADJUSTMENT",
            "lines": [
                JournalLineInput(account_code="9000", account_name="Income Tax Expense",
                                 debit=2_856_000, credit=0,
                                 description="Tax provision"),
                JournalLineInput(account_code="2600", account_name="Tax Payable",
                                 debit=0, credit=2_856_000,
                                 description="Tax liability"),
            ],
        },
    ]

    for entry_data in sample_entries:
        lines_input = entry_data.pop("lines")
        entry = JournalEntry(tenant_id=tenant_id, **entry_data)
        db.add(entry)
        await db.flush()
        for line in lines_input:
            db.add(JournalEntryLine(
                journal_entry_id=entry.id,
                tenant_id=tenant_id,
                account_code=line.account_code,
                account_name=line.account_name,
                description=line.description,
                debit=line.debit,
                credit=line.credit,
            ))
    await db.flush()


# ════════════════════════════════════════════════════════════════════════
# 1. GL JOURNAL ENTRIES
# ════════════════════════════════════════════════════════════════════════

@app.post("/journal-entries", response_model=JournalEntryResponse)
async def create_journal_entry(
    payload: JournalEntryCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Create a double-entry journal entry. Debits must equal credits."""
    # Validate double-entry balance
    total_debit = sum(l.debit for l in payload.lines)
    total_credit = sum(l.credit for l in payload.lines)
    if abs(total_debit - total_credit) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Debits ({total_debit}) must equal credits ({total_credit})",
        )

    entry = JournalEntry(
        tenant_id=tenant_id,
        entry_date=payload.entry_date,
        reference=payload.reference or await next_journal_reference(db, tenant_id),
        description=payload.description,
        source=payload.source,
        source_id=payload.source_id,
    )
    db.add(entry)
    await db.flush()

    for line in payload.lines:
        db.add(JournalEntryLine(
            journal_entry_id=entry.id,
            tenant_id=tenant_id,
            account_code=line.account_code,
            account_name=line.account_name or CHART_OF_ACCOUNTS.get(line.account_code, "Unknown"),
            description=line.description,
            debit=line.debit,
            credit=line.credit,
        ))

    await db.refresh(entry)
    lines_result = await db.execute(
        select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry.id)
    )
    return _entry_to_dict(entry, lines_result.scalars().all())


@app.get("/journal-entries", response_model=List[JournalEntryResponse])
async def list_journal_entries(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    source: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    is_posted: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List journal entries with optional filters."""
    await _ensure_sample_data(tenant_id, db)

    query = select(JournalEntry).where(
        JournalEntry.tenant_id == tenant_id,
        JournalEntry.deleted_at.is_(None),
    )
    if source:
        query = query.where(JournalEntry.source == source)
    if from_date:
        query = query.where(JournalEntry.entry_date >= from_date)
    if to_date:
        query = query.where(JournalEntry.entry_date <= to_date)
    if is_posted is not None:
        query = query.where(JournalEntry.is_posted == is_posted)

    query = query.order_by(desc(JournalEntry.entry_date)).limit(limit).offset(offset)
    result = await db.execute(query)
    entries = result.scalars().all()

    response = []
    for entry in entries:
        lines_result = await db.execute(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry.id)
        )
        response.append(_entry_to_dict(entry, lines_result.scalars().all()))
    return response


@app.get("/journal-entries/{entry_id}", response_model=JournalEntryResponse)
async def get_journal_entry(
    entry_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(JournalEntry).where(
            JournalEntry.id == entry_id,
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.deleted_at.is_(None),
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    lines_result = await db.execute(
        select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry.id)
    )
    return _entry_to_dict(entry, lines_result.scalars().all())


@app.post("/journal-entries/{entry_id}/post")
async def post_journal_entry(
    entry_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Post a journal entry (mark as posted, no longer editable)."""
    result = await db.execute(
        select(JournalEntry).where(
            JournalEntry.id == entry_id,
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.deleted_at.is_(None),
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    if entry.is_posted:
        raise HTTPException(status_code=400, detail="Entry already posted")
    entry.is_posted = True
    return {"status": "posted", "id": str(entry_id)}


@app.delete("/journal-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_journal_entry(
    entry_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Soft-delete a journal entry (only if not posted).

    Rows are kept (deleted_at set) rather than physically removed, so GL
    history is never silently destroyed — mirrors the soft-delete convention
    used for master-data entities elsewhere in the platform.
    """
    result = await db.execute(
        select(JournalEntry).where(
            JournalEntry.id == entry_id,
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.deleted_at.is_(None),
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    if entry.is_posted:
        raise HTTPException(status_code=400, detail="Cannot delete posted entry — reverse with correcting entry")

    entry.deleted_at = datetime.utcnow()
    await db.flush()


# ════════════════════════════════════════════════════════════════════════
# 2. TRIAL BALANCE
# ════════════════════════════════════════════════════════════════════════

@app.get("/trial-balance")
async def trial_balance(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    as_of_date: Optional[date] = None,
):
    """Compute trial balance from posted GL entries.

    Returns account-level debit/credit totals and running balance.
    Total debits must equal total credits for a balanced trial balance.
    """
    await _ensure_sample_data(tenant_id, db)

    query = (
        select(
            JournalEntryLine.account_code,
            JournalEntryLine.account_name,
            func.sum(JournalEntryLine.debit).label("total_debit"),
            func.sum(JournalEntryLine.credit).label("total_credit"),
        )
        .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalEntryLine.tenant_id == tenant_id,
            JournalEntry.is_posted == True,
        )
    )
    if as_of_date:
        query = query.where(JournalEntry.entry_date <= as_of_date)

    query = query.group_by(
        JournalEntryLine.account_code, JournalEntryLine.account_name
    ).order_by(JournalEntryLine.account_code)

    result = await db.execute(query)
    rows = result.all()

    items = []
    total_debits = 0
    total_credits = 0
    for row in rows:
        debit = float(row.total_debit or 0)
        credit = float(row.total_credit or 0)
        balance = debit - credit
        items.append({
            "account_code": row.account_code,
            "account_name": row.account_name,
            "debit_total": round(debit, 2),
            "credit_total": round(credit, 2),
            "balance": round(balance, 2),
        })
        total_debits += debit
        total_credits += credit

    return {
        "as_of_date": as_of_date.isoformat() if as_of_date else "all",
        "accounts": items,
        "total_debits": round(total_debits, 2),
        "total_credits": round(total_credits, 2),
        "is_balanced": abs(total_debits - total_credits) < 0.01,
        "currency": "ZAR",
    }


# ════════════════════════════════════════════════════════════════════════
# 3. CASH FLOW STATEMENT
# ════════════════════════════════════════════════════════════════════════

@app.get("/cash-flow")
async def cash_flow_statement(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
):
    """Generate a cash flow statement (direct method) from GL entries.

    Classifies cash-related entries into:
        - Operating activities
        - Investing activities
        - Financing activities
    """
    await _ensure_sample_data(tenant_id, db)

    query = (
        select(
            JournalEntryLine.account_code,
            func.sum(JournalEntryLine.debit).label("total_debit"),
            func.sum(JournalEntryLine.credit).label("total_credit"),
        )
        .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalEntryLine.tenant_id == tenant_id,
            JournalEntry.is_posted == True,
        )
    )
    if from_date:
        query = query.where(JournalEntry.entry_date >= from_date)
    if to_date:
        query = query.where(JournalEntry.entry_date <= to_date)

    query = query.group_by(JournalEntryLine.account_code)
    result = await db.execute(query)
    rows = result.all()

    operating = []
    investing = []
    financing = []

    for row in rows:
        code = row.account_code
        debit = float(row.total_debit or 0)
        credit = float(row.total_credit or 0)
        net = credit - debit  # positive = cash inflow, negative = outflow

        # Only include cash-related accounts (1000 = Cash & Bank is the balancing entry)
        # For the cash flow statement, we show the non-cash account side
        if code == "1000":
            continue

        name = CHART_OF_ACCOUNTS.get(code, "Unknown")
        category = _cash_flow_category(code)
        item = {"account_code": code, "account_name": name, "amount": round(net, 2)}

        if category == "INVESTING":
            investing.append(item)
        elif category == "FINANCING":
            financing.append(item)
        else:
            operating.append(item)

    operating_total = sum(i["amount"] for i in operating)
    investing_total = sum(i["amount"] for i in investing)
    financing_total = sum(i["amount"] for i in financing)
    net_change = operating_total + investing_total + financing_total

    return {
        "from_date": from_date.isoformat() if from_date else "all",
        "to_date": to_date.isoformat() if to_date else "all",
        "currency": "ZAR",
        "operating_activities": {
            "items": operating,
            "total": round(operating_total, 2),
        },
        "investing_activities": {
            "items": investing,
            "total": round(investing_total, 2),
        },
        "financing_activities": {
            "items": financing,
            "total": round(financing_total, 2),
        },
        "net_change_in_cash": round(net_change, 2),
    }


# ════════════════════════════════════════════════════════════════════════
# 4. FINANCIAL STATEMENTS (from GL)
# ════════════════════════════════════════════════════════════════════════

@app.get("/statements")
async def statements(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Generate income statement and balance sheet from GL trial balance."""
    await _ensure_sample_data(tenant_id, db)

    # Get all posted GL balances
    query = (
        select(
            JournalEntryLine.account_code,
            JournalEntryLine.account_name,
            func.sum(JournalEntryLine.debit).label("total_debit"),
            func.sum(JournalEntryLine.credit).label("total_credit"),
        )
        .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalEntryLine.tenant_id == tenant_id,
            JournalEntry.is_posted == True,
        )
        .group_by(JournalEntryLine.account_code, JournalEntryLine.account_name)
    )
    result = await db.execute(query)
    balances = {row.account_code: {
        "name": row.account_name,
        "debit": float(row.total_debit or 0),
        "credit": float(row.total_credit or 0),
        "balance": float(row.total_debit or 0) - float(row.total_credit or 0),
    } for row in result.all()}

    # ── Income Statement ──
    revenue_accounts = {k: v for k, v in balances.items() if ACCOUNT_TYPE_MAP.get(k) == "REVENUE"}
    expense_accounts = {k: v for k, v in balances.items() if ACCOUNT_TYPE_MAP.get(k) == "EXPENSE"}

    total_revenue = sum(v["balance"] for v in revenue_accounts.values())
    total_cogs = sum(v["balance"] for v in expense_accounts.values() if k.startswith("5") for k, v in expense_accounts.items())
    # Simplified: accounts 5xxx = COS, 6xxx+8xxx+9xxx = OpEx
    cogs = sum(v["balance"] for k, v in expense_accounts.items() if k.startswith("5"))
    gross_profit = total_revenue - cogs
    opex = sum(v["balance"] for k, v in expense_accounts.items() if not k.startswith("5"))
    ebit = gross_profit - opex
    interest_expense = balances.get("8000", {}).get("balance", 0)
    tax_expense = balances.get("9000", {}).get("balance", 0)
    net_income = ebit - interest_expense - tax_expense

    income_statement = [
        {"line": "Revenue", "amount": round(total_revenue, 2)},
        {"line": "Cost of Service", "amount": round(-cogs, 2)},
        {"line": "Gross Profit", "amount": round(gross_profit, 2)},
        {"line": "Operating Expenses", "amount": round(-opex, 2)},
        {"line": "EBIT", "amount": round(ebit, 2)},
        {"line": "Interest Expense", "amount": round(-interest_expense, 2)},
        {"line": "Tax Expense", "amount": round(-tax_expense, 2)},
        {"line": "Net Income", "amount": round(net_income, 2)},
    ]

    # ── Balance Sheet ──
    assets = {k: v for k, v in balances.items() if ACCOUNT_TYPE_MAP.get(k) == "ASSET"}
    liabilities = {k: v for k, v in balances.items() if ACCOUNT_TYPE_MAP.get(k) == "LIABILITY"}
    equity = {k: v for k, v in balances.items() if ACCOUNT_TYPE_MAP.get(k) == "EQUITY"}

    total_assets = sum(v["balance"] for v in assets.values())
    total_liabilities = sum(-v["balance"] for v in liabilities.values())  # liabilities have credit balances
    total_equity = sum(-v["balance"] for v in equity.values()) + net_income  # add retained earnings

    balance_sheet = [
        {"line": "ASSETS", "amount": "", "section": True},
        *[{"line": f"  {v['name']}", "amount": round(v['balance'], 2)} for v in assets.values()],
        {"line": "Total Assets", "amount": round(total_assets, 2), "total": True},
        {"line": "", "amount": ""},
        {"line": "LIABILITIES", "amount": "", "section": True},
        *[{"line": f"  {v['name']}", "amount": round(-v['balance'], 2)} for v in liabilities.values()],
        {"line": "Total Liabilities", "amount": round(total_liabilities, 2), "total": True},
        {"line": "", "amount": ""},
        {"line": "EQUITY", "amount": "", "section": True},
        *[{"line": f"  {v['name']}", "amount": round(-v['balance'], 2)} for v in equity.values()],
        {"line": "Retained Earnings (Net Income)", "amount": round(net_income, 2)},
        {"line": "Total Equity", "amount": round(total_equity, 2), "total": True},
        {"line": "", "amount": ""},
        {"line": "Total Liabilities + Equity", "amount": round(total_liabilities + total_equity, 2), "total": True},
    ]

    return {
        "income_statement": income_statement,
        "balance_sheet": balance_sheet,
        "currency": "ZAR",
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


# ════════════════════════════════════════════════════════════════════════
# 5. BILLING INTEGRATION
# ════════════════════════════════════════════════════════════════════════

@app.post("/billing/sync-invoices")
async def sync_billing_invoices(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Pull invoices from billing service and create GL journal entries.

    Cross-service integration: fetches unpaid invoices from billing service,
    creates corresponding GL entries for revenue recognition.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{BILLING_SERVICE_URL}/invoices",
                params={"tenant_id": str(tenant_id), "status": "sent"},
            )
            if r.status_code >= 400:
                return {"status": "billing_unavailable", "invoices_synced": 0}
            # billing's /invoices returns a PaginatedResponse ({"items": [...], "total": ...}),
            # not a bare list.
            invoices = r.json().get("items", [])
    except httpx.RequestError as exc:
        logger.warning("Billing service unreachable: %s", exc)
        return {"status": "billing_unavailable", "error": str(exc), "invoices_synced": 0}

    synced = 0
    for inv in invoices:
        invoice_id = inv.get("id")
        # Check if already synced
        existing = await db.execute(
            select(JournalEntry).where(
                JournalEntry.tenant_id == tenant_id,
                JournalEntry.source == "BILLING",
                JournalEntry.source_id == invoice_id,
            )
        )
        if existing.scalar_one_or_none():
            continue

        amount = float(inv.get("total_zar", 0))
        customer_id = inv.get("customer_id", "")

        entry = JournalEntry(
            tenant_id=tenant_id,
            entry_date=date.today(),
            reference=f"INV-{inv.get('number', invoice_id[:8])}",
            description=f"Revenue recognition - Invoice {inv.get('number', '')}",
            source="BILLING",
            source_id=invoice_id,
        )
        db.add(entry)
        await db.flush()

        # Debit AR, Credit Revenue
        db.add(JournalEntryLine(
            journal_entry_id=entry.id,
            tenant_id=tenant_id,
            account_code="1100",
            account_name="Accounts Receivable",
            description=f"AR - Customer {customer_id[:8]}",
            debit=amount,
            credit=0,
        ))
        db.add(JournalEntryLine(
            journal_entry_id=entry.id,
            tenant_id=tenant_id,
            account_code="4000",
            account_name="Revenue - FTTH Subscriptions",
            description=f"Revenue - Invoice {inv.get('invoice_number', '')}",
            debit=0,
            credit=amount,
        ))
        synced += 1

    return {"status": "synced", "invoices_synced": synced}


@app.get("/billing/revenue-summary")
async def revenue_summary(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Get revenue summary from billing integration."""
    result = await db.execute(
        select(
            func.count(JournalEntry.id).label("invoice_count"),
            func.sum(JournalEntryLine.credit).label("total_revenue"),
        )
        .join(JournalEntryLine, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.source == "BILLING",
            JournalEntryLine.account_code == "4000",
        )
    )
    row = result.one()
    return {
        "invoices_synced": row.invoice_count or 0,
        "total_revenue": float(row.total_revenue or 0),
        "currency": "ZAR",
    }


# ════════════════════════════════════════════════════════════════════════
# 6. OVERVIEW & SCENARIOS (kept from v1)
# ════════════════════════════════════════════════════════════════════════

@app.get("/overview")
async def overview(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Financial overview computed from GL trial balance."""
    await _ensure_sample_data(tenant_id, db)

    query = (
        select(
            JournalEntryLine.account_code,
            func.sum(JournalEntryLine.debit).label("total_debit"),
            func.sum(JournalEntryLine.credit).label("total_credit"),
        )
        .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalEntryLine.tenant_id == tenant_id,
            JournalEntry.is_posted == True,
        )
        .group_by(JournalEntryLine.account_code)
    )
    result = await db.execute(query)
    balances = {row.account_code: float(row.total_debit or 0) - float(row.total_credit or 0)
                for row in result.all()}

    revenue = sum(-v for k, v in balances.items() if ACCOUNT_TYPE_MAP.get(k) == "REVENUE")
    expenses = sum(v for k, v in balances.items() if ACCOUNT_TYPE_MAP.get(k) == "EXPENSE")
    ebit = revenue - expenses
    cash = balances.get("1000", 0)

    return {
        "tenant_id": str(tenant_id),
        "currency": "ZAR",
        "kpis": {
            "revenue": round(revenue, 2),
            "expenses": round(expenses, 2),
            "ebit": round(ebit, 2),
            "cash_position": round(cash, 2),
        },
        "period": "FY2026 YTD",
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@app.post("/scenario", response_model=ScenarioResponse)
async def scenario(
    payload: ScenarioRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Run a what-if scenario and save it."""
    BASE_REVENUE = 48_000_000
    BASE_OPEX = 30_000_000
    BASE_DEPRECIATION = 6_000_000
    BASE_INTEREST = 1_800_000
    BASE_CAPEX = 9_000_000
    TAX_RATE = 0.28

    revenue = BASE_REVENUE * (1 + payload.revenue_growth_pct / 100)
    opex = BASE_OPEX * (1 + payload.opex_change_pct / 100)
    capex = BASE_CAPEX * (1 + payload.capex_change_pct / 100)
    depreciation = BASE_DEPRECIATION * (1 + (payload.capex_change_pct / 100) * 0.4)
    ebita = revenue - opex
    ebit = ebita - depreciation
    taxable = max(0, ebit - BASE_INTEREST)
    tax = taxable * TAX_RATE
    free_cash_flow = ebita - capex - BASE_INTEREST - tax

    result = ScenarioResponse(
        revenue=round(revenue, 2),
        opex=round(opex, 2),
        ebita=round(ebita, 2),
        ebit=round(ebit, 2),
        free_cash_flow=round(free_cash_flow, 2),
    )

    db.add(BudgetScenario(
        tenant_id=tenant_id,
        name=f"Scenario {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        revenue_growth_pct=payload.revenue_growth_pct,
        opex_change_pct=payload.opex_change_pct,
        capex_change_pct=payload.capex_change_pct,
        result_revenue=result.revenue,
        result_opex=result.opex,
        result_ebita=result.ebita,
        result_ebit=result.ebit,
        result_fcf=result.free_cash_flow,
    ))
    return result


# ── Legacy Financial Records CRUD (kept for backward compat) ───────────

@app.post("/records")
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
    return {
        "id": str(record.id),
        "record_type": record.record_type,
        "amount": float(record.amount),
        "period": record.period,
    }


@app.get("/records")
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
    return [{"id": str(r.id), "record_type": r.record_type,
             "amount": float(r.amount), "period": r.period} for r in records]


@app.get("/records/{record_id}")
async def get_record(
    record_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(FinancialRecord).where(
            FinancialRecord.id == record_id,
            FinancialRecord.tenant_id == tenant_id,
        )
    )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"id": str(r.id), "record_type": r.record_type,
            "amount": float(r.amount), "period": r.period}


@app.delete("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_record(
    record_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(FinancialRecord).where(
            FinancialRecord.id == record_id,
            FinancialRecord.tenant_id == tenant_id,
        )
    )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    await db.delete(r)
    await db.flush()


# ── Revenue Recognition ─────────────────────────────────────────────────

class RevenueContractCreate(BaseModel):
    contract_reference: str
    customer_name: str
    method: str = "straight_line"
    total_contract_value: float = 0
    start_date: date
    end_date: date
    recognized_to_date: float = 0
    deferred_balance: float = 0


def _contract_out(c: RevenueContract) -> dict:
    return {
        "id": str(c.id), "contract": c.contract_reference, "customer": c.customer_name,
        "method": c.method, "start": c.start_date.isoformat(), "end": c.end_date.isoformat(),
        "recognized": float(c.recognized_to_date), "deferred": float(c.deferred_balance),
        "total_contract_value": float(c.total_contract_value),
    }


@app.get("/revenue-contracts")
async def list_revenue_contracts(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(RevenueContract).where(RevenueContract.tenant_id == tenant_id).order_by(desc(RevenueContract.created_at)))
    return [_contract_out(c) for c in result.scalars().all()]


@app.post("/revenue-contracts", status_code=status.HTTP_201_CREATED)
async def create_revenue_contract(
    payload: RevenueContractCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    c = RevenueContract(tenant_id=tenant_id, **payload.model_dump())
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return _contract_out(c)


# ── Expense Governance: Receipts, Approvals, Purchase Orders, Assets, Recurring Payments ──

class ExpenseReceiptCreate(BaseModel):
    vendor: str
    amount: float = 0
    category: Optional[str] = None
    status: str = "processed"
    ocr_confidence: Optional[int] = None
    submitted_by: Optional[str] = None
    receipt_date: date = Field(default_factory=date.today)


@app.get("/expense-receipts")
async def list_expense_receipts(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(ExpenseReceipt).where(ExpenseReceipt.tenant_id == tenant_id).order_by(desc(ExpenseReceipt.created_at)))
    return [{"id": str(r.id), "vendor": r.vendor, "amount": float(r.amount), "category": r.category,
             "status": r.status, "ocrConfidence": r.ocr_confidence, "submittedBy": r.submitted_by,
             "date": r.receipt_date.isoformat()} for r in result.scalars().all()]


@app.post("/expense-receipts", status_code=status.HTTP_201_CREATED)
async def create_expense_receipt(payload: ExpenseReceiptCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    r = ExpenseReceipt(tenant_id=tenant_id, **payload.model_dump())
    db.add(r)
    await db.flush()
    await db.refresh(r)
    return {"id": str(r.id), "vendor": r.vendor, "amount": float(r.amount), "category": r.category,
            "status": r.status, "ocrConfidence": r.ocr_confidence, "submittedBy": r.submitted_by,
            "date": r.receipt_date.isoformat()}


class ApprovalRequestCreate(BaseModel):
    request: str
    amount: float = 0
    owner: Optional[str] = None
    status: str = "pending"
    policy: Optional[str] = None


@app.get("/approval-requests")
async def list_approval_requests(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(ApprovalRequest).where(ApprovalRequest.tenant_id == tenant_id).order_by(desc(ApprovalRequest.created_at)))
    return [{"id": str(a.id), "request": a.request, "amount": float(a.amount), "owner": a.owner,
             "status": a.status, "policy": a.policy} for a in result.scalars().all()]


@app.post("/approval-requests", status_code=status.HTTP_201_CREATED)
async def create_approval_request(payload: ApprovalRequestCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    a = ApprovalRequest(tenant_id=tenant_id, **payload.model_dump())
    db.add(a)
    await db.flush()
    await db.refresh(a)
    return {"id": str(a.id), "request": a.request, "amount": float(a.amount), "owner": a.owner,
            "status": a.status, "policy": a.policy}


class PurchaseOrderCreate(BaseModel):
    vendor: str
    amount: float = 0
    status: str = "draft"
    approver: Optional[str] = None
    due_date: Optional[date] = None


@app.get("/purchase-orders")
async def list_purchase_orders(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(FinancePurchaseOrder).where(FinancePurchaseOrder.tenant_id == tenant_id).order_by(desc(FinancePurchaseOrder.created_at)))
    return [{"id": str(p.id), "vendor": p.vendor, "amount": float(p.amount), "status": p.status,
             "approver": p.approver, "dueDate": p.due_date.isoformat() if p.due_date else None} for p in result.scalars().all()]


@app.post("/purchase-orders", status_code=status.HTTP_201_CREATED)
async def create_purchase_order(payload: PurchaseOrderCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    p = FinancePurchaseOrder(tenant_id=tenant_id, **payload.model_dump())
    db.add(p)
    await db.flush()
    await db.refresh(p)
    return {"id": str(p.id), "vendor": p.vendor, "amount": float(p.amount), "status": p.status,
            "approver": p.approver, "dueDate": p.due_date.isoformat() if p.due_date else None}


class FixedAssetCreate(BaseModel):
    asset_name: str
    location: Optional[str] = None
    status: str = "active"
    cost: float = 0
    accumulated_depreciation: float = 0
    useful_life_years: Optional[float] = None


@app.get("/fixed-assets")
async def list_fixed_assets(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(FixedAsset).where(FixedAsset.tenant_id == tenant_id).order_by(desc(FixedAsset.created_at)))
    return [{"id": str(a.id), "asset": a.asset_name, "location": a.location, "status": a.status,
             "cost": float(a.cost), "depreciation": float(a.accumulated_depreciation),
             "remainingLife": f"{float(a.useful_life_years)} years" if a.useful_life_years else None} for a in result.scalars().all()]


@app.post("/fixed-assets", status_code=status.HTTP_201_CREATED)
async def create_fixed_asset(payload: FixedAssetCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    a = FixedAsset(tenant_id=tenant_id, **payload.model_dump())
    db.add(a)
    await db.flush()
    await db.refresh(a)
    return {"id": str(a.id), "asset": a.asset_name, "location": a.location, "status": a.status,
            "cost": float(a.cost), "depreciation": float(a.accumulated_depreciation),
            "remainingLife": f"{float(a.useful_life_years)} years" if a.useful_life_years else None}


class RecurringPaymentCreate(BaseModel):
    vendor: str
    amount: float = 0
    frequency: str = "Monthly"
    next_run: Optional[date] = None
    status: str = "active"


@app.get("/recurring-payments")
async def list_recurring_payments(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(RecurringPayment).where(RecurringPayment.tenant_id == tenant_id).order_by(desc(RecurringPayment.created_at)))
    return [{"id": str(r.id), "vendor": r.vendor, "amount": float(r.amount), "frequency": r.frequency,
             "nextRun": r.next_run.isoformat() if r.next_run else None, "status": r.status} for r in result.scalars().all()]


@app.post("/recurring-payments", status_code=status.HTTP_201_CREATED)
async def create_recurring_payment(payload: RecurringPaymentCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    r = RecurringPayment(tenant_id=tenant_id, **payload.model_dump())
    db.add(r)
    await db.flush()
    await db.refresh(r)
    return {"id": str(r.id), "vendor": r.vendor, "amount": float(r.amount), "frequency": r.frequency,
            "nextRun": r.next_run.isoformat() if r.next_run else None, "status": r.status}


# ── Bank Reconciliation ─────────────────────────────────────────────────

class BankStatementItemCreate(BaseModel):
    item_date: date = Field(default_factory=date.today)
    description: str
    amount: float = 0
    status: str = "unmatched"
    source: Optional[str] = None


@app.get("/bank-items")
async def list_bank_items(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(BankStatementItem).where(BankStatementItem.tenant_id == tenant_id).order_by(desc(BankStatementItem.item_date)))
    return [{"id": str(b.id), "date": b.item_date.isoformat(), "description": b.description,
             "amount": float(b.amount), "status": b.status, "source": b.source} for b in result.scalars().all()]


@app.post("/bank-items", status_code=status.HTTP_201_CREATED)
async def create_bank_item(payload: BankStatementItemCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    b = BankStatementItem(tenant_id=tenant_id, **payload.model_dump())
    db.add(b)
    await db.flush()
    await db.refresh(b)
    return {"id": str(b.id), "date": b.item_date.isoformat(), "description": b.description,
            "amount": float(b.amount), "status": b.status, "source": b.source}


# ── Health ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "finance"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8015)
