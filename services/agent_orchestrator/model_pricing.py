"""Per-model price table used to turn metered llm_calls tokens into USD.

AGENT_MODEL_PRICES (JSON) overrides/extends the table:
    {"anthropic/claude-sonnet": {"input_per_1m_usd": 3, "output_per_1m_usd": 15}, ...}
Keys are model-name prefixes (case-insensitive, longest prefix wins). The "default"
entry prices any model with no matching prefix; the built-in one is deliberately
CONSERVATIVE (frontier-class rates) so an unknown model over- rather than under-counts
against a budget cap. Local Ollama models cost 0.

Result flags: `estimated` is True whenever the figure rests on a guess: the default
entry, the flat AGENT_USD_PER_1K_TOKENS last-resort rate (only used when the table has
no default at all), or a total-tokens-only row (priced at the higher of input/output).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

logger = logging.getLogger(__name__)

DEFAULT_KEY = "default"

# CONSERVATIVE DEFAULT: priced like a frontier model; applies to any model not listed.
BUILTIN_PRICES: Dict[str, Dict[str, float]] = {
    DEFAULT_KEY: {"input_per_1m_usd": 15.0, "output_per_1m_usd": 75.0},
}

# Names that identify a locally hosted (free) model. Bare family names only count when
# the id has no "/" (OpenRouter ids are always "vendor/model").
LOCAL_PREFIXES = ("ollama/", "ollama:")
LOCAL_FAMILIES = ("gemma", "llama", "qwen", "mistral", "phi", "hermes", "nomic")


def flat_usd_per_1k() -> float:
    try:
        return float(os.getenv("AGENT_USD_PER_1K_TOKENS", "0.01"))
    except ValueError:
        return 0.01


def load_prices() -> Dict[str, Dict[str, float]]:
    prices = {k.lower(): dict(v) for k, v in BUILTIN_PRICES.items()}
    raw = (os.getenv("AGENT_MODEL_PRICES") or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            for prefix, entry in parsed.items():
                prices[str(prefix).lower()] = {
                    "input_per_1m_usd": float(entry["input_per_1m_usd"]),
                    "output_per_1m_usd": float(entry["output_per_1m_usd"]),
                }
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            logger.warning("AGENT_MODEL_PRICES ignored (invalid): %s", exc)
    return prices


def is_local_model(model: Optional[str]) -> bool:
    name = (model or "").strip().lower()
    if not name:
        return False
    if name.startswith(LOCAL_PREFIXES):
        return True
    return "/" not in name and name.startswith(LOCAL_FAMILIES)


@dataclass
class Priced:
    usd: float
    source: str  # local | table | default | flat
    estimated: bool


def price_model(model: Optional[str], prompt_tokens: int, completion_tokens: int, total_tokens: int = 0,
                prices: Optional[Dict[str, Dict[str, float]]] = None) -> Priced:
    """USD for one model's token counts. If only a total is known (no prompt/completion
    split) it is priced at the higher of the input/output rate."""
    prompt, completion = int(prompt_tokens or 0), int(completion_tokens or 0)
    total = int(total_tokens or 0)
    split_known = (prompt + completion) > 0
    if is_local_model(model):
        return Priced(0.0, "local", False)
    prices = prices if prices is not None else load_prices()
    name = (model or "").strip().lower()
    entry, source = None, "table"
    best = ""
    for prefix, value in prices.items():
        if prefix != DEFAULT_KEY and name.startswith(prefix) and len(prefix) > len(best):
            best, entry = prefix, value
    if entry is None:
        entry, source = prices.get(DEFAULT_KEY), "default"
    if entry is None:
        return Priced(float(total or prompt + completion) / 1000.0 * flat_usd_per_1k(), "flat", True)
    in_rate, out_rate = entry["input_per_1m_usd"], entry["output_per_1m_usd"]
    if split_known:
        usd = (prompt * in_rate + completion * out_rate) / 1_000_000.0
        # tokens beyond the split (rare) are priced at the higher rate
        leftover = max(0, total - prompt - completion)
        usd += leftover * max(in_rate, out_rate) / 1_000_000.0
        return Priced(usd, source, source == "default")
    usd = total * max(in_rate, out_rate) / 1_000_000.0
    return Priced(usd, source, True)


def price_rows(rows: Iterable[tuple]) -> tuple[float, bool]:
    """rows: (model, prompt_tokens, completion_tokens, total_tokens) per model.
    Returns (usd, estimated)."""
    prices = load_prices()
    usd, estimated = 0.0, False
    for model, p, c, t in rows:
        priced = price_model(model, p, c, t, prices)
        usd += priced.usd
        estimated = estimated or priced.estimated
    return usd, estimated
