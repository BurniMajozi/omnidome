"""PII detection patterns + scan/mask helpers (SA ID, SA phone, email)."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

PATTERNS: Dict[str, re.Pattern] = {
    # 13-digit SA ID number, not part of a longer digit run.
    "sa_id": re.compile(r"(?<!\d)\d{13}(?!\d)"),
    # SA phone: +27 + 9 digits or 0 + 9 digits, not part of a longer digit run.
    "sa_phone": re.compile(r"(?<!\d)(?:\+27|0)\d{9}(?!\d)"),
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
}


def scan_pii(text: Optional[str]) -> List[Dict]:
    """Return [{type, value, span}] hits for known PII in *text*.

    Returns [] for None/empty input instead of raising.
    """
    if not text:
        return []
    hits: List[Dict] = []
    for pii_type, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            hits.append(
                {"type": pii_type, "value": match.group(0), "span": match.span()}
            )
    # Earliest-first; drop spans overlapping an earlier hit (sa_id wins ties
    # by dict order so a 13-digit ID is never double-reported as a phone).
    hits.sort(key=lambda h: (h["span"][0], h["span"][1]))
    deduped: List[Dict] = []
    for hit in hits:
        if deduped and hit["span"][0] < deduped[-1]["span"][1]:
            continue
        deduped.append(hit)
    return deduped


def mask_text(text: Optional[str], hits: Optional[List[Dict]] = None) -> str:
    """Replace PII values in *text* with [TYPE_MASKED] placeholders.

    Returns "" for None/empty input instead of raising.
    """
    if not text:
        return ""
    if hits is None:
        hits = scan_pii(text)
    # Splice from the end so earlier spans stay valid; skip overlaps.
    ordered = sorted(hits, key=lambda h: (h["span"][0], h["span"][1]))
    kept: List[Dict] = []
    for hit in ordered:
        if kept and hit["span"][0] < kept[-1]["span"][1]:
            continue
        kept.append(hit)
    out = text
    for hit in reversed(kept):
        start, end = hit["span"]
        out = out[:start] + f"[{hit['type'].upper()}_MASKED]" + out[end:]
    return out
