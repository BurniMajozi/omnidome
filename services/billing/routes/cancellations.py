"""Billing Cancellation & Termination Fee routes.

Handles the full cancellation lifecycle:
- Customer initiates cancellation
- Retention offer evaluation (via journey engine)
- Early Termination Fee (ETF) calculation
- Router return (reverse logistics) tracking
- FNO cancellation (with browser automation for FNOs without API)
"""

import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from services.billing.models import (
    CancellationRequest, TerminationFee, RouterReturn, FNOCancellation,
    Subscription, Invoice, Payment,
    CANCEL_STATUS, ROUTER_RETURN_STATUS, ROUTER_CONDITION,
    FNO_CANCELLATION_STATUS, FNO_CANCELLATION_METHOD,
)
from services.common.auth import AuthContext, get_auth_context
from services.billing.access import require_tier
from services.billing import fee_policies as fees
from services.billing.models_fees import FeePolicy

logger = logging.getLogger("billing.cancellations")

router = APIRouter(prefix="/cancellations", tags=["Cancellations"])


# ── Request/Response Schemas ─────────────────────────────────────────────

class CancelInitiateRequest(BaseModel):
    subscription_id: uuid.UUID
    cancel_type: str = "voluntary"  # voluntary, move_house, debt_collection, death, other
    cancel_reason: Optional[str] = None
    cancel_reason_detail: Optional[str] = None
    effective_date: Optional[date] = None


class CancelInitiateResponse(BaseModel):
    cancellation_id: uuid.UUID
    status: str
    message: str
    retention_offer_eligible: bool
    # Fee engine result when the tenant has an applicable fee policy (auto-run on initiate).
    fee_calculation_id: Optional[uuid.UUID] = None
    fee_total_zar: Optional[Decimal] = None
    fee_amount_due_zar: Optional[Decimal] = None


class ETFCalculationResponse(BaseModel):
    customer_id: uuid.UUID
    account_number: str
    monthly_rate_zar: Decimal
    remaining_months: int
    penalty_percentage: Decimal
    contract_etf_zar: Decimal
    router_charge_zar: Decimal
    outstanding_balance_zar: Decimal
    total_etf_zar: Decimal
    router_return_option: bool
    # Fee engine fields. engine="legacy" means no fee policy applies and the hardcoded penalty tiers were used.
    engine: str = "legacy"
    calculation_id: Optional[uuid.UUID] = None
    policy_id: Optional[uuid.UUID] = None
    policy_version: Optional[int] = None
    fee_net_zar: Optional[Decimal] = None
    fee_vat_zar: Optional[Decimal] = None
    fee_total_zar: Optional[Decimal] = None   # VAT-inclusive fee after waivers
    amount_due_zar: Optional[Decimal] = None
    flags: list[str] = []
    breakdown: Optional[dict] = None


class ETFCalculationRequest(BaseModel):
    reason_code: Optional[str] = None  # e.g. fno_fault, relocation_in_coverage; defaults from the cancellation


class RouterReturnBookRequest(BaseModel):
    cancellation_request_id: uuid.UUID
    product_id: uuid.UUID
    serial_number: str
    imei: Optional[str] = None
    pickup_address: str


class RouterReturnInspectRequest(BaseModel):
    router_return_id: uuid.UUID
    condition: str  # new, good, fair, damaged, missing_parts
    condition_notes: Optional[str] = None
    refund_amount_zar: Decimal = Decimal("0.00")


class FNOCancelSubmitRequest(BaseModel):
    cancellation_request_id: uuid.UUID
    fno_name: str
    fno_account_number: Optional[str] = None


# ── ETF Calculation Constants ────────────────────────────────────────────

PENALTY_TIERS = [
    (6, Decimal("1.00")),    # < 6 months: 100% penalty
    (12, Decimal("0.75")),   # 6-12 months: 75% penalty
    (999, Decimal("0.50")),  # > 12 months: 50% penalty
]

ROUTER_DEPRECIATION = [
    (12, Decimal("1.00")),   # < 12 months: full value
    (24, Decimal("0.75")),   # 12-24 months: 75% value
    (999, Decimal("0.50")),  # > 24 months: 50% value
]

ROUTER_DEFAULT_VALUES = {
    "ONT-V1": Decimal("799.00"),
    "ONT-H1": Decimal("899.00"),
    "RTR-NET-05": Decimal("599.00"),
    "RTR-TP-01": Decimal("349.00"),
    "DEFAULT": Decimal("600.00"),
}


def _calculate_etf(
    monthly_rate: Decimal,
    remaining_months: int,
    subscription_start: date,
    device_sku: str = "DEFAULT",
) -> dict:
    """Calculate Early Termination Fee."""
    # Penalty percentage based on remaining contract
    penalty_pct = Decimal("0.50")
    for threshold, pct in PENALTY_TIERS:
        if remaining_months <= threshold:
            penalty_pct = pct
            break

    # Contract ETF
    contract_etf = Decimal(str(remaining_months)) * monthly_rate * penalty_pct
    contract_etf = contract_etf.quantize(Decimal("0.01"))

    # Router depreciation based on customer tenure
    tenure_months = (date.today() - subscription_start).days // 30
    router_value = ROUTER_DEFAULT_VALUES.get(device_sku, ROUTER_DEFAULT_VALUES["DEFAULT"])
    depreciation = Decimal("0.50")
    for threshold, dep in ROUTER_DEPRECIATION:
        if tenure_months <= threshold:
            depreciation = dep
            break
    router_charge = (router_value * depreciation).quantize(Decimal("0.01"))

    return {
        "penalty_percentage": penalty_pct,
        "contract_etf_zar": contract_etf,
        "router_charge_zar": router_charge,
        "router_value_zar": router_value,
        "router_depreciation_pct": depreciation,
    }


def _inspected_router(session, tenant_id, cancel_id):
    """(returned, condition) from the latest inspected router return of this cancellation."""
    rr = session.query(RouterReturn).filter(
        RouterReturn.tenant_id == tenant_id, RouterReturn.cancellation_request_id == cancel_id,
        RouterReturn.condition.isnot(None)).order_by(RouterReturn.inspected_at.desc()).first()
    return (True, rr.condition) if rr is not None else (False, None)


def _auto_fee(session, cancel_req, sub, ctx):
    """Auto-run the fee engine when a cancellation is initiated. Never blocks the cancellation itself."""
    try:
        with session.begin_nested():
            res = fees.calculate_for_cancellation(session, cancel_req, sub, actor_id=ctx.user_id, auto=True)
            if res is None:
                return None
            calc, _tf, pol = res
            if (pol.get("auto_invoice") and pol.get("auto_invoice_stage") == "initiate"
                    and cancel_req.status != "retention_offered" and calc.amount_due_zar > 0):
                fees.invoice_calculation(session, calc, pol, issue=True, actor_id=ctx.user_id)
            return calc
    except Exception:  # noqa: BLE001
        logger.warning("auto fee calculation failed for cancellation %s", cancel_req.id, exc_info=True)
        return None


def _engine_router_update(session, ctx, rr, calc, condition):
    """Apply the router-return credit through the engine. An un-invoiced calculation is recalculated; an invoiced
    one is never mutated: the credit that is now due is reported so a credit note can be raised."""
    cancel_req = session.get(CancellationRequest, rr.cancellation_request_id)
    sub = session.get(Subscription, cancel_req.subscription_id) if cancel_req and cancel_req.subscription_id else None
    if cancel_req is None or sub is None:
        return None
    if calc.status == "invoiced":
        try:
            _p, _pol, bd, _d, _s, _i = fees.run_calculation(
                session, tenant_id=ctx.tenant_id, sub=sub, trigger="cancellation",
                effective_date=cancel_req.effective_date or date.today(), reason_code=fees.reason_code_for(cancel_req),
                router_returned=True, router_condition=condition, policy_id=calc.policy_id)
        except LookupError:
            return None
        new_due = bd["totals"]["fee_total"]
        credit = max(calc.amount_due_zar - new_due, Decimal("0.00"))
        return {"mode": "invoiced_no_change", "invoice_id": str(calc.invoice_id), "credit_note_required_zar": str(credit)}
    res = fees.calculate_for_cancellation(
        session, cancel_req, sub, actor_id=ctx.user_id, router_returned=True, router_condition=condition)
    if res is None:
        return None
    new_calc, tf, _pol = res
    tf.router_returned = True
    tf.router_returned_at = datetime.utcnow()
    return {"mode": "recalculated", "calculation_id": str(new_calc.id), "amount_due_zar": str(new_calc.amount_due_zar),
            "flags": list(new_calc.flags or [])}


# ── POST /cancellations/initiate ─────────────────────────────────────────

@router.post("/initiate", response_model=CancelInitiateResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_tier("clerk"))])
async def initiate_cancellation(
    body: CancelInitiateRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Customer initiates cancellation — triggers retention evaluation."""
    from services.billing.database import get_session
    from sqlalchemy import select

    with get_session() as session:
        # Get subscription
        sub = session.query(Subscription).filter(
            Subscription.id == body.subscription_id,
            Subscription.tenant_id == ctx.tenant_id,
        ).first()
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")
        if sub.status == "cancelled":
            raise HTTPException(status_code=400, detail="Subscription already cancelled")

        # Create cancellation request
        cancel_req = CancellationRequest(
            tenant_id=ctx.tenant_id,
            customer_id=sub.customer_id,
            subscription_id=body.subscription_id,
            account_number="ACC-0001",  # Would come from customer record
            cancel_type=body.cancel_type,
            cancel_reason=body.cancel_reason,
            cancel_reason_detail=body.cancel_reason_detail,
            effective_date=body.effective_date or (date.today() + timedelta(days=30)),
            status="pending",
        )
        session.add(cancel_req)
        session.flush()

        # Evaluate retention eligibility
        retention_eligible = sub.base_price_zar >= Decimal("500.00")

        if retention_eligible:
            cancel_req.status = "retention_offered"
            cancel_req.retention_offer_shown = True
            session.flush()

        calc = _auto_fee(session, cancel_req, sub, ctx)

        return CancelInitiateResponse(
            cancellation_id=cancel_req.id,
            status=cancel_req.status,
            message="Cancellation initiated" + (". Retention offer available." if retention_eligible else "."),
            retention_offer_eligible=retention_eligible,
            fee_calculation_id=calc.id if calc else None,
            fee_total_zar=calc.fee_total_zar if calc else None,
            fee_amount_due_zar=calc.amount_due_zar if calc else None,
        )


# ── POST /cancellations/{id}/calculate-etf ───────────────────────────────

@router.post("/{cancel_id}/calculate-etf", response_model=ETFCalculationResponse, dependencies=[Depends(require_tier("clerk"))])
async def calculate_termination_fee(
    cancel_id: uuid.UUID,
    body: Optional[ETFCalculationRequest] = None,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Calculate the early termination / claw-back fee for a cancellation request.

    Uses the tenant's fee policy (services/billing/fee_policies.py). Only when the tenant has no applicable
    policy does it fall back to the legacy hardcoded penalty tiers (response engine="legacy")."""
    from services.billing.database import get_session
    from sqlalchemy import select, func

    with get_session() as session:
        cancel_req = session.query(CancellationRequest).filter(
            CancellationRequest.id == cancel_id,
            CancellationRequest.tenant_id == ctx.tenant_id,
        ).first()
        if not cancel_req:
            raise HTTPException(status_code=404, detail="Cancellation request not found")

        sub = session.query(Subscription).filter(
            Subscription.id == cancel_req.subscription_id,
        ).first()
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")

        returned, condition = _inspected_router(session, ctx.tenant_id, cancel_id)
        res = fees.calculate_for_cancellation(
            session, cancel_req, sub, actor_id=ctx.user_id, router_returned=returned, router_condition=condition,
            reason_code=(body.reason_code.strip().lower() if body and body.reason_code else None))
        if res is not None:
            calc, tf, _pol = res
            return ETFCalculationResponse(
                customer_id=cancel_req.customer_id, account_number=cancel_req.account_number,
                monthly_rate_zar=sub.base_price_zar, remaining_months=tf.remaining_months,
                penalty_percentage=tf.penalty_percentage, contract_etf_zar=tf.contract_etf_zar,
                router_charge_zar=tf.router_charge_zar, outstanding_balance_zar=tf.outstanding_balance_zar,
                total_etf_zar=tf.total_etf_zar, router_return_option=True, engine="policy",
                calculation_id=calc.id, policy_id=calc.policy_id, policy_version=calc.policy_version,
                fee_net_zar=calc.fee_net_zar, fee_vat_zar=calc.fee_vat_zar, fee_total_zar=calc.fee_total_zar,
                amount_due_zar=calc.amount_due_zar, flags=list(calc.flags or []), breakdown=calc.breakdown)

        # No fee policy for this tenant: legacy hardcoded tiers (kept as a clearly flagged fallback).
        # Calculate remaining months
        if cancel_req.effective_date:
            remaining = max(0, (cancel_req.effective_date - date.today()).days // 30)
        else:
            remaining = max(0, 12)  # Default 12-month assumption

        etf = _calculate_etf(
            monthly_rate=sub.base_price_zar,
            remaining_months=remaining,
            subscription_start=sub.current_period_start or date.today(),
            device_sku=sub.plan,
        )

        # Get outstanding balance
        outstanding = session.query(func.coalesce(func.sum(Invoice.total_zar - Invoice.amount_paid_zar), Decimal("0.00"))).filter(
            Invoice.customer_id == cancel_req.customer_id,
            Invoice.status.in_(["sent", "overdue", "partially_paid"]),
        ).scalar()

        total_etf = etf["contract_etf_zar"] + etf["router_charge_zar"] + outstanding

        # Store calculation
        tf = TerminationFee(
            tenant_id=ctx.tenant_id,
            customer_id=cancel_req.customer_id,
            cancellation_request_id=cancel_id,
            subscription_id=cancel_req.subscription_id,
            monthly_rate_zar=sub.base_price_zar,
            remaining_months=remaining,
            penalty_percentage=etf["penalty_percentage"],
            contract_etf_zar=etf["contract_etf_zar"],
            router_charge_zar=etf["router_charge_zar"],
            outstanding_balance_zar=outstanding,
            total_etf_zar=total_etf,
            router_value_zar=etf["router_value_zar"],
            router_depreciation_pct=etf["router_depreciation_pct"],
        )
        session.add(tf)
        session.flush()

        return ETFCalculationResponse(
            customer_id=cancel_req.customer_id,
            account_number=cancel_req.account_number,
            monthly_rate_zar=sub.base_price_zar,
            remaining_months=remaining,
            penalty_percentage=etf["penalty_percentage"],
            contract_etf_zar=etf["contract_etf_zar"],
            router_charge_zar=etf["router_charge_zar"],
            outstanding_balance_zar=outstanding,
            total_etf_zar=total_etf,
            router_return_option=True,
            engine="legacy",
            flags=["legacy_no_policy"],
        )


# ── POST /cancellations/{id}/accept-retention ────────────────────────────

@router.post("/{cancel_id}/accept-retention", dependencies=[Depends(require_tier("clerk"))])
async def accept_retention_offer(
    cancel_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Customer accepts retention offer — cancellation reversed."""
    from services.billing.database import get_session

    with get_session() as session:
        cancel_req = session.query(CancellationRequest).filter(
            CancellationRequest.id == cancel_id,
            CancellationRequest.tenant_id == ctx.tenant_id,
        ).first()
        if not cancel_req:
            raise HTTPException(status_code=404, detail="Cancellation request not found")

        cancel_req.status = "cancelled"
        cancel_req.retention_accepted = True
        cancel_req.completed_at = datetime.utcnow()

        # Reactivate subscription if paused
        if cancel_req.subscription_id:
            sub = session.query(Subscription).get(cancel_req.subscription_id)
            if sub and sub.status == "paused":
                sub.status = "active"

        return {"status": "retention_accepted", "message": "Customer retained. Subscription remains active."}


# ── POST /cancellations/{id}/proceed ─────────────────────────────────────

@router.post("/{cancel_id}/proceed", dependencies=[Depends(require_tier("admin"))])
async def proceed_with_cancellation(
    cancel_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Customer rejects retention — proceed with cancellation."""
    from services.billing.database import get_session

    with get_session() as session:
        cancel_req = session.query(CancellationRequest).filter(
            CancellationRequest.id == cancel_id,
            CancellationRequest.tenant_id == ctx.tenant_id,
        ).first()
        if not cancel_req:
            raise HTTPException(status_code=404, detail="Cancellation request not found")

        cancel_req.status = "fno_submitted"
        cancel_req.completed_at = datetime.utcnow()

        # Deactivate subscription
        if cancel_req.subscription_id:
            sub = session.query(Subscription).get(cancel_req.subscription_id)
            if sub:
                sub.status = "cancelled"
                sub.cancelled_at = datetime.utcnow()

        # Final invoice: fee engine when a policy applied, legacy hardcoded ETF otherwise.
        fee_invoice = None
        calc = fees.current_cancellation_calc(session, ctx.tenant_id, cancel_id)
        sub_row = session.query(Subscription).get(cancel_req.subscription_id) if cancel_req.subscription_id else None
        if (calc is None or calc.status != "invoiced") and sub_row is not None:
            returned, condition = _inspected_router(session, ctx.tenant_id, cancel_id)
            res = fees.calculate_for_cancellation(
                session, cancel_req, sub_row, actor_id=ctx.user_id, router_returned=returned, router_condition=condition)
            if res is not None:
                calc = res[0]
        if calc is not None:
            if calc.amount_due_zar > 0 or calc.invoice_id:
                pol = fees.policy_to_engine(session.get(FeePolicy, calc.policy_id))
                inv, _created = fees.invoice_calculation(
                    session, calc, pol, issue=bool(pol.get("auto_invoice")), actor_id=ctx.user_id)
                fee_invoice = {"invoice_id": str(inv.id), "invoice_number": inv.number, "status": inv.status,
                               "total_zar": str(inv.total_zar), "calculation_id": str(calc.id)}
        else:
            tf = session.query(TerminationFee).filter(
                TerminationFee.cancellation_request_id == cancel_id,
            ).first()
            if tf and tf.total_etf_zar > 0:
                inv = Invoice(
                    tenant_id=ctx.tenant_id,
                    customer_id=cancel_req.customer_id,
                    subscription_id=cancel_req.subscription_id,
                    number=f"ETF-{str(cancel_id)[:8]}",
                    status="sent",
                    subtotal_zar=tf.total_etf_zar,
                    vat_zar=(tf.total_etf_zar * Decimal("0.15")).quantize(Decimal("0.01")),
                    total_zar=(tf.total_etf_zar * Decimal("1.15")).quantize(Decimal("0.01")),
                    due_date=date.today() + timedelta(days=14),
                )
                session.add(inv)
                session.flush()
                tf.invoice_id = inv.id
                # Issued invoice: queue its ledger entry (delivered by the outbox retry/worker) and dun it.
                from services.billing import invoicing
                invoicing.enqueue_issue(session, inv)
                invoicing.schedule_dunning(session, inv)
                fee_invoice = {"invoice_id": str(inv.id), "invoice_number": inv.number, "status": inv.status,
                               "total_zar": str(inv.total_zar), "legacy": True}

        return {
            "status": "cancellation_proceeding",
            "message": "Cancellation confirmed. Final invoice generated.",
            "fno_cancellation_required": True,
            "fee_invoice": fee_invoice,
        }


# ── POST /cancellations/{cancel_id}/router-return ────────────────────────

@router.post("/{cancel_id}/router-return", dependencies=[Depends(require_tier("clerk"))])
async def book_router_return(
    cancel_id: uuid.UUID,
    body: RouterReturnBookRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Book a router return (reverse logistics)."""
    from services.billing.database import get_session

    with get_session() as session:
        cancel_req = session.query(CancellationRequest).filter(
            CancellationRequest.id == cancel_id,
            CancellationRequest.tenant_id == ctx.tenant_id,
        ).first()
        if not cancel_req:
            raise HTTPException(status_code=404, detail="Cancellation request not found")

        # Get termination fee for router details
        tf = session.query(TerminationFee).filter(
            TerminationFee.cancellation_request_id == cancel_id,
        ).first()

        router_return = RouterReturn(
            tenant_id=ctx.tenant_id,
            customer_id=cancel_req.customer_id,
            cancellation_request_id=cancel_id,
            termination_fee_id=tf.id if tf else None,
            product_id=body.product_id,
            serial_number=body.serial_number,
            imei=body.imei,
            status="pending",
            pickup_address=body.pickup_address,
        )
        session.add(router_return)
        session.flush()

        return {
            "router_return_id": str(router_return.id),
            "status": "pending",
            "message": "Router return booked. A courier will contact you within 48 hours.",
        }


# ── POST /cancellations/router-returns/{id}/inspect ──────────────────────

@router.post("/router-returns/{return_id}/inspect", dependencies=[Depends(require_tier("admin"))])
async def inspect_router_return(
    return_id: uuid.UUID,
    body: RouterReturnInspectRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Warehouse inspects returned router and issues refund if applicable."""
    from services.billing.database import get_session

    with get_session() as session:
        rr = session.query(RouterReturn).filter(
            RouterReturn.id == return_id,
            RouterReturn.tenant_id == ctx.tenant_id,
        ).first()
        if not rr:
            raise HTTPException(status_code=404, detail="Router return not found")

        rr.condition = body.condition
        rr.condition_notes = body.condition_notes
        rr.refund_amount_zar = body.refund_amount_zar
        rr.inspected_at = datetime.utcnow()
        rr.inspected_by = ctx.user_id

        if body.refund_amount_zar > 0:
            rr.status = "refund_issued"
            rr.refund_issued_at = datetime.utcnow()
            rr.refund_reference = f"RRF-{str(return_id)[:8]}"
        else:
            rr.status = "written_off"

        # Update the fee: engine recompute / credit when a fee policy produced a calculation, legacy otherwise.
        fee_update = None
        calc = fees.current_cancellation_calc(session, ctx.tenant_id, rr.cancellation_request_id)
        if calc is not None:
            fee_update = _engine_router_update(session, ctx, rr, calc, body.condition)
        elif rr.termination_fee_id:
            tf = session.query(TerminationFee).get(rr.termination_fee_id)
            if tf:
                tf.router_returned = True
                tf.router_returned_at = datetime.utcnow()
                tf.router_charge_zar = Decimal("0.00")  # Waived
                tf.total_etf_zar = tf.contract_etf_zar + tf.outstanding_balance_zar

        return {
            "router_return_id": str(return_id),
            "status": rr.status,
            "refund_amount_zar": rr.refund_amount_zar,
            "refund_reference": rr.refund_reference,
            "fee_update": fee_update,
        }


# ── POST /cancellations/{cancel_id}/fno-cancellation ─────────────────────

@router.post("/{cancel_id}/fno-cancellation", dependencies=[Depends(require_tier("admin"))])
async def submit_fno_cancellation(
    cancel_id: uuid.UUID,
    body: FNOCancelSubmitRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Submit cancellation to the FNO — uses browser automation for FNOs without API."""
    from services.billing.database import get_session

    with get_session() as session:
        cancel_req = session.query(CancellationRequest).filter(
            CancellationRequest.id == cancel_id,
            CancellationRequest.tenant_id == ctx.tenant_id,
        ).first()
        if not cancel_req:
            raise HTTPException(status_code=404, detail="Cancellation request not found")

        fno_cancel = FNOCancellation(
            tenant_id=ctx.tenant_id,
            customer_id=cancel_req.customer_id,
            cancellation_request_id=cancel_id,
            subscription_id=cancel_req.subscription_id,
            fno_name=body.fno_name,
            fno_account_number=body.fno_account_number,
            method="browser_automation",  # Default — most FNOs don't have APIs
            status="pending",
        )
        session.add(fno_cancel)
        session.flush()

        # Trigger browser automation via agent-orchestrator
        try:
            import httpx
            import os
            ORCHESTRATOR_URL = os.getenv("AGENT_ORCHESTRATOR_URL", "http://agent-orchestrator:8021")
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{ORCHESTRATOR_URL}/invoke",
                    json={
                        "task": "fno_cancellation",
                        "fno_name": body.fno_name,
                        "account_number": body.fno_account_number,
                        "cancellation_request_id": str(cancel_id),
                    },
                )
                if resp.status_code == 200:
                    job_data = resp.json()
                    fno_cancel.automation_job_id = job_data.get("job_id")
                    fno_cancel.status = "in_progress"
                    fno_cancel.automation_started_at = datetime.utcnow()
        except Exception as e:
            logger.warning(f"Could not trigger FNO browser automation: {e}")
            fno_cancel.status = "manual"  # Fallback to manual

        cancel_req.status = "fno_submitted"
        cancel_req.fno_name = body.fno_name

        return {
            "fno_cancellation_id": str(fno_cancel.id),
            "fno_name": body.fno_name,
            "method": fno_cancel.method,
            "status": fno_cancel.status,
            "message": "FNO cancellation submitted. You will be notified when confirmed.",
        }


# ── GET /cancellations/{cancel_id}/status ─────────────────────────────────

@router.get("/{cancel_id}/status", dependencies=[Depends(require_tier("reader"))])
async def get_cancellation_status(
    cancel_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get full cancellation status including ETF, router return, FNO status."""
    from services.billing.database import get_session

    with get_session() as session:
        cancel_req = session.query(CancellationRequest).filter(
            CancellationRequest.id == cancel_id,
            CancellationRequest.tenant_id == ctx.tenant_id,
        ).first()
        if not cancel_req:
            raise HTTPException(status_code=404, detail="Cancellation request not found")

        tf = session.query(TerminationFee).filter(
            TerminationFee.cancellation_request_id == cancel_id,
        ).first()

        router_returns = session.query(RouterReturn).filter(
            RouterReturn.cancellation_request_id == cancel_id,
        ).all()

        fno_cancellations = session.query(FNOCancellation).filter(
            FNOCancellation.cancellation_request_id == cancel_id,
        ).all()

        calc = fees.current_cancellation_calc(session, ctx.tenant_id, cancel_id)

        return {
            "cancellation": {
                "id": str(cancel_req.id),
                "status": cancel_req.status,
                "type": cancel_req.cancel_type,
                "reason": cancel_req.cancel_reason,
                "effective_date": cancel_req.effective_date.isoformat() if cancel_req.effective_date else None,
            },
            "termination_fee": {
                "total_etf_zar": float(tf.total_etf_zar) if tf else 0,
                "contract_etf_zar": float(tf.contract_etf_zar) if tf else 0,
                "router_charge_zar": float(tf.router_charge_zar) if tf else 0,
                "router_returned": tf.router_returned if tf else False,
            } if tf else None,
            "fee_calculation": fees.calc_to_dict(calc) if calc else None,
            "fee_engine": "policy" if calc else ("legacy" if tf else None),
            "router_returns": [
                {
                    "id": str(rr.id),
                    "serial_number": rr.serial_number,
                    "status": rr.status,
                    "condition": rr.condition,
                    "refund_amount_zar": float(rr.refund_amount_zar),
                }
                for rr in router_returns
            ],
            "fno_cancellations": [
                {
                    "id": str(fc.id),
                    "fno_name": fc.fno_name,
                    "status": fc.status,
                    "reference": fc.confirmation_reference,
                }
                for fc in fno_cancellations
            ],
        }
