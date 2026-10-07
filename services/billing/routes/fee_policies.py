"""Early-termination / claw-back fee engine API (see services/billing/fee_policies.py and
docs/billing-fee-policies-api.md).

Static paths are declared before /{policy_id} so they are not swallowed by the UUID route.
Money in responses is a decimal string; dates are ISO.
"""
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator

from services.billing import access, fee_policies as fp
from services.billing.access import require_tier
from services.billing.database import get_session
from services.billing.models import CancellationRequest, Subscription
from services.billing.models_fees import (
    ContractFeeSnapshot, FeeAuditEvent, FeeCalculation, FeePolicy,
)
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("billing.fee_policies")

router = APIRouter(prefix="/fee-policies", tags=["Fee Policies"])


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------

def policy_to_dict(r: FeePolicy) -> dict:
    d = {
        "id": str(r.id), "policy_key": str(r.policy_key), "version": r.version, "name": r.name,
        "description": r.description, "is_active": r.is_active, "is_default": r.is_default,
        "effective_from": r.effective_from.isoformat(), "effective_to": r.effective_to.isoformat() if r.effective_to else None,
        "superseded_by": str(r.superseded_by) if r.superseded_by else None,
        "trigger_types": r.trigger_types, "applies_to_plans": r.applies_to_plans, "term_months": r.term_months,
        "created_by": str(r.created_by) if r.created_by else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
    d.update(r.config or {})
    return d


def _new_policy_row(p: fp.PolicyIn, tenant_id: uuid.UUID, actor: uuid.UUID, *, policy_key: Optional[uuid.UUID] = None,
                    version: int = 1) -> FeePolicy:
    return FeePolicy(
        tenant_id=tenant_id, policy_key=policy_key or uuid.uuid4(), version=version, name=p.name,
        description=p.description, is_active=p.is_active, is_default=p.is_default,
        effective_from=p.effective_from or date.today(), effective_to=p.effective_to,
        trigger_types=p.trigger_types, applies_to_plans=p.applies_to_plans, term_months=p.term_months,
        config=fp.policy_config_from_input(p), created_by=actor)


def _get_policy(session, tenant_id: uuid.UUID, policy_id: uuid.UUID) -> FeePolicy:
    r = session.query(FeePolicy).filter(FeePolicy.id == policy_id, FeePolicy.tenant_id == tenant_id).first()
    if r is None:
        raise HTTPException(status_code=404, detail="Fee policy not found")
    return r


def _get_sub(session, tenant_id: uuid.UUID, sub_id: uuid.UUID) -> Subscription:
    s = session.query(Subscription).filter(Subscription.id == sub_id, Subscription.tenant_id == tenant_id).first()
    if s is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return s


def _get_calc(session, tenant_id: uuid.UUID, calc_id: uuid.UUID) -> FeeCalculation:
    c = session.query(FeeCalculation).filter(FeeCalculation.id == calc_id, FeeCalculation.tenant_id == tenant_id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="Fee calculation not found")
    return c


def _close_other_defaults(session, tenant_id: uuid.UUID, keep: FeePolicy) -> None:
    """At most one default per (tenant, trigger set overlap): a new default demotes older default versions of other policies."""
    if not keep.is_default:
        return
    for o in session.query(FeePolicy).filter(
            FeePolicy.tenant_id == tenant_id, FeePolicy.is_default.is_(True), FeePolicy.is_active.is_(True),
            FeePolicy.policy_key != keep.policy_key).all():
        if set(o.trigger_types or []) & set(keep.trigger_types or []) and set(o.applies_to_plans or []) == set(keep.applies_to_plans or []):
            o.is_default = False


# ---------------------------------------------------------------------------------------------
# Policy CRUD
# ---------------------------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_tier("admin"))])
async def create_policy(body: fp.PolicyIn, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        row = _new_policy_row(body, ctx.tenant_id, ctx.user_id)
        session.add(row)
        session.flush()
        _close_other_defaults(session, ctx.tenant_id, row)
        fp.audit(session, ctx.tenant_id, "policy", row.id, "created", ctx.user_id, {"name": row.name, "version": 1})
        return policy_to_dict(row)


@router.post("/templates/default-24m", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_tier("admin"))])
async def create_default_template(ctx: AuthContext = Depends(get_auth_context)):
    """Create (only when an admin calls it) a standard 24-month straight-line claw-back policy: router +
    activation + installation recovered from the contract snapshot, 15% VAT exclusive, router return offsets the
    router component, 7-day cooling-off, provider-fault exits waived automatically, hardship waivers by approvers."""
    with get_session() as session:
        exists = session.query(FeePolicy).filter(
            FeePolicy.tenant_id == ctx.tenant_id, FeePolicy.name == "Standard 24-month claw-back",
            FeePolicy.is_active.is_(True)).first()
        if exists:
            raise HTTPException(status_code=409, detail=f"Default template already exists (policy {exists.id})")
        p = fp.PolicyIn(
            name="Standard 24-month claw-back",
            description="Unamortised router, activation and installation cost over a 24-month term.",
            trigger_types=["cancellation", "downgrade", "plan_change", "relocation"],
            is_default=True, term_months=24,
            components=[fp.ComponentIn(code="router", label="Router"),
                        fp.ComponentIn(code="activation", label="Activation fee"),
                        fp.ComponentIn(code="installation", label="Installation fee")],
            method="straight_line", month_rule=fp.MonthRule(mode="whole_months", remaining_rounding="up"),
            grace_period_days=7,
            waivers=[
                fp.WaiverRule(reason_code="fno_fault", label="Network operator fault", required_tier="none"),
                fp.WaiverRule(reason_code="provider_breach", label="Provider breach of contract", required_tier="none"),
                fp.WaiverRule(reason_code="relocation_in_coverage", label="Relocation within coverage", required_tier="clerk"),
                fp.WaiverRule(reason_code="death", label="Death of account holder", required_tier="admin"),
                fp.WaiverRule(reason_code="retrenchment_with_proof", label="Retrenchment (proof supplied)",
                              required_tier="admin", evidence_required=True),
            ],
            auto_approve_waiver_limit_zar=Decimal("200.00"),
            router_credit=fp.RouterCredit(enabled=True, mode="offset_router_component"),
            vat=fp.VatRule(rate=Decimal("0.15"), treatment="exclusive"),
            outstanding_balance="exclude", auto_invoice=False)
        row = _new_policy_row(p, ctx.tenant_id, ctx.user_id)
        session.add(row)
        session.flush()
        _close_other_defaults(session, ctx.tenant_id, row)
        fp.audit(session, ctx.tenant_id, "policy", row.id, "created", ctx.user_id, {"name": row.name, "template": "default-24m"})
        return policy_to_dict(row)


@router.get("", dependencies=[Depends(require_tier("reader"))])
async def list_policies(active_only: bool = Query(False), trigger: Optional[str] = Query(None),
                        current_only: bool = Query(True, description="hide superseded versions"),
                        ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        q = session.query(FeePolicy).filter(FeePolicy.tenant_id == ctx.tenant_id)
        if active_only:
            q = q.filter(FeePolicy.is_active.is_(True))
        if current_only:
            q = q.filter(FeePolicy.superseded_by.is_(None))
        rows = q.order_by(FeePolicy.created_at.desc()).all()
        if trigger:
            rows = [r for r in rows if trigger in (r.trigger_types or [])]
        return [policy_to_dict(r) for r in rows]


@router.get("/audit", dependencies=[Depends(require_tier("reader"))])
async def list_audit(entity_type: Optional[str] = None, entity_id: Optional[uuid.UUID] = None,
                     limit: int = Query(100, ge=1, le=500), ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        q = session.query(FeeAuditEvent).filter(FeeAuditEvent.tenant_id == ctx.tenant_id)
        if entity_type:
            q = q.filter(FeeAuditEvent.entity_type == entity_type)
        if entity_id:
            q = q.filter(FeeAuditEvent.entity_id == entity_id)
        return [{"id": str(e.id), "entity_type": e.entity_type, "entity_id": str(e.entity_id), "action": e.action,
                 "actor_id": str(e.actor_id) if e.actor_id else None, "details": e.details,
                 "created_at": e.created_at.isoformat() if e.created_at else None}
                for e in q.order_by(FeeAuditEvent.created_at.desc()).limit(limit).all()]


# ---------------------------------------------------------------------------------------------
# Simulate / calculate
# ---------------------------------------------------------------------------------------------

class SnapshotComponentIn(BaseModel):
    code: str
    label: Optional[str] = None
    amount: Decimal = Field(ge=0)
    discount: Decimal = Field(default=Decimal("0"), ge=0)


class SnapshotInputs(BaseModel):
    term_start: date
    term_months: int = Field(ge=1, le=120)
    components: list[SnapshotComponentIn] = Field(default_factory=list)
    monthly_rental_zar: Decimal = Field(default=Decimal("0"), ge=0)
    plan_id: Optional[uuid.UUID] = None
    plan_name: Optional[str] = None


class SimulateRequest(BaseModel):
    subscription_id: Optional[uuid.UUID] = None
    snapshot: Optional[SnapshotInputs] = None
    policy_id: Optional[uuid.UUID] = None
    policy: Optional[fp.PolicyIn] = None  # try an unsaved policy
    trigger: str = "cancellation"
    effective_date: Optional[date] = None
    reason_code: Optional[str] = None
    router_returned: bool = False
    router_condition: Optional[str] = None
    outstanding_balance_zar: Optional[Decimal] = Field(default=None, ge=0)  # snapshot mode only

    @model_validator(mode="after")
    def _one_subject(self):
        if (self.subscription_id is None) == (self.snapshot is None):
            raise ValueError("give exactly one of subscription_id or snapshot")
        return self


class CalculateRequest(BaseModel):
    subscription_id: uuid.UUID
    trigger: str = "cancellation"
    effective_date: Optional[date] = None
    reason_code: Optional[str] = None
    router_returned: bool = False
    router_condition: Optional[str] = None
    cancellation_id: Optional[uuid.UUID] = None
    policy_id: Optional[uuid.UUID] = None


def _norm_trigger(t: str) -> str:
    t = (t or "").strip().lower()
    if not fp._SLUG.match(t):
        raise HTTPException(status_code=422, detail="invalid trigger")
    return t


@router.post("/simulate", dependencies=[Depends(require_tier("reader"))])
async def simulate(body: SimulateRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Full transparent breakdown. Persists nothing."""
    trigger = _norm_trigger(body.trigger)
    effective = body.effective_date or date.today()
    with get_session() as session:
        if body.subscription_id:
            sub = _get_sub(session, ctx.tenant_id, body.subscription_id)
            try:
                prow, pol, bd, digest, snap, inputs = fp.run_calculation(
                    session, tenant_id=ctx.tenant_id, sub=sub, trigger=trigger, effective_date=effective,
                    reason_code=body.reason_code, router_returned=body.router_returned,
                    router_condition=body.router_condition, policy_id=body.policy_id) if body.policy is None else \
                    _run_inline(session, ctx, sub, body, trigger, effective)
            except LookupError:
                raise HTTPException(status_code=404, detail="No active fee policy applies to this subscription and trigger")
            return {"persisted": False, "policy": bd["policy"], "snapshot_id": str(snap.id) if snap else None,
                    "snapshot_missing": snap is None, "inputs_hash": digest, "inputs": fp.jsonable(inputs),
                    "flags": bd["flags"], "breakdown": fp.jsonable(bd)}
        s = body.snapshot
        plan_keys = [str(s.plan_id) if s.plan_id else "", s.plan_name or ""]
        if body.policy is not None:
            pol = _inline_policy(body.policy)
        else:
            prow = fp.select_policy(session, ctx.tenant_id, trigger, effective, plan_keys, body.policy_id)
            if prow is None:
                raise HTTPException(status_code=404, detail="No active fee policy applies to these inputs")
            pol = fp.policy_to_engine(prow)
        inputs = {
            "trigger": trigger, "term_start": s.term_start, "term_months": s.term_months,
            "components": {c.code.strip().lower(): c.amount for c in s.components},
            "monthly_rental_zar": s.monthly_rental_zar, "plan_keys": plan_keys, "effective_date": effective,
            "reason_code": body.reason_code, "router_returned": body.router_returned,
            "router_condition": body.router_condition,
            "outstanding_balance_zar": body.outstanding_balance_zar or Decimal("0"), "snapshot_present": True}
        bd = fp.calculate_fee(pol, inputs)
        bd["policy"] = {"id": pol.get("id"), "policy_key": pol.get("policy_key"), "version": pol.get("version"), "name": pol["name"]}
        digest = fp.inputs_hash(pol, inputs)
        return {"persisted": False, "policy": bd["policy"], "snapshot_id": None, "snapshot_missing": False,
                "inputs_hash": digest, "inputs": fp.jsonable(inputs), "flags": bd["flags"], "breakdown": fp.jsonable(bd)}


def _inline_policy(p: fp.PolicyIn) -> dict:
    d = fp.policy_config_from_input(p)
    d.update(id=None, policy_key=None, version=0, name=p.name, term_months=p.term_months,
             trigger_types=p.trigger_types, applies_to_plans=p.applies_to_plans)
    return d


def _run_inline(session, ctx, sub, body: SimulateRequest, trigger: str, effective: date):
    pol = _inline_policy(body.policy)
    snap = fp.current_snapshot(session, ctx.tenant_id, sub.id)
    inputs = fp.build_inputs(session, ctx.tenant_id, sub, snap, pol, trigger=trigger, effective_date=effective,
                             reason_code=body.reason_code, router_returned=body.router_returned,
                             router_condition=body.router_condition)
    bd = fp.calculate_fee(pol, inputs)
    bd["policy"] = {"id": None, "policy_key": None, "version": 0, "name": pol["name"]}
    return None, pol, bd, fp.inputs_hash(pol, inputs), snap, inputs


@router.post("/calculate", dependencies=[Depends(require_tier("clerk"))])
async def calculate(body: CalculateRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Persist an immutable calculation. Idempotent on (tenant, trigger, subject, effective_date, inputs_hash):
    repeat calls return the same row with created=false."""
    trigger = _norm_trigger(body.trigger)
    effective = body.effective_date or date.today()
    with get_session() as session:
        sub = _get_sub(session, ctx.tenant_id, body.subscription_id)
        subject_type, subject_id, cancel_id = "subscription", sub.id, None
        if body.cancellation_id:
            cr = session.query(CancellationRequest).filter(
                CancellationRequest.id == body.cancellation_id, CancellationRequest.tenant_id == ctx.tenant_id,
                CancellationRequest.subscription_id == sub.id).first()
            if cr is None:
                raise HTTPException(status_code=404, detail="Cancellation request not found for this subscription")
            subject_type, subject_id, cancel_id = "cancellation", cr.id, cr.id
        try:
            prow, pol, bd, digest, snap, inputs = fp.run_calculation(
                session, tenant_id=ctx.tenant_id, sub=sub, trigger=trigger, effective_date=effective,
                reason_code=body.reason_code, router_returned=body.router_returned,
                router_condition=body.router_condition, policy_id=body.policy_id)
        except LookupError:
            raise HTTPException(status_code=404, detail="No active fee policy applies to this subscription and trigger")
        row, created = fp.persist_calculation(
            session, tenant_id=ctx.tenant_id, sub=sub, snap=snap, policy_row=prow, trigger=trigger,
            subject_type=subject_type, subject_id=subject_id, cancellation_request_id=cancel_id,
            effective_date=effective, reason_code=body.reason_code, inputs=inputs, bd=bd, digest=digest,
            actor_id=ctx.user_id)
        if cancel_id:
            cr = session.get(CancellationRequest, cancel_id)
            fp.sync_termination_fee_row(session, cr, sub, row)
        return {**fp.calc_to_dict(row), "created": created}


# ---------------------------------------------------------------------------------------------
# Calculations: list / get / waive / invoice
# ---------------------------------------------------------------------------------------------

@router.get("/calculations", dependencies=[Depends(require_tier("reader"))])
async def list_calculations(subscription_id: Optional[uuid.UUID] = None, customer_id: Optional[uuid.UUID] = None,
                            cancellation_id: Optional[uuid.UUID] = None, include_superseded: bool = False,
                            limit: int = Query(100, ge=1, le=500), ctx: AuthContext = Depends(get_auth_context)):
    if not (subscription_id or customer_id or cancellation_id):
        raise HTTPException(status_code=422, detail="filter by subscription_id, customer_id or cancellation_id")
    with get_session() as session:
        q = session.query(FeeCalculation).filter(FeeCalculation.tenant_id == ctx.tenant_id)
        if subscription_id:
            q = q.filter(FeeCalculation.subscription_id == subscription_id)
        if customer_id:
            q = q.filter(FeeCalculation.customer_id == customer_id)
        if cancellation_id:
            q = q.filter(FeeCalculation.cancellation_request_id == cancellation_id)
        if not include_superseded:
            q = q.filter(FeeCalculation.status != "superseded")
        return [fp.calc_to_dict(c) for c in q.order_by(FeeCalculation.created_at.desc()).limit(limit).all()]


@router.get("/calculations/{calc_id}", dependencies=[Depends(require_tier("reader"))])
async def get_calculation(calc_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        return fp.calc_to_dict(_get_calc(session, ctx.tenant_id, calc_id))


class WaiveRequest(BaseModel):
    reason_code: str = Field(min_length=2, max_length=100)
    reason: str = Field(min_length=3, max_length=1000)
    percent: Optional[Decimal] = Field(default=None, gt=0, le=100)
    amount_zar: Optional[Decimal] = Field(default=None, gt=0, description="gross (VAT-inclusive) amount to waive")

    @model_validator(mode="after")
    def _one(self):
        if (self.percent is None) == (self.amount_zar is None):
            raise ValueError("give exactly one of percent or amount_zar")
        self.reason_code = self.reason_code.strip().lower()
        return self


@router.post("/calculations/{calc_id}/waive", dependencies=[Depends(require_tier("clerk"))])
async def waive(calc_id: uuid.UUID, body: WaiveRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Partial or full waiver. Clerks may approve up to the policy's auto-approve limit; above it, or for
    reason codes whose rule says so, an admin must approve. You cannot approve a waiver above the auto-approve
    limit on a fee you calculated yourself (policy.allow_self_approval=true lifts this)."""
    actor_tier = "admin" if await access.has_tier(ctx, "admin") else "clerk"
    with get_session() as session:
        calc = _get_calc(session, ctx.tenant_id, calc_id)
        prow = session.get(FeePolicy, calc.policy_id)
        pol = fp.policy_to_engine(prow)
        try:
            entry = fp.waive_calculation(session, calc, pol, reason_code=body.reason_code, reason=body.reason,
                                         percent=body.percent, amount=body.amount_zar, actor_id=ctx.user_id,
                                         actor_tier=actor_tier)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=409 if "invoiced" in str(exc) or "superseded" in str(exc) else 400, detail=str(exc))
        if calc.cancellation_request_id and calc.subscription_id:
            cr = session.get(CancellationRequest, calc.cancellation_request_id)
            sub = session.get(Subscription, calc.subscription_id)
            if cr and sub:
                fp.sync_termination_fee_row(session, cr, sub, calc)
        return {"waiver": entry, "calculation": fp.calc_to_dict(calc)}


class InvoiceRequest(BaseModel):
    issue: Optional[bool] = None  # default: the policy's auto_invoice (true = issued, false = draft)


@router.post("/calculations/{calc_id}/invoice", dependencies=[Depends(require_tier("clerk"))])
async def invoice(calc_id: uuid.UUID, body: Optional[InvoiceRequest] = None, ctx: AuthContext = Depends(get_auth_context)):
    """Create the termination_fee invoice (one line per component/adjustment/waiver). Idempotent."""
    with get_session() as session:
        calc = _get_calc(session, ctx.tenant_id, calc_id)
        prow = session.get(FeePolicy, calc.policy_id)
        pol = fp.policy_to_engine(prow)
        issue = body.issue if body is not None and body.issue is not None else bool(pol.get("auto_invoice"))
        try:
            inv, created = fp.invoice_calculation(session, calc, pol, issue=issue, actor_id=ctx.user_id)
        except LookupError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return {"created": created, "invoice_id": str(inv.id), "invoice_number": inv.number, "status": inv.status,
                "subtotal_zar": format(inv.subtotal_zar, "f"), "vat_zar": format(inv.vat_zar, "f"),
                "total_zar": format(inv.total_zar, "f"), "invoice_type": "termination_fee",
                "calculation_id": str(calc.id), "cancellation_request_id": str(calc.cancellation_request_id) if calc.cancellation_request_id else None}


# ---------------------------------------------------------------------------------------------
# Contract snapshots
# ---------------------------------------------------------------------------------------------

class SnapshotCreate(BaseModel):
    subscription_id: uuid.UUID
    term_start: Optional[date] = None            # default: subscription billing_anchor
    term_months: Optional[int] = Field(default=None, ge=1, le=120)  # default: the policy's term
    components: list[SnapshotComponentIn] = Field(min_length=1)
    monthly_rental_zar: Optional[Decimal] = Field(default=None, ge=0)  # default: subscription base price
    policy_id: Optional[uuid.UUID] = None
    backfill: bool = False
    supersede: bool = False                       # add a new version over an existing snapshot
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _dupes(self):
        codes = [c.code.strip().lower() for c in self.components]
        if len(codes) != len(set(codes)):
            raise ValueError("duplicate component codes")
        return self


@router.post("/snapshots", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_tier("clerk"))])
async def create_snapshot(body: SnapshotCreate, ctx: AuthContext = Depends(get_auth_context)):
    """Record (or backfill) the immutable contract_fee_snapshot for a subscription (manager role)."""
    with get_session() as session:
        sub = _get_sub(session, ctx.tenant_id, body.subscription_id)
        start = body.term_start or sub.billing_anchor or date.today()
        prow = None
        if body.policy_id:
            prow = _get_policy(session, ctx.tenant_id, body.policy_id)
        else:
            prow = fp.select_policy(session, ctx.tenant_id, "cancellation", start, fp.plan_keys_for(sub))
        term = body.term_months or (prow.term_months if prow else None)
        if term is None:
            raise HTTPException(status_code=422, detail="term_months is required when no fee policy applies")
        try:
            snap = fp.create_snapshot(
                session, tenant_id=ctx.tenant_id, sub=sub, term_start=start, term_months=term,
                components=[{"code": c.code.strip().lower(), "label": c.label, "amount": c.amount, "discount": c.discount}
                            for c in body.components],
                monthly_rental=body.monthly_rental_zar if body.monthly_rental_zar is not None else sub.base_price_zar,
                policy_row=prow, source="backfill" if body.backfill else "manual", actor_id=ctx.user_id,
                notes=body.notes, supersede=body.supersede)
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=f"A contract snapshot already exists ({exc}); pass supersede=true to add a new version")
        return fp.snapshot_to_dict(snap)


@router.get("/snapshots", dependencies=[Depends(require_tier("reader"))])
async def list_snapshots(subscription_id: uuid.UUID, all_versions: bool = False, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        q = session.query(ContractFeeSnapshot).filter(
            ContractFeeSnapshot.tenant_id == ctx.tenant_id, ContractFeeSnapshot.subscription_id == subscription_id)
        if not all_versions:
            q = q.filter(ContractFeeSnapshot.is_current.is_(True))
        return [fp.snapshot_to_dict(s) for s in q.order_by(ContractFeeSnapshot.version.desc()).all()]


# ---------------------------------------------------------------------------------------------
# Policy by id (declared last)
# ---------------------------------------------------------------------------------------------

@router.get("/{policy_id}", dependencies=[Depends(require_tier("reader"))])
async def get_policy(policy_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        return policy_to_dict(_get_policy(session, ctx.tenant_id, policy_id))


@router.get("/{policy_id}/versions", dependencies=[Depends(require_tier("reader"))])
async def policy_versions(policy_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        r = _get_policy(session, ctx.tenant_id, policy_id)
        rows = session.query(FeePolicy).filter(FeePolicy.tenant_id == ctx.tenant_id, FeePolicy.policy_key == r.policy_key) \
            .order_by(FeePolicy.version.desc()).all()
        return [policy_to_dict(x) for x in rows]


@router.put("/{policy_id}", dependencies=[Depends(require_tier("admin"))])
async def update_policy(policy_id: uuid.UUID, body: fp.PolicyIn, ctx: AuthContext = Depends(get_auth_context)):
    """Policies are versioned: this inserts version N+1 effective from `effective_from` (default today) and
    closes the previous version the day before. Past calculations keep pointing at the version they used."""
    with get_session() as session:
        old = _get_policy(session, ctx.tenant_id, policy_id)
        if old.superseded_by is not None:
            raise HTTPException(status_code=409, detail="This version was already superseded; edit the latest version")
        latest = session.query(FeePolicy).filter(FeePolicy.tenant_id == ctx.tenant_id, FeePolicy.policy_key == old.policy_key) \
            .order_by(FeePolicy.version.desc()).first()
        new = _new_policy_row(body, ctx.tenant_id, ctx.user_id, policy_key=old.policy_key, version=latest.version + 1)
        session.add(new)
        session.flush()
        from datetime import timedelta
        old.superseded_by = new.id
        if old.effective_to is None or old.effective_to >= new.effective_from:
            old.effective_to = max(new.effective_from - timedelta(days=1), old.effective_from)
        _close_other_defaults(session, ctx.tenant_id, new)
        fp.audit(session, ctx.tenant_id, "policy", new.id, "versioned", ctx.user_id,
                 {"from_version": old.version, "to_version": new.version, "previous_id": old.id})
        return policy_to_dict(new)


@router.delete("/{policy_id}", dependencies=[Depends(require_tier("admin"))])
async def deactivate_policy(policy_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    """Soft delete: deactivates every version of the policy. Calculations that used it are untouched."""
    with get_session() as session:
        r = _get_policy(session, ctx.tenant_id, policy_id)
        for x in session.query(FeePolicy).filter(FeePolicy.tenant_id == ctx.tenant_id, FeePolicy.policy_key == r.policy_key).all():
            x.is_active = False
            x.is_default = False
        fp.audit(session, ctx.tenant_id, "policy", r.id, "deactivated", ctx.user_id, {"policy_key": r.policy_key})
        return {"deactivated": True, "policy_key": str(r.policy_key)}
