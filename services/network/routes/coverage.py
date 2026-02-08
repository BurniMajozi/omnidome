"""Coverage check and coverage area management routes.

Provides multi-FNO coverage lookups — first checking the local cache,
then falling back to live FNO adapter calls for each provider.
"""

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func

from services.common.auth import AuthContext, get_auth_context
from services.network.adapters.factory import FNOFactory
from services.network.database import get_session
from services.network.models import CoverageArea
from services.network.schemas import (
    CoverageAreaCreate,
    CoverageAreaRead,
    CoverageCheckRequest,
    CoverageResult,
    PaginatedResponse,
)
from services.network.routes.fno import _get_adapter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/coverage", tags=["Coverage"])


# ---------------------------------------------------------------------------
# MULTI-FNO COVERAGE CHECK
# ---------------------------------------------------------------------------

@router.post("/check", response_model=list[CoverageResult])
async def check_coverage(
    payload: CoverageCheckRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Check fibre coverage across all (or selected) SA FNOs.

    1. First checks local coverage_areas cache.
    2. Falls back to live FNO adapter calls for providers not in cache.
    """
    target_providers = payload.fno_providers or FNOFactory.list_providers()
    results: list[CoverageResult] = []

    # Step 1: Check local cache
    cached_providers: set[str] = set()
    with get_session() as session:
        q = select(CoverageArea).where(
            CoverageArea.tenant_id == auth.tenant_id,
            CoverageArea.is_active.is_(True),
        )
        if payload.province:
            q = q.where(CoverageArea.province == payload.province.lower())
        if payload.city:
            q = q.where(CoverageArea.city.ilike(f"%{payload.city}%"))
        if payload.postal_code:
            q = q.where(CoverageArea.postal_codes.contains([payload.postal_code]))

        areas = session.execute(q).scalars().all()
        for area in areas:
            if area.fno_provider in target_providers:
                cached_providers.add(area.fno_provider)
                results.append(CoverageResult(
                    fno_provider=area.fno_provider,
                    available=True,
                    technology=area.technology,
                    max_download_mbps=area.max_download_mbps,
                    area_name=area.area_name,
                    adapter_type="cache",
                ))

    # Step 2: Live checks for providers not found in cache
    uncached = [p for p in target_providers if p not in cached_providers]
    if uncached:
        async def _live_check(provider: str) -> CoverageResult:
            try:
                adapter = _get_adapter(provider)
                data = await adapter.check_availability(payload.address)
                adapter_type = data.get("adapter_type", "api")
                return CoverageResult(
                    fno_provider=provider,
                    available=data.get("available", False),
                    technology=(data.get("technologies") or [None])[0] if data.get("technologies") else None,
                    max_download_mbps=data.get("max_speed_mbps"),
                    area_name=data.get("area_name"),
                    adapter_type=adapter_type,
                    message=data.get("message"),
                )
            except Exception as exc:
                logger.warning("Live coverage check failed for %s: %s", provider, exc)
                return CoverageResult(
                    fno_provider=provider,
                    available=False,
                    adapter_type="error",
                    message=str(exc),
                )

        live_results = await asyncio.gather(*[_live_check(p) for p in uncached])
        results.extend(live_results)

    # Sort: available first, then by FNO name
    results.sort(key=lambda r: (not r.available, r.fno_provider))
    return results


# ---------------------------------------------------------------------------
# COVERAGE AREAS — CRUD (admin-managed cache)
# ---------------------------------------------------------------------------

@router.post("/areas", response_model=CoverageAreaRead, status_code=status.HTTP_201_CREATED)
async def create_coverage_area(
    payload: CoverageAreaCreate,
    auth: AuthContext = Depends(get_auth_context),
):
    """Add a pre-cached coverage area entry."""
    with get_session() as session:
        area = CoverageArea(
            tenant_id=auth.tenant_id,
            fno_provider=payload.fno_provider,
            area_name=payload.area_name,
            city=payload.city,
            province=payload.province,
            postal_codes=payload.postal_codes,
            technology=payload.technology,
            max_download_mbps=payload.max_download_mbps,
            is_active=payload.is_active,
        )
        session.add(area)
        session.flush()
        session.refresh(area)
        logger.info("Created coverage area %s [%s/%s]", area.area_name, area.fno_provider, area.province)
        return CoverageAreaRead.model_validate(area)


@router.get("/areas", response_model=PaginatedResponse)
async def list_coverage_areas(
    auth: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    fno_provider: Optional[str] = None,
    province: Optional[str] = None,
    city: Optional[str] = None,
    active_only: bool = True,
):
    """List coverage areas for the current tenant."""
    with get_session() as session:
        q = select(CoverageArea).where(CoverageArea.tenant_id == auth.tenant_id)
        count_q = select(func.count(CoverageArea.id)).where(CoverageArea.tenant_id == auth.tenant_id)

        if active_only:
            q = q.where(CoverageArea.is_active.is_(True))
            count_q = count_q.where(CoverageArea.is_active.is_(True))
        if fno_provider:
            q = q.where(CoverageArea.fno_provider == fno_provider.lower())
            count_q = count_q.where(CoverageArea.fno_provider == fno_provider.lower())
        if province:
            q = q.where(CoverageArea.province == province.lower())
            count_q = count_q.where(CoverageArea.province == province.lower())
        if city:
            q = q.where(CoverageArea.city.ilike(f"%{city}%"))
            count_q = count_q.where(CoverageArea.city.ilike(f"%{city}%"))

        total = session.execute(count_q).scalar() or 0
        rows = session.execute(
            q.order_by(CoverageArea.fno_provider, CoverageArea.province, CoverageArea.city)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()

        return PaginatedResponse(
            items=[CoverageAreaRead.model_validate(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get("/areas/{area_id}", response_model=CoverageAreaRead)
async def get_coverage_area(
    area_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        area = session.execute(
            select(CoverageArea).where(
                CoverageArea.id == area_id,
                CoverageArea.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not area:
            raise HTTPException(status_code=404, detail="Coverage area not found")
        return CoverageAreaRead.model_validate(area)


@router.delete("/areas/{area_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_coverage_area(
    area_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
):
    """Soft-delete: deactivate a coverage area."""
    with get_session() as session:
        area = session.execute(
            select(CoverageArea).where(
                CoverageArea.id == area_id,
                CoverageArea.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not area:
            raise HTTPException(status_code=404, detail="Coverage area not found")
        area.is_active = False
        logger.info("Deactivated coverage area %s", area_id)
