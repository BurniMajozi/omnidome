"""Billing test defaults: role gates off (the DB-backed suites use header identity with no RBAC rows;
the role tests turn them back on explicitly) and no real calls to the finance service. The gateway
requires a tenant subaccount in production; the legacy money tests predate it, so it is off here and the
gateway suites turn it back on."""
import pytest


@pytest.fixture(autouse=True)
def _billing_test_defaults(monkeypatch):
    monkeypatch.setenv("BILLING_ENFORCE_ROLES", "false")
    monkeypatch.setenv("GATEWAY_REQUIRE_SUBACCOUNT", "false")
    # The shipped default is VAT-registered (15% added on top of OmniDome fees). The money tests state exact fee amounts, so they run
    # with OmniDome unregistered; tests/test_fee_vat.py turns VAT on explicitly.
    from decimal import Decimal
    from services.billing import finance_posting, platform_tax
    monkeypatch.setattr(platform_tax, "position", lambda session: {"registered": False, "rate": Decimal("0.15")})

    async def no_post(*_a, **_k):
        return None
    monkeypatch.setattr(finance_posting, "post_entry", no_post)
    yield
