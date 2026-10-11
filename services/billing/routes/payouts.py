"""Funded payouts (payroll, supplier payments): wallet, quote, funding, bulk transfers, transfer webhooks.

Money rule: Paystack transfers come out of OmniDome's own balance, so nothing is sent unless the tenant's payout
wallet already holds the amount plus OmniDome's fee. The wallet is topped up by a card payment (no subaccount: the
money stays with OmniDome) or by an EFT that a platform admin records. A batch reserves (debits) the wallet first,
then sends Paystack `POST /transfer/bulk`; an item that fails or is reversed credits its amount and fee back, so
the wallet always equals what the tenant has paid in minus what actually left. Open refund / chargeback liabilities
are recovered from the wallet as money arrives.

The fee uses the same marginal tiers as card collections (services/billing/gateway.py) on the tenant's month-to-date
processed volume (card charges + payouts), unless the tenant has a negotiated override.

HR (and later purchasing) call the internal endpoints with the service key; the batch is created and executed in one
call and is idempotent per (kind, source_id, attempt): an item that already went out or is in flight is never sent again.
"""

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from services.billing import gateway
from services.billing.access import internal_key_ok, require_tier
from services.billing.database import get_session
from services.billing.models import BillingWebhookEvent
from services.billing.models_gateway import GatewayCharge, GatewayLiability, GatewaySettings
from services.billing.models_payouts import (
    PayoutBatch, PayoutFunding, PayoutItem, PayoutWallet, PayoutWalletEntry)
from services.billing.routes import gateway as gw
from services.billing.routes.paystack_recurring import _paystack, _secret
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("billing.payouts")

router = APIRouter(prefix="/payouts", tags=["Payouts"])

MAX_ITEMS = 500
CHUNK = 100                                    # Paystack bulk transfer limit per request
LIVE = ("pending", "processing", "success")    # item states that mean the money is, or may be, on its way out
FAILED_STATES = ("failed", "reversed", "rejected", "blocked", "abandoned", "cancelled")
REF_RE = re.compile(r"^[a-z0-9_=-]{5,100}$")


def _cents(value) -> int:
    return int((Decimal(str(value)) * 100).to_integral_value())


# ---------------------------------------------------------------------------
# Wallet
# ---------------------------------------------------------------------------

def wallet_locked(session, tenant_id) -> PayoutWallet:
    w = session.execute(select(PayoutWallet).where(PayoutWallet.tenant_id == tenant_id).with_for_update()).scalar_one_or_none()
    if w is None:
        try:
            with session.begin_nested():
                session.add(PayoutWallet(tenant_id=tenant_id, balance_cents=0))
                session.flush()
        except IntegrityError:
            pass
        w = session.execute(select(PayoutWallet).where(PayoutWallet.tenant_id == tenant_id).with_for_update()).scalar_one()
    return w


def post_entry(session, tenant_id, kind: str, amount_cents: int, ref: str, note: Optional[str] = None) -> bool:
    """Apply one wallet movement. Idempotent per (tenant, kind, ref): returns False (and changes nothing) on a repeat."""
    w = wallet_locked(session, tenant_id)
    try:
        with session.begin_nested():
            session.add(PayoutWalletEntry(tenant_id=tenant_id, kind=kind, amount_cents=amount_cents, ref=ref[:120], note=note))
            session.flush()
    except IntegrityError:
        return False
    w.balance_cents += amount_cents
    return True


def recover_liabilities(session, tenant_id) -> int:
    """Net open refund / chargeback liabilities against the wallet, oldest first, whole liabilities only."""
    recovered = 0
    for liab in session.execute(select(GatewayLiability).where(
            GatewayLiability.tenant_id == tenant_id, GatewayLiability.status == "open")
            .order_by(GatewayLiability.created_at).with_for_update()).scalars():
        w = wallet_locked(session, tenant_id)
        if w.balance_cents < liab.amount_cents:
            break
        if post_entry(session, tenant_id, "liability_recovery", -liab.amount_cents, str(liab.id), liab.note):
            liab.status, liab.recovered_at = "recovered", datetime.now(timezone.utc)
            recovered += liab.amount_cents
    return recovered


def credit_funding(session, tenant_id, kind: str, amount_cents: int, ref: str, note: Optional[str] = None) -> bool:
    if not post_entry(session, tenant_id, kind, amount_cents, ref, note):
        return False
    recover_liabilities(session, tenant_id)
    return True


def open_liabilities_cents(session, tenant_id) -> int:
    return int(session.execute(select(func.coalesce(func.sum(GatewayLiability.amount_cents), 0)).where(
        GatewayLiability.tenant_id == tenant_id, GatewayLiability.status == "open")).scalar_one())


# ---------------------------------------------------------------------------
# Fee quote
# ---------------------------------------------------------------------------

def month_volume_cents(session, tenant_id, period: str) -> int:
    cards = gw.month_volume_cents(session, tenant_id, period)
    out = int(session.execute(select(func.coalesce(func.sum(PayoutItem.amount_cents), 0)).select_from(PayoutItem).join(
        PayoutBatch, PayoutBatch.id == PayoutItem.batch_id).where(
        PayoutItem.tenant_id == tenant_id, PayoutBatch.period == period, PayoutItem.status.in_(("processing", "success")))).scalar_one())
    return cards + out


def quote(session, tenant_id, total_cents: int) -> dict:
    settings = session.execute(select(GatewaySettings).where(GatewaySettings.tenant_id == tenant_id)).scalar_one_or_none()
    period = gateway.period_key()
    calc = gateway.calculate(total_cents, month_volume_cents(session, tenant_id, period), gw._tiers_for(settings))
    w = session.execute(select(PayoutWallet).where(PayoutWallet.tenant_id == tenant_id)).scalar_one_or_none()
    balance = w.balance_cents if w else 0
    required = total_cents + calc.commission_cents
    return {"amount_zar": total_cents / 100, "fee_zar": calc.commission_cents / 100, "required_zar": required / 100,
            "effective_rate_percent": float(calc.effective_bps) / 100, "balance_zar": balance / 100,
            "shortfall_zar": max(0, required - balance) / 100, "period": period,
            "_fee_cents": calc.commission_cents, "_required_cents": required, "_balance_cents": balance}


def public_quote(q: dict) -> dict:
    return {k: v for k, v in q.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Batch create / execute
# ---------------------------------------------------------------------------

class PayoutItemIn(BaseModel):
    item_ref: str = Field(min_length=1, max_length=80)
    recipient_code: str = Field(min_length=3, max_length=60)
    amount_zar: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reason: Optional[str] = Field(None, max_length=200)
    reference: Optional[str] = Field(None, description="Paystack reference for attempt 1; derived when omitted")


class BatchIn(BaseModel):
    tenant_id: uuid.UUID
    kind: str = Field(pattern="^(payroll|supplier|other)$")
    source_id: str = Field(min_length=1, max_length=80)
    requested_by: Optional[uuid.UUID] = None
    items: list[PayoutItemIn] = Field(min_length=1, max_length=MAX_ITEMS)


def _reference(kind: str, item: PayoutItemIn, attempt: int) -> str:
    base = (item.reference or f"{kind}-{item.item_ref}").lower()
    ref = base if attempt == 1 else f"{base}-r{attempt}"
    if not REF_RE.match(ref):
        raise HTTPException(status_code=422, detail=f"Invalid payout reference for item {item.item_ref}")
    return ref


def create_batch(session, body: BatchIn) -> tuple[PayoutBatch, list[PayoutItem]]:
    """Reserve the wallet and record the batch. Raises 402 (nothing reserved) when the wallet cannot cover amount + fee."""
    refs = [i.item_ref for i in body.items]
    if len(set(refs)) != len(refs):
        raise HTTPException(status_code=422, detail="Duplicate item_ref in batch")
    wallet_locked(session, body.tenant_id)                     # serialise everything for this tenant
    live = session.execute(select(PayoutItem.item_ref, PayoutItem.status).where(
        PayoutItem.tenant_id == body.tenant_id, PayoutItem.kind == body.kind, PayoutItem.item_ref.in_(refs),
        PayoutItem.status.in_(LIVE))).all()
    if live:
        raise HTTPException(status_code=409, detail={"message": "Some items were already paid or are in flight",
                                                     "items": sorted({r for r, _ in live})})
    total = sum(_cents(i.amount_zar) for i in body.items)
    q = quote(session, body.tenant_id, total)
    if q["_balance_cents"] < q["_required_cents"]:
        raise HTTPException(status_code=402, detail={
            "message": "Payout wallet is short", "required_zar": q["required_zar"], "balance_zar": q["balance_zar"],
            "shortfall_zar": q["shortfall_zar"], "fee_zar": q["fee_zar"]})
    attempt = 1 + int(session.execute(select(func.coalesce(func.max(PayoutBatch.attempt), 0)).where(
        PayoutBatch.tenant_id == body.tenant_id, PayoutBatch.kind == body.kind, PayoutBatch.source_id == body.source_id)).scalar_one())
    batch = PayoutBatch(tenant_id=body.tenant_id, kind=body.kind, source_id=body.source_id, attempt=attempt, period=q["period"],
                        total_cents=total, fee_cents=q["_fee_cents"], requested_by=body.requested_by)
    session.add(batch)
    session.flush()
    post_entry(session, body.tenant_id, "payout", -total, str(batch.id), f"{body.kind} {body.source_id}")
    if q["_fee_cents"]:
        post_entry(session, body.tenant_id, "payout_fee", -q["_fee_cents"], str(batch.id), f"fee {body.kind} {body.source_id}")
    items, fee_left = [], q["_fee_cents"]
    for n, i in enumerate(body.items):
        cents = _cents(i.amount_zar)
        fee = fee_left if n == len(body.items) - 1 else (q["_fee_cents"] * cents) // total
        fee_left -= fee
        item = PayoutItem(batch_id=batch.id, tenant_id=body.tenant_id, kind=body.kind, item_ref=i.item_ref, recipient_code=i.recipient_code,
                          amount_cents=cents, fee_cents=fee, reference=_reference(body.kind, i, attempt), reason=i.reason, status="pending")
        session.add(item)
        items.append(item)
    session.flush()
    return batch, items


def settle_item(session, item: PayoutItem, status: str, message: Optional[str] = None, transfer_code: Optional[str] = None) -> bool:
    """Move one item to its provider state. Returns True when it changed. A failure (or a later reversal) credits the
    amount and its fee back to the wallet exactly once."""
    status = "failed" if status in FAILED_STATES else status
    if item.status == status and not (message or transfer_code):
        return False
    previous = item.status
    if transfer_code:
        item.transfer_code = transfer_code
    if message:
        item.message = message[:500]
    if previous == "failed":                                   # failed is final: a late event cannot resurrect it
        return False
    item.status = status
    if status == "failed":
        post_entry(session, item.tenant_id, "reversal", item.amount_cents, str(item.id), f"returned {item.item_ref}")
        if item.fee_cents:
            post_entry(session, item.tenant_id, "fee_reversal", item.fee_cents, str(item.id), f"fee returned {item.item_ref}")
    return previous != status


def map_status(value: Optional[str]) -> str:
    v = str(value or "").lower()
    return "success" if v == "success" else "failed" if v in FAILED_STATES else "processing"


async def provider_balance_cents() -> Optional[int]:
    """OmniDome's own ZAR balance at Paystack, or None when it cannot be read."""
    res = await _paystack("GET", "/balance")
    if not res.get("status"):
        return None
    for row in res.get("data") or []:
        if str(row.get("currency")).upper() == "ZAR":
            return int(row.get("balance") or 0)
    return None


async def execute_batch(batch_id: uuid.UUID) -> dict:
    """Send the batch's pending items to Paystack in chunks and record the result per item."""
    with get_session() as session:
        items = session.execute(select(PayoutItem).where(PayoutItem.batch_id == batch_id, PayoutItem.status == "pending")
                                .order_by(PayoutItem.created_at)).scalars().all()
        todo = [{"id": i.id, "amount": i.amount_cents, "recipient": i.recipient_code, "reference": i.reference,
                 "reason": i.reason or "Payout"} for i in items]
    if todo and not _secret():
        # no Paystack key (local development): simulate success so the flow is exercisable offline
        with get_session() as session:
            for it in session.execute(select(PayoutItem).where(PayoutItem.batch_id == batch_id, PayoutItem.status == "pending")).scalars():
                settle_item(session, it, "success", "mock (no key configured)", "TRF_MOCK_" + it.reference[-8:])
        return batch_summary(batch_id)
    for start in range(0, len(todo), CHUNK):
        chunk = todo[start:start + CHUNK]
        res = await _paystack("POST", "/transfer/bulk", {"currency": "ZAR", "source": "balance", "transfers": [
            {"amount": t["amount"], "recipient": t["recipient"], "reference": t["reference"], "reason": t["reason"]} for t in chunk]})
        if res.get("_http_status", 200) >= 500:
            logger.error("bulk transfer gateway error batch=%s; items stay pending for reconcile", batch_id)
            continue                                           # outcome unknown: never guess, reconcile later
        with get_session() as session:
            rows = {i.reference: i for i in session.execute(select(PayoutItem).where(
                PayoutItem.reference.in_([t["reference"] for t in chunk]))).scalars()}
            if not res.get("status"):
                msg = (res.get("message") or "Paystack rejected the transfers")[:300]
                for it in rows.values():
                    settle_item(session, it, "failed", msg)
                continue
            seen = set()
            for d in res.get("data") or []:
                it = rows.get(d.get("reference"))
                if it is not None:
                    seen.add(it.reference)
                    settle_item(session, it, map_status(d.get("status")), None, d.get("transfer_code"))
            for ref, it in rows.items():                       # accepted request but this item was not echoed back: reconcile
                if ref not in seen and it.status == "pending":
                    logger.warning("payout item %s not in bulk response; left pending for reconcile", ref)
    return batch_summary(batch_id)


async def reconcile_batch(batch_id: uuid.UUID) -> dict:
    """Ask Paystack about every item that is not final and settle it. A transfer Paystack has never heard of cannot
    have left, so it is failed and returned to the wallet."""
    with get_session() as session:
        refs = [r for (r,) in session.execute(select(PayoutItem.reference).where(
            PayoutItem.batch_id == batch_id, PayoutItem.status.in_(("pending", "processing")))).all()]
    for ref in refs:
        res = await _paystack("GET", f"/transfer/verify/{ref}")
        code = res.get("_http_status", 200)
        with get_session() as session:
            it = session.execute(select(PayoutItem).where(PayoutItem.reference == ref)).scalar_one()
            if res.get("status"):
                d = res.get("data") or {}
                settle_item(session, it, map_status(d.get("status")), d.get("reason") if map_status(d.get("status")) == "failed" else None,
                            d.get("transfer_code"))
            elif code == 404:
                settle_item(session, it, "failed", "Transfer was never created at Paystack")
    return batch_summary(batch_id)


def batch_summary(batch_id: uuid.UUID) -> dict:
    with get_session() as session:
        b = session.get(PayoutBatch, batch_id)
        items = session.execute(select(PayoutItem).where(PayoutItem.batch_id == batch_id).order_by(PayoutItem.created_at)).scalars().all()
        counts = {s: sum(1 for i in items if i.status == s) for s in ("pending", "processing", "success", "failed")}
        status = ("failed" if counts["failed"] == len(items) else "completed" if counts["success"] == len(items)
                  else "partial" if counts["failed"] else "processing")
        return {"id": str(b.id), "kind": b.kind, "source_id": b.source_id, "attempt": b.attempt, "status": status,
                "total_zar": b.total_cents / 100, "fee_zar": b.fee_cents / 100, "counts": counts,
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "items": [{"item_ref": i.item_ref, "reference": i.reference, "status": i.status, "amount_zar": i.amount_cents / 100,
                           "fee_zar": i.fee_cents / 100, "transfer_code": i.transfer_code, "message": i.message} for i in items]}


# ---------------------------------------------------------------------------
# Internal endpoints (HR / purchasing call these with the service key)
# ---------------------------------------------------------------------------

def _internal(request: Request) -> None:
    if not internal_key_ok(request):
        raise HTTPException(status_code=403, detail="internal service key required")


@router.post("/internal/batches")
async def internal_create_batch(body: BatchIn, request: Request):
    _internal(request)
    short = None
    if _secret():
        have = await provider_balance_cents()
        need = sum(_cents(i.amount_zar) for i in body.items)
        if have is not None and have < need:
            short = {"message": "The payout provider balance is too low right now; try again shortly", "provider_balance_zar": have / 100}
    if short:
        raise HTTPException(status_code=503, detail=short)
    with get_session() as session:
        batch, _ = create_batch(session, body)
        batch_id = batch.id
    return await execute_batch(batch_id)


@router.get("/internal/by-source")
async def internal_by_source(request: Request, tenant_id: uuid.UUID, kind: str, source_id: str, reconcile: bool = False):
    """Latest state of every item ever sent for this source (HR uses it to refresh payslips)."""
    _internal(request)
    with get_session() as session:
        batch_ids = [b for (b,) in session.execute(select(PayoutBatch.id).where(
            PayoutBatch.tenant_id == tenant_id, PayoutBatch.kind == kind, PayoutBatch.source_id == source_id)
            .order_by(PayoutBatch.attempt)).all()]
    if reconcile and _secret():
        for b in batch_ids:
            await reconcile_batch(b)
    return {"batches": [batch_summary(b) for b in batch_ids]}


@router.post("/internal/quote")
async def internal_quote(request: Request, tenant_id: uuid.UUID, amount_zar: Decimal):
    _internal(request)
    with get_session() as session:
        return public_quote(quote(session, tenant_id, _cents(amount_zar)))


# ---------------------------------------------------------------------------
# Tenant-facing endpoints
# ---------------------------------------------------------------------------

class QuoteIn(BaseModel):
    amount_zar: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class FundingIn(BaseModel):
    amount_zar: Decimal = Field(gt=0, le=Decimal("5000000"), max_digits=12, decimal_places=2)
    email: str = Field(max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    callback_url: Optional[str] = None


class ManualFundingIn(BaseModel):
    tenant_id: uuid.UUID
    amount_zar: Decimal = Field(gt=0, le=Decimal("50000000"), max_digits=14, decimal_places=2)
    bank_reference: str = Field(min_length=3, max_length=100)


@router.get("/wallet", dependencies=[Depends(require_tier("reader"))])
async def wallet(ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        w = session.execute(select(PayoutWallet).where(PayoutWallet.tenant_id == ctx.tenant_id)).scalar_one_or_none()
        entries = session.execute(select(PayoutWalletEntry).where(PayoutWalletEntry.tenant_id == ctx.tenant_id)
                                  .order_by(PayoutWalletEntry.created_at.desc()).limit(50)).scalars().all()
        return {"balance_zar": (w.balance_cents if w else 0) / 100,
                "open_liabilities_zar": open_liabilities_cents(session, ctx.tenant_id) / 100,
                "entries": [{"kind": e.kind, "amount_zar": e.amount_cents / 100, "note": e.note,
                             "created_at": e.created_at.isoformat() if e.created_at else None} for e in entries]}


@router.post("/quote", dependencies=[Depends(require_tier("reader"))])
async def post_quote(body: QuoteIn, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        return public_quote(quote(session, ctx.tenant_id, _cents(body.amount_zar)))


@router.get("/batches", dependencies=[Depends(require_tier("reader"))])
async def list_batches(ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        ids = [b for (b,) in session.execute(select(PayoutBatch.id).where(PayoutBatch.tenant_id == ctx.tenant_id)
                                             .order_by(PayoutBatch.created_at.desc()).limit(50)).all()]
    return {"batches": [batch_summary(b) for b in ids]}


@router.post("/batches/{batch_id}/reconcile", dependencies=[Depends(require_tier("admin"))])
async def reconcile(batch_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        b = session.get(PayoutBatch, batch_id)
        if b is None or b.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="Batch not found")
    return await reconcile_batch(batch_id)


@router.post("/funding/initialize", dependencies=[Depends(require_tier("admin"))])
async def initialize_funding(body: FundingIn, ctx: AuthContext = Depends(get_auth_context)):
    """Top up the payout wallet by card. No subaccount: the money is OmniDome's until it is paid out. Large payrolls
    are cheaper by EFT (card processing costs OmniDome about 3%): see POST /payouts/funding/manual."""
    from services.billing.routes import paystack as ps
    if not _secret():
        raise HTTPException(status_code=503, detail="Paystack not configured")
    if body.callback_url and not ps.callback_allowed(body.callback_url):
        raise HTTPException(status_code=400, detail="callback_url host is not allowed")
    cents = _cents(body.amount_zar)
    reference = f"fund-{uuid.uuid4().hex}"
    with get_session() as session:
        session.add(PayoutFunding(tenant_id=ctx.tenant_id, reference=reference, amount_cents=cents, created_by=ctx.user_id))
    payload = {"email": body.email, "amount": cents, "currency": "ZAR", "reference": reference,
               "metadata": {"kind": "payout_funding", "tenant_id": str(ctx.tenant_id)}}
    if body.callback_url:
        payload["callback_url"] = body.callback_url
    res = await _paystack("POST", "/transaction/initialize", payload)
    data = res.get("data") or {}
    if not res.get("status") or not data.get("authorization_url"):
        with get_session() as session:
            session.query(PayoutFunding).filter(PayoutFunding.reference == reference).delete()
        raise HTTPException(status_code=502, detail="Payment gateway error")
    return {"authorization_url": data["authorization_url"], "reference": reference}


@router.post("/funding/manual", dependencies=[Depends(require_tier("admin"))])
async def manual_funding(body: ManualFundingIn, ctx: AuthContext = Depends(get_auth_context)):
    """A platform admin records an EFT the tenant paid to OmniDome. Idempotent per bank reference."""
    if not (getattr(ctx, "is_platform_admin", False) or "platform_admin" in {str(r).lower() for r in ctx.roles or []}):
        raise HTTPException(status_code=403, detail="Platform admin only")
    with get_session() as session:
        credited = credit_funding(session, body.tenant_id, "manual_funding", _cents(body.amount_zar), body.bank_reference,
                                  f"EFT {body.bank_reference} recorded by {ctx.user_id}")
    logger.info("manual payout funding tenant=%s ref=%s by=%s credited=%s", body.tenant_id, body.bank_reference, ctx.user_id, credited)
    return {"credited": credited, "tenant_id": str(body.tenant_id), "bank_reference": body.bank_reference}


# ---------------------------------------------------------------------------
# Webhook hooks (called from routes/paystack.py)
# ---------------------------------------------------------------------------

async def handle_funding_success(data: dict, key: str) -> str:
    """charge.success for a payout-funding checkout. Credits the wallet once, only for the amount we initialised."""
    reference = data.get("reference") or ""
    cents = int(data.get("amount") or 0)
    with get_session() as session:
        try:
            with session.begin_nested():
                session.add(BillingWebhookEvent(provider="paystack", event_key=key, event_type="charge.success", reference=reference or None))
                session.flush()
        except IntegrityError:
            return "duplicate"
        f = session.execute(select(PayoutFunding).where(PayoutFunding.reference == reference).with_for_update()).scalar_one_or_none()
        if f is None:
            logger.error("ALERT: funding charge %s matches no initialisation", reference)
            return "ignored"
        if str(data.get("currency") or "").upper() != "ZAR" or cents != f.amount_cents:
            logger.error("ALERT: funding charge %s amount/currency mismatch (%s %s vs %s)", reference, cents, data.get("currency"), f.amount_cents)
            return "rejected"
        if credit_funding(session, f.tenant_id, "funding", f.amount_cents, reference, "Card funding"):
            f.status = "credited"
    return "accepted"


async def handle_transfer_event(event: str, data: dict) -> str:
    """transfer.success | transfer.failed | transfer.reversed. Matches our items by reference; anything else
    (for example transfers made outside this system) is ignored."""
    reference = data.get("reference") or ""
    status = {"transfer.success": "success", "transfer.failed": "failed", "transfer.reversed": "failed"}.get(event)
    if not reference or status is None:
        return "ignored"
    key = f"{event}:{data.get('id') or reference}:{data.get('status')}:{data.get('updatedAt') or data.get('updated_at') or ''}"[:200]
    with get_session() as session:
        try:
            with session.begin_nested():
                session.add(BillingWebhookEvent(provider="paystack", event_key=key, event_type=event, reference=reference))
                session.flush()
        except IntegrityError:
            return "duplicate"
        item = session.execute(select(PayoutItem).where(PayoutItem.reference == reference).with_for_update()).scalar_one_or_none()
        if item is None:
            return "ignored"
        failure = (data.get("failures") or data.get("reason") or event) if status == "failed" else None
        settle_item(session, item, status, str(failure)[:300] if failure else None, data.get("transfer_code"))
    return "accepted"


class RecipientIn(BaseModel):
    tenant_id: uuid.UUID
    name: str = Field(min_length=2, max_length=200)
    account_number: str = Field(min_length=6, max_length=20, pattern=r"^\d+$")
    bank_code: str = Field(min_length=1, max_length=20)


@router.post("/internal/recipients")
async def internal_create_recipient(body: RecipientIn, request: Request):
    """Create a Paystack transfer recipient (South African bank account) for a supplier or employee. The account number
    is sent to Paystack once and never stored here; the caller keeps the returned recipient code and the last 4 digits."""
    _internal(request)
    if not _secret():
        return {"recipient_code": "RCP_MOCK_" + body.account_number[-6:], "mock": True}
    res = await _paystack("POST", "/transferrecipient", {"type": "basa", "name": body.name, "account_number": body.account_number,
                                                          "bank_code": body.bank_code, "currency": "ZAR",
                                                          "metadata": {"tenant_id": str(body.tenant_id)}})
    code = (res.get("data") or {}).get("recipient_code")
    if not res.get("status") or not code:
        raise HTTPException(status_code=422, detail=res.get("message") or "Paystack rejected the bank details")
    logger.info("transfer recipient created tenant=%s code=%s", body.tenant_id, code)
    return {"recipient_code": code}
