"""A/B Testing routes — create, manage, and assign customers to A/B tests.

Endpoints:
  POST   /ab-tests              — create a new A/B test
  GET    /ab-tests              — list A/B tests for tenant
  GET    /ab-tests/{id}         — get A/B test details with results summary
  POST   /ab-tests/{id}/start   — start an A/B test
  POST   /ab-tests/{id}/stop    — stop an A/B test (computes winner)
  POST   /ab-tests/{id}/assign  — assign a customer to a variant
  DELETE /ab-tests/{id}         — delete an A/B test
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from services.journey_engine.database import get_db
from services.journey_engine.models import (
    ABTest,
    ABTestAssignment,
    JourneyOutcome,
    RetentionJourney,
)
from services.common.auth import AuthContext, get_auth_context
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("journey_engine.ab_testing")

router = APIRouter(prefix="/ab-testing", tags=["A/B Testing"])


# ── Request / Response Schemas ─────────────────────────────────────────────

class ABTestCreateRequest(BaseModel):
    name: str
    journey_a_id: uuid.UUID
    journey_b_id: uuid.UUID
    traffic_split: Decimal = Decimal("50.00")  # % to journey_b


class ABTestCreateResponse(BaseModel):
    ab_test: dict
    status: str = "created"


class ABTestAssignRequest(BaseModel):
    customer_id: uuid.UUID


class ABTestAssignResponse(BaseModel):
    ab_test_id: uuid.UUID
    customer_id: uuid.UUID
    variant: str  # "a" or "b"
    journey_id: uuid.UUID


class ABTestStartResponse(BaseModel):
    ab_test_id: uuid.UUID
    status: str
    started_at: str


class ABTestStopResponse(BaseModel):
    ab_test_id: uuid.UUID
    status: str
    ended_at: str
    winner: Optional[str] = None
    results: dict


# ── POST /ab-tests ────────────────────────────────────────────────────────

@router.post("/ab-tests", response_model=ABTestCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_ab_test(
    data: ABTestCreateRequest,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
):
    """Create a new A/B test between two retention journeys."""
    # Validate both journeys exist and belong to tenant
    for jid, label in [(data.journey_a_id, "journey_a_id"), (data.journey_b_id, "journey_b_id")]:
        query = select(RetentionJourney).where(
            RetentionJourney.id == jid,
            RetentionJourney.tenant_id == ctx.tenant_id,
        )
        result = await session.execute(query)
        journey = result.scalar_one_or_none()
        if not journey:
            raise HTTPException(404, f"Journey {jid} ({label}) not found")

    if data.journey_a_id == data.journey_b_id:
        raise HTTPException(400, "journey_a_id and journey_b_id must be different")

    if not (Decimal("0") <= data.traffic_split <= Decimal("100")):
        raise HTTPException(400, "traffic_split must be between 0 and 100")

    ab_test = ABTest(
        tenant_id=ctx.tenant_id,
        name=data.name,
        journey_a_id=data.journey_a_id,
        journey_b_id=data.journey_b_id,
        traffic_split=data.traffic_split,
        status="draft",
    )
    session.add(ab_test)
    await session.flush()

    return {"ab_test": _ab_test_to_dict(ab_test), "status": "created"}


# ── GET /ab-tests ─────────────────────────────────────────────────────────

@router.get("/ab-tests")
async def list_ab_tests(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
    status_filter: Optional[str] = None,
):
    """List A/B tests for the current tenant."""
    query = select(ABTest).where(ABTest.tenant_id == ctx.tenant_id)
    if status_filter:
        query = query.where(ABTest.status == status_filter)
    query = query.order_by(ABTest.created_at.desc())

    result = await session.execute(query)
    tests = result.scalars().all()
    return {"ab_tests": [_ab_test_to_dict(t) for t in tests]}


# ── GET /ab-tests/{id} ────────────────────────────────────────────────────

@router.get("/ab-tests/{test_id}")
async def get_ab_test(
    test_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
):
    """Get A/B test details with results summary."""
    query = select(ABTest).where(
        ABTest.id == test_id,
        ABTest.tenant_id == ctx.tenant_id,
    )
    result = await session.execute(query)
    ab_test = result.scalar_one_or_none()
    if not ab_test:
        raise HTTPException(404, "A/B test not found")

    test_dict = _ab_test_to_dict(ab_test)

    # Compute results summary from journey outcomes
    results = await _compute_results_summary(ab_test, session)
    test_dict["results"] = results

    return {"ab_test": test_dict}


# ── POST /ab-tests/{id}/start ─────────────────────────────────────────────

@router.post("/ab-tests/{test_id}/start", response_model=ABTestStartResponse)
async def start_ab_test(
    test_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
):
    """Start an A/B test (sets status=running, started_at=now)."""
    query = select(ABTest).where(
        ABTest.id == test_id,
        ABTest.tenant_id == ctx.tenant_id,
    )
    result = await session.execute(query)
    ab_test = result.scalar_one_or_none()
    if not ab_test:
        raise HTTPException(404, "A/B test not found")

    if ab_test.status != "draft":
        raise HTTPException(400, f"Cannot start A/B test in status: {ab_test.status}")

    now = datetime.now(timezone.utc)
    ab_test.status = "running"
    ab_test.started_at = now
    ab_test.updated_at = now

    return {
        "ab_test_id": ab_test.id,
        "status": "running",
        "started_at": now.isoformat(),
    }


# ── POST /ab-tests/{id}/stop ──────────────────────────────────────────────

@router.post("/ab-tests/{test_id}/stop", response_model=ABTestStopResponse)
async def stop_ab_test(
    test_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
):
    """Stop an A/B test (sets status=completed, ended_at=now, computes winner)."""
    query = select(ABTest).where(
        ABTest.id == test_id,
        ABTest.tenant_id == ctx.tenant_id,
    )
    result = await session.execute(query)
    ab_test = result.scalar_one_or_none()
    if not ab_test:
        raise HTTPException(404, "A/B test not found")

    if ab_test.status not in ("running", "paused"):
        raise HTTPException(400, f"Cannot stop A/B test in status: {ab_test.status}")

    now = datetime.now(timezone.utc)
    ab_test.status = "completed"
    ab_test.ended_at = now
    ab_test.updated_at = now

    # Compute winner based on outcome rates
    results = await _compute_results_summary(ab_test, session)
    winner = _determine_winner(results)
    ab_test.winner = winner

    return {
        "ab_test_id": ab_test.id,
        "status": "completed",
        "ended_at": now.isoformat(),
        "winner": winner,
        "results": results,
    }


# ── POST /ab-tests/{id}/assign ────────────────────────────────────────────

@router.post("/ab-tests/{test_id}/assign", response_model=ABTestAssignResponse)
async def assign_customer(
    test_id: uuid.UUID,
    data: ABTestAssignRequest,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
):
    """Assign a customer to a variant (returns which journey to use)."""
    query = select(ABTest).where(
        ABTest.id == test_id,
        ABTest.tenant_id == ctx.tenant_id,
    )
    result = await session.execute(query)
    ab_test = result.scalar_one_or_none()
    if not ab_test:
        raise HTTPException(404, "A/B test not found")

    if ab_test.status != "running":
        raise HTTPException(400, f"Cannot assign customers to A/B test in status: {ab_test.status}")

    # Check if customer already assigned
    existing_query = select(ABTestAssignment).where(
        ABTestAssignment.ab_test_id == test_id,
        ABTestAssignment.customer_id == data.customer_id,
    )
    existing_result = await session.execute(existing_query)
    existing = existing_result.scalar_one_or_none()
    if existing:
        journey_id = ab_test.journey_a_id if existing.variant == "a" else ab_test.journey_b_id
        return {
            "ab_test_id": test_id,
            "customer_id": data.customer_id,
            "variant": existing.variant,
            "journey_id": journey_id,
        }

    # Deterministic assignment based on customer_id hash
    # traffic_split % go to variant "b", rest to "a"
    import hashlib
    hash_val = int(hashlib.md5(f"{test_id}:{data.customer_id}".encode()).hexdigest(), 16)
    hash_pct = Decimal(str((hash_val % 10000) / 100))  # 0.00 - 99.99

    variant = "b" if hash_pct < ab_test.traffic_split else "a"
    journey_id = ab_test.journey_b_id if variant == "b" else ab_test.journey_a_id

    assignment = ABTestAssignment(
        ab_test_id=test_id,
        customer_id=data.customer_id,
        variant=variant,
    )
    session.add(assignment)
    await session.flush()

    return {
        "ab_test_id": test_id,
        "customer_id": data.customer_id,
        "variant": variant,
        "journey_id": journey_id,
    }


# ── DELETE /ab-tests/{id} ─────────────────────────────────────────────────

@router.delete("/ab-tests/{test_id}")
async def delete_ab_test(
    test_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
):
    """Delete an A/B test (only if draft or completed)."""
    query = select(ABTest).where(
        ABTest.id == test_id,
        ABTest.tenant_id == ctx.tenant_id,
    )
    result = await session.execute(query)
    ab_test = result.scalar_one_or_none()
    if not ab_test:
        raise HTTPException(404, "A/B test not found")

    if ab_test.status not in ("draft", "completed"):
        raise HTTPException(400, f"Cannot delete A/B test in status: {ab_test.status}. Stop it first.")

    await session.delete(ab_test)
    return {"status": "deleted", "ab_test_id": str(test_id)}


# ── Helpers ────────────────────────────────────────────────────────────────

def _ab_test_to_dict(ab_test: ABTest) -> dict:
    return {
        "id": str(ab_test.id),
        "tenant_id": str(ab_test.tenant_id),
        "name": ab_test.name,
        "journey_a_id": str(ab_test.journey_a_id),
        "journey_b_id": str(ab_test.journey_b_id),
        "traffic_split": float(ab_test.traffic_split),
        "status": ab_test.status,
        "started_at": ab_test.started_at.isoformat() if ab_test.started_at else None,
        "ended_at": ab_test.ended_at.isoformat() if ab_test.ended_at else None,
        "winner": ab_test.winner,
        "created_at": ab_test.created_at.isoformat() if ab_test.created_at else None,
        "updated_at": ab_test.updated_at.isoformat() if ab_test.updated_at else None,
    }


async def _compute_results_summary(ab_test: ABTest, session: AsyncSession) -> dict:
    """Compute outcome-based results for each variant."""
    summary = {
        "variant_a": {"total_outcomes": 0, "accepted": 0, "rejected": 0, "acceptance_rate": 0.0},
        "variant_b": {"total_outcomes": 0, "accepted": 0, "rejected": 0, "acceptance_rate": 0.0},
    }

    for variant, journey_id in [("a", ab_test.journey_a_id), ("b", ab_test.journey_b_id)]:
        # Count total outcomes for this journey
        count_query = (
            select(
                func.count(JourneyOutcome.id).label("total"),
                func.sum(func.case((JourneyOutcome.outcome == "accepted", 1), else_=0)).label("accepted"),
                func.sum(func.case((JourneyOutcome.outcome == "rejected", 1), else_=0)).label("rejected"),
            )
            .where(
                JourneyOutcome.journey_id == journey_id,
                JourneyOutcome.tenant_id == ab_test.tenant_id,
            )
        )
        # If test has started_at, only count outcomes after that
        if ab_test.started_at:
            count_query = count_query.where(JourneyOutcome.created_at >= ab_test.started_at)

        result = await session.execute(count_query)
        row = result.one_or_none()
        if row:
            total = row.total or 0
            accepted = row.accepted or 0
            rejected = row.rejected or 0
            rate = round(accepted / total * 100, 1) if total > 0 else 0.0
            key = f"variant_{variant}"
            summary[key] = {
                "total_outcomes": total,
                "accepted": accepted,
                "rejected": rejected,
                "acceptance_rate": rate,
            }

    return summary


def _determine_winner(results: dict) -> Optional[str]:
    """Determine the winner based on acceptance rates."""
    a_rate = results["variant_a"]["acceptance_rate"]
    b_rate = results["variant_b"]["acceptance_rate"]
    a_total = results["variant_a"]["total_outcomes"]
    b_total = results["variant_b"]["total_outcomes"]

    # Need minimum sample size to declare a winner
    MIN_SAMPLES = 10
    if a_total < MIN_SAMPLES or b_total < MIN_SAMPLES:
        return None

    if a_rate > b_rate:
        return "a"
    elif b_rate > a_rate:
        return "b"
    return None  # tie
