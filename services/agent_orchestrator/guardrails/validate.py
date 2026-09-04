"""JSON validity helper for guardrail gating."""

from __future__ import annotations

import json
from typing import Optional, Tuple


def validate_json(text: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Return (True, None) if *text* parses as JSON, else (False, error)."""
    if not text:
        return False, "empty text is not valid JSON"
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        return False, str(exc)
    return True, None
