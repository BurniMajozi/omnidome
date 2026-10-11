"""Payment-gateway commission engine (OmniDome collects for the tenant through a Paystack subaccount).

Commercial model: OmniDome keeps a commission on every tenant-customer charge, stepping down with the
tenant's processed volume in the calendar month (SAST):

    first   R250,000   6.0%
    next    R750,000   5.5%      (up to R1,000,000)
    above   R1,000,000 5.0%

The rate is *marginal*: each band's rate applies only to the part of the volume inside that band. The
rate is all-in: Paystack's own fee is paid out of the commission (initialize is called with bearer
"account"), so the tenant's net is always charge - commission.

Paystack mapping: `subaccount` = the tenant, `transaction_charge` = the flat amount (cents) that stays in
OmniDome's main account; the remainder settles to the tenant's bank. A flat per-charge amount (not the
subaccount's percentage_charge) is what lets the tier change without touching the subaccount.

All maths is integer cents / Decimal; nothing here touches the network or the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional, Sequence
from zoneinfo import ZoneInfo

SAST = ZoneInfo("Africa/Johannesburg")

# (upper bound of the band in cents, None = unbounded; rate in basis points). Must be ascending.
DEFAULT_TIERS: tuple[tuple[Optional[int], int], ...] = (
    (25_000_000, 600),     # up to R250,000
    (100_000_000, 550),    # up to R1,000,000
    (None, 500),           # above
)
MAX_RATE_BPS = 1500  # sanity ceiling for a negotiated override: 15%


class TierError(ValueError):
    pass


def validate_tiers(raw: Sequence) -> tuple[tuple[Optional[int], int], ...]:
    """Accept [[upper_cents|null, bps], ...] (e.g. a negotiated per-tenant override) or raise TierError."""
    try:
        tiers = tuple((None if t[0] is None else int(t[0]), int(t[1])) for t in raw)
    except (TypeError, ValueError, IndexError) as exc:
        raise TierError("tiers must be [[upper_cents_or_null, rate_bps], ...]") from exc
    if not tiers:
        raise TierError("at least one tier is required")
    last = 0
    for i, (upper, bps) in enumerate(tiers):
        if not 0 <= bps <= MAX_RATE_BPS:
            raise TierError(f"rate must be between 0 and {MAX_RATE_BPS} bps")
        if upper is None:
            if i != len(tiers) - 1:
                raise TierError("only the last tier may be unbounded")
        else:
            if upper <= last:
                raise TierError("tier bounds must be strictly ascending")
            last = upper
    if tiers[-1][0] is not None:
        raise TierError("the last tier must be unbounded (null)")
    return tiers


def period_key(when: Optional[datetime] = None) -> str:
    """Calendar month in SAST, e.g. '2026-10'. Tier volume resets on the 1st (SAST)."""
    now = when or datetime.now(SAST)
    if now.tzinfo is not None:
        now = now.astimezone(SAST)
    return f"{now.year:04d}-{now.month:02d}"


@dataclass(frozen=True)
class Commission:
    gross_cents: int
    commission_cents: int
    tenant_net_cents: int
    effective_bps: Decimal          # commission / gross, for display
    bands: tuple[dict, ...]         # [{"from_cents","to_cents","amount_cents","rate_bps","commission_cents"}]
    volume_before_cents: int


def calculate(gross_cents: int, volume_before_cents: int = 0,
              tiers: Iterable = DEFAULT_TIERS) -> Commission:
    """Marginal commission for one charge given the tenant's month-to-date processed volume.

    The total is computed in exact Decimal and rounded half-up once (not per band), so splitting a charge
    across a band boundary cannot gain or lose a cent."""
    if gross_cents < 0 or volume_before_cents < 0:
        raise ValueError("amounts must be non-negative")
    tiers = validate_tiers(list(tiers))
    remaining = gross_cents
    cursor = volume_before_cents
    total = Decimal(0)
    bands: list[dict] = []
    for upper, bps in tiers:
        if remaining <= 0:
            break
        if upper is not None and cursor >= upper:
            continue
        room = remaining if upper is None else min(remaining, upper - cursor)
        part = Decimal(room) * Decimal(bps) / Decimal(10_000)
        total += part
        bands.append({"from_cents": cursor, "to_cents": cursor + room, "amount_cents": room,
                      "rate_bps": bps, "commission_cents": float(part)})
        cursor += room
        remaining -= room
    commission = int(total.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    commission = min(commission, gross_cents)
    eff = (Decimal(commission) * 10_000 / Decimal(gross_cents)).quantize(Decimal("0.01")) if gross_cents else Decimal(0)
    return Commission(gross_cents, commission, gross_cents - commission, eff, tuple(bands), volume_before_cents)


def band_for_volume(volume_cents: int, tiers: Iterable = DEFAULT_TIERS) -> dict:
    """Which band the next rand falls in, and how much is left before the rate steps down."""
    tiers = validate_tiers(list(tiers))
    for upper, bps in tiers:
        if upper is None or volume_cents < upper:
            return {"rate_bps": bps, "next_threshold_cents": upper,
                    "remaining_in_band_cents": None if upper is None else upper - volume_cents}
    raise AssertionError("unreachable: last tier is unbounded")
