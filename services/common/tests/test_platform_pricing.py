from decimal import Decimal
import pytest
from pydantic import ValidationError
from services.common.platform_pricing import Selection, quote, catalog


@pytest.mark.parametrize("bundle,net,seats", [("professional",3500,6),("enterprise",9500,8),("growth",999,3),("starter",0,1)])
def test_bundle_monthly_invoice(bundle,net,seats):
    q = quote(Selection(bundle=bundle))
    assert Decimal(q["net_zar"]) == net
    assert q["seats"] == seats
    assert Decimal(q["total_zar"]) == Decimal(net) * Decimal("1.15")
    assert q["amount_cents"] == int(Decimal(q["total_zar"]) * 100)
    assert quote(Selection(**q["selection"])) == q


def test_annual_invoice_is_twelve_discounted_months():
    q = quote(Selection(bundle="professional",period="annually"))
    assert q["monthly_net_zar"] == "2800"
    assert q["net_zar"] == "33600.00"
    assert q["amount_cents"] == 3864000
    assert q["lines"][0]["quantity"] == 12


def test_extra_seats_and_addons_are_in_invoice():
    q = quote(Selection(bundle="professional",modules={"network":"enterprise"},seats=8))
    assert q["net_zar"] == "8589.00"
    assert "network" in q["entitlements"]
    assert len(q["lines"]) == 3


@pytest.mark.parametrize("selection", [{"modules":{}},{"modules":{"platform_admin":"starter"}},{"bundle":"bogus"},{"modules":{"crm":"bogus"}},{"bundle":"professional","amount":1},{"bundle":"professional","seats":0}])
def test_invalid_or_client_price_rejected(selection):
    with pytest.raises(ValidationError): Selection(**selection)


def test_bundle_cannot_hide_tier_changes_or_remove_seats():
    with pytest.raises(ValueError): quote(Selection(bundle="professional",modules={"crm":"enterprise"}))
    with pytest.raises(ValueError): quote(Selection(bundle="professional",seats=1))


def test_catalogue_has_all_priced_panels_and_no_admin_role():
    ids = {m["id"] for m in catalog()["modules"]}
    assert len(ids) == 14
    assert {"support", "call_center", "hr", "portal", "products"} <= ids
    assert not {"owner", "org_admin", "platform_admin", "admin"} & ids


def test_tenant_owner_rag_scope_intersects_enabled_panels():
    from types import SimpleNamespace
    from services.tenant_memory.knowledge.access import build_scope, restrict_to_tenant
    ctx = SimpleNamespace(tenant_id="tenant",user_id="user",roles=["owner"],permissions=[],is_platform_admin=False,modules=[])
    scope = restrict_to_tenant(build_scope(ctx), ["crm", "portal"])
    assert "crm" in scope.modules and "portal" in scope.modules
    assert "billing" not in scope.modules and "network" not in scope.modules
    assert "personal" in scope.modules
