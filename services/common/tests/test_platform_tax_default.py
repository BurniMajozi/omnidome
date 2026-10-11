"""OmniDome's own default tax position: VAT-registered at the South African standard rate (15%), prices VAT-EXCLUSIVE.
The catalogue price is the price before VAT; VAT is added in the summation section and the customer pays net + VAT."""
from decimal import Decimal

from services.common.platform_pricing import Selection, catalog, quote


def test_shipped_default_is_vat_registered_and_exclusive_at_fifteen_percent():
    policy = catalog()["tax_policy"]
    assert policy["vat_registered"] is True and policy["prices_include_vat"] is False and Decimal(str(policy["rate"])) == Decimal("0.15")
    supplier = catalog()["supplier"]
    assert supplier["vat_registered"] is True and supplier["prices_include_vat"] is False
    # PLACEHOLDER VAT number (10 digits starting with 4, the South African format) until OmniDome's real registration is entered
    assert supplier["vat_number"] == "4000000000"


def test_advertised_price_is_the_net_and_vat_is_added_on_top():
    q = quote(Selection(bundle="professional"))
    assert q["net_zar"] == "3500.00" and q["vat_zar"] == "525.00" and q["total_zar"] == "4025.00" and q["amount_cents"] == 402500
    assert Decimal(q["net_zar"]) + Decimal(q["vat_zar"]) == Decimal(q["total_zar"])


def test_a_free_bundle_has_no_vat():
    q = quote(Selection(bundle="starter"))
    assert q["total_zar"] == "0.00" and q["vat_zar"] == "0.00"
