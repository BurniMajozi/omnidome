"""Server-side number normalisation (E.164) and dial policy. Pure: no I/O.

Default country is South Africa (+27). Input forms accepted:
  +27821234567, 0027821234567, 27821234567 (11 digits), 0821234567 (national, leading 0)
Everything else (letters, short codes, extensions, '*', '#') is refused. International destinations are
refused unless an admin put their E.164 prefix (e.g. "+263") in the tenant allow-list.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence

DEFAULT_COUNTRY = "27"
_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")
_PREFIX = re.compile(r"^\+[1-9][0-9]{0,9}$")

# Premium-rate / shared-cost / satellite / international-premium ranges that are never dialled,
# even when the country is allow-listed. Tenants can only ADD to this list.
BUILTIN_BLOCKED_PREFIXES: Sequence[str] = (
    "+27900", "+27899", "+27860", "+27861", "+27862", "+2787",   # ZA premium / shared-cost
    "+881", "+882", "+883", "+870", "+871", "+872", "+873", "+874",   # satellite / intl networks
    "+979", "+800",                                              # international premium / UIFN
    "+1900", "+1976",                                            # NANP premium
    "+449", "+44870", "+44871", "+44872", "+44873",              # UK premium / non-geographic
)


class NumberError(ValueError):
    """The input is not a dialable number."""


class DialDenied(PermissionError):
    """The number is valid but policy forbids dialling it. `.reason` is a short machine-ish string."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def normalize_e164(raw: str, default_country: str = DEFAULT_COUNTRY) -> str:
    if not isinstance(raw, str):
        raise NumberError("number must be text")
    s = re.sub(r"[ \t\-.()]", "", raw.strip())
    if not s or len(s) > 24:
        raise NumberError("number is empty or too long")
    plus = s.startswith("+")
    body = s[1:] if plus else s
    if not body.isascii() or not body.isdigit():
        raise NumberError("only digits are allowed (no letters, *, # or extensions)")
    if plus:
        digits = body
    elif body.startswith("00"):
        digits = body[2:]
    elif body.startswith("0"):
        digits = default_country + body[1:]
    elif body.startswith(default_country) and len(body) == len(default_country) + 9:
        digits = body
    else:
        raise NumberError("ambiguous number: use +country code or the national 0 format")
    e164 = "+" + digits
    if not _E164.fullmatch(e164):
        raise NumberError("not a valid E.164 number (8-15 digits, no short codes)")
    if digits.startswith(default_country):
        national = digits[len(default_country):]
        if len(national) != 9 or national.startswith("0"):
            raise NumberError("invalid South African number")
    return e164


def validate_prefixes(prefixes: Iterable[str]) -> List[str]:
    out: List[str] = []
    for p in prefixes:
        p = (p or "").strip()
        if not _PREFIX.fullmatch(p):
            raise ValueError(f"invalid prefix {p!r}: use E.164 prefixes such as +27 or +263")
        if p not in out:
            out.append(p)
    return out


def check_dial_policy(e164: str, allowed_prefixes: Iterable[str], blocked_prefixes: Iterable[str] = ()) -> None:
    """Raise DialDenied unless `e164` may be dialled. Blocklist wins over the allow-list."""
    if not _E164.fullmatch(e164):
        raise DialDenied("invalid_number")
    for p in (*BUILTIN_BLOCKED_PREFIXES, *blocked_prefixes):
        if e164.startswith(p):
            raise DialDenied("blocked_prefix")
    allowed = list(allowed_prefixes)
    if not allowed or not any(e164.startswith(p) for p in allowed):
        raise DialDenied("destination_not_allowed")


def did_variants(e164: str, default_country: str = DEFAULT_COUNTRY) -> List[str]:
    """Digit-only forms a provider may present in the INVITE request-URI for a DID."""
    digits = e164.lstrip("+")
    out = [digits, "+" + digits]
    if digits.startswith(default_country):
        out.append("0" + digits[len(default_country):])
    return out
