"""Database session management for the Billing service."""

import uuid
from contextlib import contextmanager
from decimal import Decimal
from typing import Generator

from sqlalchemy.orm import Session, sessionmaker

from services.common.db import get_engine
from services.billing.models import Base, InvoiceSequence


_session_factory: sessionmaker | None = None
VAT_RATE = Decimal("0.15")


def _get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return _session_factory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a transactional DB session and commit on success."""
    factory = _get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_tables() -> None:
    """Create all Billing tables if they don't exist (dev convenience)."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def next_invoice_number(session: Session, tenant_id: uuid.UUID) -> str:
    """Generate the next sequential invoice number for a tenant.

    Uses a `FOR UPDATE` lock on the sequence row to prevent duplicates
    under concurrent generation.
    """
    seq = (
        session.query(InvoiceSequence)
        .filter(InvoiceSequence.tenant_id == tenant_id)
        .with_for_update()
        .first()
    )
    if seq is None:
        seq = InvoiceSequence(tenant_id=tenant_id, last_number=0)
        session.add(seq)
        session.flush()

    seq.last_number += 1
    session.flush()

    short_tenant = str(tenant_id).split("-")[0].upper()[:4]
    return f"INV-{short_tenant}-{seq.last_number:06d}"


def compute_vat(subtotal: Decimal) -> Decimal:
    """Compute 15% SA VAT on a subtotal."""
    return (subtotal * VAT_RATE).quantize(Decimal("0.01"))
