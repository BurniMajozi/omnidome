"""Database session management for the Communication Service."""

from communication.models import Base
from services.common.db import get_async_engine, get_engine, session_scope, init_tables

# Re-export for route convenience
__all__ = ["session_scope", "init_tables", "Base"]
