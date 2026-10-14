"""Home Assistant reference library: refresh from official docs and the community, and look answers up."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services.common.auth import AuthContext
from services.iot import ha_reference
from services.iot.access import require_tier
from services.iot.database import get_session
from services.iot.integration_catalog import INTEGRATIONS

router = APIRouter()
CATALOGUE_IDS = [item[0] for item in INTEGRATIONS]


class RefreshRequest(BaseModel):
    integrations: Optional[List[str]] = Field(None, max_length=60, description="Integration ids; default is every catalogue integration")
    queries: List[str] = Field(default_factory=list, max_length=6)
    categories: List[str] = Field(default_factory=list, max_length=3)
    category_pages: int = Field(1, ge=1, le=3)


@router.post("/refresh")
async def refresh_reference(body: RefreshRequest, ctx: AuthContext = Depends(require_tier("admin"))):
    """Fetch official docs for the catalogue integrations and any community searches or categories."""
    integrations = CATALOGUE_IDS if body.integrations is None else body.integrations
    try:
        async with get_session() as session:
            stats = await ha_reference.refresh(session, integrations, body.queries, body.categories, category_pages=body.category_pages)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return stats


@router.get("/lookup")
async def lookup_reference(q: str = Query(..., min_length=3, max_length=200), live: bool = True, limit: int = Query(5, ge=1, le=10),
                           ctx: AuthContext = Depends(require_tier("viewer"))):
    """Search the stored library; fetch from the community now when it knows little about the question."""
    async with get_session() as session:
        return await ha_reference.lookup(session, q, limit, live)


@router.get("/docs")
async def list_reference(ctx: AuthContext = Depends(require_tier("viewer"))):
    from sqlalchemy import text
    async with get_session() as session:
        await ha_reference.ensure_table(session)
        rows = (await session.execute(text(
            "SELECT doc_key, kind, title, url, integration_id, license, fetched_at, length(body) AS chars "
            "FROM ha_reference_docs ORDER BY kind, title LIMIT 500"))).mappings().all()
    return {"count": len(rows), "docs": [dict(r) for r in rows]}
