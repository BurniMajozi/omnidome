"""Support job -> finance expense, from REAL recorded costs only.

Cost sources (nothing is invented; no flat call-out fee):
  * parts: sum(unit_cost * quantity) of the parts the technician recorded on resolve;
  * labour: `labour_minutes` the technician recorded on resolve x SUPPORT_LABOUR_RATE_PER_HOUR
    (the tenant's configured hourly rate; unset => labour is not costed).
If the total is zero, or the ledger accounts are not configured, NOTHING is posted.

Config (env): SUPPORT_EXPENSE_ACCOUNT_CODE (debit), SUPPORT_OFFSET_ACCOUNT_CODE (credit),
SUPPORT_LABOUR_RATE_PER_HOUR, SUPPORT_SERVICE_USER_ID, FINANCE_SERVICE_URL (default http://finance:8015),
SUPPORT_FINANCE_TIMEOUT.

Contract (finance POST /journal-entries, idempotent on (source, source_id)):
  {date, description, source:'support.job', source_id:<ticket uuid>, auto_post:true,
   lines:[{account_code, debit, credit}, ...]}
Identity: x-tenant-id AND x-user-id, signed with services.common.internal_auth (finance runs AUTH_MODE=signed).
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, Iterable, Optional

import httpx

from services.common import internal_auth

logger = logging.getLogger("support.finance_bridge")
_CENT = Decimal("0.01")
SOURCE = "support.job"


def _money(v) -> Decimal:
    return Decimal(v).quantize(_CENT, rounding=ROUND_HALF_UP)


def _dec(v, default=Decimal("0")) -> Decimal:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return default
    return d if d.is_finite() and d >= 0 else default


def parts_cost(parts: Iterable[Dict[str, Any]]) -> Decimal:
    total = Decimal("0")
    for p in parts or []:
        qty = _dec(p.get("quantity", 1))
        total += _dec(p.get("unit_cost", 0)) * qty
    return total


def labour_cost(labour_minutes: Optional[int], rate_per_hour: Optional[str] = None) -> Decimal:
    rate = _dec(rate_per_hour if rate_per_hour is not None else os.getenv("SUPPORT_LABOUR_RATE_PER_HOUR", ""))
    mins = _dec(labour_minutes or 0)
    if rate <= 0 or mins <= 0:
        return Decimal("0")
    return mins / Decimal(60) * rate


def build_entry(ticket_id: uuid.UUID, subject: str, on: date, parts: Iterable[Dict[str, Any]],
                labour_minutes: Optional[int]) -> Optional[dict]:
    """Balanced two-line entry, or None when there is no real cost / the accounts are not configured."""
    expense = os.getenv("SUPPORT_EXPENSE_ACCOUNT_CODE", "").strip()
    offset = os.getenv("SUPPORT_OFFSET_ACCOUNT_CODE", "").strip()
    total = _money(parts_cost(parts) + labour_cost(labour_minutes))
    if total <= 0 or not expense or not offset:
        return None
    amt = f"{total:.2f}"
    return {
        "date": on.isoformat(),
        "description": f"Support job {str(ticket_id)[:8]} - {(subject or '')[:80]}",
        "source": SOURCE,
        "source_id": str(ticket_id),
        "auto_post": True,
        "lines": [
            {"account_code": expense, "debit": amt, "credit": "0.00"},
            {"account_code": offset, "debit": "0.00", "credit": amt},
        ],
    }


def finance_url() -> str:
    return (os.getenv("FINANCE_SERVICE_URL") or "http://finance:8015").rstrip("/")


def signed_headers(tenant_id: uuid.UUID, user_id: Optional[uuid.UUID], method: str, path: str) -> dict:
    """x-tenant-id + x-user-id (+ signature). Raises IdentityConfigError when no secret is configured."""
    headers = {
        "x-tenant-id": str(tenant_id),
        "x-user-id": str(user_id or os.getenv("SUPPORT_SERVICE_USER_ID", "00000000-0000-0000-0000-000000000001")),
        "content-type": "application/json",
    }
    headers.update(internal_auth.sign_headers(headers, method, path))
    return headers


async def post_entry(tenant_id: uuid.UUID, user_id: Optional[uuid.UUID], entry: dict, client: Optional[httpx.AsyncClient] = None) -> tuple:
    """(status, error): ("posted", None) on 2xx, otherwise ("failed", short reason). Never raises."""
    try:
        headers = signed_headers(tenant_id, user_id, "POST", "/journal-entries")
    except Exception as exc:  # noqa: BLE001 - IdentityConfigError etc.
        return "failed", f"signing: {type(exc).__name__}"
    owns = client is None
    client = client or httpx.AsyncClient(timeout=float(os.getenv("SUPPORT_FINANCE_TIMEOUT", "8")))
    try:
        resp = await client.post(f"{finance_url()}/journal-entries", json=entry, headers=headers)
    except httpx.HTTPError as exc:
        return "failed", f"transport: {type(exc).__name__}"
    finally:
        if owns:
            await client.aclose()
    if 200 <= resp.status_code < 300:
        return "posted", None
    return "failed", f"finance HTTP {resp.status_code}"
