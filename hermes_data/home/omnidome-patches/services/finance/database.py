"""Database session management for the Finance service.

Uses the async session_scope from services.common.db with tenant-scoped
query helpers, matching the OmniDome data layer pattern.
"""

import uuid
from typing import Optional

from services.common.db import session_scope

from services.finance.models import Base


async def init_tables() -> None:
    """Create all finance tables if they don't exist (dev convenience).

    Uses the async engine from services.common.db to run DDL.
    """
    from services.common.db import get_async_engine
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_period_by_id(tenant_id: uuid.UUID, period_id: uuid.UUID) -> "FinancePeriod":
    """Fetch a single finance period by ID, scoped to tenant."""
    from services.finance.models import FinancePeriod
    from sqlalchemy import select
    async with session_scope(tenant_id=tenant_id) as session:
        stmt = select(FinancePeriod).where(
            FinancePeriod.id == period_id,
            FinancePeriod.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
