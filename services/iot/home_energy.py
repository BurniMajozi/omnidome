"""Measured counter deltas; missing and reset counters are never silently zeroed."""
import math
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from services.iot.models import IoTHomeReading, IoTHomeEntity

SOURCES = {"grid_import", "grid_export", "solar", "battery_charge", "battery_discharge", "gas", "water"}
POWER = {"grid_power", "solar_power", "battery_power", "home_power"}


def numeric(state):
    try:
        value = float(state)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def factor(source, unit):
    if source == "water":
        return {"L": 1, "l": 1, "m³": 1000, "m3": 1000}.get(unit)
    if source == "gas":
        return {"m³": 1, "m3": 1}.get(unit)
    return {"kWh": 1, "Wh": .001}.get(unit)


def counter_total(source, readings):
    unit = "L" if source == "water" else "m³" if source == "gas" else "kWh"
    points = []
    for row in readings:
        value, multiplier = numeric(row.state), factor(source, row.unit)
        if value is not None and multiplier is not None:
            points.append(value * multiplier)
    if len(points) < 2:
        return {"value": None, "unit": unit, "reason": "At least two compatible meter readings are needed"}
    if any(right < left for left, right in zip(points, points[1:])):
        return {"value": None, "unit": unit, "reason": "Meter reset detected; total needs review"}
    return {"value": round(points[-1] - points[0], 4), "unit": unit, "reason": None}


async def energy_report(session, home, day):
    start = datetime.combine(day, time.min, ZoneInfo("Africa/Johannesburg"))
    config = home.energy_config or {}
    configured = [value for key, value in config.items() if key in SOURCES | POWER and isinstance(value, str)]
    rows = (await session.scalars(select(IoTHomeReading).where(
        IoTHomeReading.tenant_id == home.tenant_id, IoTHomeReading.home_id == home.id,
        IoTHomeReading.entity_id.in_(configured),
        IoTHomeReading.observed_at >= start, IoTHomeReading.observed_at < start + timedelta(days=1)
    ).order_by(IoTHomeReading.observed_at).limit(50000))).all()
    totals, power = {}, {}
    for source in sorted(SOURCES):
        identity = config.get(source)
        total = counter_total(source, [row for row in rows if row.entity_id == identity])
        if not identity:
            total["reason"] = "Not connected"
        totals[source] = total
    for source in sorted(POWER):
        identity = config.get(source)
        points = []
        for row in rows:
            if row.entity_id != identity or row.unit not in {"W", "kW"}:
                continue
            value = numeric(row.state)
            if value is not None:
                points.append({"time": row.observed_at, "kw": value / 1000 if row.unit == "W" else value})
        power[source] = points[-500:]
    tariff = config.get("grid_tariff")
    usage = totals["grid_import"]["value"]
    entities = (await session.scalars(select(IoTHomeEntity).where(
        IoTHomeEntity.tenant_id == home.tenant_id, IoTHomeEntity.home_id == home.id,
        IoTHomeEntity.entity_id.in_(configured)))).all()
    flows = measured_flows(config, rows, entities, datetime.now(timezone.utc)) if home.status == "connected" else {source: False for source in SOURCES}
    return {"day": str(day), "timezone": "Africa/Johannesburg", "totals": totals, "power": power,
        "flows": flows,
        "grid_cost_zar": round(usage * tariff, 2) if usage is not None and tariff is not None else None,
        "note": "Totals cover the recorded portion of this day. Cost is an estimate from your tariff, not a utility bill."}


def measured_flows(config, readings, entities, current):
    """Animate only fresh, available measurements. Battery direction uses distinct counters."""
    def aware(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    available = {entity.entity_id for entity in entities
        if numeric(entity.state) is not None and 0 <= (current - aware(entity.observed_at)).total_seconds() <= 180}
    flows = {source: False for source in SOURCES}
    for source in SOURCES:
        identity = config.get(source)
        values = [row for row in readings if row.entity_id == identity and numeric(row.state) is not None and factor(source, row.unit) is not None]
        if identity not in available or len(values) < 2:
            continue
        left, right = values[-2:]
        age = (current - aware(right.observed_at)).total_seconds()
        duration = (aware(right.observed_at) - aware(left.observed_at)).total_seconds()
        if 0 <= age <= 180 and 0 < duration <= 300:
            flows[source] = numeric(right.state) * factor(source, right.unit) > numeric(left.state) * factor(source, left.unit)
    for source, positive, negative in [("grid_power", "grid_import", "grid_export"), ("solar_power", "solar", None)]:
        identity = config.get(source)
        values = [row for row in readings if row.entity_id == identity and row.unit in {"W", "kW"} and numeric(row.state) is not None]
        if identity not in available or not values:
            continue
        latest = values[-1]
        if 0 <= (current - aware(latest.observed_at)).total_seconds() <= 180:
            watts = numeric(latest.state) * (1000 if latest.unit == "kW" else 1)
            flows[positive] = watts > 5
            if negative:
                flows[negative] = watts < -5
    return flows
