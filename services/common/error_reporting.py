"""Service-side error hook: uncaught exceptions and failed background work become support tickets.

One call site per kind of failure, all funnelling into the shared event bus:

    request handlers     services/common/middleware.py     500 handler        -> report_exception()
    background tasks     services/common/background_tasks.py  task crash      -> report_exception()
    event consumers      services/common/event_bus.py      dead delivery      -> report_job_failure()

The report is published as `system.error.raised` / `system.job.failed`; the support service's ticket
consumer turns it into ONE ticket per fingerprint (see services/support/ticket_rules.py) and counts
repeats. Nothing here may raise, block the request, or leak secrets: the message is redacted, the
traceback is reduced to `file:function` frames (no locals, no source lines), and the request path is
the route template, never the raw URL.

Fingerprint = sha1(service | exception type | innermost in-repo frame `file:function`).
Rate limit = one published report per fingerprint per ERROR_REPORT_WINDOW_SECONDS (suppressed repeats are
counted and carried on the next report) plus ERROR_REPORT_MAX_PER_MINUTE across the process.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
import traceback
import uuid
from typing import Any, Optional

from services.common.redaction import redact_text

logger = logging.getLogger("omnidome.error_reporting")

EVENT_ERROR = "system.error.raised"
EVENT_JOB_FAILED = "system.job.failed"

# Exceptions that are control flow or client behaviour, not defects.
IGNORED_EXCEPTIONS = frozenset({
    "CancelledError", "GeneratorExit", "KeyboardInterrupt", "SystemExit", "ClientDisconnect",
    "ConnectionResetError", "BrokenPipeError", "WebSocketDisconnect", "TimeoutError_Client",
})

_FRAME_RE = re.compile(r"[\\/](services[\\/].+)$")


def _enabled() -> bool:
    return os.getenv("ERROR_TICKETS_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def _window() -> float:
    try:
        return max(5.0, float(os.getenv("ERROR_REPORT_WINDOW_SECONDS", "300")))
    except ValueError:
        return 300.0


def _max_per_minute() -> int:
    try:
        return max(1, int(os.getenv("ERROR_REPORT_MAX_PER_MINUTE", "20")))
    except ValueError:
        return 20


# ── Pure helpers (unit-tested) ──────────────────────────────────────────────

def _repo_frames(exc: BaseException) -> list[tuple[str, str, int]]:
    """(relative file, function, line) of in-repo frames, outermost first."""
    frames = []
    for fs in traceback.extract_tb(exc.__traceback__):
        m = _FRAME_RE.search(fs.filename or "")
        if m:
            frames.append((m.group(1).replace("\\", "/"), fs.name, fs.lineno or 0))
    return frames


def service_of(exc: BaseException, default: str = "unknown") -> str:
    frames = _repo_frames(exc)
    for path, _fn, _ln in reversed(frames):
        parts = path.split("/")
        if len(parts) > 1 and parts[1] != "common":
            return parts[1]
    if frames:
        return frames[-1][0].split("/")[1] if "/" in frames[-1][0] else default
    return os.getenv("SERVICE_NAME", default)


def location_of(exc: BaseException) -> str:
    frames = _repo_frames(exc)
    if not frames:
        return "unknown"
    path, fn, _ln = frames[-1]
    return f"{path}:{fn}"


def fingerprint(service: str, exc_type: str, location: str) -> str:
    return hashlib.sha1(f"{service}|{exc_type}|{location}".encode()).hexdigest()[:16]


def unwrap(exc: BaseException) -> BaseException:
    """BaseHTTPMiddleware (anyio) wraps the endpoint's error in an ExceptionGroup; report the real one."""
    for _ in range(5):
        if isinstance(exc, BaseExceptionGroup) and exc.exceptions:
            exc = exc.exceptions[0]
        else:
            break
    return exc


def is_ignored(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in IGNORED_EXCEPTIONS:
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and status < 500


def build_report(exc: BaseException, *, service: Optional[str] = None, kind: str = "request",
                 method: Optional[str] = None, route: Optional[str] = None, job: Optional[str] = None) -> dict:
    svc = service or service_of(exc)
    exc_type = type(exc).__name__
    location = location_of(exc)
    frames = _repo_frames(exc)[-6:]
    return {
        "service": svc,
        "kind": kind,
        "exception_type": exc_type,
        "message": redact_text(str(exc), 300),
        "location": location,
        "fingerprint": fingerprint(svc, exc_type, location),
        "frames": [f"{p}:{ln} in {fn}" for p, fn, ln in frames],
        "method": method,
        "route": redact_text(route, 200) if route else None,
        "job": redact_text(job, 120) if job else None,
    }


class ErrorLimiter:
    """Per-fingerprint window + per-process global cap. `admit` returns (publish?, suppressed_count)."""

    def __init__(self) -> None:
        self._seen: dict[str, tuple[float, int]] = {}
        self._minute_start = 0.0
        self._minute_count = 0

    def admit(self, fp: str, now: Optional[float] = None) -> tuple[bool, int]:
        now = time.monotonic() if now is None else now
        if now - self._minute_start >= 60:
            self._minute_start, self._minute_count = now, 0
        last, suppressed = self._seen.get(fp, (None, 0))
        if last is not None and now - last < _window():
            self._seen[fp] = (last, suppressed + 1)
            return False, 0
        if self._minute_count >= _max_per_minute():
            self._seen[fp] = (last if last is not None else now, suppressed + 1)
            return False, 0
        self._minute_count += 1
        self._seen[fp] = (now, 0)
        if len(self._seen) > 2000:
            cutoff = now - _window()
            self._seen = {k: v for k, v in self._seen.items() if v[0] >= cutoff}
        return True, suppressed


_limiter = ErrorLimiter()


def _target_tenant(request_tenant: Optional[Any]) -> Optional[str]:
    for candidate in (os.getenv("PLATFORM_OPS_TENANT_ID"), request_tenant, os.getenv("DEFAULT_TENANT_ID")):
        if candidate:
            try:
                return str(uuid.UUID(str(candidate)))
            except ValueError:
                continue
    return None


# ── Publishing ──────────────────────────────────────────────────────────────

async def _publish(report: dict, tenant: str, affected_tenant: Optional[str], suppressed: int) -> None:
    from services.common.db import session_scope
    from services.common.event_bus import publish

    event_type = EVENT_JOB_FAILED if report["kind"] != "request" else EVENT_ERROR
    payload = {**report, "suppressed": suppressed, "affected_tenant": affected_tenant}
    bucket = int(time.time() // _window())
    async with session_scope() as session:
        await publish(session, tenant, event_type, payload, source=f"svc.{report['service']}"[:60],
                      subject=("error_fingerprint", report["fingerprint"]),
                      idempotency_key=f"err:{report['fingerprint']}:{bucket}")


async def _safe_publish(report: dict, tenant: str, affected: Optional[str], suppressed: int) -> None:
    try:
        await _publish(report, tenant, affected, suppressed)
    except Exception as exc:  # noqa: BLE001 - the hook must never make things worse
        logger.warning("could not publish error report %s: %s", report.get("fingerprint"), type(exc).__name__)


def report_exception(exc: BaseException, *, service: Optional[str] = None, kind: str = "request",
                     method: Optional[str] = None, route: Optional[str] = None, job: Optional[str] = None,
                     tenant_id: Optional[Any] = None) -> Optional[dict]:
    """Queue a deduplicated, rate-limited ticket report for `exc`. Never raises; returns the report or None."""
    try:
        exc = unwrap(exc)
        if not _enabled() or is_ignored(exc):
            return None
        report = build_report(exc, service=service, kind=kind, method=method, route=route, job=job)
        publish_it, suppressed = _limiter.admit(report["fingerprint"])
        if not publish_it:
            return None
        tenant = _target_tenant(tenant_id)
        if tenant is None:
            return None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        from services.common.background_tasks import schedule_background_quiet
        schedule_background_quiet(_safe_publish(report, tenant, str(tenant_id) if tenant_id else None, suppressed), loop)
        return report
    except Exception:  # noqa: BLE001
        return None


def report_job_failure(*, service: str, job: str, error: str, tenant_id: Optional[Any] = None,
                       location: str = "") -> None:
    """For failures that are not Python exceptions in our frames (e.g. a dead event delivery)."""
    try:
        if not _enabled():
            return
        exc_type = "JobFailed"
        fp = fingerprint(service, exc_type, f"{job}:{location}")
        publish_it, suppressed = _limiter.admit(fp)
        tenant = _target_tenant(tenant_id)
        if not publish_it or tenant is None:
            return
        report = {"service": service, "kind": "job", "exception_type": exc_type, "message": redact_text(error, 300),
                  "location": f"{job}:{location}".strip(":"), "fingerprint": fp, "frames": [], "method": None,
                  "route": None, "job": redact_text(job, 120)}
        loop = asyncio.get_running_loop()
        from services.common.background_tasks import schedule_background_quiet
        schedule_background_quiet(_safe_publish(report, tenant, str(tenant_id) if tenant_id else None, suppressed), loop)
    except Exception:  # noqa: BLE001
        return
