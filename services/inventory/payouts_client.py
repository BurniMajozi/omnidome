"""Billing payouts client for supplier payments (the same funded-wallet path as payroll; see billing/routes/payouts.py)."""
import os

import httpx


class PayoutError(Exception):
    pass


class InsufficientFunding(PayoutError):
    def __init__(self, detail):
        super().__init__("payout wallet is short")
        self.detail = detail if isinstance(detail, dict) else {}


def _headers() -> dict:
    key = os.getenv("INTERNAL_SERVICE_KEY", "")
    if not key:
        raise PayoutError("INTERNAL_SERVICE_KEY is not configured: cannot reach billing payouts")
    return {"x-internal-key": key, "Content-Type": "application/json"}


def _url() -> str:
    return os.getenv("BILLING_SERVICE_URL", "http://billing:8003").rstrip("/")


def _detail(data) -> str:
    d = data.get("detail") if isinstance(data, dict) else None
    return str(d.get("message") if isinstance(d, dict) else d)


async def create_recipient(tenant_id, name: str, account_number: str, bank_code: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{_url()}/payouts/internal/recipients", headers=_headers(), json={
                "tenant_id": str(tenant_id), "name": name, "account_number": account_number, "bank_code": bank_code})
    except httpx.HTTPError as exc:
        raise PayoutError(f"recipient request failed: {exc}") from exc
    data = resp.json() if resp.content else {}
    if resp.status_code != 200:
        raise PayoutError(_detail(data) or f"billing returned HTTP {resp.status_code}")
    return data["recipient_code"]


async def pay(tenant_id, user_id, source_id: str, item_ref: str, recipient_code: str, amount_zar: str, reason: str) -> dict:
    body = {"tenant_id": str(tenant_id), "kind": "supplier", "source_id": source_id,
            "requested_by": str(user_id) if user_id else None,
            "items": [{"item_ref": item_ref, "recipient_code": recipient_code, "amount_zar": amount_zar, "reason": reason,
                       "reference": f"supplier-{item_ref}"}]}
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{_url()}/payouts/internal/batches", headers=_headers(), json=body)
    except httpx.HTTPError as exc:
        raise PayoutError(f"payout request failed: {exc}") from exc
    data = resp.json() if resp.content else {}
    if resp.status_code == 402:
        raise InsufficientFunding(data.get("detail"))
    if resp.status_code != 200:
        raise PayoutError(_detail(data) or f"billing returned HTTP {resp.status_code}")
    return data


async def status(tenant_id, source_id: str, reconcile: bool = True) -> dict:
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(f"{_url()}/payouts/internal/by-source", headers=_headers(), params={
                "tenant_id": str(tenant_id), "kind": "supplier", "source_id": source_id, "reconcile": str(reconcile).lower()})
    except httpx.HTTPError as exc:
        raise PayoutError(f"payout status request failed: {exc}") from exc
    if resp.status_code != 200:
        raise PayoutError(f"billing returned HTTP {resp.status_code}")
    return resp.json()
