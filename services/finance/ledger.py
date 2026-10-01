"""Journal rules for the finance service: Decimal money, exact balance, tenant chart of
accounts, period lock, idempotent (source, source_id) posting. Pure helpers plus
`create_entry`, which the routes call."""

from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.finance.database import (
    FinanceAccount, FinancePeriod, JournalEntry, JournalEntryLine, next_journal_reference,
)

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
CODE_RE = re.compile(r"^[1-9]\d{3}$")

# Structural default chart (SA ISP). Added idempotently per tenant on first use.
CHART_OF_ACCOUNTS = {
    "1000": "Bank",
    "1010": "Paystack Clearing",
    "1100": "Accounts Receivable",
    "1200": "Inventory",
    "1500": "PP&E - Network Infrastructure",
    "1510": "PP&E - Equipment",
    "1600": "Accumulated Depreciation",
    "2000": "Accounts Payable",
    "2100": "Accrued Expenses",
    "2110": "Commission Payable",
    "2200": "VAT Output",
    "2210": "VAT Input",
    "2300": "Deferred Revenue",
    "2500": "Long-Term Debt",
    "2600": "Tax Payable",
    "3000": "Share Capital",
    "3100": "Retained Earnings",
    "4000": "Revenue - FTTH Subscriptions",
    "4100": "Revenue - Installation Fees",
    "4200": "Revenue - Equipment Sales",
    "4900": "Other Revenue",
    "5000": "Cost of Service - FNO Access",
    "5100": "Cost of Service - Equipment COGS",
    "6000": "Salaries & Wages",
    "6050": "Commission Expense",
    "6100": "Rent & Facilities",
    "6200": "Marketing & Advertising",
    "6300": "Software & Licenses",
    "6400": "Depreciation & Amortization",
    "6500": "Bad Debt Expense",
    "6900": "General & Administrative",
    "7000": "Interest Income",
    "8000": "Interest Expense",
    "9000": "Income Tax Expense",
}


def account_type(code: str) -> str:
    p = (code or " ")[0]
    return {"1": "ASSET", "2": "LIABILITY", "3": "EQUITY", "4": "REVENUE", "7": "REVENUE"}.get(p, "EXPENSE")


ACCOUNT_TYPE_MAP = {c: account_type(c) for c in CHART_OF_ACCOUNTS}


def to_money(value) -> Decimal:
    """Parse a string / int / float / Decimal amount to a cent-quantised Decimal."""
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Invalid amount: {value!r}") from exc
    if not d.is_finite():
        raise HTTPException(status_code=422, detail="Amount must be finite")
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def money_float(d) -> float:
    """Presentation only: JSON numbers for the existing UI. All arithmetic stays Decimal."""
    return float(Decimal(d or 0).quantize(CENT))


def period_of(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


async def ensure_chart(db: AsyncSession, tenant_id: uuid.UUID) -> dict:
    """Return {code: name} for the tenant, adding any missing structural default account."""
    rows = (await db.execute(select(FinanceAccount.code, FinanceAccount.name).where(FinanceAccount.tenant_id == tenant_id))).all()
    have = {r.code: r.name for r in rows}
    for code in [c for c in CHART_OF_ACCOUNTS if c not in have]:
        try:
            async with db.begin_nested():
                db.add(FinanceAccount(tenant_id=tenant_id, code=code, name=CHART_OF_ACCOUNTS[code]))
                await db.flush()
        except IntegrityError:  # concurrent first use inserted it
            pass
        have[code] = CHART_OF_ACCOUNTS[code]
    return have


async def period_status(db: AsyncSession, tenant_id: uuid.UUID, period: str) -> str:
    row = (await db.execute(select(FinancePeriod.status).where(
        FinancePeriod.tenant_id == tenant_id, FinancePeriod.period == period))).scalar_one_or_none()
    return row or "open"


async def assert_period_open(db: AsyncSession, tenant_id: uuid.UUID, entry_date: date) -> None:
    p = period_of(entry_date)
    if await period_status(db, tenant_id, p) == "closed":
        raise HTTPException(status_code=409, detail=f"Accounting period {p} is closed; reopen it or post into an open period")


def normalise_lines(raw_lines: Iterable, chart: dict) -> list:
    """Validate and quantise lines. 422 for shape problems / unknown accounts, 400 for imbalance."""
    lines = list(raw_lines)
    if len(lines) < 2:
        raise HTTPException(status_code=422, detail="A journal entry needs at least 2 lines")
    out, total_d, total_c = [], ZERO, ZERO
    for i, ln in enumerate(lines, 1):
        code = str(ln["account_code"]).strip()
        debit, credit = to_money(ln.get("debit") or 0), to_money(ln.get("credit") or 0)
        if debit < 0 or credit < 0:
            raise HTTPException(status_code=422, detail=f"Line {i}: amounts must be >= 0")
        if debit > 0 and credit > 0:
            raise HTTPException(status_code=422, detail=f"Line {i}: a line cannot have both debit and credit")
        if debit == 0 and credit == 0:
            raise HTTPException(status_code=422, detail=f"Line {i}: a line needs a debit or a credit")
        if code not in chart:
            raise HTTPException(status_code=422, detail=f"Line {i}: unknown account code {code}")
        total_d += debit
        total_c += credit
        out.append({"account_code": code, "account_name": chart[code], "description": ln.get("description"),
                    "debit": debit, "credit": credit})
    if total_d != total_c:
        raise HTTPException(status_code=400, detail=f"Debits ({total_d}) must equal credits ({total_c})")
    return out


async def find_by_source(db, tenant_id, source: Optional[str], source_id: Optional[str]) -> Optional[JournalEntry]:
    if not source or not source_id:
        return None
    return (await db.execute(select(JournalEntry).where(
        JournalEntry.tenant_id == tenant_id, JournalEntry.source == source,
        JournalEntry.source_id == source_id, JournalEntry.deleted_at.is_(None)))).scalars().first()


async def entry_lines(db, entry_id) -> list:
    return list((await db.execute(select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry_id))).scalars().all())


async def create_entry(
    db: AsyncSession, tenant_id: uuid.UUID, *, entry_date: date, description: Optional[str],
    source: Optional[str], source_id: Optional[str], reference: Optional[str], lines: list,
    auto_post: bool,
):
    """Create (and optionally post) an entry in the caller's transaction.
    Returns (entry, lines, duplicate). A repeated (source, source_id) returns the first entry."""
    existing = await find_by_source(db, tenant_id, source, source_id)
    if existing is not None:
        return existing, await entry_lines(db, existing.id), True
    chart = await ensure_chart(db, tenant_id)
    norm = normalise_lines(lines, chart)
    if auto_post:
        await assert_period_open(db, tenant_id, entry_date)
    entry = JournalEntry(
        tenant_id=tenant_id, entry_date=entry_date,
        reference=reference or await next_journal_reference(db, tenant_id),
        description=description, source=source, source_id=source_id, is_posted=False,
    )
    try:
        async with db.begin_nested():
            db.add(entry)
            await db.flush()
    except IntegrityError:  # lost the race on (tenant, source, source_id)
        existing = await find_by_source(db, tenant_id, source, source_id)
        if existing is None:
            raise
        return existing, await entry_lines(db, existing.id), True
    objs = []
    for ln in norm:
        o = JournalEntryLine(journal_entry_id=entry.id, tenant_id=tenant_id, **ln)
        db.add(o)
        objs.append(o)
    if auto_post:
        entry.is_posted = True
    await db.flush()
    return entry, objs, False


def entry_to_dict(entry: JournalEntry, lines: list) -> dict:
    td = sum((Decimal(l.debit or 0) for l in lines), ZERO)
    tc = sum((Decimal(l.credit or 0) for l in lines), ZERO)
    return {
        "id": str(entry.id), "tenant_id": str(entry.tenant_id),
        "entry_date": entry.entry_date.isoformat() if entry.entry_date else None,
        "reference": entry.reference, "description": entry.description,
        "source": entry.source, "source_id": entry.source_id, "is_posted": bool(entry.is_posted),
        "total_debit": money_float(td), "total_credit": money_float(tc),
        "lines": [{"id": str(l.id), "account_code": l.account_code, "account_name": l.account_name,
                   "description": l.description, "debit": money_float(l.debit), "credit": money_float(l.credit)} for l in lines],
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }
