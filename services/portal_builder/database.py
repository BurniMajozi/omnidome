"""Database session management for the Portal Builder Service."""
from services.portal_builder.main import PortalPage, PortalPageVersion, PortalSubmission, PortalSeoProfile, PortalCampaign, PortalPageView, PortalPageShare  # noqa: ensure models registered
from services.common.db import Base, session_scope, get_engine
from services.common.entitlements import EntitlementGuard
from services.common.auth import AuthContext, get_auth_context
from services.portal_builder.migrations import run_migrations


def init_tables() -> None:
    """Create tables and apply idempotent, locked column migrations."""
    run_migrations()


__all__ = ["session_scope", "init_tables", "PortalPage", "PortalPageVersion", "PortalSubmission", "PortalSeoProfile", "PortalCampaign", "PortalPageView", "PortalPageShare"]
