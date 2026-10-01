"""OmniDome Finance Service — GAAP-aligned financials, GL, and billing integration.

Port: 8015

Features:
    - GL Journal Entries (double-entry, Decimal, exact balance, immutable once posted)
    - Reversals, accounting period lock, per-tenant chart of accounts
    - Trial Balance, Cash Flow, Income Statement & Balance Sheet (posted entries only)
    - Billing service integration (invoice -> GL sync)
    - Budget Scenarios (what-if)

No demo data is ever written: a tenant with no entries sees empty/zero reports.
"""

import logging
import os
from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional
import uuid

import httpx
from fastapi import FastAPI, Depends, HTTPException, Request, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
from services.common.auth import AuthContext, get_auth_context, get_current_tenant_id
from services.finance import access, ledger
from services.finance.access import require_tier
from services.finance.ledger import (
    ACCOUNT_TYPE_MAP, CHART_OF_ACCOUNTS, CODE_RE, PERIOD_RE, ZERO, account_type, entry_to_dict, money_float, to_money,
)
from services.finance.database import (
    get_session, init_tables,
    JournalEntry, JournalEntryLine,
    FinancialRecord, BudgetScenario,
    FinanceAccount, FinancePeriod,
    RevenueContract, ExpenseReceipt, ApprovalRequest, FinancePurchaseOrder,
    FixedAsset, RecurringPayment, BankStatementItem,
)

logger = logging.getLogger("finance")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(
    title="OmniDome Finance Service",
    version="2.1.0",
    description="GAAP-aligned GL, trial balance, cash flow, and billing integration for ISPs.",
)

guard = EntitlementGuard(module_id="finance")

configure_production(app)

# ── Billing service URL for cross-service integration ──────────────────
BILLING_SERVICE_URL = os.getenv("BILLING_SERVICE_URL", "http://billing:8003")

reader = require_tier("reader")
clerk = require_tier("clerk")
admin = require_tier("admin")
journal_writer = require_tier("clerk", internal_ok=True)


# ── Pydantic models ────────────────────────────────────────────────────

class JournalLineInput(BaseModel):
    account_code: str = Field(..., description="Chart of accounts code, e.g. 4000")
    account_name: Optional[str] = Field(None, description="Ignored: the name comes from the tenant chart")
    description: Optional[str] = None
    debit: Decimal = Field(Decimal("0"), ge=0, description="string or number")
    credit: Decimal = Field(Decimal("0"), ge=0, description="string or number")


class JournalEntryCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    entry_date: Optional[date] = Field(default=None, validation_alias=AliasChoices("entry_date", "date"))
    reference: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = Field(None, max_length=50, description="e.g. billing.invoice, sales.commission, MANUAL")
    source_id: Optional[str] = Field(None, max_length=100)
    auto_post: bool = Field(False, description="System callers (internal key) or finance admins only")
    lines: List[JournalLineInput] = Field(..., min_length=2)


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
    record_type: str = Field(..., max_length=50)
    description: Optional[str] = Field(None, max_length=500)
    amount: Decimal = Field(..., ge=0)
    period: Optional[str] = Field(None, max_length=20)


# Cash flow classification
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
    return "OPERATING"


CASH_ACCOUNTS = ("1000", "1010")


# ── App setup ──────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    await init_tables()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


# ════════════════════════════════════════════════════════════════════════
# 0. CHART OF ACCOUNTS & ACCOUNTING PERIODS
# ════════════════════════════════════════════════════════════════════════

class AccountCreate(BaseModel):
    code: str
    name: str = Field(..., min_length=1, max_length=200)


@app.get("/accounts")
async def list_accounts(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(reader),
):
    chart = await ledger.ensure_chart(db, tenant_id)
    return [{"code": c, "name": n, "type": account_type(c)} for c, n in sorted(chart.items())]


@app.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(admin),
):
    if not CODE_RE.match(payload.code):
        raise HTTPException(status_code=422, detail="Account code must be 4 digits starting 1-9 (1=asset ... 9=tax)")
    chart = await ledger.ensure_chart(db, tenant_id)
    if payload.code in chart:
        raise HTTPException(status_code=409, detail="Account code already exists")
    db.add(FinanceAccount(tenant_id=tenant_id, code=payload.code, name=payload.name))
    await db.flush()
    return {"code": payload.code, "name": payload.name, "type": account_type(payload.code)}


def _check_period(period: str) -> None:
    if not PERIOD_RE.match(period):
        raise HTTPException(status_code=422, detail="Period must be YYYY-MM")


@app.get("/periods")
async def list_periods(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(reader),
):
    rows = (await db.execute(select(FinancePeriod).where(FinancePeriod.tenant_id == tenant_id)
                             .order_by(desc(FinancePeriod.period)))).scalars().all()
    return [{"period": r.period, "status": r.status, "closed_by": r.closed_by,
             "closed_at": r.closed_at.isoformat() if r.closed_at else None} for r in rows]


async def _set_period(db, tenant_id, period: str, new_status: str, auth: AuthContext) -> dict:
    _check_period(period)
    row = (await db.execute(select(FinancePeriod).where(
        FinancePeriod.tenant_id == tenant_id, FinancePeriod.period == period).with_for_update())).scalar_one_or_none()
    if row is None:
        row = FinancePeriod(tenant_id=tenant_id, period=period, status="open")
        db.add(row)
    row.status = new_status
    row.closed_by = str(auth.user_id) if new_status == "closed" else None
    row.closed_at = datetime.utcnow() if new_status == "closed" else None
    await db.flush()
    return {"period": period, "status": row.status, "closed_by": row.closed_by}


@app.post("/periods/{period}/close")
async def close_period(period: str, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                       db: AsyncSession = Depends(get_session), auth: AuthContext = Depends(admin)):
    return await _set_period(db, tenant_id, period, "closed", auth)


@app.post("/periods/{period}/reopen")
async def reopen_period(period: str, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                        db: AsyncSession = Depends(get_session), auth: AuthContext = Depends(admin)):
    return await _set_period(db, tenant_id, period, "open", auth)


# ════════════════════════════════════════════════════════════════════════
# 1. GL JOURNAL ENTRIES
# ════════════════════════════════════════════════════════════════════════

@app.post("/journal-entries")
async def create_journal_entry(
    payload: JournalEntryCreate,
    request: Request,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(journal_writer),
):
    """Create a double-entry journal entry.

    Body: {date|entry_date, description, source, source_id, auto_post, lines:[{account_code, debit, credit}]}
    (amounts as strings or numbers). Debits must equal credits exactly. A repeated
    (source, source_id) returns 200 {"status": "duplicate", "id": ...} and creates nothing.
    auto_post posts in the same transaction and needs the internal key or a finance admin role.
    Errors: 400 imbalance, 403 auto_post not allowed, 409 closed period, 422 bad line / unknown account.
    """
    if payload.auto_post and not await access.has_tier(auth, db, "admin", request, internal_ok=True):
        raise HTTPException(status_code=403, detail="auto_post needs a system caller or a finance admin role")
    entry, lines, duplicate = await ledger.create_entry(
        db, tenant_id,
        entry_date=payload.entry_date or date.today(), description=payload.description,
        source=payload.source, source_id=payload.source_id, reference=payload.reference,
        lines=[l.model_dump() for l in payload.lines], auto_post=payload.auto_post,
    )
    if duplicate:
        return {"status": "duplicate", "id": str(entry.id), "entry_id": str(entry.id), "is_posted": bool(entry.is_posted)}
    out = entry_to_dict(entry, lines)
    out["status"] = "posted" if entry.is_posted else "created"
    out["entry_id"] = out["id"]
    return out


@app.get("/journal-entries")
async def list_journal_entries(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(reader),
    source: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    is_posted: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List journal entries with optional filters (read-only: never seeds anything)."""
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

    query = query.order_by(desc(JournalEntry.entry_date)).limit(max(1, min(limit, 500))).offset(max(0, offset))
    entries = (await db.execute(query)).scalars().all()
    return [entry_to_dict(e, await ledger.entry_lines(db, e.id)) for e in entries]


async def _load_entry(db, tenant_id, entry_id) -> JournalEntry:
    entry = (await db.execute(select(JournalEntry).where(
        JournalEntry.id == entry_id, JournalEntry.tenant_id == tenant_id,
        JournalEntry.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return entry


@app.get("/journal-entries/{entry_id}")
async def get_journal_entry(
    entry_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(reader),
):
    entry = await _load_entry(db, tenant_id, entry_id)
    return entry_to_dict(entry, await ledger.entry_lines(db, entry.id))


@app.post("/journal-entries/{entry_id}/post")
async def post_journal_entry(
    entry_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(admin),
):
    """Post a draft entry. Posted entries are immutable; correct them with /reverse."""
    entry = await _load_entry(db, tenant_id, entry_id)
    if entry.is_posted:
        raise HTTPException(status_code=400, detail="Entry already posted")
    await ledger.assert_period_open(db, tenant_id, entry.entry_date)
    entry.is_posted = True
    await db.flush()
    return {"status": "posted", "id": str(entry_id)}


@app.post("/journal-entries/{entry_id}/reverse")
async def reverse_journal_entry(
    entry_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(admin),
):
    """Reverse a POSTED entry with a posted entry of swapped debits/credits dated today.
    Idempotent: source 'finance.reversal', source_id = original id."""
    entry = await _load_entry(db, tenant_id, entry_id)
    if not entry.is_posted:
        raise HTTPException(status_code=400, detail="Only posted entries can be reversed; delete a draft instead")
    lines = await ledger.entry_lines(db, entry.id)
    rev, rev_lines, duplicate = await ledger.create_entry(
        db, tenant_id, entry_date=date.today(),
        description=f"Reversal of {entry.reference or entry.id}",
        source="finance.reversal", source_id=str(entry.id), reference=None,
        lines=[{"account_code": l.account_code, "description": l.description,
                "debit": l.credit, "credit": l.debit} for l in lines],
        auto_post=True,
    )
    if duplicate:
        return {"status": "duplicate", "id": str(rev.id), "entry_id": str(rev.id), "reverses": str(entry.id)}
    out = entry_to_dict(rev, rev_lines)
    out.update({"status": "reversed", "entry_id": out["id"], "reverses": str(entry.id)})
    return out


@app.delete("/journal-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_journal_entry(
    entry_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(clerk),
):
    """Soft-delete a DRAFT journal entry. Posted entries are immutable (reverse them)."""
    entry = await _load_entry(db, tenant_id, entry_id)
    if entry.is_posted:
        raise HTTPException(status_code=400, detail="Cannot delete posted entry; reverse it with POST /journal-entries/{id}/reverse")
    entry.deleted_at = datetime.utcnow()
    await db.flush()


# ════════════════════════════════════════════════════════════════════════
# 2. TRIAL BALANCE
# ════════════════════════════════════════════════════════════════════════

def _d(value) -> Decimal:
    return Decimal(str(value if value is not None else 0)).quantize(ledger.CENT)


@app.get("/trial-balance")
async def trial_balance(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(reader),
    as_of_date: Optional[date] = None,
):
    """Trial balance from POSTED GL entries (Decimal sums). Empty for a tenant with none."""
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
            JournalEntry.is_posted == True,  # noqa: E712
            JournalEntry.deleted_at.is_(None),
        )
    )
    if as_of_date:
        query = query.where(JournalEntry.entry_date <= as_of_date)

    query = query.group_by(
        JournalEntryLine.account_code, JournalEntryLine.account_name
    ).order_by(JournalEntryLine.account_code)

    rows = (await db.execute(query)).all()

    items = []
    total_debits = ZERO
    total_credits = ZERO
    for row in rows:
        debit, credit = _d(row.total_debit), _d(row.total_credit)
        items.append({
            "account_code": row.account_code,
            "account_name": row.account_name,
            "debit_total": money_float(debit),
            "credit_total": money_float(credit),
            "balance": money_float(debit - credit),
        })
        total_debits += debit
        total_credits += credit

    return {
        "as_of_date": as_of_date.isoformat() if as_of_date else "all",
        "accounts": items,
        "total_debits": money_float(total_debits),
        "total_credits": money_float(total_credits),
        "is_balanced": total_debits == total_credits,
        "currency": "ZAR",
    }


# ════════════════════════════════════════════════════════════════════════
# 3. CASH FLOW STATEMENT
# ════════════════════════════════════════════════════════════════════════

@app.get("/cash-flow")
async def cash_flow_statement(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(reader),
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
):
    """Cash flow statement (direct method) from posted GL entries: operating / investing / financing."""
    query = (
        select(
            JournalEntryLine.account_code,
            func.sum(JournalEntryLine.debit).label("total_debit"),
            func.sum(JournalEntryLine.credit).label("total_credit"),
        )
        .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalEntryLine.tenant_id == tenant_id,
            JournalEntry.is_posted == True,  # noqa: E712
            JournalEntry.deleted_at.is_(None),
        )
    )
    if from_date:
        query = query.where(JournalEntry.entry_date >= from_date)
    if to_date:
        query = query.where(JournalEntry.entry_date <= to_date)

    query = query.group_by(JournalEntryLine.account_code)
    rows = (await db.execute(query)).all()

    operating, investing, financing = [], [], []
    for row in rows:
        code = row.account_code
        net = _d(row.total_credit) - _d(row.total_debit)  # positive = inflow
        if code in CASH_ACCOUNTS:
            continue  # the cash side is the balancing entry; show the counter-accounts
        item = {"account_code": code, "account_name": CHART_OF_ACCOUNTS.get(code, "Unknown"), "amount": money_float(net),
                "_net": net}
        category = _cash_flow_category(code)
        (investing if category == "INVESTING" else financing if category == "FINANCING" else operating).append(item)

    def total(items):
        return sum((i["_net"] for i in items), ZERO)

    totals = (total(operating), total(investing), total(financing))
    for items in (operating, investing, financing):
        for i in items:
            i.pop("_net")

    return {
        "from_date": from_date.isoformat() if from_date else "all",
        "to_date": to_date.isoformat() if to_date else "all",
        "currency": "ZAR",
        "operating_activities": {"items": operating, "total": money_float(totals[0])},
        "investing_activities": {"items": investing, "total": money_float(totals[1])},
        "financing_activities": {"items": financing, "total": money_float(totals[2])},
        "net_change_in_cash": money_float(sum(totals, ZERO)),
    }


# ════════════════════════════════════════════════════════════════════════
# 4. FINANCIAL STATEMENTS (from GL)
# ════════════════════════════════════════════════════════════════════════

@app.get("/statements")
async def statements(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(reader),
):
    """Income statement and balance sheet from posted GL balances (Decimal)."""
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
            JournalEntry.is_posted == True,  # noqa: E712
            JournalEntry.deleted_at.is_(None),
        )
        .group_by(JournalEntryLine.account_code, JournalEntryLine.account_name)
    )
    balances: dict = {}
    for row in (await db.execute(query)).all():
        b = balances.setdefault(row.account_code, {"name": row.account_name, "balance": ZERO})
        b["balance"] += _d(row.total_debit) - _d(row.total_credit)

    revenue_accounts = {k: v for k, v in balances.items() if account_type(k) == "REVENUE"}
    expense_accounts = {k: v for k, v in balances.items() if account_type(k) == "EXPENSE"}

    total_revenue = sum((-v["balance"] for v in revenue_accounts.values()), ZERO)  # credit-normal
    cogs = sum((v["balance"] for k, v in expense_accounts.items() if k.startswith("5")), ZERO)
    gross_profit = total_revenue - cogs
    # OpEx = 6xxx only; 8xxx interest and 9xxx tax are shown on their own lines (was double-counted)
    opex = sum((v["balance"] for k, v in expense_accounts.items() if k.startswith("6")), ZERO)
    ebit = gross_profit - opex
    interest_expense = balances.get("8000", {}).get("balance", ZERO)
    tax_expense = balances.get("9000", {}).get("balance", ZERO)
    net_income = ebit - interest_expense - tax_expense

    income_statement = [
        {"line": "Revenue", "amount": money_float(total_revenue)},
        {"line": "Cost of Service", "amount": money_float(-cogs)},
        {"line": "Gross Profit", "amount": money_float(gross_profit)},
        {"line": "Operating Expenses", "amount": money_float(-opex)},
        {"line": "EBIT", "amount": money_float(ebit)},
        {"line": "Interest Expense", "amount": money_float(-interest_expense)},
        {"line": "Tax Expense", "amount": money_float(-tax_expense)},
        {"line": "Net Income", "amount": money_float(net_income)},
    ]

    assets = {k: v for k, v in balances.items() if account_type(k) == "ASSET"}
    liabilities = {k: v for k, v in balances.items() if account_type(k) == "LIABILITY"}
    equity = {k: v for k, v in balances.items() if account_type(k) == "EQUITY"}

    total_assets = sum((v["balance"] for v in assets.values()), ZERO)
    total_liabilities = sum((-v["balance"] for v in liabilities.values()), ZERO)
    total_equity = sum((-v["balance"] for v in equity.values()), ZERO) + net_income

    balance_sheet = [
        {"line": "ASSETS", "amount": "", "section": True},
        *[{"line": f"  {v['name']}", "amount": money_float(v["balance"])} for v in assets.values()],
        {"line": "Total Assets", "amount": money_float(total_assets), "total": True},
        {"line": "", "amount": ""},
        {"line": "LIABILITIES", "amount": "", "section": True},
        *[{"line": f"  {v['name']}", "amount": money_float(-v["balance"])} for v in liabilities.values()],
        {"line": "Total Liabilities", "amount": money_float(total_liabilities), "total": True},
        {"line": "", "amount": ""},
        {"line": "EQUITY", "amount": "", "section": True},
        *[{"line": f"  {v['name']}", "amount": money_float(-v["balance"])} for v in equity.values()],
        {"line": "Retained Earnings (Net Income)", "amount": money_float(net_income)},
        {"line": "Total Equity", "amount": money_float(total_equity), "total": True},
        {"line": "", "amount": ""},
        {"line": "Total Liabilities + Equity", "amount": money_float(total_liabilities + total_equity), "total": True},
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

PAGE_SIZE = 100
MAX_PAGES = 500  # hard stop: 50k invoices per sync call


def _signed_billing_headers(tenant_id: uuid.UUID, auth: AuthContext) -> dict:
    """Identity headers for billing; the httpx transport patch (internal_auth) signs them."""
    h = {"x-tenant-id": str(tenant_id), "x-user-id": str(auth.user_id),
         "x-roles": ",".join(auth.roles or []) or "finance_admin"}
    key = os.getenv("INTERNAL_SERVICE_KEY", "")
    if key:
        h["x-internal-key"] = key
    return h


async def fetch_billing_invoices(client, tenant_id: uuid.UUID, auth: AuthContext) -> list:
    """All 'sent' invoices, paginated with limit/offset until exhausted. Raises httpx errors."""
    headers = _signed_billing_headers(tenant_id, auth)
    out: list = []
    for page in range(MAX_PAGES):
        r = await client.get(f"{BILLING_SERVICE_URL}/invoices", headers=headers,
                             params={"status": "sent", "limit": PAGE_SIZE, "offset": page * PAGE_SIZE})
        if r.status_code >= 400:
            raise httpx.HTTPStatusError(f"billing returned {r.status_code}", request=r.request, response=r)
        body = r.json()
        items = body.get("items", []) if isinstance(body, dict) else body
        out.extend(items)
        total = body.get("total") if isinstance(body, dict) else None
        if len(items) < PAGE_SIZE or (total is not None and len(out) >= int(total)):
            break
    return out


@app.post("/billing/sync-invoices")
async def sync_billing_invoices(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(admin),
):
    """Admin-only. Pull ALL sent invoices from billing (signed, paginated) and post
    Dr 1100 AR / Cr 4000 Revenue per invoice, idempotent by (source='billing.invoice', source_id).
    Invoices already booked under the legacy source 'BILLING' are skipped."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            invoices = await fetch_billing_invoices(client, tenant_id, auth)
    except httpx.HTTPStatusError as exc:
        logger.warning("Billing sync failed: %s", exc)
        return {"status": "billing_unavailable", "invoices_synced": 0}
    except httpx.RequestError as exc:
        logger.warning("Billing service unreachable: %s", exc)
        return {"status": "billing_unavailable", "error": str(exc), "invoices_synced": 0}

    synced = skipped = failed = 0
    for inv in invoices:
        invoice_id = str(inv.get("id") or "")
        if not invoice_id:
            failed += 1
            continue
        if await ledger.find_by_source(db, tenant_id, "BILLING", invoice_id) is not None:
            skipped += 1
            continue
        number = inv.get("invoice_number") or inv.get("number") or invoice_id[:8]
        try:
            amount = to_money(inv.get("total_zar", inv.get("total", 0)))
            if amount <= 0:
                skipped += 1
                continue
            entry_date = date.fromisoformat(str(inv.get("issue_date") or inv.get("created_at") or date.today().isoformat())[:10])
            async with db.begin_nested():
                _, _, duplicate = await ledger.create_entry(
                    db, tenant_id, entry_date=entry_date, description=f"Revenue recognition - Invoice {number}",
                    source="billing.invoice", source_id=invoice_id, reference=f"INV-{number}",
                    lines=[
                        {"account_code": "1100", "description": f"AR - Customer {str(inv.get('customer_id', ''))[:8]}",
                         "debit": amount, "credit": 0},
                        {"account_code": "4000", "description": f"Revenue - Invoice {number}", "debit": 0, "credit": amount},
                    ],
                    auto_post=True,
                )
            skipped += 1 if duplicate else 0
            synced += 0 if duplicate else 1
        except HTTPException as exc:  # e.g. closed period: leave it for a later sync, report it
            logger.warning("Invoice %s not synced: %s", invoice_id, exc.detail)
            failed += 1
    return {"status": "synced", "invoices_synced": synced, "already_synced": skipped, "failed": failed}


@app.get("/billing/revenue-summary")
async def revenue_summary(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(reader),
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
            JournalEntry.source.in_(("billing.invoice", "BILLING")),
            JournalEntry.deleted_at.is_(None),
            JournalEntry.is_posted == True,  # noqa: E712
            JournalEntryLine.account_code == "4000",
        )
    )
    row = result.one()
    return {
        "invoices_synced": row.invoice_count or 0,
        "total_revenue": money_float(row.total_revenue or 0),
        "currency": "ZAR",
    }


# ════════════════════════════════════════════════════════════════════════
# 6. OVERVIEW & SCENARIOS (kept from v1)
# ════════════════════════════════════════════════════════════════════════

@app.get("/overview")
async def overview(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(reader),
):
    """Financial overview computed from the posted GL (zeros for a tenant with none)."""

    query = (
        select(
            JournalEntryLine.account_code,
            func.sum(JournalEntryLine.debit).label("total_debit"),
            func.sum(JournalEntryLine.credit).label("total_credit"),
        )
        .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalEntryLine.tenant_id == tenant_id,
            JournalEntry.is_posted == True,  # noqa: E712
            JournalEntry.deleted_at.is_(None),
        )
        .group_by(JournalEntryLine.account_code)
    )
    result = await db.execute(query)
    balances = {row.account_code: _d(row.total_debit) - _d(row.total_credit) for row in result.all()}

    revenue = sum((-v for k, v in balances.items() if account_type(k) == "REVENUE"), ZERO)
    expenses = sum((v for k, v in balances.items() if account_type(k) == "EXPENSE"), ZERO)
    ebit = revenue - expenses
    cash = sum((balances.get(c, ZERO) for c in CASH_ACCOUNTS), ZERO)

    return {
        "tenant_id": str(tenant_id),
        "currency": "ZAR",
        "kpis": {
            "revenue": money_float(revenue),
            "expenses": money_float(expenses),
            "ebit": money_float(ebit),
            "cash_position": money_float(cash),
        },
        "period": "FY2026 YTD",
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@app.post("/scenario", response_model=ScenarioResponse)
async def scenario(
    payload: ScenarioRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(clerk),
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
    _auth: AuthContext = Depends(clerk),
):
    record = FinancialRecord(
        tenant_id=tenant_id,
        record_type=payload.record_type,
        description=payload.description,
        amount=to_money(payload.amount),
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
    db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(reader),
):
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
    db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(reader),
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
    db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(clerk),
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
    total_contract_value: Decimal = Field(Decimal("0"), ge=0)
    start_date: date
    end_date: date
    recognized_to_date: Decimal = Field(Decimal("0"), ge=0)
    deferred_balance: Decimal = Field(Decimal("0"), ge=0)


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
    db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(reader),
):
    result = await db.execute(select(RevenueContract).where(RevenueContract.tenant_id == tenant_id).order_by(desc(RevenueContract.created_at)))
    return [_contract_out(c) for c in result.scalars().all()]


@app.post("/revenue-contracts", status_code=status.HTTP_201_CREATED)
async def create_revenue_contract(
    payload: RevenueContractCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(clerk),
):
    c = RevenueContract(tenant_id=tenant_id, **payload.model_dump())
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return _contract_out(c)


# ── Expense Governance: Receipts, Approvals, Purchase Orders, Assets, Recurring Payments ──

class ExpenseReceiptCreate(BaseModel):
    vendor: str
    amount: Decimal = Field(Decimal("0"), ge=0)
    category: Optional[str] = None
    status: str = "processed"
    ocr_confidence: Optional[int] = None
    submitted_by: Optional[str] = None
    receipt_date: date = Field(default_factory=date.today)


@app.get("/expense-receipts")
async def list_expense_receipts(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(reader)):
    result = await db.execute(select(ExpenseReceipt).where(ExpenseReceipt.tenant_id == tenant_id).order_by(desc(ExpenseReceipt.created_at)))
    return [{"id": str(r.id), "vendor": r.vendor, "amount": float(r.amount), "category": r.category,
             "status": r.status, "ocrConfidence": r.ocr_confidence, "submittedBy": r.submitted_by,
             "date": r.receipt_date.isoformat()} for r in result.scalars().all()]


@app.post("/expense-receipts", status_code=status.HTTP_201_CREATED)
async def create_expense_receipt(payload: ExpenseReceiptCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(clerk)):
    r = ExpenseReceipt(tenant_id=tenant_id, **payload.model_dump())
    db.add(r)
    await db.flush()
    await db.refresh(r)
    return {"id": str(r.id), "vendor": r.vendor, "amount": float(r.amount), "category": r.category,
            "status": r.status, "ocrConfidence": r.ocr_confidence, "submittedBy": r.submitted_by,
            "date": r.receipt_date.isoformat()}


class ApprovalRequestCreate(BaseModel):
    request: str
    amount: Decimal = Field(Decimal("0"), ge=0)
    owner: Optional[str] = None
    status: str = "pending"
    policy: Optional[str] = None


@app.get("/approval-requests")
async def list_approval_requests(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(reader)):
    result = await db.execute(select(ApprovalRequest).where(ApprovalRequest.tenant_id == tenant_id).order_by(desc(ApprovalRequest.created_at)))
    return [{"id": str(a.id), "request": a.request, "amount": float(a.amount), "owner": a.owner,
             "status": a.status, "policy": a.policy} for a in result.scalars().all()]


@app.post("/approval-requests", status_code=status.HTTP_201_CREATED)
async def create_approval_request(payload: ApprovalRequestCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(clerk)):
    a = ApprovalRequest(tenant_id=tenant_id, **payload.model_dump())
    db.add(a)
    await db.flush()
    await db.refresh(a)
    return {"id": str(a.id), "request": a.request, "amount": float(a.amount), "owner": a.owner,
            "status": a.status, "policy": a.policy}


class PurchaseOrderCreate(BaseModel):
    vendor: str
    amount: Decimal = Field(Decimal("0"), ge=0)
    status: str = "draft"
    approver: Optional[str] = None
    due_date: Optional[date] = None


@app.get("/purchase-orders")
async def list_purchase_orders(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(reader)):
    result = await db.execute(select(FinancePurchaseOrder).where(FinancePurchaseOrder.tenant_id == tenant_id).order_by(desc(FinancePurchaseOrder.created_at)))
    return [{"id": str(p.id), "vendor": p.vendor, "amount": float(p.amount), "status": p.status,
             "approver": p.approver, "dueDate": p.due_date.isoformat() if p.due_date else None} for p in result.scalars().all()]


@app.post("/purchase-orders", status_code=status.HTTP_201_CREATED)
async def create_purchase_order(payload: PurchaseOrderCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(clerk)):
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
    cost: Decimal = Field(Decimal("0"), ge=0)
    accumulated_depreciation: Decimal = Field(Decimal("0"), ge=0)
    useful_life_years: Optional[Decimal] = Field(None, ge=0)


@app.get("/fixed-assets")
async def list_fixed_assets(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(reader)):
    result = await db.execute(select(FixedAsset).where(FixedAsset.tenant_id == tenant_id).order_by(desc(FixedAsset.created_at)))
    return [{"id": str(a.id), "asset": a.asset_name, "location": a.location, "status": a.status,
             "cost": float(a.cost), "depreciation": float(a.accumulated_depreciation),
             "remainingLife": f"{float(a.useful_life_years)} years" if a.useful_life_years else None} for a in result.scalars().all()]


@app.post("/fixed-assets", status_code=status.HTTP_201_CREATED)
async def create_fixed_asset(payload: FixedAssetCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(clerk)):
    a = FixedAsset(tenant_id=tenant_id, **payload.model_dump())
    db.add(a)
    await db.flush()
    await db.refresh(a)
    return {"id": str(a.id), "asset": a.asset_name, "location": a.location, "status": a.status,
            "cost": float(a.cost), "depreciation": float(a.accumulated_depreciation),
            "remainingLife": f"{float(a.useful_life_years)} years" if a.useful_life_years else None}


class RecurringPaymentCreate(BaseModel):
    vendor: str
    amount: Decimal = Field(Decimal("0"), ge=0)
    frequency: str = "Monthly"
    next_run: Optional[date] = None
    status: str = "active"


@app.get("/recurring-payments")
async def list_recurring_payments(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(reader)):
    result = await db.execute(select(RecurringPayment).where(RecurringPayment.tenant_id == tenant_id).order_by(desc(RecurringPayment.created_at)))
    return [{"id": str(r.id), "vendor": r.vendor, "amount": float(r.amount), "frequency": r.frequency,
             "nextRun": r.next_run.isoformat() if r.next_run else None, "status": r.status} for r in result.scalars().all()]


@app.post("/recurring-payments", status_code=status.HTTP_201_CREATED)
async def create_recurring_payment(payload: RecurringPaymentCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(clerk)):
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
    amount: Decimal = Field(Decimal("0"), ge=0)
    status: str = "unmatched"
    source: Optional[str] = None


@app.get("/bank-items")
async def list_bank_items(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(reader)):
    result = await db.execute(select(BankStatementItem).where(BankStatementItem.tenant_id == tenant_id).order_by(desc(BankStatementItem.item_date)))
    return [{"id": str(b.id), "date": b.item_date.isoformat(), "description": b.description,
             "amount": float(b.amount), "status": b.status, "source": b.source} for b in result.scalars().all()]


@app.post("/bank-items", status_code=status.HTTP_201_CREATED)
async def create_bank_item(payload: BankStatementItemCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session), _auth: AuthContext = Depends(clerk)):
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
