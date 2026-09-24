"""Pure-logic tests for opportunity-finder (SPEC-opportunity-finder.md).
No network: Overpass JSON, LLM output and URLs are inline fixtures. The
Nominatim / Overpass / Firecrawl / OpenRouter flows are live-verified.

Run with cwd = services/fno_intelligence:  python -m pytest tests/ -q
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opportunities import (  # noqa: E402
    CATEGORIES,
    RADII_KM,
    SAST,
    build_overpass_query,
    parse_overpass_elements,
    parse_sa_datetime,
    parse_tender_json,
    tender_dedupe_key,
    validate_source_url,
)

CENTER = (-26.1455, 28.0415)


# ── categories / Overpass query ───────────────────────────────────────────

def test_every_category_has_label_and_filters():
    for cid, cat in CATEGORIES.items():
        assert cat["label"] and cat["filters"], cid


def test_radius_options_match_spec():
    assert RADII_KM == (1, 2, 5, 10)


def test_query_uses_around_in_metres_and_named_features_only():
    q = build_overpass_query(CENTER[0], CENTER[1], 2, "offices")
    assert "(around:2000,-26.1455,28.0415)" in q
    assert '["name"]["office"]' in q
    assert q.startswith("[out:json]")
    assert "out center tags" in q


def test_all_category_combines_several_filters():
    q = build_overpass_query(CENTER[0], CENTER[1], 1, "all")
    assert q.count("nwr(around:1000") >= 4


def test_unknown_category_raises():
    with pytest.raises(ValueError):
        build_overpass_query(CENTER[0], CENTER[1], 2, "spaceships")


def test_unsupported_radius_raises():
    with pytest.raises(ValueError):
        build_overpass_query(CENTER[0], CENTER[1], 3, "offices")


# ── Overpass elements → companies ─────────────────────────────────────────

def _node(i, name, lat, lng, **tags):
    return {"type": "node", "id": i, "lat": lat, "lon": lng, "tags": {"name": name, **tags}}


def test_node_becomes_company_with_address_and_contacts():
    el = _node(1, "Acme Legal", -26.1450, 28.0410, office="lawyer",
               **{"addr:housenumber": "12", "addr:street": "Oxford Road", "addr:suburb": "Rosebank",
                  "addr:city": "Johannesburg", "addr:postcode": "2196",
                  "phone": "+27 11 555 0100; +27 11 555 0101", "website": "https://acme.example", "email": "hi@acme.example"})
    [c] = parse_overpass_elements([el], CENTER)
    assert c["name"] == "Acme Legal"
    assert c["category_label"] == "Lawyer"
    assert c["address_line"] == "12 Oxford Road"
    assert (c["suburb"], c["city"], c["postal_code"]) == ("Rosebank", "Johannesburg", "2196")
    assert c["phone"] == "+27 11 555 0100"
    assert c["website"] == "https://acme.example"
    assert c["email"] == "hi@acme.example"
    assert (c["osm_type"], c["osm_id"]) == ("node", 1)


def test_contact_prefixed_tags_are_used_when_plain_ones_are_missing():
    el = _node(2, "Beta Clinic", -26.1, 28.0, amenity="clinic",
               **{"contact:phone": "011 555 0200", "contact:website": "beta.example", "contact:email": "b@beta.example"})
    [c] = parse_overpass_elements([el], CENTER)
    assert (c["phone"], c["website"], c["email"]) == ("011 555 0200", "beta.example", "b@beta.example")


def test_way_uses_center_coordinates():
    el = {"type": "way", "id": 9, "center": {"lat": -26.14, "lon": 28.04}, "tags": {"name": "Mall Office Park", "office": "company"}}
    [c] = parse_overpass_elements([el], CENTER)
    assert (c["lat"], c["lng"]) == (-26.14, 28.04)


def test_elements_without_coordinates_or_name_are_skipped():
    no_coords = {"type": "relation", "id": 3, "tags": {"name": "Somewhere", "office": "company"}}
    no_name = {"type": "node", "id": 4, "lat": -26.1, "lon": 28.0, "tags": {"shop": "bakery"}}
    assert parse_overpass_elements([no_coords, no_name], CENTER) == []


def test_duplicates_are_removed_and_results_sorted_by_distance():
    near = _node(5, "Near Co", CENTER[0], CENTER[1], office="company")
    far = _node(6, "Far Co", CENTER[0] - 0.02, CENTER[1], office="company")
    companies = parse_overpass_elements([far, near, near], CENTER)
    assert [c["name"] for c in companies] == ["Near Co", "Far Co"]
    assert companies[0]["distance_km"] == 0
    assert companies[1]["distance_km"] == pytest.approx(2.22, abs=0.05)


def test_results_are_capped():
    els = [_node(i, f"Co {i}", CENTER[0] + i * 1e-5, CENTER[1], office="company") for i in range(10)]
    assert len(parse_overpass_elements(els, CENTER, limit=4)) == 4


def test_category_label_falls_back_through_known_keys():
    el = _node(7, "Fix It", -26.1, 28.0, craft="electrician")
    assert parse_overpass_elements([el], CENTER)[0]["category_label"] == "Electrician"


# ── source URL validation ─────────────────────────────────────────────────

def test_public_https_url_is_normalised():
    assert validate_source_url("  HTTPS://Www.ETenders.gov.za/Home/opportunities?id=1#top ") == \
        "https://www.etenders.gov.za/Home/opportunities?id=1"


def test_missing_scheme_defaults_to_https():
    assert validate_source_url("www.example.co.za/tenders") == "https://www.example.co.za/tenders"


@pytest.mark.parametrize("bad", [
    "ftp://example.com/tenders",
    "javascript:alert(1)",
    "http://localhost:8024/api",
    "http://127.0.0.1/x",
    "http://10.0.0.5/tenders",
    "http://192.168.1.10/tenders",
    "http://169.254.169.254/latest/meta-data",
    "http://fno_intelligence:8024/api",
    "http://printer.local/",
    "https:///nohost",
    "",
])
def test_non_public_or_malformed_urls_are_rejected(bad):
    with pytest.raises(ValueError):
        validate_source_url(bad)


# ── LLM tender JSON ───────────────────────────────────────────────────────

def test_plain_json_list_is_parsed():
    out = parse_tender_json('[{"title": "Supply of fibre", "reference": "RFQ 12/2026"}]')
    assert out[0]["title"] == "Supply of fibre"
    assert out[0]["reference"] == "RFQ 12/2026"


def test_code_fenced_object_with_tenders_key_is_parsed():
    text = 'Here you go:\n```json\n{"tenders": [{"title": "Network upgrade", "required_documents": ["CSD report", "B-BBEE certificate"]}]}\n```\nDone.'
    [t] = parse_tender_json(text)
    assert t["required_documents"] == ["CSD report", "B-BBEE certificate"]


def test_items_without_title_are_dropped_and_missing_fields_are_none():
    [t] = parse_tender_json('[{"title": "  "}, {"title": "Valid one"}]')
    assert t["title"] == "Valid one"
    assert t["closing_text"] is None
    assert t["required_documents"] == []
    assert t["document_links"] == []


def test_document_links_accept_strings_or_objects():
    [t] = parse_tender_json('[{"title": "X", "document_links": ["https://a/doc.pdf", {"label": "Spec", "url": "https://a/spec.pdf"}]}]')
    assert t["document_links"] == [{"label": None, "url": "https://a/doc.pdf"}, {"label": "Spec", "url": "https://a/spec.pdf"}]


def test_empty_list_means_no_tenders():
    assert parse_tender_json("[]") == []


def test_text_without_json_raises():
    with pytest.raises(ValueError):
        parse_tender_json("I could not find any tenders on this page.")


# ── SA date parsing ───────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("15 October 2026 11:00", datetime(2026, 10, 15, 11, 0, tzinfo=SAST)),
    ("Friday, 15 Oct 2026 at 11h00", datetime(2026, 10, 15, 11, 0, tzinfo=SAST)),
    ("2026/10/15", datetime(2026, 10, 15, 23, 59, tzinfo=SAST)),
    ("2026-10-15 09:30", datetime(2026, 10, 15, 9, 30, tzinfo=SAST)),
    ("15-10-2026", datetime(2026, 10, 15, 23, 59, tzinfo=SAST)),
    ("15/10/2026 12:00", datetime(2026, 10, 15, 12, 0, tzinfo=SAST)),
    ("Closing: 3 November 2026", datetime(2026, 11, 3, 23, 59, tzinfo=SAST)),
])
def test_common_sa_date_formats(text, expected):
    assert parse_sa_datetime(text) == expected


def test_date_only_can_default_to_start_of_day():
    assert parse_sa_datetime("2026/10/15", end_of_day=False) == datetime(2026, 10, 15, 0, 0, tzinfo=SAST)


@pytest.mark.parametrize("text", [None, "", "TBC", "See document", "31 February 2026"])
def test_unparseable_dates_return_none(text):
    assert parse_sa_datetime(text) is None


def test_sast_is_utc_plus_two():
    assert SAST.utcoffset(None) == timedelta(hours=2)


# ── dedupe key ────────────────────────────────────────────────────────────

def test_reference_wins_and_ignores_case_and_spacing():
    assert tender_dedupe_key("RFQ 12/2026", "Anything") == tender_dedupe_key("rfq12/2026 ", "Other title")


def test_title_is_used_without_reference():
    assert tender_dedupe_key(None, "Supply of  Fibre, Phase 2!") == tender_dedupe_key("", "supply of fibre phase 2")


def test_reference_and_title_keys_do_not_collide():
    assert tender_dedupe_key("abc", "x") != tender_dedupe_key(None, "abc")
