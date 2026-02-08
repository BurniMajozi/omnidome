"""Database session management for the CRM service.

Uses SQLAlchemy 2.0 async-style sessions over a synchronous engine
(matching the common db.py pattern) with tenant-scoped query helpers.
"""

import uuid
from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session, sessionmaker

from services.common.db import get_engine
from services.crm.models import Base


_session_factory: sessionmaker | None = None


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
    """Create all CRM tables if they don't exist (dev convenience)."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def generate_account_number(tenant_id: uuid.UUID) -> str:
    """Generate a unique account number for a customer."""
    short_tenant = str(tenant_id).split("-")[0].upper()[:4]
    short_id = uuid.uuid4().hex[:8].upper()
    return f"ACC-{short_tenant}-{short_id}"
