"""Pure-logic tests for geo segments (SPEC-geo-segments.md): eligibility,
area summarisation, radius maths, filter validation and CSV/KML export.
No DB, no network -- the query compiler and endpoints are live-verified.

Run with cwd = services/fno_intelligence:  python -m pytest tests/ -q
"""

import csv
import io
import os
import sys
import xml.etree.ElementTree as ET
from datetime import date

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geo_segments import (  # noqa: E402
    CSV_COLUMNS,
    MIN_RADIUS_KM,
    GeoSegmentFilters,
    HomePoint,
    areas_to_csv,
    areas_to_kml,
    exclusion_reason,
    haversine_km,
    suggested_radius_km,
    summarize_areas,
)

KML_NS = {"k": "http://www.opengis.net/kml/2.2"}


# ── exclusion_reason ──────────────────────────────────────────────────────

def test_normalized_geocoded_home_is_eligible():
    assert exclusion_reason("normalized", "geocoded", -26.14, 28.04, geocoded_only=True) is None


def test_suppressed_customer_is_excluded_as_suppressed_customer():
    assert exclusion_reason("suppressed_customer", "geocoded", -26.14, 28.04, geocoded_only=True) == "suppressed_customer"


def test_duplicate_is_excluded_as_duplicate():
    assert exclusion_reason("duplicate", "geocoded", -26.14, 28.04, geocoded_only=True) == "duplicate"


def test_invalid_is_excluded_as_invalid():
    assert exclusion_reason("invalid", "pending", None, None, geocoded_only=True) == "invalid"


def test_raw_is_excluded_as_raw():
    assert exclusion_reason("raw", "pending", None, None, geocoded_only=False) == "raw"


def test_status_reason_wins_over_missing_geocode():
    assert exclusion_reason("duplicate", "pending", None, None, geocoded_only=True) == "duplicate"


def test_normalized_but_pending_geocode_is_not_geocoded_when_geocoded_only():
    assert exclusion_reason("normalized", "pending", None, None, geocoded_only=True) == "not_geocoded"


def test_geocoded_status_without_coordinates_is_not_geocoded():
    assert exclusion_reason("normalized", "geocoded", None, 28.04, geocoded_only=True) == "not_geocoded"


def test_normalized_ungeocoded_home_is_eligible_when_geocoded_only_is_false():
    assert exclusion_reason("normalized", "failed", None, None, geocoded_only=False) is None


# ── haversine / radius ────────────────────────────────────────────────────

def test_haversine_same_point_is_zero():
    assert haversine_km((-26.1, 28.0), (-26.1, 28.0)) == 0


def test_haversine_one_degree_latitude_is_about_111_km():
    assert haversine_km((0.0, 0.0), (1.0, 0.0)) == pytest.approx(111.19, abs=0.1)


def test_radius_has_one_km_floor_for_tight_cluster():
    centroid = (-26.1450, 28.0410)
    points = [(-26.1451, 28.0411), (-26.1449, 28.0409)]
    assert suggested_radius_km(centroid, points) == MIN_RADIUS_KM == 1.0


def test_radius_rounds_furthest_point_up_to_half_km():
    centroid = (0.0, 0.0)
    points = [(0.0, 0.0), (0.0145, 0.0)]  # ~1.61 km north
    assert suggested_radius_km(centroid, points) == 2.0


def test_radius_exact_half_km_step_is_not_bumped():
    centroid = (0.0, 0.0)
    points = [(0.013489, 0.0)]  # ~1.4999 km
    assert suggested_radius_km(centroid, points) == 1.5


def test_radius_without_centroid_falls_back_to_floor():
    assert suggested_radius_km(None, []) == MIN_RADIUS_KM


# ── summarize_areas ───────────────────────────────────────────────────────

def _home(suburb, lat=None, lng=None, city="Johannesburg", postal="2196"):
    return HomePoint(suburb=suburb, city=city, postal_code=postal, lat=lat, lng=lng)


def test_areas_group_by_suburb_city_and_postcode():
    homes = [_home("Rosebank", -26.14, 28.04), _home("Rosebank", -26.15, 28.05), _home("Parkhurst", -26.13, 28.01)]
    areas = summarize_areas(homes)
    assert [(a["suburb"], a["homes"]) for a in areas] == [("Rosebank", 2), ("Parkhurst", 1)]


def test_same_suburb_in_different_postcodes_are_separate_areas():
    homes = [_home("Rosebank", postal="2196"), _home("Rosebank", postal="2195")]
    assert len(summarize_areas(homes)) == 2


def test_area_centroid_is_mean_of_geocoded_homes_only():
    homes = [_home("Rosebank", -26.0, 28.0), _home("Rosebank", -26.2, 28.2), _home("Rosebank")]
    area = summarize_areas(homes)[0]
    assert area["homes"] == 3
    assert area["centroid_lat"] == pytest.approx(-26.1)
    assert area["centroid_lng"] == pytest.approx(28.1)


def test_area_without_any_coordinates_has_null_centroid_and_floor_radius():
    area = summarize_areas([_home("Rosebank"), _home("Rosebank")])[0]
    assert area["centroid_lat"] is None
    assert area["centroid_lng"] is None
    assert area["suggested_radius_km"] == MIN_RADIUS_KM


def test_areas_are_ordered_by_homes_desc_then_suburb():
    homes = [_home("Birnam"), _home("Atholl"), _home("Craighall"), _home("Craighall")]
    assert [a["suburb"] for a in summarize_areas(homes)] == ["Craighall", "Atholl", "Birnam"]


def test_empty_home_list_gives_no_areas():
    assert summarize_areas([]) == []


# ── GeoSegmentFilters ─────────────────────────────────────────────────────

def test_filters_default_to_geocoded_only_and_empty_lists():
    f = GeoSegmentFilters()
    assert f.geocoded_only is True
    assert f.suburbs == []


def test_filters_reject_unknown_dwelling_type():
    with pytest.raises(ValidationError):
        GeoSegmentFilters(dwelling_types=["freestanding"])


def test_filters_accept_known_dwelling_types():
    assert GeoSegmentFilters(dwelling_types=["sdu", "estate"]).dwelling_types == ["sdu", "estate"]


def test_filters_reject_from_date_after_to_date():
    with pytest.raises(ValidationError):
        GeoSegmentFilters(date_passed_from=date(2026, 9, 1), date_passed_to=date(2026, 8, 1))


def test_filters_accept_same_from_and_to_date():
    f = GeoSegmentFilters(date_passed_from=date(2026, 9, 1), date_passed_to=date(2026, 9, 1))
    assert f.date_passed_from == f.date_passed_to


# ── CSV / KML ─────────────────────────────────────────────────────────────

def _areas():
    return summarize_areas([
        _home("Rosebank", -26.1450, 28.0410),
        _home("Rosebank", -26.1460, 28.0420),
        _home("Parkhurst"),  # no coordinates
    ])


def test_csv_header_is_exactly_the_spec_columns():
    rows = list(csv.reader(io.StringIO(areas_to_csv(_areas()))))
    assert rows[0] == list(CSV_COLUMNS) == [
        "suburb", "city", "postal_code", "homes", "centroid_lat", "centroid_lng", "suggested_radius_km",
    ]


def test_csv_has_one_row_per_area_including_centroidless_ones():
    rows = list(csv.DictReader(io.StringIO(areas_to_csv(_areas()))))
    assert [(r["suburb"], r["homes"]) for r in rows] == [("Rosebank", "2"), ("Parkhurst", "1")]
    assert rows[1]["centroid_lat"] == ""


def test_csv_never_contains_an_address_column():
    header = areas_to_csv(_areas()).splitlines()[0]
    assert "address" not in header


def test_kml_parses_and_has_one_placemark_per_area_with_centroid():
    root = ET.fromstring(areas_to_kml(_areas(), "Rosebank fibre"))
    placemarks = root.findall(".//k:Placemark", KML_NS)
    assert [p.find("k:name", KML_NS).text for p in placemarks] == ["Rosebank"]


def test_kml_point_is_longitude_then_latitude():
    root = ET.fromstring(areas_to_kml(_areas(), "Rosebank fibre"))
    coords = root.find(".//k:Point/k:coordinates", KML_NS).text
    lng, lat = (float(v) for v in coords.split(",")[:2])
    assert lng == pytest.approx(28.0415)
    assert lat == pytest.approx(-26.1455)


def test_kml_escapes_segment_and_suburb_names():
    areas = summarize_areas([_home("Lynn & Ridge <East>", -26.1, 28.1)])
    root = ET.fromstring(areas_to_kml(areas, "A & B"))
    assert root.find(".//k:Placemark/k:name", KML_NS).text == "Lynn & Ridge <East>"
