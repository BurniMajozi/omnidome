"""Pure-logic tests for FNO passed-homes normalization (no DB, no network).

Run with cwd = services/fno_intelligence:  python -m pytest tests/ -q
Covers: header synonym mapping, text/postal normalization, dwelling-type
heuristic, dedup key construction, and end-to-end row normalization.

The upload endpoint + background-task DB behavior (dedup counters, tenant
isolation, re-import idempotency) is covered by live testing against the
running service rather than an async-DB pytest fixture, since this repo has
no existing async-DB test harness to build on (services/sales/tests/ is also
pure-logic-only) -- see the ticket's manual verification notes.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from passed_homes import (  # noqa: E402
    build_dedup_key,
    guess_dwelling_type,
    map_columns,
    normalize_postal,
    normalize_row,
    normalize_text,
    normalize_title,
)


# ── header mapping ───────────────────────────────────────────────────────

def test_map_columns_recognizes_synonyms():
    headers = ["Site Address", "Suburb", "Town", "Postcode", "RFS Date", "No of Units"]
    mapped = map_columns(headers)
    assert mapped["address"] == "Site Address"
    assert mapped["suburb"] == "Suburb"
    assert mapped["city"] == "Town"
    assert mapped["postal_code"] == "Postcode"
    assert mapped["date_passed"] == "RFS Date"
    assert mapped["unit_count"] == "No of Units"


def test_map_columns_case_and_whitespace_insensitive():
    headers = ["  ADDRESS  ", "suburb"]
    mapped = map_columns(headers)
    assert mapped["address"] == "  ADDRESS  "
    assert mapped["suburb"] == "suburb"


def test_map_columns_missing_address_omits_key():
    mapped = map_columns(["Suburb", "City"])
    assert "address" not in mapped


def test_map_columns_first_match_wins():
    # Both "Address" and "Full Address" match the "address" canonical field --
    # first header in the list should win, not silently overwrite.
    mapped = map_columns(["Address", "Full Address"])
    assert mapped["address"] == "Address"


# ── text normalization ───────────────────────────────────────────────────

def test_normalize_text_collapses_whitespace():
    assert normalize_text("  14   Protea   Ave  ") == "14 Protea Ave"


def test_normalize_text_none_and_empty():
    assert normalize_text(None) is None
    assert normalize_text("   ") is None
    assert normalize_text("") is None


def test_normalize_title_cases():
    assert normalize_title("14 protea ave, brackenfell") == "14 Protea Ave, Brackenfell"


def test_normalize_postal_strips_non_digits():
    assert normalize_postal("7560") == "7560"
    assert normalize_postal("ZA-7560") == "7560"
    assert normalize_postal("") is None
    assert normalize_postal(None) is None


# ── dwelling type heuristic ──────────────────────────────────────────────

def test_guess_dwelling_mdu_unit():
    assert guess_dwelling_type("Unit 4, 12 Main Rd") == "mdu_unit"
    assert guess_dwelling_type("Flat 2B Ocean Towers") == "mdu_unit"


def test_guess_dwelling_complex():
    assert guess_dwelling_type("14 Vineyard Estate") == "complex"
    assert guess_dwelling_type("Gate 3, Silverwood Complex") == "complex"


def test_guess_dwelling_business():
    assert guess_dwelling_type("Shop 5, Main Street") == "business"
    assert guess_dwelling_type("Unit 2 Business Park") == "mdu_unit"  # "unit" checked first, by design


def test_guess_dwelling_unknown_default():
    assert guess_dwelling_type("14 Protea Ave, Brackenfell") == "unknown"
    assert guess_dwelling_type(None) == "unknown"
    assert guess_dwelling_type("") == "unknown"


# ── dedup key ─────────────────────────────────────────────────────────────

def test_dedup_key_case_insensitive_and_stable():
    a = build_dedup_key("14 Protea Ave", "Brackenfell", "7560")
    b = build_dedup_key("14 PROTEA AVE", "BRACKENFELL", "7560")
    assert a == b


def test_dedup_key_differs_on_postal():
    a = build_dedup_key("14 Protea Ave", "Brackenfell", "7560")
    b = build_dedup_key("14 Protea Ave", "Brackenfell", "7561")
    assert a != b


def test_dedup_key_handles_missing_parts():
    key = build_dedup_key(None, None, None)
    assert key == "||"


# ── full row normalization ──────────────────────────────────────────────

def test_normalize_row_happy_path():
    column_map = {"address": "Address", "suburb": "Suburb", "postal_code": "Postcode"}
    raw = {"Address": "14 Protea Ave", "Suburb": "Brackenfell", "Postcode": "7560"}
    result = normalize_row(raw, column_map)
    assert result["valid"] is True
    assert result["address_line1"] == "14 Protea Ave"
    assert result["suburb"] == "Brackenfell"
    assert result["postal_code"] == "7560"
    assert result["city"] == "Unknown"  # no city column mapped -- KML-precedent default
    assert result["reject_reason"] is None
    assert result["dedup_key"] == build_dedup_key("14 Protea Ave", "Brackenfell", "7560")


def test_normalize_row_missing_address_is_invalid():
    column_map = {"address": "Address"}
    raw = {"Address": "   "}
    result = normalize_row(raw, column_map)
    assert result["valid"] is False
    assert result["reject_reason"] == "missing_address"
    assert result["dedup_key"] == ""


def test_normalize_row_no_address_column_mapped():
    result = normalize_row({"Suburb": "Brackenfell"}, {"suburb": "Suburb"})
    assert result["valid"] is False
    assert result["reject_reason"] == "missing_address"


def test_normalize_row_dwelling_type_from_address():
    column_map = {"address": "Address"}
    result = normalize_row({"Address": "Unit 4, Ocean View Complex"}, column_map)
    assert result["dwelling_type"] == "mdu_unit"


# ── is_stuck_import (v2: sweep imports interrupted mid-processing) ─────────

from datetime import datetime, timedelta, timezone  # noqa: E402

from passed_homes import STUCK_IMPORT_MINUTES, is_stuck_import  # noqa: E402

_NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def test_uploaded_import_older_than_cutoff_is_stuck():
    created = _NOW - timedelta(minutes=STUCK_IMPORT_MINUTES + 1)
    assert is_stuck_import("uploaded", created, _NOW) is True


def test_parsing_import_older_than_cutoff_is_stuck():
    created = _NOW - timedelta(hours=5)
    assert is_stuck_import("parsing", created, _NOW) is True


def test_recent_uploaded_import_is_not_stuck():
    created = _NOW - timedelta(minutes=STUCK_IMPORT_MINUTES - 1)
    assert is_stuck_import("uploaded", created, _NOW) is False


def test_finished_imports_are_never_stuck():
    created = _NOW - timedelta(days=3)
    for status in ("imported", "partial", "failed"):
        assert is_stuck_import(status, created, _NOW) is False


def test_naive_created_at_is_treated_as_utc():
    created = (_NOW - timedelta(hours=1)).replace(tzinfo=None)
    assert is_stuck_import("parsing", created, _NOW) is True
