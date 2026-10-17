"""Strip secrets, tokens and customer PII from text before it is stored as a ticket.

Tickets are visible to many staff and are indexed into the tenant knowledge base, so anything an
exception message, e-mail subject or event payload carries must pass through here first. The rules
are deliberately aggressive: a ticket that says "[redacted-email]" is a nuisance, a ticket that
holds a bearer token is an incident.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S)
_BEARER = re.compile(r"(?i)\b(bearer|basic|token)\s+[A-Za-z0-9._~+/=-]{8,}")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*")
_KEY_PREFIX = re.compile(r"\b(?:sk|pk|rk|ak|xox[abprs]|ghp|gho|ghs|github_pat|AKIA|AIza|ya29|whsec|shpat)[-_A-Za-z0-9]{12,}")
_ASSIGNED = re.compile(
    r"(?i)\b([\w.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|authorization|auth|credential|private[_-]?key|"
    r"signature|session|cookie|otp|pin)[\w.-]*)(\s*[:=]\s*|\s+is\s+)(?!\[redacted-)(\"[^\"]*\"|'[^']*'|[^\s,;&}\]]+)")
_URL_CREDS = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@")
_URL_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:[\w-]*(?:token|key|secret|signature|sig|password|code|auth)[\w-]*)=)[^&\s#]+")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b")
_SA_ID = re.compile(r"\b\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{4}[01]\d{2}\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PHONE = re.compile(r"(?<![\w.])(?:\+|00)?\d{1,3}[\s-]?\(?\d{2,3}\)?[\s-]?\d{3}[\s-]?\d{3,4}\b|\b0\d{9}\b")
_ACCOUNT = re.compile(r"(?i)\b(?:acc(?:ount)?|iban)(?:\s*(?:no|number|#))?\s*[:#]?\s*[A-Z]{0,2}\d{8,}\b")
_LONG_BLOB = re.compile(r"\b[A-Za-z0-9+/_-]{40,}={0,2}")
_HEX_SECRET = re.compile(r"\b[a-fA-F0-9]{32,}\b")

_SECRET_KEY_NAMES = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|credential|private[_-]?key|cookie|signature|otp|session)")
_PII_KEY_NAMES = re.compile(r"(?i)^(email|e_mail|phone|msisdn|cell|mobile|id_number|national_id|passport|iban|account_number|card|pan|cvv|address|physical_address|first_name|last_name|full_name|name)$")

MAX_TEXT = 2000


def redact_text(value: Any, limit: int = MAX_TEXT) -> str:
    """Return `value` as text with secrets and personal identifiers replaced by [redacted-...] markers."""
    if value is None:
        return ""
    text = str(value)
    text = _PRIVATE_KEY.sub("[redacted-secret]", text)
    text = _URL_CREDS.sub(lambda m: m.group(1) + "[redacted-credentials]@", text)
    text = _URL_QUERY_SECRET.sub(lambda m: m.group(1) + "[redacted-secret]", text)
    text = _JWT.sub("[redacted-secret]", text)
    text = _BEARER.sub(lambda m: f"{m.group(1)} [redacted-secret]", text)
    text = _KEY_PREFIX.sub("[redacted-secret]", text)
    text = _ASSIGNED.sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted-secret]", text)
    text = _EMAIL.sub("[redacted-email]", text)
    text = _ACCOUNT.sub("[redacted-account]", text)
    text = _SA_ID.sub("[redacted-id]", text)
    text = _CARD.sub(lambda m: "[redacted-number]" if len(re.sub(r"\D", "", m.group(0))) >= 13 else m.group(0), text)
    text = _PHONE.sub("[redacted-phone]", text)
    text = _HEX_SECRET.sub("[redacted-secret]", text)
    text = _LONG_BLOB.sub("[redacted-secret]", text)
    text = text.replace("\x00", "")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def redact_data(value: Any, *, depth: int = 0, keep_pii_keys: bool = False) -> Any:
    """Recursively redact a JSON-like structure. Values under secret-looking keys are dropped outright;
    values under personal-detail keys (email, phone, name...) are dropped unless `keep_pii_keys`."""
    if depth > 6:
        return "[truncated]"
    if isinstance(value, Mapping):
        out = {}
        for key, item in list(value.items())[:60]:
            k = str(key)
            if _SECRET_KEY_NAMES.search(k):
                out[k] = "[redacted-secret]"
            elif not keep_pii_keys and _PII_KEY_NAMES.match(k):
                out[k] = "[redacted-pii]"
            else:
                out[k] = redact_data(item, depth=depth + 1, keep_pii_keys=keep_pii_keys)
        return out
    if isinstance(value, (list, tuple, set)):
        return [redact_data(v, depth=depth + 1, keep_pii_keys=keep_pii_keys) for v in list(value)[:40]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_text(value, 500)
