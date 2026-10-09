import os
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import uuid

import httpx
from fastapi import APIRouter, FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, desc, func, case
from starlette.concurrency import run_in_threadpool

from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
from services.common.auth import get_current_tenant_id, get_current_user_id
from services.common import secretbox
from services.common.db import run_with_db_retry
from services.common.ws_auth import authenticate_ws, ws_roles
from services.call_center import access, policy

from services.call_center.database import (
    Agent, Script, CallSession, CallQueue, WhisperSession, VoiceAgentDeployment, ProviderCredential,
    get_session, init_tables, _get_session_factory,
)
from services.call_center.deepgram_service import (
    transcribe_audio,
    synthesize_speech,
    analyze_audio,
    list_voices,
    DeepgramError,
)
VoiceboxUnavailable = DeepgramError
from services.call_center.telephony.confgen import ConfigError as TrunkConfigError, check_fields as check_trunk_fields  # noqa: E402
from services.call_center.telephony.routes import router as telephony_router  # noqa: E402
from services.call_center.telephony.service import get_runtime as get_telephony_runtime  # noqa: E402


app = FastAPI(title="OmniDome Call Center Service", version="0.3.0")
guard = EntitlementGuard(module_id="call_center")
logger = logging.getLogger("call_center")

configure_production(app)

# Every HTTP route below goes on `router`, which enforces the role tiers (access.py); /health and the
# websocket stay on `app` (the websocket authenticates itself from the signed identity).
router = APIRouter(dependencies=[Depends(access.enforce_route_tier)])


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "call_center"}


# Lifespan replaces the deprecated @app.on_event("startup") (removed in FastAPI >=0.110).
# Mirrors the pattern used in services/iot/main.py.
from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(app: FastAPI):
    guard.ensure_startup()
    # DEV ONLY — VOICE_DEV_SKIP_DB must never be set in a production deployment.
    # If set, call-center tables are never created and the service cannot persist data.
    if os.getenv("VOICE_DEV_SKIP_DB", "").lower() in {"1", "true", "yes", "on"}:
        logger.critical(
            "VOICE_DEV_SKIP_DB enabled; SKIPPING call-center table initialization "
            "(dev-only escape hatch — must not be set in production)"
        )
    else:
        await run_with_db_retry(init_tables, logger=logger)
    telephony_rt = get_telephony_runtime()
    try:
        await telephony_rt.start()
    except Exception:  # noqa: BLE001 - telephony must never stop the rest of the service from booting
        logger.exception("telephony failed to start; continuing without it")
    yield
    await telephony_rt.stop()


app.router.lifespan_context = _lifespan


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _agent_to_dict(agent: Agent) -> dict:
    return {
        "id": str(agent.id), "tenant_id": str(agent.tenant_id),
        "name": agent.name, "extension": agent.extension,
        "status": agent.status, "daily_sales": float(agent.daily_sales),
        "mttr_minutes": float(agent.mttr_minutes), "csat_score": float(agent.csat_score),
        "skills": agent.skills or [], "max_concurrent_calls": agent.max_concurrent_calls,
        "user_id": str(agent.user_id) if agent.user_id else None,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }


def _script_to_dict(script: Script) -> dict:
    return {
        "id": str(script.id), "tenant_id": str(script.tenant_id),
        "title": script.title, "category": script.category,
        "content": script.content, "active": script.active,
        "created_at": script.created_at.isoformat() if script.created_at else None,
        "updated_at": script.updated_at.isoformat() if script.updated_at else None,
    }


def _session_to_dict(session: CallSession) -> dict:
    return {
        "id": str(session.id), "tenant_id": str(session.tenant_id),
        "agent_id": str(session.agent_id),
        "customer_id": str(session.customer_id) if session.customer_id else None,
        "direction": session.direction,
        "queue_id": str(session.queue_id) if session.queue_id else None,
        "start_time": session.start_time.isoformat() if session.start_time else None,
        "end_time": session.end_time.isoformat() if session.end_time else None,
        "duration_seconds": session.duration_seconds,
        "sentiment_score": float(session.sentiment_score) if session.sentiment_score is not None else None,
        # recording download is admin tier: the reference is redacted for everyone else
        "recording_url": session.recording_url if access.request_is_admin.get() else None,
        "has_recording": bool(session.recording_url),
        "recording_consent": session.recording_consent,
        "consent_recorded_at": session.consent_recorded_at.isoformat() if session.consent_recorded_at else None,
        "retention_until": session.retention_until.isoformat() if session.retention_until else None,
        "transcript": session.transcript,
        "live_transcript": session.live_transcript,
        "outcome": session.outcome,
        "notes": session.notes,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


def _queue_to_dict(q: CallQueue) -> dict:
    return {
        "id": str(q.id), "tenant_id": str(q.tenant_id),
        "name": q.name, "direction": q.direction, "category": q.category,
        "routing_strategy": q.routing_strategy, "priority": q.priority,
        "max_wait_seconds": q.max_wait_seconds,
        "required_skills": q.required_skills or [],
        "active_calls": q.active_calls, "queued_calls": q.queued_calls,
        "avg_wait_seconds": q.avg_wait_seconds, "abandoned_count": q.abandoned_count,
        "status": q.status,
    }


def _demo_mode_enabled() -> bool:
    """Sample/seed data is only written when DEMO_MODE is explicitly enabled.

    Defaults to OFF so live tenants are never polluted with invented agents,
    queues, or call transcripts. Set DEMO_MODE=true to seed demo data.
    """
    raw = os.getenv("DEMO_MODE", "false")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


async def _ensure_sample_data(tenant_id: uuid.UUID, db) -> None:
    if not _demo_mode_enabled():
        return
    result = await db.execute(select(Agent).where(Agent.tenant_id == tenant_id).limit(1))
    if result.scalar_one_or_none():
        return
    agent1 = Agent(tenant_id=tenant_id, name="Sipho Nkosi", extension="1001", status="ON_CALL", daily_sales=12400, mttr_minutes=5.2, csat_score=4.8, skills=["sales", "support"])
    agent2 = Agent(tenant_id=tenant_id, name="Jane Doe", extension="1005", status="IDLE", daily_sales=8500, mttr_minutes=4.8, csat_score=4.9, skills=["support", "billing"])
    db.add(agent1)
    db.add(agent2)
    await db.flush()
    # Seed queues
    for qname, qdir, qcat in [("Sales Inbound", "INBOUND", "SALES"), ("Support Inbound", "INBOUND", "SUPPORT"), ("Outbound Campaigns", "OUTBOUND", "SALES")]:
        db.add(CallQueue(tenant_id=tenant_id, name=qname, direction=qdir, category=qcat))
    # Seed scripts
    db.add(Script(tenant_id=tenant_id, title="Sales: Fiber Upgrade", category="Sales", content="Targeting existing customers with a fiber upgrade offer...", active=True))
    db.add(Script(tenant_id=tenant_id, title="Support: Troubleshooting", category="Support", content="Step-by-step guide for troubleshooting connectivity issues...", active=True))
    # Seed sessions
    now = datetime.now(timezone.utc)
    db.add(CallSession(tenant_id=tenant_id, agent_id=agent1.id, direction="INBOUND", start_time=now, end_time=now, duration_seconds=312, sentiment_score=0.85, transcript="Customer inquired about upgrading their fiber package."))
    db.add(CallSession(tenant_id=tenant_id, agent_id=agent2.id, direction="INBOUND", start_time=now, end_time=now, duration_seconds=185, sentiment_score=0.72, transcript="Customer reported intermittent connectivity issues."))
    await db.flush()


# ═══════════════════════════════════════════════════════════════════════════
# AGENTS  (existing + skills)
# ═══════════════════════════════════════════════════════════════════════════

class AgentCreate(BaseModel):
    name: str
    extension: str
    status: str = "IDLE"
    daily_sales: float = 0
    mttr_minutes: float = 0
    csat_score: float = 0
    skills: List[str] = []
    max_concurrent_calls: int = 1
    user_id: Optional[uuid.UUID] = None


@router.get("/agents")
async def list_agents(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
    status: Optional[str] = Query(None),
):
    await _ensure_sample_data(tenant_id, db)
    stmt = select(Agent).where(Agent.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(Agent.status == status)
    result = await db.execute(stmt.order_by(Agent.created_at))
    return [_agent_to_dict(a) for a in result.scalars().all()]


@router.post("/agents", status_code=status.HTTP_201_CREATED)
async def create_agent(
    agent: AgentCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    a = Agent(tenant_id=tenant_id, **agent.dict())
    db.add(a)
    await db.flush()
    await db.refresh(a)
    return _agent_to_dict(a)


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.tenant_id == tenant_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_to_dict(agent)


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: uuid.UUID, body: AgentCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.tenant_id == tenant_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    for field, value in body.dict(exclude_unset=True).items():
        setattr(agent, field, value)
    await db.flush()
    await db.refresh(agent)
    return _agent_to_dict(agent)


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.tenant_id == tenant_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    await db.flush()


# ═══════════════════════════════════════════════════════════════════════════
# SCRIPTS  (existing)
# ═══════════════════════════════════════════════════════════════════════════

class ScriptCreate(BaseModel):
    title: str
    category: str
    content: str
    active: bool = True


@router.get("/scripts")
async def list_scripts(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    await _ensure_sample_data(tenant_id, db)
    result = await db.execute(select(Script).where(Script.tenant_id == tenant_id).order_by(Script.created_at))
    return [_script_to_dict(s) for s in result.scalars().all()]


@router.post("/scripts", status_code=status.HTTP_201_CREATED)
async def create_script(script: ScriptCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    s = Script(tenant_id=tenant_id, **script.dict())
    db.add(s)
    await db.flush()
    await db.refresh(s)
    return _script_to_dict(s)


@router.delete("/scripts/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_script(script_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    result = await db.execute(select(Script).where(Script.id == script_id, Script.tenant_id == tenant_id))
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    await db.delete(script)
    await db.flush()


# ═══════════════════════════════════════════════════════════════════════════
# CALL SESSIONS  (existing + direction, queue_id, live_transcript, outcome)
# ═══════════════════════════════════════════════════════════════════════════

class CallSessionCreate(BaseModel):
    agent_id: uuid.UUID
    customer_id: Optional[uuid.UUID] = None
    direction: str = "INBOUND"
    queue_id: Optional[uuid.UUID] = None
    start_time: datetime
    sentiment_score: Optional[float] = None
    recording_url: Optional[str] = None
    transcript: Optional[str] = None
    recording_consent: str = "unknown"  # unknown | given | declined | not_required


class ConsentUpdate(BaseModel):
    consent: str  # given | declined | not_required | unknown


class CallSessionEnd(BaseModel):
    end_time: datetime
    duration_seconds: int
    outcome: Optional[str] = None
    notes: Optional[str] = None


class LiveTranscriptUpdate(BaseModel):
    transcript: str


@router.get("/sessions")
async def list_sessions(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
    direction: Optional[str] = Query(None),
    agent_id: Optional[uuid.UUID] = Query(None),
):
    await _ensure_sample_data(tenant_id, db)
    stmt = select(CallSession).where(CallSession.tenant_id == tenant_id)
    if direction:
        stmt = stmt.where(CallSession.direction == direction)
    if agent_id:
        stmt = stmt.where(CallSession.agent_id == agent_id)
    result = await db.execute(stmt.order_by(desc(CallSession.start_time)))
    return [_session_to_dict(s) for s in result.scalars().all()]


async def _customer_exists(tenant_id: uuid.UUID, customer_id: uuid.UUID) -> bool:
    """Customers live in CRM: verify through it (404 -> False). Unreachable CRM -> 503 (fail closed);
    CALL_VERIFY_CUSTOMER=false skips the check (development only)."""
    if os.getenv("CALL_VERIFY_CUSTOMER", "true").strip().lower() in {"0", "false", "no", "off"}:
        return True
    crm_url = os.getenv("CRM_SERVICE_URL", "http://crm:8001")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{crm_url}/api/crm/customers/{customer_id}",
                                    headers={"x-tenant-id": str(tenant_id)})
    except Exception:
        raise HTTPException(status_code=503, detail="Cannot verify customer right now")
    if resp.status_code == 404:
        return False
    if resp.status_code == 200:
        return True
    raise HTTPException(status_code=503, detail="Cannot verify customer right now")


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(session: CallSessionCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    if session.recording_consent not in policy.CONSENT_VALUES:
        raise HTTPException(status_code=422, detail=f"recording_consent must be one of {policy.CONSENT_VALUES}")
    # agent / queue / customer must belong to the caller's tenant (404 otherwise)
    if not (await db.execute(select(Agent.id).where(Agent.id == session.agent_id, Agent.tenant_id == tenant_id))).first():
        raise HTTPException(status_code=404, detail="Agent not found")
    if session.queue_id and not (await db.execute(
            select(CallQueue.id).where(CallQueue.id == session.queue_id, CallQueue.tenant_id == tenant_id))).first():
        raise HTTPException(status_code=404, detail="Queue not found")
    if session.customer_id and not await _customer_exists(tenant_id, session.customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")
    data = session.dict()
    try:
        data["recording_url"] = await run_in_threadpool(policy.validate_recording_ref, session.recording_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if data["recording_url"] and not policy.consent_allows_recording(session.recording_consent):
        raise HTTPException(status_code=409, detail="A recording cannot be attached without recording consent")
    s = CallSession(tenant_id=tenant_id, **data)
    s.retention_until = policy.retention_until(session.start_time)
    if session.recording_consent != "unknown":
        s.consent_recorded_at = datetime.now(timezone.utc)
    db.add(s)
    await db.flush()
    await db.refresh(s)
    return _session_to_dict(s)


@router.put("/sessions/{session_id}/consent")
async def set_recording_consent(session_id: uuid.UUID, body: ConsentUpdate,
                                tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    if body.consent not in policy.CONSENT_VALUES:
        raise HTTPException(status_code=422, detail=f"consent must be one of {policy.CONSENT_VALUES}")
    result = await db.execute(select(CallSession).where(CallSession.id == session_id, CallSession.tenant_id == tenant_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")
    session.recording_consent = body.consent
    session.consent_recorded_at = datetime.now(timezone.utc)
    if body.consent == "declined":
        # declined/withdrawn consent: drop what was captured for this session
        session.recording_url = None
        session.live_transcript = None
    await db.flush()
    return {"id": str(session.id), "recording_consent": session.recording_consent,
            "consent_recorded_at": session.consent_recorded_at.isoformat()}


async def purge_expired_recordings(db, now: Optional[datetime] = None, tenant_id: Optional[uuid.UUID] = None) -> int:
    """Retention purge (NOT auto-run): clears recording_url, transcript and live_transcript of sessions whose
    retention_until has passed. Returns the number of sessions purged. Call from an admin job/script."""
    now = now or datetime.now(timezone.utc)
    stmt = select(CallSession).where(CallSession.retention_until.is_not(None), CallSession.retention_until < now)
    if tenant_id is not None:
        stmt = stmt.where(CallSession.tenant_id == tenant_id)
    rows = (await db.execute(stmt)).scalars().all()
    purged = 0
    for r in rows:
        if r.recording_url or r.transcript or r.live_transcript:
            r.recording_url = None
            r.transcript = None
            r.live_transcript = None
            purged += 1
    await db.flush()
    return purged


@router.get("/sessions/{session_id}")
async def get_call_session(session_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    result = await db.execute(select(CallSession).where(CallSession.id == session_id, CallSession.tenant_id == tenant_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")
    return _session_to_dict(session)


@router.put("/sessions/{session_id}/end")
async def end_session(session_id: uuid.UUID, payload: CallSessionEnd, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    result = await db.execute(select(CallSession).where(CallSession.id == session_id, CallSession.tenant_id == tenant_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")
    session.end_time = payload.end_time
    session.duration_seconds = payload.duration_seconds
    session.outcome = payload.outcome
    session.notes = payload.notes
    await db.flush()
    await db.refresh(session)
    return _session_to_dict(session)


@router.put("/sessions/{session_id}/live-transcript")
async def update_live_transcript(
    session_id: uuid.UUID,
    payload: LiveTranscriptUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Update the live transcript for an active call (from Whisper AI)."""
    result = await db.execute(select(CallSession).where(CallSession.id == session_id, CallSession.tenant_id == tenant_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")
    session.live_transcript = payload.transcript
    await db.flush()
    return {"id": str(session.id), "live_transcript": session.live_transcript}


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    result = await db.execute(select(CallSession).where(CallSession.id == session_id, CallSession.tenant_id == tenant_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")
    await db.delete(session)
    await db.flush()


# ═══════════════════════════════════════════════════════════════════════════
# CALL QUEUES  (new)
# ═══════════════════════════════════════════════════════════════════════════

class QueueCreate(BaseModel):
    name: str
    direction: str  # INBOUND, OUTBOUND
    category: str  # SALES, SUPPORT, BILLING, GENERAL
    routing_strategy: str = "ROUND_ROBIN"
    priority: int = 5
    max_wait_seconds: int = 300
    required_skills: List[str] = []


@router.get("/queues")
async def list_queues(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
    direction: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    await _ensure_sample_data(tenant_id, db)
    stmt = select(CallQueue).where(CallQueue.tenant_id == tenant_id)
    if direction:
        stmt = stmt.where(CallQueue.direction == direction)
    if status:
        stmt = stmt.where(CallQueue.status == status)
    result = await db.execute(stmt.order_by(CallQueue.priority))
    return [_queue_to_dict(q) for q in result.scalars().all()]


@router.post("/queues", status_code=status.HTTP_201_CREATED)
async def create_queue(queue: QueueCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    q = CallQueue(tenant_id=tenant_id, **queue.dict())
    db.add(q)
    await db.flush()
    await db.refresh(q)
    return _queue_to_dict(q)


@router.get("/queues/{queue_id}")
async def get_queue(queue_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    result = await db.execute(select(CallQueue).where(CallQueue.id == queue_id, CallQueue.tenant_id == tenant_id))
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="Queue not found")
    return _queue_to_dict(q)


@router.put("/queues/{queue_id}")
async def update_queue(queue_id: uuid.UUID, body: QueueCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    result = await db.execute(select(CallQueue).where(CallQueue.id == queue_id, CallQueue.tenant_id == tenant_id))
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="Queue not found")
    for field, value in body.dict(exclude_unset=True).items():
        setattr(q, field, value)
    await db.flush()
    await db.refresh(q)
    return _queue_to_dict(q)


@router.delete("/queues/{queue_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_queue(queue_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    result = await db.execute(select(CallQueue).where(CallQueue.id == queue_id, CallQueue.tenant_id == tenant_id))
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="Queue not found")
    await db.delete(q)
    await db.flush()


@router.get("/queues/{queue_id}/stats")
async def get_queue_stats(queue_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    """Real-time queue statistics."""
    result = await db.execute(select(CallQueue).where(CallQueue.id == queue_id, CallQueue.tenant_id == tenant_id))
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="Queue not found")
    # Count active calls for this queue
    active_result = await db.execute(
        select(func.count(CallSession.id)).where(
            CallSession.tenant_id == tenant_id,
            CallSession.queue_id == queue_id,
            CallSession.end_time.is_(None),
        )
    )
    active_calls = active_result.scalar() or 0
    # Count completed calls today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    completed_result = await db.execute(
        select(func.count(CallSession.id)).where(
            CallSession.tenant_id == tenant_id,
            CallSession.queue_id == queue_id,
            CallSession.end_time.isnot(None),
            CallSession.start_time >= today_start,
        )
    )
    completed_today = completed_result.scalar() or 0
    # Avg handle time
    avg_result = await db.execute(
        select(func.avg(CallSession.duration_seconds)).where(
            CallSession.tenant_id == tenant_id,
            CallSession.queue_id == queue_id,
            CallSession.end_time.isnot(None),
            CallSession.start_time >= today_start,
        )
    )
    avg_handle = avg_result.scalar() or 0
    return {
        "queue_id": str(queue_id),
        "queue_name": q.name,
        "active_calls": active_calls,
        "queued_calls": q.queued_calls,
        "completed_today": completed_today,
        "avg_handle_seconds": round(float(avg_handle), 1),
        "avg_wait_seconds": q.avg_wait_seconds,
        "abandoned_today": q.abandoned_count,
        "service_level_pct": round((completed_today / max(completed_today + q.queued_calls, 1)) * 100, 1),
    }


@router.get("/queues/dashboard/summary")
async def get_queues_dashboard(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    """Summary of all queues for dashboard display."""
    await _ensure_sample_data(tenant_id, db)
    result = await db.execute(select(CallQueue).where(CallQueue.tenant_id == tenant_id).order_by(CallQueue.priority))
    queues = result.scalars().all()
    inbound = [q for q in queues if q.direction == "INBOUND"]
    outbound = [q for q in queues if q.direction == "OUTBOUND"]
    return {
        "inbound": {
            "queues": [_queue_to_dict(q) for q in inbound],
            "total_active": sum(q.active_calls for q in inbound),
            "total_queued": sum(q.queued_calls for q in inbound),
        },
        "outbound": {
            "queues": [_queue_to_dict(q) for q in outbound],
            "total_active": sum(q.active_calls for q in outbound),
            "total_queued": sum(q.queued_calls for q in outbound),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# WHISPER AI — WebSocket for real-time streaming STT
# ═══════════════════════════════════════════════════════════════════════════

# Active WebSocket connections, keyed by (tenant_id, call_session_id) -> {"agents": {agent_key: websocket}}.
# In-process state: the service must run with a single worker.
whisper_connections: Dict[tuple, Dict[str, Any]] = {}


async def _load_session_for_ws(tenant_id: uuid.UUID, session_id: uuid.UUID):
    """Return (CallSession | None, Agent | None) for this tenant only."""
    async with _get_session_factory()() as db:
        sess = (await db.execute(select(CallSession).where(
            CallSession.id == session_id, CallSession.tenant_id == tenant_id))).scalar_one_or_none()
        agent = None
        if sess is not None:
            agent = (await db.execute(select(Agent).where(
                Agent.id == sess.agent_id, Agent.tenant_id == tenant_id))).scalar_one_or_none()
        return sess, agent


@app.websocket("/ws/whisper/{call_session_id}")
async def whisper_websocket(
    websocket: WebSocket,
    call_session_id: str,
):
    """
    WebSocket endpoint for real-time Whisper AI streaming STT.

    Client sends audio chunks as binary messages.
    Server responds with JSON: {"transcript": "...", "is_final": false, "confidence": 0.95}

    Auth: signed identity headers only (AUTH_MODE=signed); the tenant NEVER comes from the URL or a
    token in the query string. Close codes: 4001 unauthenticated, 4003 forbidden (not your tenant/session,
    no recording consent), 4004 unknown session.
    Query params: language (default "en").
    """
    try:
        tenant_id, user_id = authenticate_ws(websocket.headers, websocket.url.path, websocket.query_params.get("token"))
    except Exception:
        await websocket.close(code=4001, reason="Invalid or missing identity")
        return
    try:
        session_uuid = uuid.UUID(call_session_id)
    except ValueError:
        await websocket.close(code=4004, reason="Unknown session")
        return

    roles = ws_roles(websocket.headers)
    is_admin = (not access.roles_enforced()) or bool(roles & access.ADMIN_ROLES)
    sess, agent = await _load_session_for_ws(tenant_id, session_uuid)
    if sess is None:
        await websocket.close(code=4004, reason="Unknown session")  # also hides other tenants' sessions
        return
    if not policy.whisper_authorize(
        tenant_id=tenant_id, user_id=user_id, is_admin=is_admin,
        session_tenant_id=sess.tenant_id, session_agent_id=sess.agent_id,
        agent_user_id=agent.user_id if agent else None,
    ):
        await websocket.close(code=4003, reason="Not allowed on this call session")
        return
    if not policy.consent_allows_recording(sess.recording_consent):
        await websocket.close(code=4003, reason="Recording consent required")
        return

    agent_id = str(user_id)
    tenant_str = str(tenant_id)
    language = websocket.query_params.get("language", "en")[:10]

    await websocket.accept()

    session_key = policy.connection_key(tenant_id, session_uuid)
    whisper_connections.setdefault(session_key, {"agents": {}})["agents"][agent_id] = websocket

    logger.info("Whisper WS connected: tenant=%s session=%s", tenant_str, call_session_id)

    audio_buffer = bytearray()

    try:
        while True:
            data = await websocket.receive()

            if data.get("type") == "websocket.disconnect":
                break

            if data.get("bytes") is not None:
                # Audio chunk received
                audio_buffer.extend(data["bytes"])

                # Process every ~2 seconds of audio (approx 64KB at 16kHz 16-bit mono)
                if len(audio_buffer) >= 65536:
                    audio_chunk = bytes(audio_buffer)
                    audio_buffer = bytearray()

                    try:
                        result = await transcribe_audio(
                            audio_bytes=audio_chunk,
                            tenant_id=tenant_str,
                            language=language,
                            user_id=agent_id,
                        )
                        transcript = result.get("transcript", "").strip()
                        confidence = result.get("confidence", 0)

                        if transcript:
                            await websocket.send_json({
                                "type": "transcript",
                                "transcript": transcript,
                                "is_final": False,
                                "confidence": confidence,
                                "language": language,
                            })
                    except Exception as e:
                        logger.error("Whisper STT error: %s", type(e).__name__)
                        await websocket.send_json({"type": "error", "message": "Transcription failed"})
            elif data.get("text") is not None:
                # Control message (JSON)
                try:
                    msg = json.loads(data["text"])
                    action = msg.get("action")

                    if action == "finalize":
                        if audio_buffer:
                            try:
                                result = await transcribe_audio(
                                    audio_bytes=bytes(audio_buffer),
                                    tenant_id=tenant_str,
                                    language=language,
                                    user_id=agent_id,
                                )
                                transcript = result.get("transcript", "").strip()
                                if transcript:
                                    await websocket.send_json({
                                        "type": "transcript",
                                        "transcript": transcript,
                                        "is_final": True,
                                        "confidence": result.get("confidence", 0),
                                    })
                            except Exception as e:
                                logger.error("Whisper finalize error: %s", type(e).__name__)
                        await websocket.send_json({"type": "ended"})

                    elif action == "ping":
                        await websocket.send_json({"type": "pong"})

                except json.JSONDecodeError:
                    pass

    except WebSocketDisconnect:
        logger.info("Whisper WS disconnected: session=%s", call_session_id)
    finally:
        entry = whisper_connections.get(session_key)
        if entry is not None:
            entry["agents"].pop(agent_id, None)
            if not entry["agents"]:
                whisper_connections.pop(session_key, None)


@router.post("/whisper/sessions", status_code=status.HTTP_201_CREATED)
async def create_whisper_session(
    call_session_id: uuid.UUID,
    agent_id: uuid.UUID,
    language: str = "en",
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Create a Whisper AI session linked to a call session (both must belong to the caller's tenant)."""
    call = (await db.execute(select(CallSession).where(
        CallSession.id == call_session_id, CallSession.tenant_id == tenant_id))).scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=404, detail="Call session not found")
    if not (await db.execute(select(Agent.id).where(Agent.id == agent_id, Agent.tenant_id == tenant_id))).first():
        raise HTTPException(status_code=404, detail="Agent not found")
    if not policy.consent_allows_recording(call.recording_consent):
        raise HTTPException(status_code=409, detail="Recording consent is required before live transcription")
    ws = WhisperSession(
        tenant_id=tenant_id,
        call_session_id=call_session_id,
        agent_id=agent_id,
        language=language,
        status="ACTIVE",
    )
    db.add(ws)
    await db.flush()
    await db.refresh(ws)
    return {
        "id": str(ws.id), "call_session_id": str(call_session_id),
        "agent_id": str(agent_id), "language": language, "status": "ACTIVE",
        # identity comes from the signed headers, never from the URL
        "ws_url": f"/ws/whisper/{call_session_id}?language={language}",
    }


@router.put("/whisper/sessions/{whisper_id}/stop")
async def stop_whisper_session(
    whisper_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    result = await db.execute(
        select(WhisperSession).where(WhisperSession.id == whisper_id, WhisperSession.tenant_id == tenant_id)
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Whisper session not found")
    ws.status = "STOPPED"
    ws.stopped_at = datetime.now(timezone.utc)
    await db.flush()
    return {"id": str(ws.id), "status": "STOPPED"}


# ═══════════════════════════════════════════════════════════════════════════
# 360° CUSTOMER VIEW  (new — aggregates CRM, Billing, Support)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/customer-360/{customer_id}")
async def get_customer_360(
    customer_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """
    360° customer view for call center agents during active calls.
    Aggregates data from CRM, Billing, and Support services.
    """
    customer_data = {
        "customer_id": str(customer_id),
        "identity": None,
        "billing": None,
        "support": None,
        "recent_calls": [],
        "lifecycle": None,
    }
    
    # 1. CRM — customer identity + properties
    crm_url = os.getenv("CRM_SERVICE_URL", "http://crm:8001")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{crm_url}/api/crm/customers/{customer_id}",
                headers={"x-tenant-id": str(tenant_id)},
            )
            if resp.status_code == 200:
                customer_data["identity"] = resp.json()
    except Exception as e:
        logger.warning(f"CRM fetch failed for customer 360: {e}")
    
    # 2. Billing — active subscriptions + recent invoices
    billing_url = os.getenv("BILLING_SERVICE_URL", "http://billing:8003")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{billing_url}/api/billing/subscriptions",
                params={"customer_id": str(customer_id)},
                headers={"x-tenant-id": str(tenant_id)},
            )
            if resp.status_code == 200:
                customer_data["billing"] = {"subscriptions": resp.json()}
    except Exception as e:
        logger.warning(f"Billing fetch failed for customer 360: {e}")
    
    # 3. Support — open tickets
    support_url = os.getenv("SUPPORT_SERVICE_URL", "http://support:8008")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{support_url}/api/support/tickets",
                params={"customer_id": str(customer_id), "status": "open"},
                headers={"x-tenant-id": str(tenant_id)},
            )
            if resp.status_code == 200:
                customer_data["support"] = {"open_tickets": resp.json()}
    except Exception as e:
        logger.warning(f"Support fetch failed for customer 360: {e}")
    
    # 4. Recent call sessions (from local DB)
    result = await db.execute(
        select(CallSession)
        .where(CallSession.customer_id == customer_id, CallSession.tenant_id == tenant_id)
        .order_by(desc(CallSession.start_time))
        .limit(5)
    )
    customer_data["recent_calls"] = [_session_to_dict(s) for s in result.scalars().all()]
    
    # 5. Active call session (if any)
    active_result = await db.execute(
        select(CallSession)
        .where(
            CallSession.customer_id == customer_id,
            CallSession.tenant_id == tenant_id,
            CallSession.end_time.is_(None),
        )
        .order_by(desc(CallSession.start_time))
        .limit(1)
    )
    active_call = active_result.scalars().first()
    customer_data["active_call"] = _session_to_dict(active_call) if active_call else None

    # 6. Network — active services + device status + recent performance
    network_url = os.getenv("NETWORK_SERVICE_URL", "http://network:8005")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            # Get active network services for this customer
            svc_resp = await client.get(
                f"{network_url}/api/network/services",
                params={"customer_id": str(customer_id), "status": "active", "page_size": 10},
                headers={"x-tenant-id": str(tenant_id)},
            )
            if svc_resp.status_code == 200:
                services_data = svc_resp.json()
                customer_data["network"] = {
                    "active_services": services_data.get("items", []),
                    "service_count": services_data.get("total", 0),
                }

                # For the first active service, get devices and recent metrics
                services_list = services_data.get("items", [])
                if services_list:
                    first_svc_id = services_list[0].get("id")
                    if first_svc_id:
                        # Get devices
                        dev_resp = await client.get(
                            f"{network_url}/api/network/devices",
                            params={"service_id": first_svc_id, "page_size": 20},
                            headers={"x-tenant-id": str(tenant_id)},
                        )
                        if dev_resp.status_code == 200:
                            customer_data["network"]["devices"] = dev_resp.json().get("items", [])

                        # Get recent performance metrics (last hour)
                        from_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
                        met_resp = await client.get(
                            f"{network_url}/api/network/performance/metrics",
                            params={
                                "service_id": first_svc_id,
                                "from_time": from_time,
                                "limit": 20,
                            },
                            headers={"x-tenant-id": str(tenant_id)},
                        )
                        if met_resp.status_code == 200:
                            customer_data["network"]["recent_metrics"] = met_resp.json()

                        # Check for active FNO outages affecting this service
                        fno_provider = services_list[0].get("fno_provider")
                        if fno_provider:
                            # TODO(call_center): enrich with live FNO Intelligence outage
                            # data when the integration is wired; for now we surface the
                            # provider identifier only.
                            customer_data["network"]["fno_provider"] = fno_provider
    except Exception as e:
        logger.warning(f"Network fetch failed for customer 360: {e}")

    return customer_data


# ═══════════════════════════════════════════════════════════════════════════
# ANALYTICS  (existing)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/analytics/sentiment")
async def get_realtime_sentiment(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    await _ensure_sample_data(tenant_id, db)
    result = await db.execute(
        select(func.count(CallSession.id), func.avg(CallSession.sentiment_score)).where(
            CallSession.tenant_id == tenant_id, CallSession.sentiment_score.isnot(None),
        )
    )
    count, avg_sentiment = result.one()
    if count == 0:
        return {"overall_sentiment": 0.0, "positive_mentions": [], "negative_mentions": [], "alerts_count": 0, "critical_escalations": 0}
    overall = round(float(avg_sentiment), 2) if avg_sentiment else 0.0
    alerts_result = await db.execute(
        select(func.count(CallSession.id)).where(CallSession.tenant_id == tenant_id, CallSession.sentiment_score < 0.5)
    )
    critical_result = await db.execute(
        select(func.count(CallSession.id)).where(CallSession.tenant_id == tenant_id, CallSession.sentiment_score < 0.3)
    )
    return {
        "overall_sentiment": overall,
        "total_sessions_analyzed": count,
        "positive_mentions": ["fast service", "helpful agent", "easy upgrade"] if overall > 0.6 else [],
        "negative_mentions": ["high price", "load shedding outage", "waiting time"] if overall < 0.8 else [],
        "alerts_count": alerts_result.scalar() or 0,
        "critical_escalations": critical_result.scalar() or 0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# VOICE AGENT DEPLOYMENTS
# ═══════════════════════════════════════════════════════════════════════════

class VoiceAgentDeployRequest(BaseModel):
    agent_name: str = "Customer Support Agent"
    system_prompt: str = ""
    stt_model: str = "whisper-large-v3"
    tts_voice: str = "voicebox-nova"
    llm_provider: str = "anthropic"
    mode: str  # "inbound" | "outbound"
    phone_number: str


def _deployment_to_dict(d: VoiceAgentDeployment) -> dict:
    return {
        "id": str(d.id),
        "tenant_id": str(d.tenant_id),
        "agent_name": d.agent_name,
        "system_prompt": d.system_prompt or "",
        "stt_model": d.stt_model,
        "tts_voice": d.tts_voice,
        "llm_provider": d.llm_provider,
        "mode": d.mode,
        "phone_number": d.phone_number,
        "status": d.status,
        "call_session_id": str(d.call_session_id) if d.call_session_id else None,
        "deployed_at": d.deployed_at.isoformat() if d.deployed_at else None,
        "stopped_at": d.stopped_at.isoformat() if d.stopped_at else None,
    }


@router.get("/voice-agents")
async def list_voice_agents(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """List all voice agent deployments for this tenant."""
    result = await db.execute(
        select(VoiceAgentDeployment)
        .where(VoiceAgentDeployment.tenant_id == tenant_id)
        .order_by(desc(VoiceAgentDeployment.deployed_at))
    )
    return [_deployment_to_dict(d) for d in result.scalars().all()]


@router.post("/voice-agents/deploy", status_code=status.HTTP_201_CREATED)
async def deploy_voice_agent(
    body: VoiceAgentDeployRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """
    Deploy a voice agent:
    - Picks up an IDLE human agent record (or creates a virtual one) and marks it ON_CALL.
    - Opens a CallSession for the deployment with the configured direction.
    - Returns a VoiceAgentDeployment record tracking the full config.
    """
    # Find or create an agent to associate with this deployment
    agent_result = await db.execute(
        select(Agent)
        .where(Agent.tenant_id == tenant_id, Agent.status == "IDLE")
        .limit(1)
    )
    agent = agent_result.scalar_one_or_none()
    if agent:
        agent.status = "ON_CALL"
        await db.flush()
    else:
        agent = Agent(
            tenant_id=tenant_id,
            name=body.agent_name,
            extension="AI-" + str(uuid.uuid4())[:4].upper(),
            status="ON_CALL",
        )
        db.add(agent)
        await db.flush()
        await db.refresh(agent)

    # Open a call session
    direction = "INBOUND" if body.mode.lower() == "inbound" else "OUTBOUND"
    sess = CallSession(
        tenant_id=tenant_id,
        agent_id=agent.id,
        direction=direction,
        start_time=datetime.now(timezone.utc),
        notes=f"[Voice Agent] {body.agent_name} | {body.mode.upper()} | {body.phone_number}",
    )
    db.add(sess)
    await db.flush()
    await db.refresh(sess)

    # Create the deployment record
    deployment = VoiceAgentDeployment(
        tenant_id=tenant_id,
        agent_name=body.agent_name,
        system_prompt=body.system_prompt,
        stt_model=body.stt_model,
        tts_voice=body.tts_voice,
        llm_provider=body.llm_provider,
        mode=body.mode.lower(),
        phone_number=body.phone_number,
        status="active",
        call_session_id=sess.id,
    )
    db.add(deployment)
    await db.flush()
    await db.refresh(deployment)
    return _deployment_to_dict(deployment)


@router.post("/voice-agents/{deployment_id}/stop")
async def stop_voice_agent(
    deployment_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Stop a deployed voice agent and end its call session."""
    result = await db.execute(
        select(VoiceAgentDeployment).where(
            VoiceAgentDeployment.id == deployment_id,
            VoiceAgentDeployment.tenant_id == tenant_id,
        )
    )
    deployment = result.scalar_one_or_none()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    now = datetime.now(timezone.utc)
    deployment.status = "stopped"
    deployment.stopped_at = now

    # End the linked call session
    if deployment.call_session_id:
        sess_result = await db.execute(
            select(CallSession).where(CallSession.id == deployment.call_session_id)
        )
        sess = sess_result.scalar_one_or_none()
        if sess and not sess.end_time:
            sess.end_time = now
            sess.duration_seconds = int((now - sess.start_time).total_seconds())
            sess.outcome = "RESOLVED"

    await db.flush()
    return _deployment_to_dict(deployment)


@router.post("/reports/import")
async def import_external_report(
    file: UploadFile = File(...),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Import a CDR CSV (admin tier). Required columns: external_call_id, agent_extension, start_time;
    optional: direction (INBOUND|OUTBOUND), end_time, duration_seconds, outcome, customer_id. Times are ISO-8601.
    Rows are validated one by one; valid rows are persisted as call sessions (idempotent on
    (tenant, external_call_id): re-importing the same file inserts nothing twice). Size cap: CALL_IMPORT_MAX_MB
    (default 10). The response lists per-row errors (first 50)."""
    cap = policy.max_import_bytes()
    chunks, size = [], 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > cap:
            raise HTTPException(status_code=413, detail=f"File exceeds the {cap // (1024 * 1024)} MB import limit")
        chunks.append(chunk)
    try:
        text_content = b"".join(chunks).decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="File must be UTF-8 encoded CSV")

    agents = (await db.execute(select(Agent).where(Agent.tenant_id == tenant_id))).scalars().all()
    by_ext = {a.extension: a.id for a in agents}
    parsed = policy.parse_cdr_csv(text_content, by_ext)
    if parsed["header_error"]:
        raise HTTPException(status_code=422, detail=parsed["header_error"])

    rows = parsed["rows"]
    existing: set = set()
    ids = [r["external_call_id"] for r in rows]
    for i in range(0, len(ids), 500):
        found = await db.execute(select(CallSession.external_call_id).where(
            CallSession.tenant_id == tenant_id, CallSession.external_call_id.in_(ids[i:i + 500])))
        existing.update(x for (x,) in found.all())
    inserted = duplicates = 0
    for r in rows:
        if r["external_call_id"] in existing:
            duplicates += 1
            continue
        db.add(CallSession(
            tenant_id=tenant_id, agent_id=r["agent_id"], customer_id=r["customer_id"], direction=r["direction"],
            start_time=r["start_time"], end_time=r["end_time"], duration_seconds=r["duration_seconds"],
            outcome=r["outcome"], external_call_id=r["external_call_id"], recording_consent="unknown",
            retention_until=policy.retention_until(r["start_time"]),
            notes="[CDR import]",
        ))
        inserted += 1
    await db.flush()
    errors = parsed["errors"]
    if inserted == 0 and errors and not duplicates:
        result_status = "FAILED"
    elif errors:
        result_status = "PARTIAL"
    else:
        result_status = "SUCCESS"
    return {
        "status": result_status,
        "filename": file.filename,
        "rows_total": parsed["total"],
        "processed_records": inserted,
        "duplicates_skipped": duplicates,
        "rejected_rows": len(errors),
        "anomalies_detected": parsed["anomalies"],
        "errors": errors[:50],
        "message": f"{inserted} record(s) imported, {duplicates} duplicate(s) skipped, {len(errors)} rejected.",
    }


@router.get("/reports/intelligence")
async def get_hub_intelligence(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
    days: int = Query(30, ge=1, le=365),
):
    """Call KPIs for the last `days` days (default 30), computed with SQL aggregation (nothing is loaded
    into memory). Resolution counts only sessions with an explicit RESOLVED/COMPLETED outcome, over
    finished sessions; with no data the rates are null."""
    return await compute_intelligence(db, tenant_id, datetime.now(timezone.utc) - timedelta(days=days), days)


async def compute_intelligence(db, tenant_id: uuid.UUID, since: datetime, days: int = 30) -> dict:
    window = (CallSession.tenant_id == tenant_id, CallSession.start_time >= since)
    resolved_expr = func.sum(case((func.upper(CallSession.outcome).in_(policy.RESOLVED_OUTCOMES), 1), else_=0))
    finished_expr = func.sum(case((CallSession.end_time.is_not(None), 1), else_=0))
    total, finished, resolved, avg_talk = (await db.execute(
        select(func.count(CallSession.id), finished_expr, resolved_expr,
               func.avg(case((CallSession.duration_seconds > 0, CallSession.duration_seconds), else_=None)))
        .where(*window)
    )).one()
    total, finished, resolved = int(total or 0), int(finished or 0), int(resolved or 0)
    if total == 0:
        return {"window_days": days, "total_sessions": 0, "resolution_rate": None, "avg_talk_time_seconds": None,
                "closed_queries": 0, "peak_volume_period": None, "health_status": policy.health_label(None)}
    hour = func.extract("hour", CallSession.start_time)
    peak = (await db.execute(
        select(hour.label("h"), func.count(CallSession.id).label("n")).where(*window)
        .group_by(hour).order_by(func.count(CallSession.id).desc(), hour).limit(1)
    )).first()
    peak_period = None
    if peak is not None and peak[0] is not None:
        h = int(peak[0])
        peak_period = f"{h:02d}:00-{(h + 1) % 24:02d}:00 UTC"
    rate = round(resolved / finished * 100, 1) if finished else None
    return {
        "window_days": days,
        "total_sessions": total,
        "resolution_rate": rate,
        "avg_talk_time_seconds": round(float(avg_talk)) if avg_talk is not None else None,
        "closed_queries": resolved,
        "peak_volume_period": peak_period,
        "health_status": policy.health_label(rate),
    }


# ═══════════════════════════════════════════════════════════════════════════
# PROVIDER CREDENTIALS  (admin tier; Fernet-encrypted at rest, never returned)
# ═══════════════════════════════════════════════════════════════════════════

PROVIDERS = ("deepgram", "voicebox", "sip", "astpp")


class ProviderCredentialBody(BaseModel):
    # free-form string fields, e.g. {"api_key": "..."} or {"host": "...", "username": "...", "password": "..."}
    fields: Dict[str, str]


def _credential_view(row: ProviderCredential) -> dict:
    return {"provider": row.provider, "configured": True, "fields": sorted(row.field_names or []),
            "secret": "••••", "updated_at": row.updated_at.isoformat() if row.updated_at else None}


@router.get("/provider-credentials")
async def list_provider_credentials(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    rows = (await db.execute(select(ProviderCredential).where(ProviderCredential.tenant_id == tenant_id))).scalars().all()
    return [_credential_view(r) for r in rows]


@router.put("/provider-credentials/{provider}")
async def put_provider_credentials(provider: str, body: ProviderCredentialBody,
                                   tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")
    if not body.fields or len(body.fields) > 20 or any(len(k) > 50 or len(v) > 2000 for k, v in body.fields.items()):
        raise HTTPException(status_code=422, detail="fields must have 1-20 entries (names <= 50, values <= 2000 chars)")
    if provider == "sip":
        # refuse values that cannot be rendered safely into the PBX config (message never echoes the value)
        try:
            check_trunk_fields(body.fields)
        except TrunkConfigError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    try:
        blob = secretbox.encrypt(json.dumps(body.fields))
    except secretbox.SecretsUnavailable:
        logger.error("SECRETS_ENCRYPTION_KEY unavailable: refusing to store provider credentials")
        raise HTTPException(status_code=503, detail="Secret storage is not configured")
    row = (await db.execute(select(ProviderCredential).where(
        ProviderCredential.tenant_id == tenant_id, ProviderCredential.provider == provider))).scalar_one_or_none()
    if row is None:
        row = ProviderCredential(tenant_id=tenant_id, provider=provider, config_enc=blob, field_names=sorted(body.fields))
        db.add(row)
    else:
        row.config_enc = blob
        row.field_names = sorted(body.fields)
        row.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(row)
    if provider == "sip":
        get_telephony_runtime().reconcile_soon()
    return _credential_view(row)


@router.delete("/provider-credentials/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider_credentials(provider: str, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                                      db=Depends(get_session)):
    row = (await db.execute(select(ProviderCredential).where(
        ProviderCredential.tenant_id == tenant_id, ProviderCredential.provider == provider))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Credentials not found")
    await db.delete(row)
    await db.flush()
    if provider == "sip":
        get_telephony_runtime().reconcile_soon()


# ═══════════════════════════════════════════════════════════════════════════
# VOICEBOX VOICE AI  (STT/TTS/Audio Intel — replaces Deepgram)
# ═══════════════════════════════════════════════════════════════════════════

class TranscriptionResponse(BaseModel):
    transcript: str
    confidence: float
    words: list = []
    metadata: dict = {}

class TTSRequest(BaseModel):
    text: str
    voice_profile_id: Optional[uuid.UUID] = None
    agent_id: Optional[uuid.UUID] = None  # resolves the voice bound to this call-center agent
    model: Optional[str] = "aura-asteria-en"

class AudioIntelligenceResponse(BaseModel):
    transcript: str
    confidence: float
    summary: str = ""
    sentiments: dict = {}
    intents: dict = {}
    topics: dict = {}
    metadata: dict = {}


@router.get("/ai/voices")
async def get_ai_voices():
    """Return available Deepgram Aura voices."""
    return {"voices": list_voices()}


@router.post("/ai/speech-to-text")
async def speech_to_text(
    file: UploadFile = File(...),
    language: str = Form("en"),
    model: str = Form("nova-3"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    try:
        audio_bytes = await file.read()
        result = await transcribe_audio(
            audio_bytes=audio_bytes,
            tenant_id=str(tenant_id),
            language=language,
            model=model,
            user_id=str(user_id),
        )
        return TranscriptionResponse(**result)
    except DeepgramError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error(f"STT error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ai/text-to-speech")
async def text_to_speech(request: TTSRequest, tenant_id: uuid.UUID = Depends(get_current_tenant_id), user_id: uuid.UUID = Depends(get_current_user_id)):
    try:
        audio_bytes = await synthesize_speech(
            text=request.text,
            tenant_id=str(tenant_id),
            model=request.model or "aura-asteria-en",
            voice_profile_id=str(request.voice_profile_id) if request.voice_profile_id else None,
            scope_ref=str(request.agent_id) if request.agent_id else None,
            user_id=str(user_id),
        )
        return Response(content=audio_bytes, media_type="audio/mpeg", headers={"Content-Disposition": "attachment; filename=speech.mp3"})
    except DeepgramError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"TTS error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ai/audio-intelligence")
async def audio_intelligence(file: UploadFile = File(...), language: str = Form("en"), tenant_id: uuid.UUID = Depends(get_current_tenant_id), user_id: uuid.UUID = Depends(get_current_user_id)):
    try:
        audio_bytes = await file.read()
        result = await analyze_audio(audio_bytes=audio_bytes, tenant_id=str(tenant_id), language=language, user_id=str(user_id))
        return AudioIntelligenceResponse(**result)
    except VoiceboxUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error(f"Audio Intelligence error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ai/summarize")
async def summarize_call(file: UploadFile = File(...), tenant_id: uuid.UUID = Depends(get_current_tenant_id), user_id: uuid.UUID = Depends(get_current_user_id)):
    try:
        audio_bytes = await file.read()
        result = await analyze_audio(audio_bytes=audio_bytes, tenant_id=str(tenant_id), user_id=str(user_id))
        return {"summary": result["summary"], "transcript": result["transcript"], "confidence": result["confidence"]}
    except VoiceboxUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ai/sentiment")
async def sentiment_analysis(file: UploadFile = File(...), tenant_id: uuid.UUID = Depends(get_current_tenant_id), user_id: uuid.UUID = Depends(get_current_user_id)):
    try:
        audio_bytes = await file.read()
        result = await analyze_audio(audio_bytes=audio_bytes, tenant_id=str(tenant_id), user_id=str(user_id))
        return {"sentiments": result["sentiments"], "transcript": result["transcript"]}
    except VoiceboxUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ai/intents")
async def intent_detection(file: UploadFile = File(...), tenant_id: uuid.UUID = Depends(get_current_tenant_id), user_id: uuid.UUID = Depends(get_current_user_id)):
    try:
        audio_bytes = await file.read()
        result = await analyze_audio(audio_bytes=audio_bytes, tenant_id=str(tenant_id), user_id=str(user_id))
        return {"intents": result["intents"], "transcript": result["transcript"]}
    except VoiceboxUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ai/topics")
async def topic_detection(file: UploadFile = File(...), tenant_id: uuid.UUID = Depends(get_current_tenant_id), user_id: uuid.UUID = Depends(get_current_user_id)):
    try:
        audio_bytes = await file.read()
        result = await analyze_audio(audio_bytes=audio_bytes, tenant_id=str(tenant_id), user_id=str(user_id))
        return {"topics": result["topics"], "transcript": result["transcript"]}
    except VoiceboxUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# All HTTP routes are registered above; include the gated router last.
app.include_router(router)
app.include_router(telephony_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007, workers=1)
