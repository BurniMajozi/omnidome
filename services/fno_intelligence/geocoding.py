"""Address -> lat/lng geocoding client (Ticket 2 of the fibre prospecting
pipeline: normalized fno_passed_homes rows in, gps_lat/gps_lng out).

Uses OpenStreetMap's Nominatim (free, no API key) by default -- matches the
option named in the original design note over paid providers like Google
Geocoding, since this is South African street-address geocoding for an MVP
pipeline, not a service needing enterprise SLAs. Swappable later by pointing
NOMINATIM_BASE_URL at a self-hosted or commercial-compatible instance.

Nominatim's usage policy (https://operations.osmfoundation.org/policies/nominatim/)
requires: max ~1 request/second, a real identifying User-Agent, and no heavy
bulk/commercial use against the public instance. `_Pacer` below enforces the
1 req/sec ceiling for every process using this client; GEOCODE_USER_AGENT
should be set to a real contact in any deployment that isn't local dev.

Free-text `q=`, not structured (street=/city=/county=) query mode: live-tested
against 8 real South African residential addresses (2026-09-23) and Nominatim's
structured mode returned zero matches for ALL of them, at both street and
suburb granularity -- OSM's SA address coverage plus the structured endpoint's
strict field matching just don't line up for suburb-style SA addressing. Plain
free-text `q=` succeeded for the same suburb-level queries. Two-tier fallback
per address: try the full address first, and if OSM has no feature at that
street/house-number level (common for SA residential streets), fall back to a
suburb-level query so the pipeline still gets a usable (if approximate)
map pin rather than "failed" -- see geocode_precision on FNOPassedHome.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

import httpx

from services.common.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)

_BASE_URL = os.getenv("NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org").rstrip("/")
_USER_AGENT = os.getenv("GEOCODE_USER_AGENT", "OmniDome-FNO-Intelligence/1.0 (local dev)")
_MIN_INTERVAL_SECONDS = float(os.getenv("GEOCODE_MIN_INTERVAL_SECONDS", "1.1"))

# South Africa's approximate bounding box -- used only as a sanity check that
# a returned coordinate is plausible, not to filter Nominatim's own results.
_ZA_LAT_RANGE = (-35.5, -22.0)
_ZA_LNG_RANGE = (16.0, 33.5)


class GeocodeError(Exception):
    """Base error for geocoding client failures."""


class GeocodeNotFound(GeocodeError):
    """Raised when the geocoder has no match for the given address, at
    either precision tier."""


class _Pacer:
    """Serializes calls to at most one per `_MIN_INTERVAL_SECONDS`, process-wide.

    A plain asyncio.Lock + last-call timestamp rather than services.common's
    RateLimiter, which is built for throttling *inbound* FastAPI requests per
    client IP, not for pacing *outbound* calls to a single external API.
    """

    def __init__(self, min_interval: float):
        self._min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def wait(self):
        async with self._lock:
            elapsed = time.monotonic() - self._last_call
            remaining = self._min_interval - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_call = time.monotonic()


_pacer = _Pacer(_MIN_INTERVAL_SECONDS)


def is_plausible_za_coordinate(lat: float, lng: float) -> bool:
    return _ZA_LAT_RANGE[0] <= lat <= _ZA_LAT_RANGE[1] and _ZA_LNG_RANGE[0] <= lng <= _ZA_LNG_RANGE[1]


def _effective_city(suburb: Optional[str], city: Optional[str]) -> Optional[str]:
    # "Unknown" is passed_homes.py's default when no city column was mapped
    # (see normalize_row) -- fall back to suburb rather than sending the
    # literal string "Unknown" to the geocoder.
    return city if (city and city != "Unknown") else suburb


def build_full_query(*, address_line1: Optional[str], suburb: Optional[str],
                      city: Optional[str], postal_code: Optional[str]) -> Optional[str]:
    """Tier 1: full free-text address string. None if there's no street to try."""
    if not address_line1:
        return None
    eff_city = _effective_city(suburb, city)
    parts = [address_line1]
    if suburb and suburb != eff_city:
        parts.append(suburb)
    if eff_city:
        parts.append(eff_city)
    if postal_code:
        parts.append(postal_code)
    parts.append("South Africa")
    return ", ".join(parts)


def build_suburb_query(*, suburb: Optional[str], city: Optional[str]) -> Optional[str]:
    """Tier 2 fallback: suburb/city only, no street or postal code (both hurt
    matching at this coarser granularity -- see module docstring). None if
    there's no suburb or city to geocode at all."""
    eff_city = _effective_city(suburb, city)
    parts = []
    if suburb and suburb != eff_city:
        parts.append(suburb)
    if eff_city:
        parts.append(eff_city)
    if not parts:
        return None
    parts.append("South Africa")
    return ", ".join(parts)


def parse_result(payload: list) -> tuple[float, float]:
    """Parse Nominatim's jsonv2 response list into (lat, lng).

    Raises GeocodeNotFound if the list is empty, GeocodeError if the first
    result is malformed (missing/non-numeric lat or lon).
    """
    if not payload:
        raise GeocodeNotFound("No geocoding match")
    first = payload[0]
    try:
        lat = float(first["lat"])
        lng = float(first["lon"])
    except (KeyError, TypeError, ValueError) as e:
        raise GeocodeError(f"Malformed geocode result: {e}") from e
    return lat, lng


class NominatimClient:
    """Async Nominatim client: paced to <= 1 req/sec, circuit-broken."""

    def __init__(self, base_url: str = _BASE_URL, user_agent: str = _USER_AGENT):
        self.base_url = base_url
        self.user_agent = user_agent

    @circuit_breaker("nominatim", failure_threshold=5, recovery_timeout=60)
    async def _search(self, query: str, *, timeout: float = 10.0) -> list:
        await _pacer.wait()
        headers = {"User-Agent": self.user_agent}
        params = {"q": query, "format": "jsonv2", "limit": 1}
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{self.base_url}/search", params=params, headers=headers)
        if resp.status_code >= 400:
            raise GeocodeError(f"Nominatim /search -> HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    async def geocode(self, *, address_line1: Optional[str], suburb: Optional[str],
                       city: Optional[str], postal_code: Optional[str]) -> tuple[float, float, str]:
        """Geocode a normalized address. Returns (lat, lng, precision) where
        precision is "street" (full address matched) or "suburb" (fell back).
        Raises GeocodeNotFound if neither tier matches, GeocodeError on a
        malformed response or HTTP failure.
        """
        full_q = build_full_query(
            address_line1=address_line1, suburb=suburb, city=city, postal_code=postal_code,
        )
        if full_q:
            try:
                lat, lng = parse_result(await self._search(full_q))
                return lat, lng, "street"
            except GeocodeNotFound:
                pass

        suburb_q = build_suburb_query(suburb=suburb, city=city)
        if not suburb_q:
            raise GeocodeNotFound("No address, suburb, or city to geocode")
        lat, lng = parse_result(await self._search(suburb_q))
        return lat, lng, "suburb"


# Module-level singleton (mirrors services.common.firecrawl's `firecrawl`).
nominatim = NominatimClient()
