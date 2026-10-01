"""Pure policy helpers for the call-center service (no DB, no network): easy to unit test.

* consent / retention for call recording and live transcription
* recording reference validation (https URL or object key; never javascript: etc.)
* websocket ownership + connection keys
* CDR CSV parsing/validation
"""

from __future__ import annotations

import csv
import io
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from services.common.url_safety import UnsafeUrl, validate_public_url

CONSENT_VALUES = ("unknown", "given", "declined", "not_required")
RESOLVED_OUTCOMES = ("RESOLVED", "COMPLETED")


# ── consent / retention ────────────────────────────────────────────────────

def default_consent_mode() -> str:
    """CALL_RECORDING_DEFAULT_CONSENT=announced means every call opens with a recording announcement,
    so an undecided ("unknown") session may be streamed/recorded. A declined session never may."""
    return os.getenv("CALL_RECORDING_DEFAULT_CONSENT", "").strip().lower()


def consent_allows_recording(consent: Optional[str]) -> bool:
    consent = (consent or "unknown").lower()
    if consent in ("given", "not_required"):
        return True
    if consent == "unknown" and default_consent_mode() == "announced":
        return True
    return False  # declined, or unknown without an announcement policy


def retention_days() -> int:
    try:
        return max(1, int(os.getenv("CALL_RECORDING_RETENTION_DAYS", "90")))
    except ValueError:
        return 90


def retention_until(start: Optional[datetime] = None) -> datetime:
    base = start or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base + timedelta(days=retention_days())


# ── recording reference ────────────────────────────────────────────────────

_OBJECT_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,400}$")


def validate_recording_ref(value: Optional[str], *, resolver=None) -> Optional[str]:
    """Return a safe https URL (public hosts only) or an object key. Raises ValueError otherwise.

    "javascript:", "data:", "file:", private/loopback hosts and keys with path traversal are refused."""
    if value is None or not value.strip():
        return None
    raw = value.strip()
    if "://" in raw or ":" in raw:
        allow_http = os.getenv("CALL_RECORDING_ALLOW_HTTP", "").strip().lower() == "true"
        try:
            return validate_public_url(raw, resolver=resolver, allow_http=allow_http)
        except UnsafeUrl as exc:
            raise ValueError(f"recording_url rejected: {exc}")
    if not _OBJECT_KEY.match(raw) or ".." in raw.split("/") or "//" in raw:
        raise ValueError("recording_url must be an https URL or a plain object key")
    return raw


# ── websocket ──────────────────────────────────────────────────────────────

def connection_key(tenant_id, session_id) -> Tuple[str, str]:
    """Whisper connections are keyed by (tenant, session): a session id from another tenant can never
    share a registry slot."""
    return str(tenant_id), str(session_id)


def whisper_authorize(*, tenant_id, user_id, is_admin: bool, session_tenant_id, session_agent_id,
                      agent_user_id=None) -> bool:
    """May this verified identity attach to this call session?

    The session must belong to the caller's tenant. Admin tier may attach to any session of the tenant;
    otherwise the caller must be the session's agent (Agent.user_id == caller, or agent id == user id)."""
    if session_tenant_id is None or str(session_tenant_id) != str(tenant_id):
        return False
    if is_admin:
        return True
    if agent_user_id is not None and str(agent_user_id) == str(user_id):
        return True
    return session_agent_id is not None and str(session_agent_id) == str(user_id)


# ── CDR import ─────────────────────────────────────────────────────────────

CDR_COLUMNS = ("external_call_id", "agent_extension", "direction", "start_time", "end_time",
               "duration_seconds", "outcome", "customer_id")
CDR_REQUIRED = ("external_call_id", "agent_extension", "start_time")
MAX_ROWS = 50000


def max_import_bytes() -> int:
    try:
        return int(float(os.getenv("CALL_IMPORT_MAX_MB", "10")) * 1024 * 1024)
    except ValueError:
        return 10 * 1024 * 1024


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_cdr_csv(text: str, agents_by_ext: Dict[str, Any], *, max_rows: int = MAX_ROWS) -> Dict[str, Any]:
    """Validate a CDR CSV. Header row required with at least CDR_REQUIRED columns.

    Returns {"rows": [dict...], "errors": [{"row": n, "error": str}], "anomalies": int, "total": int,
             "header_error": Optional[str]}. Rows whose duration disagrees with end-start by more than 5s
    are imported with the timestamp-derived duration and counted as anomalies. Duplicate ids inside the
    file are rejected (the DB unique index handles duplicates against existing data)."""
    out: Dict[str, Any] = {"rows": [], "errors": [], "anomalies": 0, "total": 0, "header_error": None}
    reader = csv.DictReader(io.StringIO(text))
    fields = [f.strip().lower() for f in (reader.fieldnames or [])]
    missing = [c for c in CDR_REQUIRED if c not in fields]
    if missing:
        out["header_error"] = "missing required column(s): " + ", ".join(missing)
        return out
    reader.fieldnames = fields
    seen: set = set()
    for n, raw in enumerate(reader, start=2):
        out["total"] += 1
        if out["total"] > max_rows:
            out["header_error"] = f"too many rows (limit {max_rows})"
            out["rows"], out["total"] = [], max_rows
            return out
        row = {k: (v or "").strip() for k, v in raw.items() if k}
        try:
            ext_id = row["external_call_id"]
            if not ext_id or len(ext_id) > 100:
                raise ValueError("external_call_id is required (max 100 chars)")
            if ext_id in seen:
                raise ValueError("duplicate external_call_id in file")
            agent = agents_by_ext.get(row["agent_extension"])
            if agent is None:
                raise ValueError("unknown agent_extension for this tenant")
            start = _parse_dt(row["start_time"])
            end = _parse_dt(row["end_time"]) if row.get("end_time") else None
            if end is not None and end < start:
                raise ValueError("end_time is before start_time")
            direction = (row.get("direction") or "INBOUND").upper()
            if direction not in ("INBOUND", "OUTBOUND"):
                raise ValueError("direction must be INBOUND or OUTBOUND")
            duration = 0
            if row.get("duration_seconds"):
                duration = int(row["duration_seconds"])
                if duration < 0:
                    raise ValueError("duration_seconds must be >= 0")
            if end is not None:
                derived = int((end - start).total_seconds())
                if row.get("duration_seconds") and abs(derived - duration) > 5:
                    out["anomalies"] += 1
                duration = derived
            customer = None
            if row.get("customer_id"):
                customer = uuid.UUID(row["customer_id"])
            outcome = (row.get("outcome") or "").upper() or None
            if outcome and len(outcome) > 50:
                raise ValueError("outcome too long")
        except (ValueError, KeyError) as exc:
            out["errors"].append({"row": n, "error": str(exc)[:200]})
            continue
        seen.add(ext_id)
        out["rows"].append({"external_call_id": ext_id, "agent_id": agent, "direction": direction,
                            "start_time": start, "end_time": end, "duration_seconds": duration,
                            "outcome": outcome, "customer_id": customer})
    return out


def health_label(rate: Optional[float]) -> str:
    if rate is None:
        return "NO_DATA"
    return "OPTIMAL" if rate >= 80 else "NEEDS_ATTENTION" if rate >= 50 else "CRITICAL"
