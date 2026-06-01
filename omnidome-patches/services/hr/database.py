"""Database session management for the HR Service."""

from services.common.db import session_scope, get_engine

from hr.models import Base  # noqa: F401 — ensures models are registered with Base


def init_tables():
    """Create HR tables if they don't exist (dev convenience)."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


__all__ = ["session_scope", "init_tables", "Base"]
