"""Tenant-scoped email suppression list (opt-outs, hard bounces, complaints).

Every outbound marketing/sales email path must filter recipients through this module
BEFORE sending. The table is ``marketing_suppressions``; it is created by the marketing
service's startup migration, but every function here is safe when the table does not exist
yet (nothing is suppressed, a warning is logged) so callers never crash.

Async API (used with an AsyncSession):

    allowed, suppressed = await filter_suppressed(session, tenant_id, emails)
    if await is_suppressed(session, tenant_id, email): ...
    await add_suppression(session, tenant_id, email, "unsubscribe", "link")

A ``*_sync`` twin of each function takes a SQLAlchemy sync Connection (the marketing
service still uses a sync engine for its email tables).

Queries run inside a SAVEPOINT so a missing table never poisons the caller's transaction.
The caller owns commit/rollback of the outer transaction.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Iterable, List, Tuple

from sqlalchemy import text

logger = logging.getLogger("omnidome.suppression")

REASONS = ("unsubscribe", "bounce", "complaint", "manual")

SUPPRESSION_DDL = """
CREATE TABLE IF NOT EXISTS marketing_suppressions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    email_lower VARCHAR(320) NOT NULL,
    reason VARCHAR(20) NOT NULL,
    source VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, email_lower)
)
"""

_CHUNK = 500
_ADDR_RE = re.compile(r"<([^<>]+)>")


def normalize_email(email: object) -> str:
    """Lower-case + strip; also unwraps ``Name <a@b.c>``. Returns '' for non-strings."""
    if not isinstance(email, str):
        return ""
    value = email.strip()
    m = _ADDR_RE.search(value)
    if m:
        value = m.group(1)
    return value.strip().lower()


def _tid(tenant_id: object) -> str:
    return str(tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id)))


def _norm_reason(reason: str) -> str:
    r = (reason or "").strip().lower()
    if r not in REASONS:
        raise ValueError(f"reason must be one of {REASONS}")
    return r


def _split(emails: Iterable[str]) -> Tuple[List[str], List[str]]:
    """Returns (normalised unique addresses in order, unusable originals)."""
    seen: set = set()
    out: List[str] = []
    for e in emails or []:
        n = normalize_email(e)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out, []


_SELECT = (
    "SELECT email_lower FROM marketing_suppressions "
    "WHERE tenant_id = CAST(:tid AS uuid) AND email_lower = ANY(CAST(:emails AS text[]))"
)
_INSERT = (
    "INSERT INTO marketing_suppressions (tenant_id, email_lower, reason, source) "
    "VALUES (CAST(:tid AS uuid), :email, :reason, :source) "
    "ON CONFLICT (tenant_id, email_lower) DO NOTHING"
)
_DELETE = (
    "DELETE FROM marketing_suppressions "
    "WHERE tenant_id = CAST(:tid AS uuid) AND email_lower = :email"
)


# ── Async (AsyncSession) ────────────────────────────────────────────────────

async def _suppressed_set(session, tenant_id, normalized: List[str]) -> set:
    found: set = set()
    if not normalized:
        return found
    try:
        for i in range(0, len(normalized), _CHUNK):
            chunk = normalized[i:i + _CHUNK]
            async with session.begin_nested():
                rows = await session.execute(text(_SELECT), {"tid": _tid(tenant_id), "emails": chunk})
                found.update(r[0] for r in rows.all())
    except Exception as exc:  # noqa: BLE001 - table missing etc.: never crash a sender
        logger.warning("suppression lookup unavailable (treating all as allowed): %s", exc)
        return set()
    return found


async def is_suppressed(session, tenant_id, email) -> bool:
    n = normalize_email(email)
    if not n:
        return False
    return n in await _suppressed_set(session, tenant_id, [n])


async def filter_suppressed(session, tenant_id, emails: list) -> tuple:
    """Returns (allowed, suppressed); both lists hold lower-cased, de-duplicated addresses."""
    normalized, _ = _split(emails)
    hit = await _suppressed_set(session, tenant_id, normalized)
    return [e for e in normalized if e not in hit], [e for e in normalized if e in hit]


async def add_suppression(session, tenant_id, email, reason, source) -> bool:
    """Idempotent. Returns True when a row was newly inserted."""
    n = normalize_email(email)
    if not n:
        return False
    params = {"tid": _tid(tenant_id), "email": n, "reason": _norm_reason(reason), "source": (source or "")[:120]}
    try:
        async with session.begin_nested():
            res = await session.execute(text(_INSERT), params)
        return bool(res.rowcount)
    except Exception:  # noqa: BLE001 - table may not exist yet: create it once and retry
        async with session.begin_nested():
            await session.execute(text(SUPPRESSION_DDL))
        async with session.begin_nested():
            res = await session.execute(text(_INSERT), params)
        return bool(res.rowcount)


async def remove_suppression(session, tenant_id, email) -> bool:
    n = normalize_email(email)
    if not n:
        return False
    try:
        async with session.begin_nested():
            res = await session.execute(text(_DELETE), {"tid": _tid(tenant_id), "email": n})
        return bool(res.rowcount)
    except Exception as exc:  # noqa: BLE001
        logger.warning("suppression remove unavailable: %s", exc)
        return False


# ── Sync (Connection) twins ─────────────────────────────────────────────────

def _suppressed_set_sync(conn, tenant_id, normalized: List[str]) -> set:
    found: set = set()
    if not normalized:
        return found
    try:
        for i in range(0, len(normalized), _CHUNK):
            chunk = normalized[i:i + _CHUNK]
            with conn.begin_nested():
                rows = conn.execute(text(_SELECT), {"tid": _tid(tenant_id), "emails": chunk})
                found.update(r[0] for r in rows.all())
    except Exception as exc:  # noqa: BLE001
        logger.warning("suppression lookup unavailable (treating all as allowed): %s", exc)
        return set()
    return found


def is_suppressed_sync(conn, tenant_id, email) -> bool:
    n = normalize_email(email)
    return bool(n) and n in _suppressed_set_sync(conn, tenant_id, [n])


def filter_suppressed_sync(conn, tenant_id, emails: list) -> tuple:
    normalized, _ = _split(emails)
    hit = _suppressed_set_sync(conn, tenant_id, normalized)
    return [e for e in normalized if e not in hit], [e for e in normalized if e in hit]


def add_suppression_sync(conn, tenant_id, email, reason, source) -> bool:
    n = normalize_email(email)
    if not n:
        return False
    params = {"tid": _tid(tenant_id), "email": n, "reason": _norm_reason(reason), "source": (source or "")[:120]}
    try:
        with conn.begin_nested():
            res = conn.execute(text(_INSERT), params)
        return bool(res.rowcount)
    except Exception:  # noqa: BLE001
        with conn.begin_nested():
            conn.execute(text(SUPPRESSION_DDL))
        with conn.begin_nested():
            res = conn.execute(text(_INSERT), params)
        return bool(res.rowcount)


def remove_suppression_sync(conn, tenant_id, email) -> bool:
    n = normalize_email(email)
    if not n:
        return False
    try:
        with conn.begin_nested():
            res = conn.execute(text(_DELETE), {"tid": _tid(tenant_id), "email": n})
        return bool(res.rowcount)
    except Exception as exc:  # noqa: BLE001
        logger.warning("suppression remove unavailable: %s", exc)
        return False


def list_suppressions_sync(conn, tenant_id, limit: int = 200, offset: int = 0) -> list:
    try:
        with conn.begin_nested():
            rows = conn.execute(
                text("SELECT email_lower, reason, source, created_at FROM marketing_suppressions "
                     "WHERE tenant_id = CAST(:tid AS uuid) ORDER BY created_at DESC LIMIT :lim OFFSET :off"),
                {"tid": _tid(tenant_id), "lim": limit, "off": offset},
            ).mappings().all()
        return [dict(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("suppression list unavailable: %s", exc)
        return []
