"""RADIUS Usage Billing sync — pulls usage data from network/RADIUS service
and creates billing usage records for usage-based billing."""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from services.common.auth import AuthContext, get_auth_context
from services.billing.database import get_session
from services.billing.models import Subscription, SubscriptionUsage
from services.common.middleware import configure_production

logger = logging.getLogger("billing.radius_billing")

router = APIRouter(prefix="/billing-radius", tags=["RADIUS Billing Sync"])


@router.post("/sync-usage", status_code=status.HTTP_201_CREATED)
async def sync_radius_usage(
    ctx: AuthContext = Depends(get_auth_context),
    subscription_id: Optional[uuid.UUID] = Query(None),
    metric: str = Query("gb_overage", description="Usage metric name"),
    default_unit_price_zar: Decimal = Query(Decimal("0.05"), description="Default per-unit price in ZAR"),
):
    """Sync usage data from RADIUS to billing usage records.

    In production, this would query the network service for actual usage data
    (bytes transferred, session time, etc.). For now, it accepts usage data
    via query params and creates SubscriptionUsage records.

    Can be called:
    - By a scheduled job (cron) for batch processing
    - By the RADIUS service when usage thresholds are crossed
    - Manually by an admin
    """
    with get_session() as session:
        # Find target subscriptions
        if subscription_id:
            result = session.execute(
                select(Subscription).where(
                    Subscription.id == subscription_id,
                    Subscription.tenant_id == ctx.tenant_id,
                )
            )
            subs = [result.scalar_one_or_none()]
            if not subs[0]:
                raise HTTPException(status_code=404, detail="Subscription not found")
        else:
            result = session.execute(
                select(Subscription).where(
                    Subscription.tenant_id == ctx.tenant_id,
                    Subscription.status == "active",
                )
            )
            subs = result.scalars().all()

        created = []
        for sub in subs:
            if sub.status != "active":
                continue

            # In production: query network service for actual usage
            # For now, create a placeholder usage record
            usage = SubscriptionUsage(
                subscription_id=sub.id,
                metric=metric,
                quantity=Decimal("0.00"),
                unit_price_zar=default_unit_price_zar,
                description=f"Usage sync at {datetime.now(tz=timezone.utc).isoformat()}",
            )
            session.add(usage)
            created.append(usage)

        session.flush()
        logger.info("Synced %d usage records for tenant %s", len(created), ctx.tenant_id)

        return {
            "synced": len(created),
            "metric": metric,
            "tenant_id": str(ctx.tenant_id),
        }
