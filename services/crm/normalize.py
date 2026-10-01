"""Pure normalisers for the CRM: phone numbers, e-mail addresses, lead statuses.

No database, no I/O: everything here is unit-tested in tests/test_normalize.py.
"""

from __future__ import annotations

import re
from typing import Optional

# --------------------------------------------------------------------------- phone

_EXT_RE = re.compile(r"(?:ext\.?|extension|x|#)\s*\d+\s*$", re.IGNORECASE)
_MIN_DIGITS = 7
_MAX_DIGITS = 15


def normalize_phone(value: Optional[str]) -> Optional[str]:
    """E.164-ish form, or None when the input cannot be read as a phone number.

    South African numbers (0821234567, 082 123 4567, (082) 123-4567, 27821234567,
    +27 82 123 4567, 0027821234567, +270821234567) all become +27821234567. Other
    international numbers keep their country code ("+44 7911 123456" -> "+447911123456").
    Spaces, dashes, dots and brackets are removed; a trailing extension is dropped.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    raw = _EXT_RE.sub("", raw).strip()
    plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if not plus and digits.startswith("00"):  # international call prefix
        plus, digits = True, digits[2:]
    if not (_MIN_DIGITS <= len(digits) <= _MAX_DIGITS + 1):
        return None

    if plus:
        if digits.startswith("27"):
            national = digits[2:]
            if national.startswith("0"):  # +27 (0)82 ... written with the trunk zero
                national = national[1:]
            return f"+27{national}" if _MIN_DIGITS - 2 <= len(national) <= 10 else None
        return f"+{digits}" if len(digits) <= _MAX_DIGITS else None

    if digits.startswith("27") and len(digits) == 11:
        return f"+{digits}"
    if digits.startswith("0"):
        return f"+27{digits[1:]}" if len(digits) == 10 else None
    if len(digits) == 9:  # SA number typed without the leading zero
        return f"+27{digits}"
    return f"+{digits}" if len(digits) <= _MAX_DIGITS else None


# --------------------------------------------------------------------------- e-mail

def normalize_email(value: Optional[str]) -> Optional[str]:
    """Lower-cased, trimmed e-mail; None when blank."""
    if value is None:
        return None
    cleaned = str(value).strip().lower()
    return cleaned or None


# --------------------------------------------------------------------------- lead status

# The status vocabulary the sales service writes (services/sales/lead_stages.py:
# LEAD_PHASE_STATUSES + CONVERTED/WON/LOST, plus the legacy PROPOSAL/NEGOTIATION values the
# old UI still sends). The `leads` table is shared, values are stored UPPERCASE.
LEAD_STATUSES = frozenset(
    {"NEW", "CONTACTED", "QUALIFIED", "PROPOSAL", "NEGOTIATION", "DISQUALIFIED", "CONVERTED", "WON", "LOST"}
)
OPEN_LEAD_STATUSES = ("NEW", "CONTACTED", "QUALIFIED")
CONVERTED_LEAD_STATUSES = ("CONVERTED", "WON")
CLOSED_LEAD_STATUSES = ("LOST", "DISQUALIFIED")


def status_key(value: Optional[str]) -> str:
    """Case/whitespace-insensitive comparison key ("" for None). Never raises."""
    return (value or "").strip().upper()


def normalize_status(value: Optional[str], allowed=LEAD_STATUSES) -> Optional[str]:
    """Upper-case + trim a status and check it against `allowed`. None stays None."""
    if value is None:
        return None
    key = status_key(value)
    if key not in allowed:
        raise ValueError(f"status must be one of {sorted(allowed)}")
    return key
