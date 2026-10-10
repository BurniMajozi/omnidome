"""Environment-driven settings, read at call time so tests (and operators) can change them without a reload."""
from __future__ import annotations

import os
from typing import Optional


def _flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _num(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)


def enabled() -> bool:
    return _flag("INSIGHTS_ENABLED", True)


def cache_ttl_s() -> float:
    return _num("INSIGHTS_CACHE_TTL_MIN", 30.0) * 60.0


def min_regen_s() -> float:
    """Evidence changed, but do not regenerate more often than this (stops churn from a busy index)."""
    return _num("INSIGHTS_MIN_REGEN_S", 60.0)


def daily_llm_calls() -> int:
    return int(_num("INSIGHTS_DAILY_LLM_CALLS", 200))


def forced_refreshes_per_10min() -> int:
    return int(_num("INSIGHTS_REFRESH_PER_10MIN", 6))


def model() -> Optional[str]:
    """INSIGHTS_MODEL, else the BI model (BI_AI_MODEL, default claude-haiku-4.5), else the shared chain (None)."""
    own = os.getenv("INSIGHTS_MODEL")
    if own is not None and own.strip():
        return own.strip()
    bi = os.getenv("BI_AI_MODEL")
    if bi is None:
        return "anthropic/claude-haiku-4.5"
    return bi.strip() or None


def llm_timeout_s() -> float:
    return _num("INSIGHTS_LLM_TIMEOUT_S", 60.0)


def verify_enabled() -> bool:
    return _flag("INSIGHTS_VERIFY_ENABLED", True)


def verify_min_grounded() -> float:
    return _num("INSIGHTS_VERIFY_MIN_GROUNDED", 0.6)


def verify_fail_below() -> float:
    """Below this, even after a retry, the narrative is replaced by the deterministic template."""
    return _num("INSIGHTS_VERIFY_FAIL_BELOW", 0.4)


def source_timeout_s() -> float:
    return _num("INSIGHTS_SOURCE_TIMEOUT_S", 6.0)


def store_kind() -> str:
    return os.getenv("INSIGHTS_STORE", "pg").strip().lower()
