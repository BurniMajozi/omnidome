"""HR Performance Review routes — create, submit, summary."""

import math
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from hr.database import session_scope
from hr.models import Employee, PerformanceReview
from hr.schemas import (
    PaginatedResponse, PerformanceReviewCreate, PerformanceReviewRead,
    PerformanceReviewUpdate, PerformanceSummary,
)
from services.common.auth import AuthContext, get_auth_context
from sqlalchemy import func, select


router = APIRouter(prefix="/api/v1/hr/performance", tags=["HR Performance"])

# Rating ordering for averaging
_RATING_ORDER = ["unsatisfactory", "needs_improvement", "meets", "exceeds"]


def _rating_to_score(rating: str) -> int:
    """Convert rating string to numeric score for averaging."""
    try:
        return _RATING_ORDER.index(rating)
    except ValueError:
        return -1


def _score_to_rating(score: float) -> str:
    """Convert numeric score back to rating string."""
    idx = round(score)
    idx = max(0, min(len(_RATING_ORDER) - 1, idx))
    return _RATING_ORDER[idx]


@router.post("", response_model=PerformanceReviewRead, status_code=status.HTTP_201_CREATED)
async def create_review(
    body: PerformanceReviewCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        review = PerformanceReview(
            tenant_id=ctx.tenant_id,
            employee_id=body.employee_id,
            review_period=body.review_period,
            rating=body.rating,
            goals=body.goals,
            achievements=body.achievements,
            reviewer_id=body.reviewer_id,
            status="draft",
        )
        session.add(review)
        await session.flush()
        await session.refresh(review)
        return PerformanceReviewRead.model_validate(review)


@router.get("", response_model=PaginatedResponse)
async def list_reviews(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    employee_id: Optional[uuid.UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    async with session_scope() as session:
        query = select(PerformanceReview).where(PerformanceReview.tenant_id == ctx.tenant_id)
        if employee_id:
            query = query.where(PerformanceReview.employee_id == employee_id)
        if status_filter:
            query = query.where(PerformanceReview.status == status_filter)

        total = (
            await session.scalar(select(func.count()).select_from(query.subquery()))
        ) or 0

        items = (
            await session.execute(
                query.order_by(PerformanceReview.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

        return PaginatedResponse(
            items=[PerformanceReviewRead.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, math.ceil(total / page_size)),
        )


@router.get("/{review_id}", response_model=PerformanceReviewRead)
async def get_review(
    review_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        review = await session.get(PerformanceReview, review_id)
        if not review or review.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Performance review not found")
        return PerformanceReviewRead.model_validate(review)


@router.put("/{review_id}", response_model=PerformanceReviewRead)
async def update_review(
    review_id: uuid.UUID,
    body: PerformanceReviewUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        review = await session.get(PerformanceReview, review_id)
        if not review or review.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Performance review not found")
        update = body.model_dump(exclude_unset=True)
        for k, v in update.items():
            setattr(review, k, v)
        await session.flush()
        await session.refresh(review)
        return PerformanceReviewRead.model_validate(review)


@router.post("/{review_id}/submit", response_model=PerformanceReviewRead)
async def submit_review(
    review_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Submit a draft review (status -> 'submitted')."""
    async with session_scope() as session:
        review = await session.get(PerformanceReview, review_id)
        if not review or review.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Performance review not found")
        if review.status != "draft":
            raise HTTPException(400, f"Cannot submit review with status '{review.status}'")
        review.status = "submitted"
        await session.flush()
        await session.refresh(review)
        return PerformanceReviewRead.model_validate(review)


@router.get("/summary/{employee_id}", response_model=PerformanceSummary)
async def get_performance_summary(
    employee_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        # Verify employee exists
        employee = await session.get(Employee, employee_id)
        if not employee or employee.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Employee not found")

        reviews = (
            await session.execute(
                select(PerformanceReview).where(
                    PerformanceReview.tenant_id == ctx.tenant_id,
                    PerformanceReview.employee_id == employee_id,
                    PerformanceReview.status.in_(["submitted", "acknowledged"]),
                ).order_by(PerformanceReview.created_at.desc())
            )
        ).scalars().all()

        if not reviews:
            return PerformanceSummary(employee_id=employee_id, review_count=0)

        ratings = [r.rating for r in reviews if r.rating]
        scores = [_rating_to_score(r) for r in ratings if _rating_to_score(r) >= 0]

        avg_rating = None
        if scores:
            avg_rating = _score_to_rating(sum(scores) / len(scores))

        latest = reviews[0]

        return PerformanceSummary(
            employee_id=employee_id,
            review_count=len(reviews),
            average_rating=avg_rating,
            latest_rating=latest.rating,
            latest_review_period=latest.review_period,
        )
