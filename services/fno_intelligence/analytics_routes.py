"""Analytics & AI: combined router mounted at /api/fno/analytics.

    /analytics/research            A. cited online research
    /analytics/competitors         B. competitor tracking, scans, changes
    /analytics/campaign-analyses   C. market reaction to a campaign/brand
    /analytics/usage               D. Firecrawl credit usage and caps
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_current_tenant_id
from services.fno_intelligence import analytics_common as ac
from services.fno_intelligence import campaigns, competitors, database, research
from services.fno_intelligence.analytics_models import AiCreditLedger, AiCreditLimit

logger = logging.getLogger("fno_intelligence.analytics")
router = APIRouter(prefix="/analytics")
router.include_router(research.router)
router.include_router(competitors.router)
router.include_router(campaigns.router)

usage_router = APIRouter(prefix="/usage", tags=["Analytics: usage and credit caps"])


class LimitsIn(BaseModel):
    monthly_cap: Optional[int] = Field(None, ge=0, le=10_000_000, description="null = platform default")
    daily_cap: Optional[int] = Field(None, ge=0, le=10_000_000, description="null = platform default")


@usage_router.get("")
async def usage(tenant_id: uuid.UUID = Depends(get_current_tenant_id), _: AuthContext = Depends(ac.require_viewer),
                db: AsyncSession = Depends(database.get_session)):
    return await ac.get_usage(db, tenant_id)


@usage_router.get("/ledger")
async def ledger(limit: int = Query(50, ge=1, le=200), tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                 _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    rows = (await db.execute(select(AiCreditLedger).where(AiCreditLedger.tenant_id == tenant_id)
                             .order_by(desc(AiCreditLedger.created_at)).limit(limit))).scalars().all()
    return {"items": [{"id": str(r.id), "endpoint": r.endpoint, "credits": r.credits, "feature": r.feature,
                       "ref_id": str(r.ref_id) if r.ref_id else None, "note": r.note,
                       "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]}


@usage_router.put("/limits")
async def set_limits(body: LimitsIn, auth: AuthContext = Depends(ac.require_admin),
                     db: AsyncSession = Depends(database.get_session)):
    """Tenant admins may only LOWER their caps below the platform default; platform admins may set any value."""
    dm, dd = ac.default_caps()
    if not auth.is_platform_admin and ac.roles_enforced():
        if (body.monthly_cap is not None and body.monthly_cap > dm) or (body.daily_cap is not None and body.daily_cap > dd):
            raise HTTPException(403, f"Only a platform admin can raise caps above the platform default "
                                     f"({dm} monthly / {dd} daily credits)")
    row = await db.get(AiCreditLimit, auth.tenant_id)
    if row is None:
        row = AiCreditLimit(tenant_id=auth.tenant_id)
        db.add(row)
    row.monthly_cap, row.daily_cap, row.updated_by, row.updated_at = body.monthly_cap, body.daily_cap, auth.user_id, ac.now()
    await db.flush()
    return await ac.get_usage(db, auth.tenant_id)


router.include_router(usage_router)


async def sweep_stuck_runs() -> int:
    """Startup: mark runs/scans/analyses left queued or running by a restart as failed."""
    async with database.get_session_factory()() as db:
        n = await research.sweep_stuck(db) + await competitors.sweep_stuck(db) + await campaigns.sweep_stuck(db)
        await db.commit()
        return n
