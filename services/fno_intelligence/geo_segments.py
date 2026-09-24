"""Geo segments over FNO passed homes (SPEC-geo-segments.md).

Pure logic only -- no DB, no network -- so it is unit-tested directly
(tests/test_geo_segments.py). A segment describes *places*, never people:
passed-home data is address-only, and nothing here emits an individual
address. The query compiler and endpoints live in routes.py.
"""

from __future__ import annotations

import csv
import io
import math
import uuid
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Literal, Optional

from pydantic import BaseModel, Field, model_validator

MIN_RADIUS_KM = 1.0
EARTH_RADIUS_KM = 6371.0088

# Must match the `passed_home_dwelling` enum in models.py.
DwellingType = Literal["unknown", "sdu", "mdu_unit", "complex", "business", "estate"]

EXCLUSION_REASONS = ("suppressed_customer", "duplicate", "invalid", "raw", "not_geocoded")

CSV_COLUMNS = (
    "suburb", "city", "postal_code", "homes", "centroid_lat", "centroid_lng", "suggested_radius_km",
)

_KML_NS = "http://www.opengis.net/kml/2.2"


class GeoSegmentFilters(BaseModel):
    """AND across fields, OR within a list field; empty list = no constraint."""

    fno_names: list[str] = Field(default_factory=list)
    import_ids: list[uuid.UUID] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    suburbs: list[str] = Field(default_factory=list)
    postal_codes: list[str] = Field(default_factory=list)
    dwelling_types: list[DwellingType] = Field(default_factory=list)
    date_passed_from: Optional[date] = None
    date_passed_to: Optional[date] = None
    geocoded_only: bool = True

    @model_validator(mode="after")
    def _date_range_in_order(self) -> "GeoSegmentFilters":
        if self.date_passed_from and self.date_passed_to and self.date_passed_from > self.date_passed_to:
            raise ValueError("date_passed_from must be on or before date_passed_to")
        return self


@dataclass(frozen=True)
class HomePoint:
    suburb: Optional[str]
    city: Optional[str]
    postal_code: Optional[str]
    lat: Optional[float]
    lng: Optional[float]


def exclusion_reason(
    status: str,
    geocode_status: str,
    lat: Optional[float],
    lng: Optional[float],
    *,
    geocoded_only: bool,
) -> Optional[str]:
    """None if the home is eligible, else the reason it is left out.

    The status reason wins over a missing geocode, so each excluded home is
    counted exactly once.
    """
    if status != "normalized":
        return status if status in EXCLUSION_REASONS else "invalid"
    if geocoded_only and (geocode_status != "geocoded" or lat is None or lng is None):
        return "not_geocoded"
    return None


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1 = map(math.radians, a)
    lat2, lng2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def suggested_radius_km(centroid: Optional[tuple[float, float]], points: list[tuple[float, float]]) -> float:
    """Max distance from centroid to any point, rounded up to 0.5 km, min 1.0.

    The floor is the practical minimum radius ad platforms accept.
    """
    if centroid is None or not points:
        return MIN_RADIUS_KM
    furthest = max(haversine_km(centroid, p) for p in points)
    # The epsilon keeps a distance that lands exactly on a 0.5 km step from
    # being bumped a whole step by float noise.
    return max(MIN_RADIUS_KM, math.ceil(furthest * 2 - 1e-9) / 2)


def summarize_areas(homes: Iterable[HomePoint]) -> list[dict]:
    """Group eligible homes by (suburb, city, postal code) into target areas."""
    groups: dict[tuple, list[HomePoint]] = defaultdict(list)
    for h in homes:
        groups[(h.suburb, h.city, h.postal_code)].append(h)

    areas = []
    for (suburb, city, postal_code), members in groups.items():
        points = [(h.lat, h.lng) for h in members if h.lat is not None and h.lng is not None]
        centroid = (
            (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
            if points else None
        )
        areas.append({
            "suburb": suburb,
            "city": city,
            "postal_code": postal_code,
            "homes": len(members),
            "centroid_lat": round(centroid[0], 6) if centroid else None,
            "centroid_lng": round(centroid[1], 6) if centroid else None,
            "suggested_radius_km": suggested_radius_km(centroid, points),
        })
    areas.sort(key=lambda a: (-a["homes"], a["suburb"] or ""))
    return areas


def areas_to_csv(areas: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for a in areas:
        writer.writerow(["" if a[c] is None else a[c] for c in CSV_COLUMNS])
    return buf.getvalue()


def areas_to_kml(areas: list[dict], segment_name: str) -> str:
    """One Placemark per area that has a centroid (KML needs a point)."""
    ET.register_namespace("", _KML_NS)
    kml = ET.Element(f"{{{_KML_NS}}}kml")
    doc = ET.SubElement(kml, f"{{{_KML_NS}}}Document")
    ET.SubElement(doc, f"{{{_KML_NS}}}name").text = segment_name
    for a in areas:
        if a["centroid_lat"] is None or a["centroid_lng"] is None:
            continue
        pm = ET.SubElement(doc, f"{{{_KML_NS}}}Placemark")
        ET.SubElement(pm, f"{{{_KML_NS}}}name").text = a["suburb"] or "Unknown suburb"
        ET.SubElement(pm, f"{{{_KML_NS}}}description").text = (
            f"{a['homes']} homes passed; suggested radius {a['suggested_radius_km']} km"
        )
        point = ET.SubElement(pm, f"{{{_KML_NS}}}Point")
        ET.SubElement(point, f"{{{_KML_NS}}}coordinates").text = f"{a['centroid_lng']},{a['centroid_lat']},0"
    return ET.tostring(kml, encoding="unicode", xml_declaration=True)
