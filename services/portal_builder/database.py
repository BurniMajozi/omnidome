"""Database session management for the Portal Builder Service."""
from services.portal_builder.main import PortalPage, PortalPageVersion, PortalSubmission, PortalSeoProfile, PortalCampaign  # noqa: ensure models registered
from services.common.db import Base, session_scope, get_engine
from services.common.entitlements import EntitlementGuard
from services.common.auth import AuthContext, get_auth_context


def init_tables() -> None:
    """Create all Portal Builder tables if they don't exist (dev convenience)."""
    Base.metadata.create_all(bind=get_engine())


__all__ = ["session_scope", "init_tables", "PortalPage", "PortalPageVersion", "PortalSubmission", "PortalSeoProfile", "PortalCampaign"]
