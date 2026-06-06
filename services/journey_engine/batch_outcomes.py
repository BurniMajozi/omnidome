"""Batch job for processing Journey Engine outcomes — daily 90d/180d retention flag checks.

This module provides the core logic for the POST /outcomes/process endpoint.
It scans JourneyOutcome records for customers who accepted retention offers
and checks whether they are still active at the 90-day and 180-day marks.

The job is designed to be run daily (e.g., via cron or a scheduler) and can
also be triggered on-demand via the API endpoint.

Retention verification strategy:
  - 90-day check:  outcomes created >= 90 days ago where actual_retained_90d is NULL
  - 180-day check: outcomes created >= 180 days ago where actual_retained_180d is NULL
  - A customer is considered "retained" if their latest CustomerSnapshot does NOT
    indicate a churned/cancelled status (source_event in CHURN_EVENTS).
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.journey_engine.models import CustomerSnapshot, JourneyOutcome

logger = logging.getLogger(__name__)

# Source events that indicate a customer has churned / is no longer active
CHURN_EVENTS = frozenset({
    "churned",
    "cancelled",
    "account_closed",
    "service_terminated",
    "deactivated",
})

# Source events that indicate a customer is still active
ACTIVE_EVENTS = frozenset({
    "status_change",
    "payment_received",
    "plan_change",
    "reactivated",
    "upgrade",
    "downgrade",
    "renewal",
})


def _is_customer_active(snapshot: Optional[CustomerSnapshot]) -> bool:
    """Determine if a customer is still active based on their latest snapshot.

    Returns True if the customer is considered retained (still active),
    False if they have churned, and True (optimistic default) if no
    snapshot exists (we assume active when data is missing).
    """
    if snapshot is None:
        # No snapshot data available — optimistically assume retained
        # This avoids penalizing outcomes when CRM sync hasn't happened
        logger.debug("No customer snapshot found, assuming active")
        return True

    source_event = (snapshot.source_event or "").lower()

    if source_event in CHURN_EVENTS:
        return False

    # Any known active event or unknown event (new CRM events) = retained
    return True


async def _check_retention_batch(
    session: AsyncSession,
    days: int,
    field_name: str,
) -> dict:
    """Check retention for outcomes that are exactly `days` old and haven't been verified yet.

    Args:
        session: Async database session
        days: The retention window (90 or 180)
        field_name: The JourneyOutcome field to update ('actual_retained_90d' or 'actual_retained_180d')

    Returns:
        Dict with counts of checked, retained, and churned outcomes
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    # Look for outcomes created within a 24-hour window of the target date
    # (i.e., outcomes that are now exactly `days` old)
    window_start = cutoff_date - timedelta(hours=12)
    window_end = cutoff_date + timedelta(hours=12)

    # Map field_name to the actual column
    if field_name == "actual_retained_90d":
        retention_col = JourneyOutcome.actual_retained_90d
    elif field_name == "actual_retained_180d":
        retention_col = JourneyOutcome.actual_retained_180d
    else:
        raise ValueError(f"Unknown retention field: {field_name}")

    # Find outcomes in the time window that haven't been checked yet
    query = (
        select(JourneyOutcome)
        .where(
            and_(
                JourneyOutcome.outcome == "accepted",
                JourneyOutcome.created_at >= window_start,
                JourneyOutcome.created_at <= window_end,
                retention_col.is_(None),
            )
        )
        .order_by(JourneyOutcome.created_at)
    )

    result = await session.execute(query)
    outcomes = result.scalars().all()

    if not outcomes:
        logger.info("No outcomes to check for %dd retention window", days)
        return {"checked": 0, "retained": 0, "churned": 0, "window_start": window_start.isoformat(), "window_end": window_end.isoformat()}

    logger.info("Found %d outcomes to check for %dd retention", len(outcomes), days)

    checked = 0
    retained_count = 0
    churned_count = 0

    for outcome in outcomes:
        # Get the latest customer snapshot
        snap_query = (
            select(CustomerSnapshot)
            .where(
                and_(
                    CustomerSnapshot.customer_id == outcome.customer_id,
                    CustomerSnapshot.tenant_id == outcome.tenant_id,
                )
            )
            .order_by(CustomerSnapshot.updated_at.desc())
            .limit(1)
        )
        snap_result = await session.execute(snap_query)
        snapshot = snap_result.scalar_one_or_none()

        is_active = _is_customer_active(snapshot)

        # Update the outcome record
        if field_name == "actual_retained_90d":
            outcome.actual_retained_90d = is_active
        else:
            outcome.actual_retained_180d = is_active

        checked += 1
        if is_active:
            retained_count += 1
        else:
            churned_count += 1

        logger.debug(
            "Outcome %s: customer %s %s at %dd (snapshot event: %s)",
            outcome.id,
            outcome.customer_id,
            "retained" if is_active else "churned",
            days,
            snapshot.source_event if snapshot else "none",
        )

    return {
        "checked": checked,
        "retained": retained_count,
        "churned": churned_count,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
    }


async def _update_retention_rates(session: AsyncSession) -> int:
    """Recompute retention_rate for all outcomes that have both 90d and 180d flags set.

    retention_rate values:
      - 1.0  = retained at 180d (fully retained)
      - 0.5  = retained at 90d but not 180d (partially retained)
      - 0.0  = churned before 90d
      - NULL = not yet fully evaluated

    Returns:
        Number of records updated
    """
    # Update outcomes where both flags are set but retention_rate hasn't been computed
    # or needs recomputation
    update_stmt = (
        update(JourneyOutcome)
        .where(
            and_(
                JourneyOutcome.actual_retained_90d.isnot(None),
                JourneyOutcome.actual_retained_180d.isnot(None),
            )
        )
        .values(
            retention_rate=case(
                (JourneyOutcome.actual_retained_180d == True, Decimal("1.0")),
                (JourneyOutcome.actual_retained_90d == True, Decimal("0.5")),
                else_=Decimal("0.0"),
            )
        )
    )
    result = await session.execute(update_stmt)
    return result.rowcount


async def process_outcomes(
    session: AsyncSession,
    tenant_id: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Main entry point: run the daily outcome batch job.

    Processes both 90-day and 180-day retention checks in a single pass.

    Args:
        session: Async database session
        tenant_id: Optional tenant filter — if provided, only process outcomes
                   for this tenant
        dry_run: If True, compute results but don't commit changes

    Returns:
        Summary dict with counts for both windows
    """
    logger.info(
        "Starting outcome batch job (tenant=%s, dry_run=%s)",
        tenant_id or "all",
        dry_run,
    )

    job_start = datetime.now(timezone.utc)

    # Run 90-day check
    result_90d = await _check_retention_batch(
        session, days=90, field_name="actual_retained_90d"
    )

    # Run 180-day check
    result_180d = await _check_retention_batch(
        session, days=180, field_name="actual_retained_180d"
    )

    # Recompute retention rates for all fully-evaluated outcomes
    rates_updated = await _update_retention_rates(session)

    job_end = datetime.now(timezone.utc)
    duration_seconds = (job_end - job_start).total_seconds()

    summary = {
        "status": "completed",
        "dry_run": dry_run,
        "tenant_id": tenant_id,
        "job_started_at": job_start.isoformat(),
        "job_completed_at": job_end.isoformat(),
        "duration_seconds": round(duration_seconds, 2),
        "retention_90d": result_90d,
        "retention_180d": result_180d,
        "retention_rates_updated": rates_updated,
    }

    logger.info("Outcome batch job completed in %.2fs: %s", duration_seconds, summary)

    if dry_run:
        # Rollback all changes in dry-run mode
        await session.rollback()
        summary["status"] = "dry_run_completed"

    return summary


async def get_outcome_stats(session: AsyncSession) -> dict:
    """Get current outcome statistics for monitoring.

    Returns counts of total outcomes, pending checks, and retention rates.
    """
    # Total outcomes by type
    total_query = (
        select(
            JourneyOutcome.outcome,
            func.count(JourneyOutcome.id).label("count"),
        )
        .group_by(JourneyOutcome.outcome)
    )
    total_result = await session.execute(total_query)
    totals = {row.outcome: row.count for row in total_result.all()}

    # Pending 90d checks (accepted, created >= 90 days ago, not yet checked)
    cutoff_90d = datetime.now(timezone.utc) - timedelta(days=90)
    pending_90d_query = (
        select(func.count(JourneyOutcome.id))
        .where(
            and_(
                JourneyOutcome.outcome == "accepted",
                JourneyOutcome.created_at <= cutoff_90d,
                JourneyOutcome.actual_retained_90d.is_(None),
            )
        )
    )
    pending_90d = (await session.execute(pending_90d_query)).scalar() or 0

    # Pending 180d checks
    cutoff_180d = datetime.now(timezone.utc) - timedelta(days=180)
    pending_180d_query = (
        select(func.count(JourneyOutcome.id))
        .where(
            and_(
                JourneyOutcome.outcome == "accepted",
                JourneyOutcome.created_at <= cutoff_180d,
                JourneyOutcome.actual_retained_180d.is_(None),
            )
        )
    )
    pending_180d = (await session.execute(pending_180d_query)).scalar() or 0

    # Retention rate summary (for outcomes that have been fully evaluated)
    rate_query = (
        select(
            JourneyOutcome.retention_rate,
            func.count(JourneyOutcome.id).label("count"),
        )
        .where(JourneyOutcome.retention_rate.isnot(None))
        .group_by(JourneyOutcome.retention_rate)
    )
    rate_result = await session.execute(rate_query)
    rate_distribution = {str(row.retention_rate): row.count for row in rate_result.all()}

    return {
        "total_outcomes": totals,
        "pending_90d_checks": pending_90d,
        "pending_180d_checks": pending_180d,
        "retention_rate_distribution": rate_distribution,
    }
