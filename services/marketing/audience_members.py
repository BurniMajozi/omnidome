"""Resolve an audience (marketing_audience_segments.rules) into contactable members.

Audience shapes today (SPEC-marketing-audiences, `POST /segments`):
  type=businesses  rules.businesses = [{name, email, phone, website, ...}]   -> emails / phones
  type=custom      rules.contacts | rules.members = [{email, phone} | "email"]; rules.emails = ["..."]
  type=homes       rules.areas only (no individuals, by design)               -> nobody contactable

Campaign sends use this so "select an audience on the campaign" really addresses its members.
Emails are lower-cased and de-duplicated here; syntax validation, suppression and caps are applied
later by the normal send path (security.clean_recipients + suppression list).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

_EMAILISH = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_CLEAN = re.compile(r"[^\d+]")


def _norm_email(v: Any) -> str:
    s = str(v or "").strip().lower()
    return s if _EMAILISH.match(s) else ""


def _norm_phone(v: Any) -> str:
    s = _PHONE_CLEAN.sub("", str(v or ""))
    return s if len(re.sub(r"\D", "", s)) >= 7 else ""


def resolve_members(rules: Dict[str, Any]) -> Dict[str, Any]:
    rules = rules or {}
    kind = rules.get("type", "custom")
    people: List[Any] = []
    note = None
    if kind == "homes":
        return {"emails": [], "phones": [], "skipped": 0,
                "note": "This audience lists areas (homes passed), not people, so there is nobody to message. Pick a businesses or contact-list audience."}
    if kind == "businesses":
        people = list(rules.get("businesses") or [])
    else:
        people = list(rules.get("contacts") or rules.get("members") or [])
        people += [{"email": e} for e in (rules.get("emails") or [])]
    emails: List[str] = []
    phones: List[str] = []
    seen_e, seen_p = set(), set()
    skipped = 0
    for p in people:
        if isinstance(p, str):
            p = {"email": p}
        if not isinstance(p, dict):
            skipped += 1
            continue
        e, ph = _norm_email(p.get("email")), _norm_phone(p.get("phone") or p.get("mobile"))
        if not e and not ph:
            skipped += 1
            continue
        if e and e not in seen_e:
            seen_e.add(e)
            emails.append(e)
        if ph and ph not in seen_p:
            seen_p.add(ph)
            phones.append(ph)
    if not emails and not phones:
        note = "No member of this audience has an email address or phone number."
    elif not emails:
        note = "No member of this audience has an email address (phone numbers only)."
    return {"emails": emails, "phones": phones, "skipped": skipped, "note": note}
