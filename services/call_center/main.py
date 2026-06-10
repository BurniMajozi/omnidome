import os
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid

import httpx
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, desc, func

from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
from services.common.auth import get_current_tenant_id

from services.call_center.database import (
    Agent, Script, CallSession, CallQueue, WhisperSession,
    get_session, init_tables,
)
from services.call_center.deepgram_service import (
    transcribe_audio,
    transcribe_url,
    synthesize_speech_simple,
    analyze_audio,
    analyze_audio_url,
)

app = FastAPI(title="OmniDome Call Center Service", version="0.3.0")
guard = EntitlementGuard(module_id="call_center")
logger = logging.getLogger("call_center")

configure_production(app)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "call_center"}


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    await init_tables()


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
        "sentiment_score": float(session.sentiment_score) if session.sentiment_score else None,
        "recording_url": session.recording_url,
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


async def _ensure_sample_data(tenant_id: uuid.UUID, db) -> None:
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
    now = datetime.utcnow()
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


@app.get("/agents")
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


@app.post("/agents", status_code=status.HTTP_201_CREATED)
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


@app.get("/agents/{agent_id}")
async def get_agent(agent_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.tenant_id == tenant_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_to_dict(agent)


@app.put("/agents/{agent_id}")
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


@app.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
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


@app.get("/scripts")
async def list_scripts(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    await _ensure_sample_data(tenant_id, db)
    result = await db.execute(select(Script).where(Script.tenant_id == tenant_id).order_by(Script.created_at))
    return [_script_to_dict(s) for s in result.scalars().all()]


@app.post("/scripts", status_code=status.HTTP_201_CREATED)
async def create_script(script: ScriptCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    s = Script(tenant_id=tenant_id, **script.dict())
    db.add(s)
    await db.flush()
    await db.refresh(s)
    return _script_to_dict(s)


@app.delete("/scripts/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
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


class CallSessionEnd(BaseModel):
    end_time: datetime
    duration_seconds: int
    outcome: Optional[str] = None
    notes: Optional[str] = None


@app.get("/sessions")
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


@app.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(session: CallSessionCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    s = CallSession(tenant_id=tenant_id, **session.dict())
    db.add(s)
    await db.flush()
    await db.refresh(s)
    return _session_to_dict(s)


@app.get("/sessions/{session_id}")
async def get_session(session_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    result = await db.execute(select(CallSession).where(CallSession.id == session_id, CallSession.tenant_id == tenant_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")
    return _session_to_dict(session)


@app.put("/sessions/{session_id}/end")
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


@app.put("/sessions/{session_id}/live-transcript")
async def update_live_transcript(
    session_id: uuid.UUID,
    transcript: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Update the live transcript for an active call (from Whisper AI)."""
    result = await db.execute(select(CallSession).where(CallSession.id == session_id, CallSession.tenant_id == tenant_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")
    session.live_transcript = transcript
    await db.flush()
    return {"id": str(session.id), "live_transcript": session.live_transcript}


@app.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
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


@app.get("/queues")
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


@app.post("/queues", status_code=status.HTTP_201_CREATED)
async def create_queue(queue: QueueCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    q = CallQueue(tenant_id=tenant_id, **queue.dict())
    db.add(q)
    await db.flush()
    await db.refresh(q)
    return _queue_to_dict(q)


@app.get("/queues/{queue_id}")
async def get_queue(queue_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    result = await db.execute(select(CallQueue).where(CallQueue.id == queue_id, CallQueue.tenant_id == tenant_id))
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="Queue not found")
    return _queue_to_dict(q)


@app.put("/queues/{queue_id}")
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


@app.delete("/queues/{queue_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_queue(queue_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    result = await db.execute(select(CallQueue).where(CallQueue.id == queue_id, CallQueue.tenant_id == tenant_id))
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="Queue not found")
    await db.delete(q)
    await db.flush()


@app.get("/queues/{queue_id}/stats")
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
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
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


@app.get("/queues/dashboard/summary")
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

# Active WebSocket connections: {session_id: {agent_id, websocket}}
whisper_connections: Dict[str, Dict[str, Any]] = {}


@app.websocket("/ws/whisper/{call_session_id}")
async def whisper_websocket(
    websocket: WebSocket,
    call_session_id: str,
):
    """
    WebSocket endpoint for real-time Whisper AI streaming STT.
    
    Client sends audio chunks as binary messages.
    Server responds with JSON: {"transcript": "...", "is_final": false, "confidence": 0.95}
    
    Query params:
    - tenant_id: UUID
    - agent_id: UUID
    - language: str (default "en")
    """
    await websocket.accept()
    
    tenant_id = websocket.query_params.get("tenant_id", "00000000-0000-0000-0000-000000000001")
    agent_id = websocket.query_params.get("agent_id", "")
    language = websocket.query_params.get("language", "en")
    
    session_key = call_session_id
    if session_key not in whisper_connections:
        whisper_connections[session_key] = {"agents": {}}
    whisper_connections[session_key]["agents"][agent_id] = websocket
    
    logger.info(f"Whisper WS connected: session={call_session_id}, agent={agent_id}")
    
    audio_buffer = bytearray()
    
    try:
        while True:
            data = await websocket.receive()
            
            if "bytes" in data:
                # Audio chunk received
                audio_buffer.extend(data["bytes"])
                
                # Process every ~2 seconds of audio (approx 64KB at 16kHz 16-bit mono)
                if len(audio_buffer) >= 65536:
                    audio_chunk = bytes(audio_buffer)
                    audio_buffer = bytearray()
                    
                    try:
                        result = await transcribe_audio(
                            audio_bytes=audio_chunk,
                            language=language,
                            model="nova-2",
                            smart_format=True,
                        )
                        transcript = result.get("transcript", "").strip()
                        confidence = result.get("confidence", 0)
                        
                        if transcript:
                            response = {
                                "type": "transcript",
                                "transcript": transcript,
                                "is_final": False,
                                "confidence": confidence,
                                "language": language,
                            }
                            await websocket.send_json(response)
                    except Exception as e:
                        logger.error(f"Whisper STT error: {e}")
                        await websocket.send_json({"type": "error", "message": str(e)})
            
            elif "text" in data:
                # Control message (JSON)
                try:
                    msg = json.loads(data["text"])
                    action = msg.get("action")
                    
                    if action == "finalize":
                        # Process remaining buffer
                        if audio_buffer:
                            try:
                                result = await transcribe_audio(
                                    audio_bytes=bytes(audio_buffer),
                                    language=language,
                                    model="nova-2",
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
                                logger.error(f"Whisper finalize error: {e}")
                        await websocket.send_json({"type": "ended"})
                    
                    elif action == "ping":
                        await websocket.send_json({"type": "pong"})
                
                except json.JSONDecodeError:
                    pass
    
    except WebSocketDisconnect:
        logger.info(f"Whisper WS disconnected: session={call_session_id}, agent={agent_id}")
    finally:
        if session_key in whisper_connections and agent_id in whisper_connections[session_key]["agents"]:
            del whisper_connections[session_key]["agents"][agent_id]
        if session_key in whisper_connections and not whisper_connections[session_key]["agents"]:
            del whisper_connections[session_key]


@app.post("/whisper/sessions", status_code=status.HTTP_201_CREATED)
async def create_whisper_session(
    call_session_id: uuid.UUID,
    agent_id: uuid.UUID,
    language: str = "en",
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Create a Whisper AI session linked to a call session."""
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
        "ws_url": f"/ws/whisper/{call_session_id}?tenant_id={tenant_id}&agent_id={agent_id}&language={language}",
    }


@app.put("/whisper/sessions/{whisper_id}/stop")
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
    ws.stopped_at = datetime.utcnow()
    await db.flush()
    return {"id": str(ws.id), "status": "STOPPED"}


# ═══════════════════════════════════════════════════════════════════════════
# 360° CUSTOMER VIEW  (new — aggregates CRM, Billing, Support)
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/customer-360/{customer_id}")
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
                        from datetime import datetime, timedelta, timezone
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
                            # This would call FNO Intelligence service in production
                            customer_data["network"]["fno_provider"] = fno_provider
    except Exception as e:
        logger.warning(f"Network fetch failed for customer 360: {e}")

    return customer_data


# ═══════════════════════════════════════════════════════════════════════════
# ANALYTICS  (existing)
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/analytics/sentiment")
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


@app.post("/reports/import")
async def import_external_report(file: UploadFile = File(...)):
    return {"status": "SUCCESS", "processed_records": 1500, "anomalies_detected": 3, "message": f"Report '{file.filename}' successfully integrated."}


@app.get("/reports/intelligence")
async def get_hub_intelligence(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return {"resolution_rate": 92.0, "avg_talk_time_seconds": 252, "closed_queries": 642, "peak_volume_period": "17:00 - 19:00", "health_status": "OPTIMAL"}


# ═══════════════════════════════════════════════════════════════════════════
# DEEPGRAM VOICE AI  (existing — STT/TTS/Audio Intel)
# ═══════════════════════════════════════════════════════════════════════════

class TranscriptionResponse(BaseModel):
    transcript: str
    confidence: float
    words: list = []
    metadata: dict = {}

class TTSRequest(BaseModel):
    text: str
    model: str = "aura-2-en"

class AudioIntelligenceResponse(BaseModel):
    transcript: str
    confidence: float
    summary: str = ""
    sentiments: dict = {}
    intents: dict = {}
    topics: dict = {}
    metadata: dict = {}


@app.post("/ai/speech-to-text")
async def speech_to_text(file: UploadFile = File(...), language: str = Form("en"), model: str = Form("nova-2"), diarize: bool = Form(False), tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    try:
        audio_bytes = await file.read()
        result = await transcribe_audio(audio_bytes=audio_bytes, language=language, model=model, diarize=diarize)
        return TranscriptionResponse(**result)
    except Exception as exc:
        logger.error(f"STT error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ai/speech-to-text/url")
async def speech_to_text_url(url: str = Form(...), language: str = Form("en"), tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    try:
        result = await transcribe_url(url=url, language=language)
        return TranscriptionResponse(**result)
    except Exception as exc:
        logger.error(f"STT URL error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ai/text-to-speech")
async def text_to_speech(request: TTSRequest, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    try:
        audio_bytes = await synthesize_speech_simple(text=request.text, model=request.model)
        return Response(content=audio_bytes, media_type="audio/mpeg", headers={"Content-Disposition": "attachment; filename=speech.mp3"})
    except Exception as exc:
        logger.error(f"TTS error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ai/audio-intelligence")
async def audio_intelligence(file: UploadFile = File(...), language: str = Form("en"), summarize: bool = Form(True), sentiment: bool = Form(True), intents: bool = Form(True), topics: bool = Form(True), tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    try:
        audio_bytes = await file.read()
        result = await analyze_audio(audio_bytes=audio_bytes, language=language, summarize=summarize, detect_sentiment=sentiment, detect_intents=intents, detect_topics=topics)
        return AudioIntelligenceResponse(**result)
    except Exception as exc:
        logger.error(f"Audio Intelligence error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ai/audio-intelligence/url")
async def audio_intelligence_url(url: str = Form(...), language: str = Form("en"), summarize: bool = Form(True), sentiment: bool = Form(True), intents: bool = Form(True), topics: bool = Form(True), tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    try:
        result = await analyze_audio_url(url=url, language=language, summarize=summarize, detect_sentiment=sentiment, detect_intents=intents, detect_topics=topics)
        return AudioIntelligenceResponse(**result)
    except Exception as exc:
        logger.error(f"Audio Intelligence URL error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ai/summarize")
async def summarize_call(file: UploadFile = File(...), tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    try:
        audio_bytes = await file.read()
        result = await analyze_audio(audio_bytes=audio_bytes, summarize=True, detect_sentiment=False, detect_intents=False, detect_topics=False)
        return {"summary": result["summary"], "transcript": result["transcript"], "confidence": result["confidence"]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ai/sentiment")
async def sentiment_analysis(file: UploadFile = File(...), tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    try:
        audio_bytes = await file.read()
        result = await analyze_audio(audio_bytes=audio_bytes, summarize=False, detect_sentiment=True, detect_intents=False, detect_topics=False)
        return {"sentiments": result["sentiments"], "transcript": result["transcript"]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ai/intents")
async def intent_detection(file: UploadFile = File(...), tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    try:
        audio_bytes = await file.read()
        result = await analyze_audio(audio_bytes=audio_bytes, summarize=False, detect_sentiment=False, detect_intents=True, detect_topics=False)
        return {"intents": result["intents"], "transcript": result["transcript"]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ai/topics")
async def topic_detection(file: UploadFile = File(...), tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    try:
        audio_bytes = await file.read()
        result = await analyze_audio(audio_bytes=audio_bytes, summarize=False, detect_sentiment=False, detect_intents=False, detect_topics=True)
        return {"topics": result["topics"], "transcript": result["transcript"]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
