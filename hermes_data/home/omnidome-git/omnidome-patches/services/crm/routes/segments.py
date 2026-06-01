"""Segmentation routes — dynamic customer segments.

FIX: Converted from sync to async SQLAlchemy. Added pagination.
"""

import uuid
import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select

from services.common.auth import AuthContext, get_auth_context
from services.crm.database import get_session
from services.crm.models import Customer, Segment
from services.crm.schemas import (
    CustomerRead,
    PaginatedResponse,
    SegmentCreate,
    SegmentRead,
    SegmentRule,
)

router = APIRouter(prefix="/segments", tags=["Segments"])

FIELD_MAP = {
    "province": Customer.province,
    "status": Customer.status,
    "email": Customer.email,
}

OPERATOR_MAP = {
    "eq": lambda col, val: col == val,
    "ne": lambda col, val: col != val,
    "gt": lambda col, val: col > val,
    "gte": lambda col, val: col >= val,
    "lt": lambda col, val: col < val,
    "lte": lambda col, val: col <= val,
    "in": lambda col, val: col.in_(val if isinstance(val, list) else [val]),
    "contains": lambda col, val: col.ilike(f"%{val}%"),
}


def _build_segment_filters(rules: list[dict], tenant_id: uuid.UUID):
    filters = [Customer.tenant_id == tenant_id]
    for rule in rules:
        field_name = rule.get("field")
        op = rule.get("operator", "eq")
        value = rule.get("value")
        column = FIELD_MAP.get(field_name)
        if column is None:
            continue
        op_func = OPERATOR_MAP.get(op)
        if op_func:
            filters.append(op_func(column, value))
    return filters


async def _count_segment_customers(session, rules: list[dict], tenant_id: uuid.UUID) -> int:
    filters = _build_segment_filters(rules, tenant_id)
    return (await session.scalar(
        select(func.count(Customer.id)).where(and_(*filters))
    )) or 0


@router.post("", response_model=SegmentRead, status_code=status.HTTP_201_CREATED)
async def create_segment(
    body: SegmentCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        rules_dicts = [r.model_dump() for r in body.rules]
        segment = Segment(
            tenant_id=ctx.tenant_id,
            name=body.name,
            description=body.description,
            rules=rules_dicts,
            auto_refresh=body.auto_refresh,
        )
        session.add(segment)
        await session.flush()
        await session.refresh(segment)

        count = await _count_segment_customers(session, rules_dicts, ctx.tenant_id)
        result = SegmentRead.model_validate(segment)
        result.customer_count = count
        return result


@router.get("", response_model=PaginatedResponse)
async def list_segments(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """FIX: Added pagination to segment list."""
    async with get_session() as session:
        query = select(Segment).where(Segment.tenant_id == ctx.tenant_id)
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        segments = (await session.execute(
            query.order_by(Segment.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()

        results = []
        for seg in segments:
            sr = SegmentRead.model_validate(seg)
            rules = seg.rules if isinstance(seg.rules, list) else []
            sr.customer_count = await _count_segment_customers(session, rules, ctx.tenant_id)
            results.append(sr)

        return PaginatedResponse(
            items=results,
            total=total or 0, page=page, page_size=page_size,
            pages=max(1, math.ceil((total or 0) / page_size)),
        )


@router.get("/{segment_id}/customers", response_model=PaginatedResponse)
async def get_segment_customers(
    segment_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    async with get_session() as session:
        segment = (await session.execute(
            select(Segment).where(Segment.id == segment_id, Segment.tenant_id == ctx.tenant_id)
        )).scalars().first()
        if not segment:
            raise HTTPException(status_code=404, detail="Segment not found")

        rules = segment.rules if isinstance(segment.rules, list) else []
        filters = _build_segment_filters(rules, ctx.tenant_id)

        query = select(Customer).where(and_(*filters))
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        items = (await session.execute(
            query.order_by(Customer.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()

        return PaginatedResponse(
            items=[CustomerRead.model_validate(c) for c in items],
            total=total or 0, page=page, page_size=page_size,
            pages=max(1, math.ceil((total or 0) / page_size)),
        )


@router.delete("/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_segment(
    segment_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        segment = (await session.execute(
            select(Segment).where(Segment.id == segment_id, Segment.tenant_id == ctx.tenant_id)
        )).scalars().first()
        if not segment:
            raise HTTPException(status_code=404, detail="Segment not found")
        await session.delete(segment)
