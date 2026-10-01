"""Billing test defaults: role gates off (the DB-backed suites use header identity with no RBAC rows;
the role tests turn them back on explicitly) and no real calls to the finance service."""
import pytest


@pytest.fixture(autouse=True)
def _billing_test_defaults(monkeypatch):
    monkeypatch.setenv("BILLING_ENFORCE_ROLES", "false")
    from services.billing import finance_posting

    async def no_post(*_a, **_k):
        return None
    monkeypatch.setattr(finance_posting, "post_entry", no_post)
    yield
