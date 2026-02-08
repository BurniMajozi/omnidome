"""Database session management for the Network service.

Uses SQLAlchemy 2.0 synchronous sessions (matching the common db.py pattern)
with tenant-scoped query helpers.
"""

import uuid
from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session, sessionmaker

from services.common.db import get_engine
from services.network.models import Base


_session_factory: sessionmaker | None = None


def _get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return _session_factory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a transactional DB session; commits on success, rollbacks on error."""
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
    """Create all Network tables if they don't exist (dev convenience)."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def generate_service_reference(tenant_id: uuid.UUID) -> str:
    """Generate a unique service reference for a network service.
    Format: SVC-<short_tenant>-<random> e.g. SVC-A1B2-7F3E4D
    """
    tenant_short = str(tenant_id).split("-")[0][:4].upper()
    unique_part = uuid.uuid4().hex[:6].upper()
    return f"SVC-{tenant_short}-{unique_part}"
