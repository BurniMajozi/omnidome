from decimal import Decimal
import pytest
from pydantic import ValidationError
from services.common.platform_pricing import Selection, quote, catalog


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


@pytest.mark.parametrize("bundle,net,seats", [("professional",3500,6),("enterprise",9500,8),("growth",599,3),("starter",0,1)])
def test_bundle_monthly_invoice(bundle,net,seats):
    q = quote(Selection(bundle=bundle))
    assert Decimal(q["net_zar"]) == net
    assert q["seats"] == seats
    assert Decimal(q["total_zar"]) == Decimal(net)
    assert q["amount_cents"] == int(Decimal(q["total_zar"]) * 100)
    assert quote(Selection(**q["selection"])) == q


def test_annual_invoice_is_twelve_discounted_months():
    q = quote(Selection(bundle="professional",period="annually"))
    assert Decimal(q["monthly_net_zar"]) == Decimal("2800")
    assert q["net_zar"] == "33600.00"
    assert q["amount_cents"] == 3360000
    assert q["lines"][0]["quantity"] == 12


@pytest.mark.parametrize("selection,monthly,net,total,cents", [
    (Selection(bundle="growth", period="annually"), "479.20", "5750.40", "5750.40", 575040),
    (Selection(modules={"crm": "starter"}, period="annually"), "199.20", "2390.40", "2390.40", 239040),
])
def test_discounted_cents_match_public_price_and_gateway_amount(selection, monthly, net, total, cents):
    q = quote(selection)
    assert Decimal(q["monthly_net_zar"]) == Decimal(monthly)
    assert q["net_zar"] == net
    assert q["total_zar"] == total
    assert q["amount_cents"] == cents
    assert quote(Selection(**q["selection"])) == q


def test_extra_seats_and_addons_are_in_invoice():
    q = quote(Selection(bundle="professional",modules={"network":"enterprise"},seats=8))
    assert q["net_zar"] == "8589.00"
    assert "network" in q["entitlements"]
    assert len(q["lines"]) == 3


def test_vat_registration_and_inclusive_toggle_do_not_change_catalogue_price():
    selection = Selection(bundle="growth")
    unregistered = quote(selection)
    assert unregistered["total_zar"] == "599.00" and unregistered["vat_zar"] == "0.00"
    inclusive = quote(selection,{"vat_registered":True,"prices_include_vat":True,"rate":"0.15"})
    assert inclusive["total_zar"] == "599.00" and inclusive["net_zar"] == "520.87" and inclusive["vat_zar"] == "78.13"
    exclusive = quote(selection,{"vat_registered":True,"prices_include_vat":False,"rate":"0.15"})
    assert exclusive["net_zar"] == "599.00" and exclusive["total_zar"] == "688.85"
    assert inclusive["amount_cents"] == 59900 and exclusive["amount_cents"] == 68885


def test_online_seats_require_review_above_one_hundred():
    with pytest.raises(ValidationError): Selection(bundle="enterprise",seats=101)


@pytest.mark.parametrize("selection", [{"modules":{}},{"modules":{"platform_admin":"starter"}},{"bundle":"bogus"},{"modules":{"crm":"bogus"}},{"bundle":"professional","amount":1},{"bundle":"professional","seats":0}])
def test_invalid_or_client_price_rejected(selection):
    with pytest.raises(ValidationError): Selection(**selection)


def test_bundle_cannot_hide_tier_changes_or_remove_seats():
    with pytest.raises(ValueError): quote(Selection(bundle="professional",modules={"crm":"enterprise"}))
    with pytest.raises(ValueError): quote(Selection(bundle="professional",seats=1))


def test_catalogue_has_all_priced_panels_and_no_admin_role():
    ids = {m["id"] for m in catalog()["modules"]}
    assert len(ids) == 18
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
