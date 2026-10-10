"""Dream-state settings: environment defaults, per-tenant overrides (stored in `dream_settings`), safe clamping.

Everything is read lazily from the environment so tests can monkeypatch. The calibrated JEV thresholds can only be
made STRICTER per tenant (approve >= 0.80, reject <= 0.20), never looser than that.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields, replace
from typing import Any, Optional


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _b(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str) -> tuple:
    return tuple(x.strip() for x in os.getenv(name, default).split(",") if x.strip())


def kill_switch_on() -> bool:
    """Global emergency stop, re-read on every check (also between batches)."""
    return _b("DREAM_KILL_SWITCH", False)


@dataclass(frozen=True)
class DreamSettings:
    enabled: bool = False                      # nightly schedule on/off (manual runs always allowed unless the kill switch is on)
    window_start: str = "02:30"                # local wall-clock time the nightly window opens
    window_hours: float = 3.0
    timezone: str = "Africa/Johannesburg"
    batch_size: int = 100
    sleep_s: float = 0.5                       # pause between batches (VM friendly)
    tenant_pause_s: float = 30.0
    max_cards_per_night: int = 1500            # phase 1 re-renders at most this many cards
    rotation_days: int = 7                     # a card outside the high-importance set is re-verified about once per N nights
    high_importance: float = 0.75              # cards at or above this are verified every night
    embed_scan_per_night: int = 2000
    reembed_per_night: int = 200
    semantic_drift: float = 0.25               # cosine DISTANCE between old and new embedding of a changed card
    canary_n: int = 20
    canary_recall_floor: float = 0.60
    canary_alert_drop: float = 0.10
    metric_lookback_days: int = 100
    metric_tolerance: float = 0.005            # relative change in an ACTUAL fact that counts as data drift
    importance_max_step: float = 0.05          # per night
    importance_max_drift: float = 0.25         # total distance from the builder's base importance
    min_samples: int = 5                       # retrievals needed before usage says anything
    telemetry_days: int = 30
    decay_after_days: int = 60
    max_adjustments: int = 300
    conflict_cosine: float = 0.90
    jev_enabled: bool = False                  # JEV is an EXTERNAL service; off unless DREAM_JEV_ENABLED=true
    jev_max_calls: int = 20                    # per tenant per night
    jev_max_cost_usd: float = 0.50
    jev_approve: float = 0.90
    jev_reject: float = 0.10
    stale_days: dict = field(default_factory=dict)          # {source_type: days} overrides of the freshness SLA
    jev_exclude_modules: tuple = ("hr", "finance", "billing", "compliance")
    auto_merge_identical_types: tuple = ("memory_entry",)

    def to_dict(self) -> dict:
        d = {f.name: getattr(self, f.name) for f in fields(self)}
        d["jev_exclude_modules"] = list(self.jev_exclude_modules)
        d["auto_merge_identical_types"] = list(self.auto_merge_identical_types)
        return d


# What a tenant admin may change through PUT /knowledge/dream/settings.
TENANT_KEYS = ("enabled", "window_start", "window_hours", "timezone", "max_cards_per_night", "rotation_days", "semantic_drift",
               "canary_n", "canary_recall_floor", "canary_alert_drop", "metric_tolerance", "decay_after_days",
               "jev_enabled", "jev_max_calls", "jev_max_cost_usd", "jev_approve", "jev_reject", "stale_days")


def from_env() -> DreamSettings:
    stale: dict = {}
    raw = os.getenv("DREAM_STALE_DAYS", "").strip()
    if raw:
        try:
            stale = {str(k): int(v) for k, v in json.loads(raw).items()}
        except (ValueError, AttributeError, TypeError):
            stale = {}
    return DreamSettings(
        enabled=_b("DREAM_ENABLED", False), window_start=os.getenv("DREAM_WINDOW_START", "02:30"),
        window_hours=_f("DREAM_WINDOW_HOURS", 3.0), timezone=os.getenv("DREAM_TIMEZONE", "Africa/Johannesburg"),
        batch_size=max(10, _i("DREAM_BATCH_SIZE", 100)), sleep_s=max(0.0, _f("DREAM_SLEEP_S", 0.5)),
        tenant_pause_s=max(0.0, _f("DREAM_TENANT_PAUSE_S", 30.0)), max_cards_per_night=max(0, _i("DREAM_MAX_CARDS", 1500)),
        rotation_days=max(1, _i("DREAM_ROTATION_DAYS", 7)), high_importance=_f("DREAM_HIGH_IMPORTANCE", 0.75),
        embed_scan_per_night=max(0, _i("DREAM_EMBED_SCAN", 2000)), reembed_per_night=max(0, _i("DREAM_REEMBED_PER_NIGHT", 200)),
        semantic_drift=_f("DREAM_SEMANTIC_DRIFT", 0.25), canary_n=max(0, _i("DREAM_CANARY_N", 20)),
        canary_recall_floor=_f("DREAM_CANARY_FLOOR", 0.60), canary_alert_drop=_f("DREAM_CANARY_ALERT_DROP", 0.10),
        metric_lookback_days=max(7, _i("DREAM_METRIC_LOOKBACK_DAYS", 100)), metric_tolerance=_f("DREAM_METRIC_TOLERANCE", 0.005),
        importance_max_step=_f("DREAM_IMPORTANCE_STEP", 0.05), importance_max_drift=_f("DREAM_IMPORTANCE_DRIFT", 0.25),
        min_samples=max(1, _i("DREAM_MIN_SAMPLES", 5)), telemetry_days=max(7, _i("DREAM_TELEMETRY_DAYS", 30)),
        decay_after_days=max(14, _i("DREAM_DECAY_AFTER_DAYS", 60)), max_adjustments=max(0, _i("DREAM_MAX_ADJUSTMENTS", 300)),
        conflict_cosine=_f("DREAM_CONFLICT_COSINE", 0.90),
        jev_enabled=_b("DREAM_JEV_ENABLED", False), jev_max_calls=max(0, _i("DREAM_JEV_MAX_CALLS", 20)),
        jev_max_cost_usd=max(0.0, _f("DREAM_JEV_MAX_COST_USD", 0.50)),
        jev_approve=_f("DREAM_JEV_APPROVE", 0.90), jev_reject=_f("DREAM_JEV_REJECT", 0.10), stale_days=stale,
        jev_exclude_modules=_csv("DREAM_JEV_EXCLUDE_MODULES", "hr,finance,billing,compliance"),
        auto_merge_identical_types=_csv("DREAM_AUTO_MERGE_IDENTICAL_TYPES", "memory_entry"),
    )


def clamp(s: DreamSettings) -> DreamSettings:
    """Keep every knob inside a safe range, whatever was stored or typed."""
    def lim(v, lo, hi):
        return max(lo, min(hi, v))
    hh, _, mm = (s.window_start or "02:30").partition(":")
    try:
        start = f"{lim(int(hh), 0, 23):02d}:{lim(int(mm or 0), 0, 59):02d}"
    except ValueError:
        start = "02:30"
    return replace(
        s, window_start=start, window_hours=lim(float(s.window_hours), 0.5, 12.0),
        max_cards_per_night=int(lim(s.max_cards_per_night, 0, 20000)), rotation_days=int(lim(s.rotation_days, 1, 60)),
        semantic_drift=lim(float(s.semantic_drift), 0.05, 1.0), canary_n=int(lim(s.canary_n, 0, 100)),
        canary_recall_floor=lim(float(s.canary_recall_floor), 0.0, 1.0), canary_alert_drop=lim(float(s.canary_alert_drop), 0.01, 1.0),
        metric_tolerance=lim(float(s.metric_tolerance), 0.0, 0.5), decay_after_days=int(lim(s.decay_after_days, 14, 720)),
        jev_max_calls=int(lim(s.jev_max_calls, 0, 200)), jev_max_cost_usd=lim(float(s.jev_max_cost_usd), 0.0, 20.0),
        jev_approve=lim(float(s.jev_approve), 0.80, 0.999), jev_reject=lim(float(s.jev_reject), 0.001, 0.20),
        importance_max_step=lim(float(s.importance_max_step), 0.0, 0.1), importance_max_drift=lim(float(s.importance_max_drift), 0.0, 0.4),
    )


def merged(overrides: Optional[dict], base: Optional[DreamSettings] = None) -> DreamSettings:
    """Env defaults + a tenant's stored overrides (only TENANT_KEYS are honoured), clamped."""
    s = base or from_env()
    patch: dict[str, Any] = {}
    for k in TENANT_KEYS:
        if overrides and k in overrides and overrides[k] is not None:
            patch[k] = overrides[k]
    if "stale_days" in patch:
        try:
            patch["stale_days"] = {str(a): int(b) for a, b in dict(patch["stale_days"]).items()}
        except (TypeError, ValueError):
            patch.pop("stale_days")
    try:
        return clamp(replace(s, **patch))
    except (TypeError, ValueError):
        return clamp(s)
