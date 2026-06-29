"""Billing Plan & Bundle routes — service catalog (Fibre/LTE/VoIP/TV plans)
and multi-plan bundles, with subscriber counts and MRR aggregated from
live subscriptions.
"""

import logging
import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.billing.database import get_session
from services.billing.models import BillingPlan, Bundle, BundleItem, Subscription

logger = logging.getLogger("billing.plans")

router = APIRouter(tags=["Plans & Bundles"])


class PlanCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    price: Decimal = Decimal("0")
    currency: str = "ZAR"
    billing_cycle: str = "MONTHLY"
    fno_provider: Optional[str] = None
    is_active: bool = True


class BundleCreate(BaseModel):
    name: str
    discount_pct: Decimal = Decimal("0")
    plan_ids: list[uuid.UUID]


def _plan_stats(session, tenant_id: uuid.UUID) -> dict:
    """subscriber count + MRR per plan_id, from active subscriptions."""
    rows = session.execute(
        select(
            Subscription.plan_id,
            func.count(Subscription.id),
            func.sum(Subscription.base_price_zar),
        )
        .where(Subscription.tenant_id == tenant_id, Subscription.status == "active")
        .group_by(Subscription.plan_id)
    ).all()
    return {row[0]: {"subscribers": row[1], "mrr": float(row[2] or 0)} for row in rows}


@router.get("/plans")
async def list_plans(ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        plans = session.execute(
            select(BillingPlan).where(BillingPlan.tenant_id == ctx.tenant_id).order_by(BillingPlan.created_at.desc())
        ).scalars().all()
        stats = _plan_stats(session, ctx.tenant_id)
        return [
            {
                "id": str(p.id), "name": p.name, "category": p.category,
                "price": float(p.price), "currency": p.currency, "billing_cycle": p.billing_cycle,
                "fno_provider": p.fno_provider, "is_active": p.is_active,
                "subscribers": stats.get(p.id, {}).get("subscribers", 0),
                "mrr": stats.get(p.id, {}).get("mrr", 0.0),
            }
            for p in plans
        ]


@router.post("/plans", status_code=status.HTTP_201_CREATED)
async def create_plan(body: PlanCreate, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        plan = BillingPlan(tenant_id=ctx.tenant_id, **body.model_dump())
        session.add(plan)
        session.flush()
        session.refresh(plan)
        return {
            "id": str(plan.id), "name": plan.name, "category": plan.category,
            "price": float(plan.price), "currency": plan.currency, "billing_cycle": plan.billing_cycle,
            "fno_provider": plan.fno_provider, "is_active": plan.is_active,
            "subscribers": 0, "mrr": 0.0,
        }


@router.get("/bundles")
async def list_bundles(ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        bundles = session.execute(
            select(Bundle).where(Bundle.tenant_id == ctx.tenant_id).order_by(Bundle.created_at.desc())
        ).scalars().all()
        result = []
        for b in bundles:
            plan_ids = [item.plan_id for item in b.items]
            plans = session.execute(select(BillingPlan).where(BillingPlan.id.in_(plan_ids))).scalars().all() if plan_ids else []
            base_price = sum(float(p.price) for p in plans)
            discounted_price = base_price * (1 - float(b.discount_pct) / 100)
            result.append({
                "id": str(b.id), "name": b.name, "discount_pct": float(b.discount_pct),
                "products": [p.name for p in plans],
                "price": round(discounted_price, 2),
                "subscribers": 0,
            })
        return result


@router.post("/bundles", status_code=status.HTTP_201_CREATED)
async def create_bundle(body: BundleCreate, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        bundle = Bundle(tenant_id=ctx.tenant_id, name=body.name, discount_pct=body.discount_pct)
        session.add(bundle)
        session.flush()
        for plan_id in body.plan_ids:
            plan = session.execute(select(BillingPlan).where(BillingPlan.id == plan_id, BillingPlan.tenant_id == ctx.tenant_id)).scalar_one_or_none()
            if not plan:
                raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
            session.add(BundleItem(bundle_id=bundle.id, plan_id=plan_id))
        session.flush()
        session.refresh(bundle)
        plans = session.execute(select(BillingPlan).where(BillingPlan.id.in_(body.plan_ids))).scalars().all()
        base_price = sum(float(p.price) for p in plans)
        discounted_price = base_price * (1 - float(bundle.discount_pct) / 100)
        return {
            "id": str(bundle.id), "name": bundle.name, "discount_pct": float(bundle.discount_pct),
            "products": [p.name for p in plans], "price": round(discounted_price, 2), "subscribers": 0,
        }
