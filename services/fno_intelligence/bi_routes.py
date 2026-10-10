"""BI Studio router mounted at /api/fno/bi:

    /bi/datasets, /bi/query, /bi/chart-suggestions     semantic layer (governed, no free SQL)
    /bi/brand-kits                                      brand kits
    /bi/decks                                           Deck Studio documents, versions, runs, resolve, export
    /bi/ai                                              outline / slide patch / narrative
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_current_tenant_id
from services.fno_intelligence import analytics_common as ac
from services.fno_intelligence import bi_ai, bi_brand, bi_deck, bi_metrics_routes, database
from services.fno_intelligence import bi_semantic as sem
from services.fno_intelligence.bi_deck_model import CHART_TYPES, LAYOUTS, MAX_BLOCKS, MAX_BLOCKS_PER_SLIDE, MAX_SLIDES

router = APIRouter(prefix="/bi", tags=["BI Studio"])


@router.get("/datasets")
async def datasets(_: AuthContext = Depends(ac.require_viewer)):
    """Catalog of governed datasets with their dimensions, measures, formats and limits."""
    return sem.catalog()


@router.get("/meta")
async def meta(_: AuthContext = Depends(ac.require_viewer)):
    return {"deck_schema_version": 1, "layouts": list(LAYOUTS), "chart_types": list(CHART_TYPES),
            "block_types": ["text", "kpi", "chart", "table", "image", "shape"],
            "token_formats": sorted(__import__("services.fno_intelligence.bi_tokens", fromlist=["FORMATS"]).FORMATS),
            "limits": {"slides": MAX_SLIDES, "blocks_per_slide": MAX_BLOCKS_PER_SLIDE, "blocks": MAX_BLOCKS,
                       "queries": 60, "ai_calls_per_day": bi_ai.daily_call_cap(), **sem.catalog()["limits"]}}


@router.post("/query")
async def query(spec: sem.QuerySpec, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    return await sem.run_query(db, tenant_id, spec)


@router.post("/chart-suggestions")
async def chart_suggestions_post(spec: sem.SuggestSpec, _: AuthContext = Depends(ac.require_viewer)):
    return sem.suggest_charts(spec)


@router.get("/chart-suggestions")
async def chart_suggestions_get(dataset: str = Query(..., max_length=50), measures: str = Query("", max_length=600),
                                dimensions: str = Query("", max_length=300), time_dimension: Optional[str] = Query(None, max_length=50),
                                grain: Optional[str] = Query(None, pattern="^(day|week|month|quarter|year)$"),
                                row_count: Optional[int] = Query(None, ge=0, le=100000),
                                _: AuthContext = Depends(ac.require_viewer)):
    """Same as POST; fields comma separated. Pass grain (and optionally time_dimension) to include a time axis."""
    spec = sem.SuggestSpec(dataset=dataset, measures=[m for m in measures.split(",") if m],
                           dimensions=[d for d in dimensions.split(",") if d],
                           time=sem.TimeSpec(dimension=time_dimension, grain=grain) if grain else None, row_count=row_count)
    return sem.suggest_charts(spec)


router.include_router(bi_brand.router)
router.include_router(bi_deck.router)
router.include_router(bi_ai.router)
router.include_router(bi_metrics_routes.router)  # metric catalog / snapshot / forecast-run queue
