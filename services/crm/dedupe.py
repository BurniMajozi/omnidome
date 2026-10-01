"""Duplicate-customer detection shared by customer create / update and lead conversion."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, or_, select

from services.crm.models import Customer


async def find_duplicate_customer(
    session,
    tenant_id: uuid.UUID,
    phone_normalized: Optional[str],
    email_normalized: Optional[str],
    exclude_id: Optional[uuid.UUID] = None,
) -> Optional[Customer]:
    """The tenant's existing customer with this normalised phone or (case-insensitive) e-mail."""
    clauses = []
    if phone_normalized:
        clauses.append(Customer.phone_normalized == phone_normalized)
    if email_normalized:
        clauses.append(func.lower(Customer.email) == email_normalized)
    if not clauses:
        return None
    stmt = select(Customer).where(Customer.tenant_id == tenant_id, or_(*clauses))
    if exclude_id is not None:
        stmt = stmt.where(Customer.id != exclude_id)
    return (await session.execute(stmt.order_by(Customer.created_at, Customer.id).limit(1))).scalar_one_or_none()


MERGEABLE_FIELDS = ("phone", "id_number", "address", "province", "email")


def merge_missing_fields(existing: Customer, incoming: dict) -> list[str]:
    """Fill ONLY empty fields of `existing` from `incoming`; never overwrite. Returns changed names."""
    changed = []
    for name in MERGEABLE_FIELDS:
        value = incoming.get(name)
        if value not in (None, "") and not getattr(existing, name, None):
            setattr(existing, name, value)
            changed.append(name)
    if incoming.get("phone_normalized") and not existing.phone_normalized:
        existing.phone_normalized = incoming["phone_normalized"]
    return changed
