"""Pure report calculations; unknown data is never represented as zero."""
import math
from collections import defaultdict
from datetime import timezone
from zoneinfo import ZoneInfo

FIELDS = {"mean", "min", "max", "sum", "state", "change"}

def finite(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None

def clean_statistic(row):
    if not isinstance(row, dict):
        return {}
    return {key: value for key in FIELDS if (value := finite(row.get(key))) is not None}

def series_report(entity, rows, source):
    """Daily consumption from sums, daily means for measurements; preserve gaps."""
    grouped = defaultdict(list)
    previous = None
    skipped = 0
    meter = entity.attributes.get("state_class") in {"total", "total_increasing"}
    for stamp, values in sorted(rows, key=lambda row: row[0]):
        stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
        day = stamp.astimezone(ZoneInfo("Africa/Johannesburg")).date().isoformat()
        if meter:
            cumulative = finite(values.get("sum") if source == "recorder" else values.get("state"))
            value = finite(values.get("change")) if source == "recorder" else None
            if value is None and previous and cumulative is not None:
                gap = (stamp - previous[0]).total_seconds()
                delta = cumulative - previous[1]
                # A reset or long gap needs reconciliation, not a fabricated total.
                if 0 < gap <= (7200 if source == "recorder" else 900) and delta >= 0:
                    value = delta
            if cumulative is not None:
                previous = (stamp, cumulative)
        else:
            value = finite(values.get("mean") if source == "recorder" else values.get("state"))
        if value is None or (meter and value < 0):
            skipped += 1
            continue
        grouped[day].append(value)
    points = []
    for day, values in sorted(grouped.items()):
        value = finite(sum(values) if meter else sum(v / len(values) for v in values))
        if value is None:
            skipped += len(values)
            continue
        points.append({"date": day, "value": round(value, 3), "samples": len(values)})
    total = finite(sum(p["value"] for p in points)) if meter and points else None
    average = finite(sum(p["value"] / len(points) for p in points)) if not meter and points else None
    return {"entity_id": entity.entity_id, "name": entity.name, "room": entity.room,
        "unit": entity.attributes.get("unit_of_measurement", ""), "kind": "consumption" if meter else "measurement",
        "source": source, "points": points, "skipped_samples": skipped,
        "total": round(total, 3) if total is not None else None,
        "average": round(average, 3) if average is not None else None}
