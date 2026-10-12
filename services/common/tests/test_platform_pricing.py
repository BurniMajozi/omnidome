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


def test_free_plan_gives_six_real_free_tiers_and_one_shared_allowance():
    q = quote(Selection(bundle="starter"))
    expected = {"crm", "support", "portal", "retention", "products", "inventory"}
    assert set(q["entitlements"]) == expected
    assert set(q["selection"]["modules"].values()) == {"free"}
    assert q["tier"] == "FREE" and q["amount_cents"] == 0
    assert q["usage_policy"]["monthly_credits"] == 50
    assert all(limits["writes_per_month"] == 100 for limits in q["usage_policy"]["module_limits"].values())
    from services.common.platform_access import blocked_feature
    assert blocked_feature("inventory", "free", "/reports/valuation")
    assert blocked_feature("portal", "free", "/api/v1/portal/campaigns")
    assert blocked_feature("inventory", "free", "/items") is None


def test_free_modules_can_be_selected_or_upgraded_without_hidden_charges():
    free = {key: "free" for key in catalog()["free_modules"]}
    q = quote(Selection(modules=free))
    assert q["amount_cents"] == 0 and q["usage_policy"]["monthly_credits"] == 50
    inclusive = quote(Selection(modules=free), {"vat_registered": False, "prices_include_vat": True, "rate": "0.15"})
    assert inclusive["amount_cents"] == 0 and inclusive["total_zar"] == "0.00"
    upgraded = quote(Selection(bundle="starter", modules={"crm": "professional"}))
    assert upgraded["net_zar"] == "749.00"
    assert upgraded["selection"]["modules"]["inventory"] == "free"
    assert upgraded["tier"] == "PROFESSIONAL"
    assert quote(Selection(**upgraded["selection"])) == upgraded
    with pytest.raises(ValidationError): Selection(modules={"billing": "free"})


def test_paid_bundle_keeps_basic_free_panels_without_inflating_allowance():
    q = quote(Selection(bundle="growth"))
    assert set(catalog()["free_modules"]) <= set(q["entitlements"])
    assert q["selection"]["modules"]["crm"] == "starter"
    assert q["selection"]["modules"]["inventory"] == "free"
    assert q["usage_policy"]["module_limits"]["inventory"]["writes_per_month"] == 100
    assert q["usage_policy"]["monthly_credits"] == 500



def test_tenant_owner_rag_scope_intersects_enabled_panels():
    from types import SimpleNamespace
    from services.tenant_memory.knowledge.access import build_scope, restrict_to_tenant
    ctx = SimpleNamespace(tenant_id="tenant",user_id="user",roles=["owner"],permissions=[],is_platform_admin=False,modules=[])
    scope = restrict_to_tenant(build_scope(ctx), ["crm", "portal"])
    assert "crm" in scope.modules and "portal" in scope.modules
    assert "billing" not in scope.modules and "network" not in scope.modules
    assert "personal" in scope.modules
