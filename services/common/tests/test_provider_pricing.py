from decimal import Decimal
import pytest
from services.common.provider_pricing import draft_rate_card


def test_draft_floor_covers_fx_vat_payment_and_allocation():
    card=draft_rate_card()
    assert card["charges_enabled"] is False
    for rate in card["rates"]:
        assert rate["meets_target"]
        assert Decimal(rate["scenario_margin_percent"])>=65
    social=next(r for r in card["rates"] if r["id"]=="zernio_account")
    assert Decimal(social["minimum_net_zar"])>470  # More than a naive cost markup.


def test_margin_warning_when_fx_moves_and_free_vendor_slots_not_assumed():
    assert not all(r["meets_target"] for r in draft_rate_card(30)["rates"])
    assert all(r["cost_usd"]>0 for r in draft_rate_card()["rates"])
    with pytest.raises(ValueError): draft_rate_card(0)
