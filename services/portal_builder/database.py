"""Database session management for the Portal Builder Service."""
from services.portal_builder.main import PortalPage, PortalPageVersion, PortalSubmission, PortalSeoProfile, PortalCampaign  # noqa: ensure models registered
from services.common.db import session_scope, get_engine, init_tables
from services.common.entitlements import EntitlementGuard
from services.common.auth import AuthContext, get_auth_context
__all__ = ["session_scope", "init_tables", "PortalPage", "PortalPageVersion", "PortalSubmission", "PortalSeoProfile", "PortalCampaign"]
