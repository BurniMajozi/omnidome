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
    """Create all Network tables if they don't exist (dev convenience).

    Several columns here have real FKs into OTHER services' declarative
    Bases -- NetworkService.product_id -> inventory_products.id
    (services.inventory.models), FNOSessionRecording.session_id/job_id ->
    fno_portal_sessions.id/fno_automation_jobs.id (services.fno_intelligence.
    models). Base.metadata.create_all() can't resolve any of these unless
    the referenced tables already exist AND are registered in *this*
    metadata -- creating them in the database via their owning service's own
    init_tables() isn't enough by itself; SQLAlchemy resolves a string
    ForeignKey("some_table.id") against this module's own Base.metadata.
    tables, which has never heard of a table belonging to another Base.
    Found 2026-09-23 debugging journey_engine, which imports this function
    as part of a longer cross-service FK chain (journey_engine -> network ->
    inventory / fno_intelligence). All services share one physical Postgres
    DB (see docker-compose.yaml), so reflecting the real, already-existing
    tables here is safe; create_all()'s default checkfirst=True then skips
    re-creating them.
    """
    import logging
    from sqlalchemy import Table

    engine = get_engine()

    for table_name in ("inventory_products", "fno_portal_sessions", "fno_automation_jobs"):
        if table_name not in Base.metadata.tables:
            try:
                Table(table_name, Base.metadata, autoload_with=engine)
            except Exception:
                logging.getLogger("network").exception(
                    "Failed to reflect %s -- a network FK to it may fail "
                    "(it must already exist in the database, created by its owning service).",
                    table_name,
                )

    Base.metadata.create_all(bind=engine)


def generate_service_reference(tenant_id: uuid.UUID) -> str:
    """Generate a unique service reference for a network service.
    Format: SVC-<short_tenant>-<random> e.g. SVC-A1B2-7F3E4D
    """
    tenant_short = str(tenant_id).split("-")[0][:4].upper()
    unique_part = uuid.uuid4().hex[:6].upper()
    return f"SVC-{tenant_short}-{unique_part}"
