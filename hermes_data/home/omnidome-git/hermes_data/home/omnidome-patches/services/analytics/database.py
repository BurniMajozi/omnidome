"""Database session management for the Analytics Service."""

from services.common.db import session_scope, get_engine

from analytics.routes.insights import AnalyticsReport  # noqa: F401 — ensures model is registered with Base

Base = None
for cls in AnalyticsReport.__mro__:
    if hasattr(cls, 'metadata'):
        Base = cls
        break


def init_tables():
    """Create analytics tables if they don't exist."""
    if Base is not None:
        engine = get_engine()
        Base.metadata.create_all(bind=engine, tables=[AnalyticsReport.__tablename__ and AnalyticsReport.__table__])


__all__ = ["session_scope", "init_tables"]
