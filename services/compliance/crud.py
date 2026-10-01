"""Tenant-scoped query helpers: every read/write goes through the caller's tenant.

Foreign ids (another tenant's row) behave exactly like missing ids: 404.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext
from services.compliance.access import tenant_str

MAX_LIST = 1000


def scoped_select(model, ctx: AuthContext, *where):
    return select(model).where(model.tenant_id == tenant_str(ctx), *where)


async def list_rows(db: AsyncSession, ctx: AuthContext, model, *where, order_by=None, limit: int = MAX_LIST) -> list:
    q = scoped_select(model, ctx, *where)
    if order_by is not None:
        q = q.order_by(*(order_by if isinstance(order_by, (list, tuple)) else (order_by,)))
    result = await db.execute(q.limit(limit))
    return list(result.scalars().all())


async def get_owned(db: AsyncSession, ctx: AuthContext, model, row_id: int, label: str = "Record"):
    result = await db.execute(scoped_select(model, ctx, model.id == row_id))
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"{label} not found")
    return obj


async def assert_owned(db: AsyncSession, ctx: AuthContext, model, row_id: Optional[int], label: str) -> None:
    """A referenced id (contract_id, plan_id...) must belong to the caller's tenant."""
    if row_id is None:
        return
    await get_owned(db, ctx, model, row_id, label)


async def create_row(db: AsyncSession, ctx: AuthContext, model, data: dict[str, Any]):
    data = dict(data)
    for forbidden in ("id", "tenant_id"):
        data.pop(forbidden, None)
    obj = model(**data, tenant_id=tenant_str(ctx))
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def update_row(db: AsyncSession, ctx: AuthContext, model, row_id: int, data: dict[str, Any], label: str = "Record"):
    obj = await get_owned(db, ctx, model, row_id, label)
    for k, v in data.items():
        if k in ("id", "tenant_id"):
            continue
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj
