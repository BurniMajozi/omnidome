"""Gateway commission tiers (services/billing/gateway.py): pure maths, no database."""
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.billing import gateway  # noqa: E402

R = 100  # cents per rand


def test_first_band_is_six_percent():
    c = gateway.calculate(1000 * R, 0)
    assert c.commission_cents == 60 * R and c.tenant_net_cents == 940 * R


def test_second_and_third_band_rates():
    assert gateway.calculate(1000 * R, 300_000 * R).commission_cents == 55 * R   # 5.5%
    assert gateway.calculate(1000 * R, 1_200_000 * R).commission_cents == 50 * R  # 5.0%


def test_charge_straddling_a_boundary_is_marginal():
    # R250,000 threshold: R10,000 below at 6% + R10,000 above at 5.5%
    c = gateway.calculate(20_000 * R, 240_000 * R)
    assert c.commission_cents == 600 * R + 550 * R
    assert [b["rate_bps"] for b in c.bands] == [600, 550]
    assert sum(b["amount_cents"] for b in c.bands) == 20_000 * R


def test_charge_spanning_all_three_bands():
    c = gateway.calculate(1_500_000 * R, 0)
    # 250k@6% + 750k@5.5% + 500k@5%
    assert c.commission_cents == (15_000 + 41_250 + 25_000) * R


def test_rounding_is_half_up_once_not_per_band():
    # R0.01 charge: 0.06 cent -> 0 ; R0.09 at 6% = 5.4 cents -> 5
    assert gateway.calculate(1, 0).commission_cents == 0
    assert gateway.calculate(9, 0).commission_cents == 1  # 0.54 cent -> 1
    assert gateway.calculate(25, 0).commission_cents == 2  # 1.5 -> 2 (half up)


def test_commission_never_exceeds_gross_and_net_adds_up():
    for gross in (0, 1, 7, 99, 12_345, 99_999_999):
        c = gateway.calculate(gross, 0)
        assert 0 <= c.commission_cents <= gross and c.commission_cents + c.tenant_net_cents == gross


def test_band_for_volume():
    assert gateway.band_for_volume(0)["rate_bps"] == 600
    assert gateway.band_for_volume(25_000_000)["rate_bps"] == 550   # exactly at the threshold -> next band
    assert gateway.band_for_volume(100_000_000) == {"rate_bps": 500, "next_threshold_cents": None, "remaining_in_band_cents": None}
    assert gateway.band_for_volume(24_999_900)["remaining_in_band_cents"] == 100


def test_negotiated_override_is_validated():
    ok = gateway.validate_tiers([[10_000_000, 450], [None, 400]])
    assert gateway.calculate(1000 * R, 0, ok).commission_cents == 45 * R
    for bad in ([], [[None, 500], [None, 400]], [[100, 500], [50, 400], [None, 300]], [[100, 500]], [[None, 5000]],
                [[100, -1], [None, 5]], "x"):
        with pytest.raises(gateway.TierError):
            gateway.validate_tiers(bad)


def test_period_key_uses_sast_month_boundary():
    from datetime import datetime, timezone
    # 22:30 UTC on 30 Sep is already 00:30 on 1 Oct in SAST
    assert gateway.period_key(datetime(2026, 9, 30, 22, 30, tzinfo=timezone.utc)) == "2026-10"
    assert gateway.period_key(datetime(2026, 9, 30, 21, 30, tzinfo=timezone.utc)) == "2026-09"


def test_negative_amounts_rejected():
    with pytest.raises(ValueError):
        gateway.calculate(-1, 0)
    with pytest.raises(ValueError):
        gateway.calculate(1, -1)
