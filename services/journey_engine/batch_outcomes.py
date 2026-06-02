"""Daily batch job: verify 90-day and 180-day retention for journey outcomes.

This script runs as a standalone Python process (not FastAPI).  It:
  1. Queries journey_outcomes for records approaching their 90-day or 180-day
     verification window (created_at between 85-90 days ago or 175-180 days ago).
  2. For each matching outcome, checks whether the customer is still active
     by calling the lifecycle service or querying the database directly.
  3. Updates actual_retained_90d / actual_retained_180d and computes a
     retention_rate for each record.
  4. POSTs aggregated feedback to the retention service at /retention/feedback.

Designed to be invoked via:
    docker compose run journey_engine python -m services.journey_engine.batch_outcomes

Or directly:
    python -m services.journey_engine.batch_outcomes

Environment variables:
    DATABASE_URL        — PostgreSQL connection string (required)
    LIFECYCLE_URL       — Base URL of the lifecycle service (default: http://lifecycle:8016)
    RETENTION_URL       — Base URL of the retention service (default: http://retention:8018)
    BATCH_DRY_RUN       — If "true", skip DB writes and HTTP feedback (default: false)
    BATCH_LOG_LEVEL     — Logging level (default: INFO)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.engine import make_url

from services.journey_engine.models import JourneyOutcome

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

logger = logging.getLogger("batch_outcomes")

DEFAULT_DATABASE_URL = "postgresql://postgres:***@localhost:5432/postgres"
DEFAULT_LIFECYCLE_URL = "http://lifecycle:8016"
DEFAULT_RETENTION_URL = "http://retention:8018"

# Windows for "approaching" the check date (days ago)
DAY_90_WINDOW_START = 85
DAY_90_WINDOW_END = 90
DAY_180_WINDOW_START = 175
DAY_180_WINDOW_END = 180


def _build_async_url(url: str) -> str:
    parsed = make_url(url)
    if parsed.drivername.startswith("postgresql") and "+asyncpg" not in parsed.drivername:
        parsed = parsed.set(drivername="postgresql+asyncpg")
    return str(parsed)


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    db_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    engine = create_async_engine(_build_async_url(db_url), pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RetentionCheck:
    """Result of a single retention verification."""
    outcome_id: UUID
    customer_id: UUID
    tenant_id: UUID
    journey_id: Optional[UUID]
    offer_id: Optional[UUID]
    outcome: str
    check_type: str  # "90d" or "180d"
    is_retained: bool


@dataclass
class BatchResult:
    """Aggregated results for the retention service feedback."""
    total_checked: int = 0
    retained_90d_count: int = 0
    retained_180d_count: int = 0
    checks: list[RetentionCheck] = field(default_factory=list)

    @property
    def retention_rate_90d(self) -> Optional[float]:
        ninety = [c for c in self.checks if c.check_type == "90d"]
        if not ninety:
            return None
        return sum(1 for c in ninety if c.is_retained) / len(ninety)

    @property
    def retention_rate_180d(self) -> Optional[float]:
        oneeighty = [c for c in self.checks if c.check_type == "180d"]
        if not oneeighty:
            return None
        return sum(1 for c in oneeighty if c.is_retained) / len(oneeighty)


# ---------------------------------------------------------------------------
# Retention verification
# ---------------------------------------------------------------------------

async def check_customer_active_lifecycle(
    client: httpx.AsyncClient,
    customer_id: UUID,
    base_url: str,
) -> bool:
    """Check if a customer is still active via the lifecycle service.

    Calls GET /customers/{customer_id}/status and returns True if the
    customer's status is 'active'.
    """
    try:
        resp = await client.get(
            f"{base_url}/customers/{customer_id}/status",
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("status") == "active"
        elif resp.status_code == 404:
            logger.warning("Customer %s not found in lifecycle service", customer_id)
            return False
        else:
            logger.error(
                "Unexpected status %d from lifecycle for customer %s",
                resp.status_code,
                customer_id,
            )
            return False
    except httpx.HTTPError as exc:
        logger.error("HTTP error checking customer %s: %s", customer_id, exc)
        return False


async def check_customer_active_db(
    session: AsyncSession,
    customer_id: UUID,
) -> bool:
    """Fallback: check if a customer is still active via direct DB query.

    Looks up the customer in the lifecycle_customers table (if it exists)
    and checks the status column.  Returns True if active.
    """
    try:
        result = await session.execute(
            select(1).select_from(
                # Use raw text to avoid hard dependency on lifecycle models
                __import__("sqlalchemy").text(
                    "SELECT 1 FROM lifecycle_customers "
                    "WHERE id = :cid AND status = 'active'"
                )
            ).params(cid=customer_id)
        )
        return result.scalar_one_or_none() is not None
    except Exception as exc:
        logger.error("DB fallback check failed for customer %s: %s", customer_id, exc)
        return False


async def verify_retention(
    session: AsyncSession,
    client: httpx.AsyncClient,
    outcome: JourneyOutcome,
    check_type: str,
    lifecycle_url: str,
) -> RetentionCheck:
    """Verify whether a customer retained for the given check window."""
    # Try lifecycle service first, fall back to direct DB
    is_retained = await check_customer_active_lifecycle(
        client, outcome.customer_id, lifecycle_url
    )
    if not is_retained:
        is_retained = await check_customer_active_db(session, outcome.customer_id)

    return RetentionCheck(
        outcome_id=outcome.id,
        customer_id=outcome.customer_id,
        tenant_id=outcome.tenant_id,
        journey_id=outcome.journey_id,
        offer_id=outcome.offer_id,
        outcome=outcome.outcome,
        check_type=check_type,
        is_retained=is_retained,
    )


# ---------------------------------------------------------------------------
# Retention rate computation
# ---------------------------------------------------------------------------

def compute_retention_rate(actual_90d: Optional[bool], actual_180d: Optional[bool]) -> Optional[float]:
    """Compute a scalar retention rate from the two boolean flags.

    Rules:
        actual_180d == True  → 1.0   (fully retained)
        actual_90d  == True  → 0.5   (retained at 90d but not verified at 180d)
        otherwise           → 0.0   (churned)
        both None           → None  (not yet verified)
    """
    if actual_180d is True:
        return 1.0
    if actual_90d is True:
        return 0.5
    if actual_90d is False or actual_180d is False:
        return 0.0
    return None


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

async def fetch_outcomes_for_window(
    session: AsyncSession,
    window_start_days: int,
    window_end_days: int,
) -> list[JourneyOutcome]:
    """Fetch outcomes created within the given day window that haven't been verified."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=window_end_days)
    window_end = now - timedelta(days=window_start_days)

    # For the 90d window, we check actual_retained_90d IS NULL
    # For the 180d window, we check actual_retained_180d IS NULL
    if window_start_days == DAY_90_WINDOW_START:
        verify_col = JourneyOutcome.actual_retained_90d
    else:
        verify_col = JourneyOutcome.actual_retained_180d

    stmt = (
        select(JourneyOutcome)
        .where(
            JourneyOutcome.created_at >= window_start,
            JourneyOutcome.created_at <= window_end,
            JourneyOutcome.outcome.in_(["accepted", "retained"]),
            verify_col.is_(None),
        )
        .order_by(JourneyOutcome.created_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_outcome_retention(
    session: AsyncSession,
    check: RetentionCheck,
    dry_run: bool,
) -> None:
    """Update a single outcome record with the verified retention flag."""
    rate = compute_retention_rate(
        actual_90d=check.is_retained if check.check_type == "90d" else None,
        actual_180d=check.is_retained if check.check_type == "180d" else None,
    )

    if check.check_type == "90d":
        update_values = {
            "actual_retained_90d": check.is_retained,
            "retention_rate": rate,
        }
    else:
        update_values = {
            "actual_retained_180d": check.is_retained,
            "retention_rate": rate,
        }

    if dry_run:
        logger.info(
            "[DRY RUN] Would update outcome %s: %s",
            check.outcome_id,
            update_values,
        )
        return

    stmt = (
        update(JourneyOutcome)
        .where(JourneyOutcome.id == check.outcome_id)
        .values(**update_values)
    )
    await session.execute(stmt)
    logger.info(
        "Updated outcome %s: %s=%s rate=%s",
        check.outcome_id,
        check.check_type,
        check.is_retained,
        rate,
    )


# ---------------------------------------------------------------------------
# Feedback to retention service
# ---------------------------------------------------------------------------

async def send_retention_feedback(
    client: httpx.AsyncClient,
    result: BatchResult,
    retention_url: str,
    dry_run: bool,
) -> bool:
    """POST aggregated retention feedback to the retention service."""
    payload: dict[str, Any] = {
        "source": "journey_engine_batch_outcomes",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_checked": result.total_checked,
        "retention_rate_90d": result.retention_rate_90d,
        "retention_rate_180d": result.retention_rate_180d,
        "retained_90d_count": result.retained_90d_count,
        "retained_180d_count": result.retained_180d_count,
        "checks": [
            {
                "outcome_id": str(c.outcome_id),
                "customer_id": str(c.customer_id),
                "tenant_id": str(c.tenant_id),
                "journey_id": str(c.journey_id) if c.journey_id else None,
                "offer_id": str(c.offer_id) if c.offer_id else None,
                "outcome": c.outcome,
                "check_type": c.check_type,
                "is_retained": c.is_retained,
            }
            for c in result.checks
        ],
    }

    if dry_run:
        logger.info("[DRY RUN] Would POST to %s/retention/feedback", retention_url)
        logger.debug("[DRY RUN] Payload: %s", payload)
        return True

    try:
        resp = await client.post(
            f"{retention_url}/retention/feedback",
            json=payload,
            timeout=30.0,
        )
        if resp.status_code in (200, 201, 202, 204):
            logger.info(
                "Feedback sent to retention service: %d records, status=%d",
                result.total_checked,
                resp.status_code,
            )
            return True
        else:
            logger.error(
                "Retention service returned %d: %s",
                resp.status_code,
                resp.text[:500],
            )
            return False
    except httpx.HTTPError as exc:
        logger.error("Failed to send feedback to retention service: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Main batch logic
# ---------------------------------------------------------------------------

async def run_batch() -> BatchResult:
    """Execute the full batch job."""
    dry_run = os.getenv("BATCH_DRY_RUN", "false").lower() == "true"
    lifecycle_url = os.getenv("LIFECYCLE_URL", DEFAULT_LIFECYCLE_URL)
    retention_url = os.getenv("RETENTION_URL", DEFAULT_RETENTION_URL)

    logger.info("=" * 60)
    logger.info("Journey Engine — Outcome Retention Batch Job")
    logger.info("Dry run: %s", dry_run)
    logger.info("=" * 60)

    session_factory = _get_session_factory()
    result = BatchResult()

    async with session_factory() as session:
        async with httpx.AsyncClient() as client:
            # ---- 90-day window ----
            logger.info(
                "Fetching outcomes for 90-day window (%d-%d days ago)…",
                DAY_90_WINDOW_START,
                DAY_90_WINDOW_END,
            )
            outcomes_90d = await fetch_outcomes_for_window(
                session, DAY_90_WINDOW_START, DAY_90_WINDOW_END
            )
            logger.info("Found %d outcomes for 90-day check", len(outcomes_90d))

            for outcome in outcomes_90d:
                check = await verify_retention(
                    session, client, outcome, "90d", lifecycle_url
                )
                result.checks.append(check)
                result.total_checked += 1
                if check.is_retained:
                    result.retained_90d_count += 1
                await update_outcome_retention(session, check, dry_run)

            # ---- 180-day window ----
            logger.info(
                "Fetching outcomes for 180-day window (%d-%d days ago)…",
                DAY_180_WINDOW_START,
                DAY_180_WINDOW_END,
            )
            outcomes_180d = await fetch_outcomes_for_window(
                session, DAY_180_WINDOW_START, DAY_180_WINDOW_END
            )
            logger.info("Found %d outcomes for 180-day check", len(outcomes_180d))

            for outcome in outcomes_180d:
                check = await verify_retention(
                    session, client, outcome, "180d", lifecycle_url
                )
                result.checks.append(check)
                result.total_checked += 1
                if check.is_retained:
                    result.retained_180d_count += 1
                await update_outcome_retention(session, check, dry_run)

            # Commit all updates (unless dry run)
            if not dry_run:
                await session.commit()
                logger.info("All updates committed.")
            else:
                logger.info("[DRY RUN] No changes committed.")

            # ---- Send feedback ----
            logger.info("Sending retention feedback to retention service…")
            await send_retention_feedback(client, result, retention_url, dry_run)

    # ---- Summary ----
    logger.info("=" * 60)
    logger.info("Batch complete.")
    logger.info("  Total checked:     %d", result.total_checked)
    logger.info("  90d retained:      %d (rate=%s)", result.retained_90d_count, result.retention_rate_90d)
    logger.info("  180d retained:     %d (rate=%s)", result.retained_180d_count, result.retention_rate_180d)
    logger.info("=" * 60)

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def setup_logging() -> None:
    level = os.getenv("BATCH_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


def main() -> None:
    setup_logging()
    asyncio.run(run_batch())


if __name__ == "__main__":
    main()
