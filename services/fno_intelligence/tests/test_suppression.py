"""Pure-logic tests for the Ticket 3 customer-suppression check (no DB, no
network). SuppressionCandidates.load() (the DB prefetch) is exercised by
manual/live testing against the running service, same convention as
test_passed_homes.py and test_geocoding.py -- these tests exercise
street_segment(), best_match(), and SuppressionCandidates.check() by
constructing the candidate dict directly instead of via load().

Run with cwd = services/fno_intelligence:  python -m pytest tests/ -q
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from suppression import (  # noqa: E402
    SuppressionCandidates,
    best_match,
    street_segment,
)


# ── street_segment ────────────────────────────────────────────────────────

def test_street_segment_takes_text_before_first_comma():
    assert street_segment("14 Protea Ave, Brackenfell, Cape Town") == "14 protea ave"


def test_street_segment_collapses_whitespace_and_lowercases():
    assert street_segment("  14   Protea   Ave  ") == "14 protea ave"


def test_street_segment_no_comma_uses_whole_string():
    assert street_segment("14 Protea Ave") == "14 protea ave"


def test_street_segment_none_and_empty():
    assert street_segment(None) == ""
    assert street_segment("") == ""


# ── best_match ────────────────────────────────────────────────────────────

def test_best_match_finds_close_variant():
    candidates = [("id-1", "14 Protea Avenue, Brackenfell, Cape Town")]
    result = best_match("14 Protea Ave", candidates)
    assert result is not None
    assert result[0] == "id-1"


def test_best_match_rejects_different_street_same_suburb():
    # Same suburb/postal-code group (that's why they're candidates at all),
    # but a genuinely different street -- must not match on the shared
    # ", Brackenfell, Cape Town" suffix alone.
    candidates = [("id-1", "22 Church St, Brackenfell, Cape Town")]
    result = best_match("14 Protea Ave", candidates)
    assert result is None


def test_best_match_picks_highest_scoring_of_several():
    candidates = [
        ("id-low", "9 Long St, Bellville"),
        ("id-high", "14 Protea Avenue, Brackenfell"),
    ]
    result = best_match("14 Protea Ave", candidates)
    assert result[0] == "id-high"


def test_best_match_empty_candidates():
    assert best_match("14 Protea Ave", []) is None


def test_best_match_no_address_to_match():
    assert best_match(None, [("id-1", "14 Protea Ave")]) is None
    assert best_match("", [("id-1", "14 Protea Ave")]) is None


# ── SuppressionCandidates.check() ────────────────────────────────────────

def _candidates_with(contacts=None, services=None) -> SuppressionCandidates:
    sc = SuppressionCandidates()
    for postal, addr in (contacts or []):
        sc.contacts_by_postal[postal].append(("contact-id", addr))
    for postal, addr in (services or []):
        sc.services_by_postal[postal].append(("service-id", addr))
    return sc


def test_check_no_match_returns_none():
    sc = _candidates_with(contacts=[("7560", "9 Long St, Bellville")])
    assert sc.check(address_line1="14 Protea Ave", postal_code="7560") is None


def test_check_matches_contact():
    sc = _candidates_with(contacts=[("7560", "14 Protea Avenue, Brackenfell")])
    assert sc.check(address_line1="14 Protea Ave", postal_code="7560") == "existing_contact"


def test_check_matches_active_service():
    sc = _candidates_with(services=[("7560", "14 Protea Ave")])
    assert sc.check(address_line1="14 Protea Ave", postal_code="7560") == "existing_active_service"


def test_check_active_service_takes_priority_over_contact():
    sc = _candidates_with(
        contacts=[("7560", "14 Protea Avenue")],
        services=[("7560", "14 Protea Ave")],
    )
    assert sc.check(address_line1="14 Protea Ave", postal_code="7560") == "existing_active_service"


def test_check_different_postal_code_never_matches():
    # Candidate exists but under a different postal code -- groups are never
    # cross-checked, by design (postal_code is the whole point of the
    # pre-filter that keeps this cheap and precise).
    sc = _candidates_with(contacts=[("8005", "14 Protea Ave")])
    assert sc.check(address_line1="14 Protea Ave", postal_code="7560") is None


def test_check_missing_postal_code_or_address_skips_check():
    sc = _candidates_with(contacts=[("7560", "14 Protea Ave")])
    assert sc.check(address_line1="14 Protea Ave", postal_code=None) is None
    assert sc.check(address_line1=None, postal_code="7560") is None


def test_check_empty_candidates_returns_none():
    sc = SuppressionCandidates()
    assert sc.check(address_line1="14 Protea Ave", postal_code="7560") is None
