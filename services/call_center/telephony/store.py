"""DB access for the telephony bridge/service. Every statement filters by tenant_id explicitly."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, List, Optional

from sqlalchemy import func, select

from services.call_center import policy
from services.call_center.database import (
    Agent, CallQueue, CallSession, TelephonyAudit, TelephonySettings, WebrtcEndpointRow, _get_session_factory,
)
from services.call_center.telephony.bridge import RingAgent, TenantRoute

logger = logging.getLogger("call_center.telephony.store")

DEFAULT_ALLOWED_PREFIXES = ["+27"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def route_from_settings(row: TelephonySettings) -> TenantRoute:
    return TenantRoute(
        tenant_id=row.tenant_id, queue_id=row.inbound_queue_id,
        max_concurrent_calls=row.max_concurrent_calls or 5, max_call_seconds=row.max_call_seconds or 3600,
        recording=bool(row.recording_enabled and row.recording_announcement_confirmed),
    )


class DbStore:
    """Bridge persistence. `on_recording_ready(tenant_id, session_id)` is the Deepgram transcription hook."""

    def __init__(self, session_factory=None,
                 on_recording_ready: Optional[Callable[[uuid.UUID, uuid.UUID], Awaitable[None]]] = None):
        self._factory = session_factory or _get_session_factory()
        self._on_recording_ready = on_recording_ready

    # ── routing ──────────────────────────────────────────────────────
    async def route_for_did(self, did: str) -> Optional[TenantRoute]:
        async with self._factory() as db:
            rows = (await db.execute(select(TelephonySettings).where(TelephonySettings.enabled.is_(True)))).scalars().all()
        owners = [r for r in rows if did in (r.dids or [])]
        if len(owners) != 1:   # unknown DID, or (misconfigured) claimed by several tenants: ignore
            if len(owners) > 1:
                logger.error("a DID is claimed by %d tenants; ignoring inbound calls to it", len(owners))
            return None
        return route_from_settings(owners[0])

    async def ring_agents(self, tenant_id, queue_id) -> List[RingAgent]:
        async with self._factory() as db:
            skills: List[str] = []
            if queue_id:
                q = (await db.execute(select(CallQueue).where(
                    CallQueue.id == queue_id, CallQueue.tenant_id == tenant_id))).scalar_one_or_none()
                skills = list((q.required_skills or []) if q else [])
            agents = (await db.execute(select(Agent).where(
                Agent.tenant_id == tenant_id, Agent.status == "IDLE").order_by(Agent.created_at))).scalars().all()
            eps = (await db.execute(select(WebrtcEndpointRow).where(
                WebrtcEndpointRow.tenant_id == tenant_id).order_by(WebrtcEndpointRow.created_at.desc()))).scalars().all()
        latest = {}
        now = _now()
        for e in eps:
            if _aware(e.expires_at) > now and e.agent_id not in latest:
                latest[e.agent_id] = e.endpoint_id
        out = []
        for a in agents:
            if a.id in latest and all(s in (a.skills or []) for s in skills):
                out.append(RingAgent(a.id, latest[a.id]))
        return out

    # ── sessions ─────────────────────────────────────────────────────
    async def create_session(self, tenant_id, agent_id, direction, queue_id, external_id, consent) -> uuid.UUID:
        now = _now()
        async with self._factory() as db:
            s = CallSession(tenant_id=tenant_id, agent_id=agent_id, direction=direction, queue_id=queue_id,
                            start_time=now, external_call_id=external_id, provider="asterisk",
                            recording_consent=consent, retention_until=policy.retention_until(now),
                            consent_recorded_at=now if consent != "unknown" else None)
            db.add(s)
            await db.commit()
            return s.id

    async def _session(self, db, tenant_id, session_id) -> Optional[CallSession]:
        return (await db.execute(select(CallSession).where(
            CallSession.id == session_id, CallSession.tenant_id == tenant_id))).scalar_one_or_none()

    async def set_session_agent(self, tenant_id, session_id, agent_id) -> None:
        async with self._factory() as db:
            s = await self._session(db, tenant_id, session_id)
            if s:
                s.agent_id = agent_id
                await db.commit()

    async def set_consent(self, tenant_id, session_id, consent) -> None:
        async with self._factory() as db:
            s = await self._session(db, tenant_id, session_id)
            if s:
                s.recording_consent = consent
                s.consent_recorded_at = _now()
                await db.commit()

    async def finish_session(self, tenant_id, session_id, outcome, duration) -> None:
        async with self._factory() as db:
            s = await self._session(db, tenant_id, session_id)
            if s and s.end_time is None:
                s.end_time = _now()
                s.duration_seconds = duration
                s.outcome = s.outcome or outcome
                await db.commit()

    async def set_agent_status(self, tenant_id, agent_id, status, only_if=None) -> None:
        if not agent_id:
            return
        async with self._factory() as db:
            a = (await db.execute(select(Agent).where(Agent.id == agent_id, Agent.tenant_id == tenant_id))).scalar_one_or_none()
            if a and (only_if is None or a.status == only_if):
                a.status = status
                await db.commit()

    async def recording_done(self, tenant_id, session_id, name: Optional[str]) -> None:
        """Store recording METADATA (an object key under the recordings volume), never audio."""
        async with self._factory() as db:
            s = await self._session(db, tenant_id, session_id)
            if s is None:
                return
            if name and policy.consent_allows_recording(s.recording_consent):
                s.recording_url = policy.validate_recording_ref(f"asterisk/{name}.wav")
            else:
                s.recording_url = None
            await db.commit()
        if name and self._on_recording_ready:
            try:
                await self._on_recording_ready(tenant_id, session_id)
            except Exception:  # noqa: BLE001
                logger.exception("recording-ready hook failed")

    async def close_orphans(self) -> int:
        async with self._factory() as db:
            rows = (await db.execute(select(CallSession).where(
                CallSession.provider == "asterisk", CallSession.end_time.is_(None)))).scalars().all()
            for s in rows:
                s.end_time = _now()
                s.outcome = s.outcome or "ABANDONED"
            await db.commit()
            return len(rows)

    # ── audit / limits ───────────────────────────────────────────────
    async def audit(self, tenant_id, kind, result, *, user_id=None, agent_id=None, to_number=None,
                    session_id=None) -> uuid.UUID:
        async with self._factory() as db:
            row = TelephonyAudit(tenant_id=tenant_id, kind=kind, result=result[:60], user_id=user_id,
                                 agent_id=agent_id, to_number=to_number, session_id=session_id, created_at=_now())
            db.add(row)
            await db.commit()
            return row.id

    async def update_audit(self, tenant_id, audit_id, result, session_id=None) -> None:
        async with self._factory() as db:
            row = (await db.execute(select(TelephonyAudit).where(
                TelephonyAudit.id == audit_id, TelephonyAudit.tenant_id == tenant_id))).scalar_one_or_none()
            if row:
                row.result = result[:60]
                row.session_id = session_id or row.session_id
                await db.commit()

    async def agent_calls_last_hour(self, tenant_id, agent_id) -> int:
        since = _now() - timedelta(hours=1)
        async with self._factory() as db:
            n = (await db.execute(select(func.count()).select_from(TelephonyAudit).where(
                TelephonyAudit.tenant_id == tenant_id, TelephonyAudit.agent_id == agent_id,
                TelephonyAudit.kind == "originate", TelephonyAudit.created_at >= since,
                TelephonyAudit.result.in_(("accepted", "originated"))))).scalar_one()
        return int(n)
