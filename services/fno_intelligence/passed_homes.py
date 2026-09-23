"""Pure normalization logic for FNO 'homes passed' file imports.

No DB, no I/O, no FastAPI -- kept separate from routes.py so it's directly
unit-testable (see tests/test_passed_homes.py), matching the pure-logic test
convention used by services/sales/tests/test_sales_logic.py.

Deliberately dumb: this only normalizes what's on the row and guesses
dwelling_type from address text. Geocoding, customer suppression, and scoring
are out of scope here (see follow-up tickets referenced in routes.py).
"""

import re
from typing import Dict, List, Optional

# Header synonyms (case-insensitive, matched against stripped/lowered headers).
# Vuma/Openserve/MetroFibre "homes passed" exports all use slightly different
# column names for the same concept.
HEADER_SYNONYMS: Dict[str, List[str]] = {
    "address": ["address", "street address", "site address", "stand address", "location", "full address"],
    "suburb": ["suburb", "area", "township", "neighbourhood", "neighborhood"],
    "city": ["city", "town", "municipality"],
    "postal_code": ["postal code", "postcode", "zip", "postal_code"],
    "date_passed": ["date passed", "passed date", "live date", "rfs date"],
    "unit_count": ["units", "unit count", "no of units"],
}


def map_columns(headers: List[str]) -> Dict[str, str]:
    """Return {canonical_field: actual_header} for headers matching a synonym.

    First matching header wins per canonical field. Headers that don't match
    any synonym are simply absent from the result (not an error) -- callers
    decide whether "address" being present is required.
    """
    result: Dict[str, str] = {}
    for canonical, synonyms in HEADER_SYNONYMS.items():
        for header in headers:
            if header.strip().lower() in synonyms:
                result[canonical] = header
                break
    return result


_WS_RE = re.compile(r"\s+")


def normalize_text(value) -> Optional[str]:
    """Strip + collapse internal whitespace. Empty/None -> None."""
    if value is None:
        return None
    text = _WS_RE.sub(" ", str(value).strip())
    return text or None


def normalize_title(value) -> Optional[str]:
    """normalize_text() + title-case, for address/suburb/city display."""
    text = normalize_text(value)
    return text.title() if text else None


def normalize_postal(value) -> Optional[str]:
    """Digits only (SA postal codes are 4 digits; strips any stray text)."""
    text = normalize_text(value)
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    return digits or None


# Ordered so more specific keywords are checked before generic ones.
_DWELLING_KEYWORDS = [
    (("unit", "flat", "tower", "block"), "mdu_unit"),
    (("complex", "estate", "gate"), "complex"),
    (("shop", "office", "warehouse", "business"), "business"),
]


def guess_dwelling_type(address: Optional[str]) -> str:
    """Heuristic only -- refined later once geocoding/parcel data exists."""
    if not address:
        return "unknown"
    low = address.lower()
    for keywords, dwelling in _DWELLING_KEYWORDS:
        if any(k in low for k in keywords):
            return dwelling
    return "unknown"


def build_dedup_key(address_line1: Optional[str], suburb: Optional[str], postal_code: Optional[str]) -> str:
    """Case-insensitive composite key used for both in-file and DB dedup.

    Deliberately exact-match (not fuzzy) for this ticket -- fuzzy matching
    against sales.contacts is a separate, explicitly out-of-scope follow-up.
    """
    parts = [
        (address_line1 or "").lower(),
        (suburb or "").lower(),
        (postal_code or ""),
    ]
    return "|".join(parts)


def normalize_row(raw_row: dict, column_map: Dict[str, str]) -> dict:
    """Normalize one raw source row into passed-home fields.

    Returns a dict always containing: address_line1, suburb, city, province,
    postal_code, date_passed_raw, unit_count_raw, dwelling_type, dedup_key,
    valid, reject_reason. Caller (the background task) owns parsing
    date_passed_raw/unit_count_raw into real Date/int types and persisting.
    """
    address_raw = raw_row.get(column_map.get("address", "")) if "address" in column_map else None
    address_line1 = normalize_title(address_raw)

    if not address_line1:
        return {
            "address_line1": None,
            "suburb": None,
            "city": "Unknown",
            "province": None,
            "postal_code": None,
            "date_passed_raw": None,
            "unit_count_raw": None,
            "dwelling_type": "unknown",
            "dedup_key": "",
            "valid": False,
            "reject_reason": "missing_address",
        }

    suburb = normalize_title(raw_row.get(column_map.get("suburb", ""))) if "suburb" in column_map else None
    city = normalize_title(raw_row.get(column_map.get("city", ""))) if "city" in column_map else None
    postal_code = normalize_postal(raw_row.get(column_map.get("postal_code", ""))) if "postal_code" in column_map else None
    date_passed_raw = normalize_text(raw_row.get(column_map.get("date_passed", ""))) if "date_passed" in column_map else None
    unit_count_raw = normalize_text(raw_row.get(column_map.get("unit_count", ""))) if "unit_count" in column_map else None

    return {
        "address_line1": address_line1,
        "suburb": suburb,
        # KML import precedent (routes.py) defaults city to "Unknown" rather
        # than leaving it null -- kept consistent here.
        "city": city or "Unknown",
        "province": None,  # not in HEADER_SYNONYMS -- no source column for it yet
        "postal_code": postal_code,
        "date_passed_raw": date_passed_raw,
        "unit_count_raw": unit_count_raw,
        "dwelling_type": guess_dwelling_type(address_line1),
        "dedup_key": build_dedup_key(address_line1, suburb, postal_code),
        "valid": True,
        "reject_reason": None,
    }
