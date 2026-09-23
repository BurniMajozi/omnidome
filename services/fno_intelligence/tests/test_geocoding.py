"""Pure-logic tests for the Ticket 2 geocoding client (no real network, no DB).

Run with cwd = services/fno_intelligence:  python -m pytest tests/ -q
Covers: free-text query building (both precision tiers), jsonv2 response
parsing, the South Africa bounding-box sanity check, and the two-tier
fallback orchestration in NominatimClient.geocode() (mocked HTTP -- the real
call is exercised by manual/live testing, same convention as
test_passed_homes.py; live-tested 2026-09-23 against 8 real SA addresses,
see geocoding.py's module docstring for why free-text + fallback was chosen
over Nominatim's structured query mode).
"""

import asyncio
import sys
import os
from unittest.mock import AsyncMock, patch

_SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _SERVICE_DIR)
# geocoding.py imports services.common.circuit_breaker -- needs the repo root
# (two levels up from _SERVICE_DIR) on sys.path too, unlike passed_homes.py
# which has zero external deps.
sys.path.insert(0, os.path.dirname(os.path.dirname(_SERVICE_DIR)))

from geocoding import (  # noqa: E402
    GeocodeError,
    GeocodeNotFound,
    NominatimClient,
    build_full_query,
    build_suburb_query,
    is_plausible_za_coordinate,
    parse_result,
)


def _run(coro):
    return asyncio.run(coro)


# ── tier 1: full-address query building ──────────────────────────────────

def test_build_full_query_all_fields():
    q = build_full_query(address_line1="14 Protea Ave", suburb="Brackenfell",
                          city="Cape Town", postal_code="7560")
    assert q == "14 Protea Ave, Brackenfell, Cape Town, 7560, South Africa"


def test_build_full_query_none_without_address():
    assert build_full_query(address_line1=None, suburb="Brackenfell", city="Cape Town", postal_code="7560") is None


def test_build_full_query_city_unknown_falls_back_to_suburb():
    q = build_full_query(address_line1="9 Long St", suburb="Bellville", city="Unknown", postal_code="7530")
    assert q == "9 Long St, Bellville, 7530, South Africa"  # no duplicate "Bellville"


def test_build_full_query_omits_suburb_when_equal_to_city():
    q = build_full_query(address_line1="1 Main Rd", suburb="Sea Point", city="Sea Point", postal_code=None)
    assert q == "1 Main Rd, Sea Point, South Africa"


# ── tier 2: suburb-level fallback query building ─────────────────────────

def test_build_suburb_query_uses_suburb_and_city():
    q = build_suburb_query(suburb="Brackenfell", city="Cape Town")
    assert q == "Brackenfell, Cape Town, South Africa"


def test_build_suburb_query_omits_postal_and_street_by_design():
    # Live-tested 2026-09-23: adding postal_code at suburb granularity
    # returned zero matches where the bare suburb+city succeeded.
    q = build_suburb_query(suburb="Bellville", city="Unknown")
    assert q == "Bellville, South Africa"
    assert "7530" not in q


def test_build_suburb_query_none_when_nothing_usable():
    assert build_suburb_query(suburb=None, city=None) is None
    assert build_suburb_query(suburb=None, city="Unknown") is None


# ── response parsing ──────────────────────────────────────────────────────

def test_parse_result_happy_path():
    payload = [{"lat": "-33.9249", "lon": "18.4241", "display_name": "Cape Town"}]
    lat, lng = parse_result(payload)
    assert lat == -33.9249
    assert lng == 18.4241


def test_parse_result_empty_raises_not_found():
    try:
        parse_result([])
        assert False, "expected GeocodeNotFound"
    except GeocodeNotFound:
        pass


def test_parse_result_malformed_raises_geocode_error():
    try:
        parse_result([{"lat": "not-a-number", "lon": "18.4"}])
        assert False, "expected GeocodeError"
    except GeocodeError:
        pass


def test_parse_result_missing_keys_raises_geocode_error():
    try:
        parse_result([{"display_name": "somewhere"}])
        assert False, "expected GeocodeError"
    except GeocodeError:
        pass


# ── bounding-box sanity check ────────────────────────────────────────────

def test_plausible_za_coordinate_cape_town():
    assert is_plausible_za_coordinate(-33.9249, 18.4241) is True


def test_plausible_za_coordinate_johannesburg():
    assert is_plausible_za_coordinate(-26.2041, 28.0473) is True


def test_implausible_coordinate_outside_za():
    assert is_plausible_za_coordinate(51.5074, -0.1278) is False  # London


def test_implausible_coordinate_null_island():
    assert is_plausible_za_coordinate(0.0, 0.0) is False


# ── two-tier fallback orchestration (mocked HTTP) ────────────────────────

def test_geocode_returns_street_precision_when_tier1_matches():
    client = NominatimClient()
    with patch.object(client, "_search", new=AsyncMock(return_value=[{"lat": "-33.9", "lon": "18.4"}])) as mock_search:
        lat, lng, precision = _run(client.geocode(
            address_line1="14 Protea Ave", suburb="Brackenfell", city="Cape Town", postal_code="7560",
        ))
    assert (lat, lng, precision) == (-33.9, 18.4, "street")
    mock_search.assert_called_once()  # tier 2 never attempted


def test_geocode_falls_back_to_suburb_when_tier1_empty():
    client = NominatimClient()
    responses = [[], [{"lat": "-33.88", "lon": "18.71"}]]  # tier1 empty, tier2 matches

    async def fake_search(query, **kwargs):
        return responses.pop(0)

    with patch.object(client, "_search", new=AsyncMock(side_effect=fake_search)) as mock_search:
        lat, lng, precision = _run(client.geocode(
            address_line1="14 Protea Ave", suburb="Brackenfell", city="Cape Town", postal_code="7560",
        ))
    assert (lat, lng, precision) == (-33.88, 18.71, "suburb")
    assert mock_search.call_count == 2


def test_geocode_raises_not_found_when_both_tiers_empty():
    client = NominatimClient()
    with patch.object(client, "_search", new=AsyncMock(return_value=[])):
        try:
            _run(client.geocode(address_line1="14 Protea Ave", suburb="Brackenfell", city="Cape Town", postal_code="7560"))
            assert False, "expected GeocodeNotFound"
        except GeocodeNotFound:
            pass


def test_geocode_skips_tier1_and_uses_suburb_when_no_address():
    client = NominatimClient()
    with patch.object(client, "_search", new=AsyncMock(return_value=[{"lat": "-33.88", "lon": "18.71"}])) as mock_search:
        lat, lng, precision = _run(client.geocode(
            address_line1=None, suburb="Brackenfell", city="Cape Town", postal_code="7560",
        ))
    assert precision == "suburb"
    mock_search.assert_called_once()  # only the suburb-tier call, no wasted tier-1 attempt


def test_geocode_raises_not_found_when_nothing_usable_at_all():
    client = NominatimClient()
    with patch.object(client, "_search", new=AsyncMock(return_value=[])) as mock_search:
        try:
            _run(client.geocode(address_line1=None, suburb=None, city=None, postal_code=None))
            assert False, "expected GeocodeNotFound"
        except GeocodeNotFound:
            pass
    mock_search.assert_not_called()  # nothing to query at all, tier 1 or 2
