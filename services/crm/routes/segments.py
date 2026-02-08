"""Segmentation routes — dynamic customer segments."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_

from services.common.auth import AuthContext, get_auth_context
from services.crm.database import get_session
from services.crm.models import Customer, Segment
from services.crm.schemas import (
    CustomerRead,
    PaginatedResponse,
    SegmentCreate,
    SegmentRead,
)

router = APIRouter(prefix="/segments", tags=["Segments"])


# ---------------------------------------------------------------------------
# Segment rule → SQLAlchemy filter mapping
# ---------------------------------------------------------------------------

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
    """Convert segment rule dicts into SQLAlchemy filter clauses."""
    filters = [Customer.tenant_id == tenant_id]
    for rule in rules:
        field_name = rule.get("field")
        op = rule.get("operator", "eq")
        value = rule.get("value")
        column = FIELD_MAP.get(field_name)
        if column is None:
            # For tenure / spend / churn_risk — store as JSONB-based rules
            # evaluated later; skip for now (extend as billing data integrates)
            continue
        op_func = OPERATOR_MAP.get(op)
        if op_func:
            filters.append(op_func(column, value))
    return filters


def _count_segment_customers(session, rules: list[dict], tenant_id: uuid.UUID) -> int:
    """Count customers matching segment rules."""
    filters = _build_segment_filters(rules, tenant_id)
    return session.query(func.count(Customer.id)).filter(and_(*filters)).scalar() or 0


# ---------------------------------------------------------------------------
# POST /segments — Create segment
# ---------------------------------------------------------------------------

@router.post("", response_model=SegmentRead, status_code=status.HTTP_201_CREATED)
def create_segment(
    body: SegmentCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        rules_dicts = [r.model_dump() for r in body.rules]
        segment = Segment(
            tenant_id=ctx.tenant_id,
            name=body.name,
            description=body.description,
            rules=rules_dicts,
            auto_refresh=body.auto_refresh,
        )
        session.add(segment)
        session.flush()
        session.refresh(segment)

        count = _count_segment_customers(session, rules_dicts, ctx.tenant_id)
        result = SegmentRead.model_validate(segment)
        result.customer_count = count
        return result


# ---------------------------------------------------------------------------
# GET /segments — List segments with customer counts
# ---------------------------------------------------------------------------

@router.get("", response_model=list[SegmentRead])
def list_segments(
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        segments = (
            session.query(Segment)
            .filter(Segment.tenant_id == ctx.tenant_id)
            .order_by(Segment.created_at.desc())
            .all()
        )
        results = []
        for seg in segments:
            sr = SegmentRead.model_validate(seg)
            rules = seg.rules if isinstance(seg.rules, list) else []
            sr.customer_count = _count_segment_customers(session, rules, ctx.tenant_id)
            results.append(sr)
        return results


# ---------------------------------------------------------------------------
# GET /segments/{id}/customers — Customers matching segment
# ---------------------------------------------------------------------------

@router.get("/{segment_id}/customers", response_model=PaginatedResponse)
def get_segment_customers(
    segment_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    with get_session() as session:
        segment = (
            session.query(Segment)
            .filter(Segment.id == segment_id, Segment.tenant_id == ctx.tenant_id)
            .first()
        )
        if not segment:
            raise HTTPException(status_code=404, detail="Segment not found")

        rules = segment.rules if isinstance(segment.rules, list) else []
        filters = _build_segment_filters(rules, ctx.tenant_id)

        query = session.query(Customer).filter(and_(*filters))
        total = query.count()
        pages = max(1, (total + page_size - 1) // page_size)
        items = (
            query.order_by(Customer.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return PaginatedResponse(
            items=[CustomerRead.model_validate(c) for c in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )
