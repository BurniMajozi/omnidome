"""Gateway settings (tenant subaccount), commission preview/summary, and the hooks the charge flow uses.

The tenant registers the bank account its customers' payments settle to. We create a Paystack subaccount
once and keep only its code plus the last 4 digits of the account. Every tenant-customer charge then goes
through `split_for_charge`, which returns the `subaccount` / `transaction_charge` / `bearer` Paystack fields
and records the commission in billing_gateway_charges. See services/billing/gateway.py for the tier maths.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from services.billing import gateway, platform_tax
from services.billing.access import require_tier
from services.billing.database import get_session
from services.billing.models_gateway import GatewayChangeEvent, GatewayCharge, GatewaySettings
from services.billing.routes.paystack_recurring import _paystack, _secret
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("billing.gateway")

router = APIRouter(prefix="/gateway", tags=["Payment gateway"])


def require_subaccount() -> bool:
    """A tenant-customer charge is refused unless the tenant has an active subaccount; otherwise the money
    would land in OmniDome's own account with no commission record and no settlement to the tenant.
    On by default. GATEWAY_REQUIRE_SUBACCOUNT=false is an explicit escape hatch (tests / bring-up only)."""
    return os.getenv("GATEWAY_REQUIRE_SUBACCOUNT", "true").strip().lower() not in {"0", "false", "no", "off"}


def _tiers_for(settings: Optional[GatewaySettings]):
    if settings is not None and settings.commission_tiers:
        try:
            return gateway.validate_tiers(settings.commission_tiers)
        except gateway.TierError:
            logger.error("invalid commission_tiers on tenant %s; using defaults", settings.tenant_id)
    return gateway.DEFAULT_TIERS


def month_volume_cents(session, tenant_id, period: str) -> int:
    return int(session.execute(
        select(func.coalesce(func.sum(GatewayCharge.gross_cents), 0)).where(
            GatewayCharge.tenant_id == tenant_id, GatewayCharge.period == period,
            GatewayCharge.status == "succeeded")).scalar_one())


def split_for_charge(session, tenant_id, amount_cents: int, reference: str,
                     invoice_id=None, kind: str = "invoice") -> Optional[dict]:
    """Paystack split fields for a tenant-customer charge, or None when the tenant has no active subaccount.

    Records the ledger row in the caller's transaction. Only *succeeded* charges count toward the month's
    volume, so two charges initialised at the same moment see the same volume (a few rand can land in the
    wrong band; the ledger keeps the inputs so the difference is auditable)."""
    settings = session.execute(select(GatewaySettings).where(GatewaySettings.tenant_id == tenant_id)).scalar_one_or_none()
    if settings is None or settings.status != "active":
        if require_subaccount():
            raise HTTPException(status_code=409, detail="Payment gateway is not set up for this account")
        return None
    period = gateway.period_key()
    before = month_volume_cents(session, tenant_id, period)
    calc = gateway.calculate(amount_cents, before, _tiers_for(settings))
    session.add(GatewayCharge(
        tenant_id=tenant_id, reference=reference, invoice_id=invoice_id, kind=kind,
        subaccount_code=settings.subaccount_code, period=period, gross_cents=amount_cents,
        commission_cents=calc.commission_cents, volume_before_cents=before,
        commission_vat_cents=platform_tax.vat_inside(calc.commission_cents, session)))
    return {"subaccount": settings.subaccount_code, "transaction_charge": calc.commission_cents, "bearer": "account"}


def discard_charge(session, reference: str) -> None:
    session.query(GatewayCharge).filter(GatewayCharge.reference == reference, GatewayCharge.status == "initialized").delete()


def mark_charge_succeeded(session, reference: str, paystack_fee_cents: Optional[int]) -> Optional[dict]:
    """Webhook hook: runs inside the webhook transaction, so it commits or rolls back with the payment.
    Returns the tenant-ledger entry for OmniDome's commission (Dr 6950 / Cr 1010) for the caller to enqueue."""
    from services.billing import finance_posting as fp
    row = session.query(GatewayCharge).filter(GatewayCharge.reference == reference).with_for_update().first()
    if row is None or row.status == "succeeded":
        return None
    row.status = "succeeded"
    row.settled_at = datetime.now(timezone.utc)
    if paystack_fee_cents is not None:
        row.paystack_fee_cents = int(paystack_fee_cents)
    if row.commission_cents > 0:
        return fp.gateway_fee_entry(row.id, reference, fp.sast_today(), Decimal(row.commission_cents) / 100)
    return None


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GatewaySetupRequest(BaseModel):
    business_name: str = Field(min_length=2, max_length=200)
    settlement_bank_code: str = Field(min_length=1, max_length=20)
    account_number: str = Field(min_length=6, max_length=20, pattern=r"^\d+$")


def _public(settings: Optional[GatewaySettings]) -> dict:
    if settings is None:
        return {"configured": False, "status": "not_configured", "require_subaccount": require_subaccount()}
    return {"configured": True, "status": settings.status, "business_name": settings.business_name,
            "settlement_bank_code": settings.settlement_bank_code, "settlement_bank_name": settings.settlement_bank_name,
            "account_last4": settings.account_last4, "subaccount_code": settings.subaccount_code,
            "custom_tiers": bool(settings.commission_tiers), "require_subaccount": require_subaccount(),
            "pending_change": None if not settings.pending_subaccount_code else {
                "bank": settings.pending_bank_code, "last4": settings.pending_account_last4,
                "requested_at": settings.pending_requested_at.isoformat() if settings.pending_requested_at else None},
            "updated_at": settings.updated_at.isoformat() if settings.updated_at else None}


def _tiers_public(tiers) -> list[dict]:
    out, lower = [], 0
    for upper, bps in tiers:
        out.append({"from_zar": lower / 100, "to_zar": None if upper is None else upper / 100, "rate_percent": bps / 100})
        lower = upper or lower
    return out


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/settings", dependencies=[Depends(require_tier("reader"))])
async def get_settings(ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        settings = session.execute(select(GatewaySettings).where(GatewaySettings.tenant_id == ctx.tenant_id)).scalar_one_or_none()
        return {**_public(settings), "tiers": _tiers_public(_tiers_for(settings))}


@router.get("/banks", dependencies=[Depends(require_tier("admin"))])
async def list_banks(ctx: AuthContext = Depends(get_auth_context)):
    """South African banks Paystack can settle to (code + name), for the setup form."""
    if not _secret():
        return {"banks": [], "mock": True}
    res = await _paystack("GET", "/bank?country=south%20africa&currency=ZAR&perPage=100")
    if not res.get("status"):
        raise HTTPException(status_code=502, detail="Could not load the bank list")
    return {"banks": [{"code": b.get("code"), "name": b.get("name")} for b in res.get("data", []) if b.get("code")]}


async def _create_subaccount(ctx: AuthContext, body: "GatewaySetupRequest") -> str:
    """New Paystack subaccount for these bank details. Paystack gets the full account number; we never keep it.
    `percentage_charge` is the share that stays with OmniDome if a charge is ever made without an explicit
    commission, so it is set to the top rate (6%) as the safe default."""
    if not _secret():
        code = "ACCT_MOCK_" + uuid.uuid4().hex[:8]
        logger.warning("PAYSTACK_SECRET_KEY not set; mock subaccount %s", code)
        return code
    res = await _paystack("POST", "/subaccount", {
        "business_name": body.business_name, "settlement_bank": body.settlement_bank_code,
        "account_number": body.account_number,
        "percentage_charge": float(gateway.DEFAULT_TIERS[0][1]) / 100,
        "metadata": {"tenant_id": str(ctx.tenant_id)}})
    if not res.get("status"):
        raise HTTPException(status_code=502, detail=res.get("message", "Paystack rejected the bank details"))
    code = (res.get("data") or {}).get("subaccount_code")
    if not code:
        raise HTTPException(status_code=502, detail="Paystack did not return a subaccount code")
    return code


async def _alert_ops(subject: str, html: str) -> None:
    """Best-effort email to GATEWAY_ALERT_EMAIL (platform finance/ops). Never blocks or fails the request."""
    to = os.getenv("GATEWAY_ALERT_EMAIL", "").strip()
    if not to:
        return
    try:
        from services.common.agentmail import send_email
        await send_email(to, subject, html)
    except Exception as exc:  # noqa: BLE001
        logger.warning("gateway alert email failed: %s", type(exc).__name__)


def _is_platform_admin(ctx: AuthContext) -> bool:
    return bool(getattr(ctx, "is_platform_admin", False)) or "platform_admin" in {str(r).lower() for r in ctx.roles or []}


@router.put("/settings", dependencies=[Depends(require_tier("admin"))])
async def set_settings(body: GatewaySetupRequest, ctx: AuthContext = Depends(get_auth_context)):
    """First setup takes effect immediately. Any later change is a *request*: it gets its own new Paystack
    subaccount, charges keep settling to the existing one, and a different platform admin must approve the
    swap (POST /gateway/changes/{tenant_id}/approve). That stops a hijacked tenant admin from silently
    redirecting settlements."""
    last4 = body.account_number[-4:]
    with get_session() as session:
        existing = session.execute(select(GatewaySettings).where(GatewaySettings.tenant_id == ctx.tenant_id)).scalar_one_or_none()
        first_time = existing is None

    code = await _create_subaccount(ctx, body)

    with get_session() as session:
        row = session.execute(select(GatewaySettings).where(GatewaySettings.tenant_id == ctx.tenant_id)).scalar_one_or_none()
        if row is None:
            row = GatewaySettings(tenant_id=ctx.tenant_id, status="active", business_name=body.business_name,
                                  settlement_bank_code=body.settlement_bank_code, account_last4=last4,
                                  subaccount_code=code, updated_by=ctx.user_id)
            session.add(row)
            session.add(GatewayChangeEvent(tenant_id=ctx.tenant_id, event="setup", actor_id=ctx.user_id,
                                           detail={"bank": body.settlement_bank_code, "last4": last4, "subaccount": code}))
            event = None
        else:
            row.pending_subaccount_code, row.pending_business_name = code, body.business_name
            row.pending_bank_code, row.pending_account_last4 = body.settlement_bank_code, last4
            row.pending_requested_by, row.pending_requested_at = ctx.user_id, datetime.now(timezone.utc)
            session.add(GatewayChangeEvent(tenant_id=ctx.tenant_id, event="change_requested", actor_id=ctx.user_id,
                                           detail={"from": {"bank": row.settlement_bank_code, "last4": row.account_last4},
                                                   "to": {"bank": body.settlement_bank_code, "last4": last4}, "subaccount": code}))
            event = (row.business_name, row.account_last4, last4)
        logger.info("gateway %s tenant=%s subaccount=%s by=%s", "setup" if first_time else "change requested",
                    ctx.tenant_id, code, ctx.user_id)
        session.flush()
        out = _public(row)
    if event:
        await _alert_ops("Settlement account change awaiting approval",
                         f"<p>Tenant <b>{event[0]}</b> ({ctx.tenant_id}) asked to change its settlement account "
                         f"(…{event[1]} → …{event[2]}). Approve or reject it in OmniDome billing; settlements stay on the "
                         f"current account until then.</p>")
    return out


def _require_platform_admin(ctx: AuthContext) -> None:
    if not _is_platform_admin(ctx):
        raise HTTPException(status_code=403, detail="Platform admin only")


@router.get("/changes/pending", dependencies=[Depends(require_tier("admin"))])
async def pending_changes(ctx: AuthContext = Depends(get_auth_context)):
    _require_platform_admin(ctx)
    with get_session() as session:
        rows = session.execute(select(GatewaySettings).where(GatewaySettings.pending_subaccount_code.is_not(None))).scalars().all()
        return {"changes": [{
            "tenant_id": str(r.tenant_id), "business_name": r.business_name,
            "current": {"bank": r.settlement_bank_code, "last4": r.account_last4},
            "requested": {"bank": r.pending_bank_code, "last4": r.pending_account_last4, "business_name": r.pending_business_name},
            "requested_by": str(r.pending_requested_by) if r.pending_requested_by else None,
            "requested_at": r.pending_requested_at.isoformat() if r.pending_requested_at else None} for r in rows]}


@router.post("/changes/{tenant_id}/approve", dependencies=[Depends(require_tier("admin"))])
async def approve_change(tenant_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    _require_platform_admin(ctx)
    with get_session() as session:
        row = session.execute(select(GatewaySettings).where(GatewaySettings.tenant_id == tenant_id).with_for_update()).scalar_one_or_none()
        if row is None or not row.pending_subaccount_code:
            raise HTTPException(status_code=404, detail="No pending change for this tenant")
        if row.pending_requested_by is not None and row.pending_requested_by == ctx.user_id:
            raise HTTPException(status_code=403, detail="A different admin must approve this change")
        session.add(GatewayChangeEvent(tenant_id=tenant_id, event="change_approved", actor_id=ctx.user_id,
                                       detail={"from": {"bank": row.settlement_bank_code, "last4": row.account_last4},
                                               "to": {"bank": row.pending_bank_code, "last4": row.pending_account_last4},
                                               "subaccount": row.pending_subaccount_code}))
        row.subaccount_code, row.business_name = row.pending_subaccount_code, row.pending_business_name or row.business_name
        row.settlement_bank_code, row.account_last4 = row.pending_bank_code, row.pending_account_last4
        row.updated_by = ctx.user_id
        row.pending_subaccount_code = row.pending_business_name = row.pending_bank_code = row.pending_account_last4 = None
        row.pending_requested_by = row.pending_requested_at = None
        session.flush()
        logger.info("gateway change approved tenant=%s by=%s", tenant_id, ctx.user_id)
        return _public(row)


@router.post("/changes/{tenant_id}/reject", dependencies=[Depends(require_tier("admin"))])
async def reject_change(tenant_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    _require_platform_admin(ctx)
    with get_session() as session:
        row = session.execute(select(GatewaySettings).where(GatewaySettings.tenant_id == tenant_id).with_for_update()).scalar_one_or_none()
        if row is None or not row.pending_subaccount_code:
            raise HTTPException(status_code=404, detail="No pending change for this tenant")
        session.add(GatewayChangeEvent(tenant_id=tenant_id, event="change_rejected", actor_id=ctx.user_id,
                                       detail={"subaccount": row.pending_subaccount_code}))
        row.pending_subaccount_code = row.pending_business_name = row.pending_bank_code = row.pending_account_last4 = None
        row.pending_requested_by = row.pending_requested_at = None
        session.flush()
        logger.info("gateway change rejected tenant=%s by=%s", tenant_id, ctx.user_id)
        return _public(row)


@router.get("/commission/preview", dependencies=[Depends(require_tier("reader"))])
async def preview(amount_zar: Decimal, ctx: AuthContext = Depends(get_auth_context)):
    if amount_zar <= 0 or amount_zar > Decimal("10000000"):
        raise HTTPException(status_code=400, detail="amount_zar out of range")
    with get_session() as session:
        settings = session.execute(select(GatewaySettings).where(GatewaySettings.tenant_id == ctx.tenant_id)).scalar_one_or_none()
        before = month_volume_cents(session, ctx.tenant_id, gateway.period_key())
        calc = gateway.calculate(int((amount_zar * 100).to_integral_value()), before, _tiers_for(settings))
    return {"amount_zar": float(amount_zar), "commission_zar": calc.commission_cents / 100,
            "tenant_receives_zar": calc.tenant_net_cents / 100, "effective_rate_percent": float(calc.effective_bps) / 100,
            "month_volume_zar": before / 100}


@router.get("/summary", dependencies=[Depends(require_tier("reader"))])
async def summary(ctx: AuthContext = Depends(get_auth_context)):
    """This month's processed volume, the current band, and commission charged so far."""
    period = gateway.period_key()
    with get_session() as session:
        settings = session.execute(select(GatewaySettings).where(GatewaySettings.tenant_id == ctx.tenant_id)).scalar_one_or_none()
        tiers = _tiers_for(settings)
        volume, commission, count = session.execute(
            select(func.coalesce(func.sum(GatewayCharge.gross_cents), 0), func.coalesce(func.sum(GatewayCharge.commission_cents), 0),
                   func.count()).where(
                GatewayCharge.tenant_id == ctx.tenant_id, GatewayCharge.period == period,
                GatewayCharge.status == "succeeded")).one()
    band = gateway.band_for_volume(int(volume), tiers)
    return {"period": period, "volume_zar": int(volume) / 100, "charges": int(count), "commission_zar": int(commission) / 100,
            "current_rate_percent": band["rate_bps"] / 100,
            "next_threshold_zar": None if band["next_threshold_cents"] is None else band["next_threshold_cents"] / 100,
            "remaining_in_band_zar": None if band["remaining_in_band_cents"] is None else band["remaining_in_band_cents"] / 100,
            "tiers": _tiers_public(tiers)}


@router.get("/liabilities", dependencies=[Depends(require_tier("reader"))])
async def liabilities(ctx: AuthContext = Depends(get_auth_context)):
    """Refunds and lost disputes OmniDome paid out of its own balance for this tenant's customers. The tenant was
    already settled for those charges, so the amount is owed back and is netted against future pre-funding / top-ups."""
    from services.billing.models_gateway import GatewayLiability
    with get_session() as session:
        rows = session.execute(select(GatewayLiability).where(GatewayLiability.tenant_id == ctx.tenant_id)
                               .order_by(GatewayLiability.created_at.desc()).limit(200)).scalars().all()
        items = [{"id": str(r.id), "kind": r.kind, "amount_zar": r.amount_cents / 100, "status": r.status, "note": r.note,
                  "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]
    owed = sum(i["amount_zar"] for i in items if i["status"] == "open")
    return {"owed_zar": round(owed, 2), "items": items}
