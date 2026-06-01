"""Database session management for the IoT Service."""

from services.common.db import session_scope, get_engine

from iot.models import Device, TelemetryReading  # noqa: F401 — ensures models are registered with Base

Base = None
for cls in Device.__mro__:
    if hasattr(cls, 'metadata'):
        Base = cls
        break


def init_tables():
    """Create IoT tables if they don't exist."""
    if Base is not None:
        engine = get_engine()
        Base.metadata.create_all(
            bind=engine,
            tables=[
                Device.__table__,
                TelemetryReading.__table__,
            ],
        )


__all__ = ["session_scope", "init_tables", "Base"]
