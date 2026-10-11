from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from services.common.platform_pricing import Selection, quote
from services.common.platform_proration import change_quote, quote_expired
from services.common.platform_access import blocked_feature, payment_access


@pytest.fixture(autouse=True)
def _unregistered_catalogue_default(monkeypatch):
    """These tests are about price arithmetic, which is easiest to read with no VAT split. The shipped default is
    VAT-registered with VAT-inclusive prices (see test_platform_tax_default.py); here the catalogue is unregistered."""
    import copy
    from services.common import platform_pricing as pp
    real = pp.catalog

    def unregistered():
        data = copy.deepcopy(real())
        data["tax_policy"]["vat_registered"] = False
        data["supplier"]["vat_registered"] = False
        return data
    monkeypatch.setattr(pp, "catalog", unregistered)

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)

def current(bundle="professional"):
    return {"active_quote":quote(Selection(bundle=bundle)),"billing_mode":"payment",
            "period_start":(NOW-timedelta(days=15)).isoformat(),"period_end":(NOW+timedelta(days=15)).isoformat()}

def test_upgrade_credits_unused_half_and_sets_full_recurring_price():
    changed = change_quote(quote(Selection(bundle="enterprise")), current(), NOW)
    assert changed["proration"]["unused_net_credit"] == "1750.00"
    assert changed["net_zar"] == "7750.00"
    assert changed["amount_cents"] == 775000
    assert changed["recurring_total_zar"] == "9500.00"
    assert sum(Decimal(line["net_zar"]) for line in changed["lines"]) == Decimal(changed["net_zar"])
    assert not quote_expired(changed, NOW+timedelta(minutes=14))
    assert quote_expired(changed, NOW+timedelta(minutes=15))

def test_free_downgrade_keeps_credit_without_payment_and_expired_time_is_not_credited():
    changed = change_quote(quote(Selection(bundle="starter")), current(), NOW)
    assert changed["amount_cents"] == 0
    assert changed["proration"]["credit_remaining"] == "1750.00"
    old = current(); old["period_end"] = (NOW-timedelta(days=1)).isoformat()
    assert change_quote(quote(Selection(bundle="growth")),old,NOW)["proration"]["unused_net_credit"] == "0.00"

def test_tier_gate_is_per_panel_not_highest_tenant_tier():
    assert blocked_feature("portal","starter","/api/v1/portal/seo/audit")
    assert blocked_feature("portal","professional","/api/v1/portal/pages/id/versions")
    assert blocked_feature("portal","enterprise","/api/v1/portal/pages/id/versions") is None
    assert blocked_feature("finance","professional","/scenario")
    assert blocked_feature("finance","starter","/accounts") is None

def test_payment_grace_expires_but_free_and_owner_grants_remain():
    p=current(); settings={"platform_pricing":p}
    assert payment_access(settings,"past_due",NOW+timedelta(days=21))
    assert not payment_access(settings,"past_due",NOW+timedelta(days=22))
    p["active_quote"] = quote(Selection(bundle="starter"))
    assert payment_access(settings,"cancelled",NOW+timedelta(days=400))
    assert not payment_access(settings,"suspended",NOW)
    p["billing_mode"]="platform_owner"
    assert payment_access(settings,"active",NOW+timedelta(days=400))


def test_free_core_panels_do_not_require_a_commercial_license():
    from services.common.entitlements import EntitlementGuard
    for key in ("overview","admin"):
        guard=EntitlementGuard(module_name=key)
        guard.license.ensure_valid=lambda: (_ for _ in ()).throw(AssertionError("Core panels must stay accessible"))
        guard.ensure_startup()
        assert guard.is_licensed()
