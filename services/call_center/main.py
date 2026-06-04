from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid
from datetime import datetime
import logging
from sqlalchemy import select, desc

from services.common.entitlements import EntitlementGuard
from services.common.auth import get_current_tenant_id

from services.call_center.database import Agent, Script, CallSession, get_session, init_tables
from services.call_center.deepgram_service import (
    transcribe_audio,
    transcribe_url,
    synthesize_speech_simple,
    analyze_audio,
    analyze_audio_url,
)

app = FastAPI(title="CoreConnect Call Center Service", version="0.2.0")
guard = EntitlementGuard(module_id="call_center")


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


# ── Pydantic request / response schemas --

class AgentCreate(BaseModel):
    name: str
    extension: str
    status: str = "IDLE"
    daily_sales: float = 0
    mttr_minutes: float = 0
    csat_score: float = 0


class AgentResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    extension: str
    status: str
    daily_sales: float
    mttr_minutes: float
    csat_score: float
    created_at: Optional[str]
    updated_at: Optional[str]


class ScriptCreate(BaseModel):
    title: str
    category: str
    content: str
    active: bool = True


class ScriptResponse(BaseModel):
    id: str
    tenant_id: str
    title: str
    category: str
    content: str
    active: bool
    created_at: Optional[str]
    updated_at: Optional[str]


class CallSessionCreate(BaseModel):
    agent_id: uuid.UUID
    customer_id: Optional[uuid.UUID] = None
    start_time: datetime
    sentiment_score: Optional[float] = None
    recording_url: Optional[str] = None
    transcript: Optional[str] = None


class CallSessionEnd(BaseModel):
    end_time: datetime
    duration_seconds: int


class CallSessionResponse(BaseModel):
    id: str
    tenant_id: str
    agent_id: str
    customer_id: Optional[str]
    start_time: str
    end_time: Optional[str]
    duration_seconds: int
    sentiment_score: Optional[float]
    recording_url: Optional[str]
    transcript: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]


# ── Helper functions ─────────────────────────────────────────────────────

def _agent_to_dict(agent: Agent) -> dict:
    return {
        "id": str(agent.id),
        "tenant_id": str(agent.tenant_id),
        "name": agent.name,
        "extension": agent.extension,
        "status": agent.status,
        "daily_sales": float(agent.daily_sales) if agent.daily_sales else 0,
        "mttr_minutes": float(agent.mttr_minutes) if agent.mttr_minutes else 0,
        "csat_score": float(agent.csat_score) if agent.csat_score else 0,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }


def _script_to_dict(script: Script) -> dict:
    return {
        "id": str(script.id),
        "tenant_id": str(script.tenant_id),
        "title": script.title,
        "category": script.category,
        "content": script.content,
        "active": script.active,
        "created_at": script.created_at.isoformat() if script.created_at else None,
        "updated_at": script.updated_at.isoformat() if script.updated_at else None,
    }


def _session_to_dict(session: CallSession) -> dict:
    return {
        "id": str(session.id),
        "tenant_id": str(session.tenant_id),
        "agent_id": str(session.agent_id),
        "customer_id": str(session.customer_id) if session.customer_id else None,
        "start_time": session.start_time.isoformat() if session.start_time else None,
        "end_time": session.end_time.isoformat() if session.end_time else None,
        "duration_seconds": session.duration_seconds,
        "sentiment_score": float(session.sentiment_score) if session.sentiment_score else None,
        "recording_url": session.recording_url,
        "transcript": session.transcript,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


async def _ensure_sample_data(tenant_id: uuid.UUID, db) -> None:
    """Seed sample agents, scripts, and call sessions if tenant has none."""
    # Check if tenant already has agents
    result = await db.execute(
        select(Agent).where(Agent.tenant_id == tenant_id).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return

    # Seed agents
    agent1 = Agent(
        tenant_id=tenant_id,
        name="Sipho Nkosi",
        extension="1001",
        status="ON_CALL",
        daily_sales=12400,
        mttr_minutes=5.2,
        csat_score=4.8,
    )
    agent2 = Agent(
        tenant_id=tenant_id,
        name="Jane Doe",
        extension="1005",
        status="IDLE",
        daily_sales=8500,
        mttr_minutes=4.8,
        csat_score=4.9,
    )
    db.add(agent1)
    db.add(agent2)
    await db.flush()
    await db.refresh(agent1)
    await db.refresh(agent2)

    # Seed scripts
    script1 = Script(
        tenant_id=tenant_id,
        title="Sales: Fiber Upgrade",
        category="Sales",
        content="Targeting existing customers with a fiber upgrade offer. Start by confirming account details, then present the benefits of upgrading to a higher-speed package...",
        active=True,
    )
    script2 = Script(
        tenant_id=tenant_id,
        title="Support: Troubleshooting",
        category="Support",
        content="Step-by-step guide for troubleshooting connectivity issues. Step 1: Check physical connections. Step 2: Power cycle the ONT and router. Step 3: Verify signal levels...",
        active=True,
    )
    db.add(script1)
    db.add(script2)
    await db.flush()

    # Seed call sessions
    now = datetime.utcnow()
    session1 = CallSession(
        tenant_id=tenant_id,
        agent_id=agent1.id,
        start_time=now,
        end_time=now,
        duration_seconds=312,
        sentiment_score=0.85,
        recording_url="https://recordings.example.com/call-001.mp3",
        transcript="Customer inquired about upgrading their fiber package. Agent successfully upselled to the 100Mbps plan.",
    )
    session2 = CallSession(
        tenant_id=tenant_id,
        agent_id=agent2.id,
        start_time=now,
        end_time=now,
        duration_seconds=185,
        sentiment_score=0.72,
        recording_url="https://recordings.example.com/call-002.mp3",
        transcript="Customer reported intermittent connectivity issues. Agent walked through troubleshooting steps and resolved the issue.",
    )
    db.add(session1)
    db.add(session2)
    await db.flush()


# ── Routes ───────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "CoreConnect Call Center Service is active"}


# ── Agents ───────────────────────────────────────────────────────────────

@app.get("/agents", response_model=List[AgentResponse])
async def list_agents(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """List all call center agents — DB-persisted with sample data seeding."""
    await _ensure_sample_data(tenant_id, db)
    result = await db.execute(
        select(Agent)
        .where(Agent.tenant_id == tenant_id)
        .order_by(Agent.created_at)
    )
    agents = result.scalars().all()
    return [_agent_to_dict(a) for a in agents]


@app.post("/agents", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    agent: AgentCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Create a new call center agent."""
    a = Agent(
        tenant_id=tenant_id,
        name=agent.name,
        extension=agent.extension,
        status=agent.status,
        daily_sales=agent.daily_sales,
        mttr_minutes=agent.mttr_minutes,
        csat_score=agent.csat_score,
    )
    db.add(a)
    await db.flush()
    await db.refresh(a)
    logging.info(f"New agent created: {a.name} (ext {a.extension})")
    return _agent_to_dict(a)


@app.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Get a single agent by ID."""
    result = await db.execute(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.tenant_id == tenant_id,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_to_dict(agent)


@app.put("/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Update an agent"""
    result = await db.execute(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.tenant_id == tenant_id,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(agent, field, value)

    await db.flush()
    await db.refresh(agent)
    return _agent_to_dict(agent)


@app.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Delete an agent"""
    result = await db.execute(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.tenant_id == tenant_id,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    await db.delete(agent)
    await db.flush()


# ── Scripts ──────────────────────────────────────────────────────────────

@app.get("/scripts", response_model=List[ScriptResponse])
async def list_scripts(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """List all call center scripts — DB-persisted with sample data seeding."""
    await _ensure_sample_data(tenant_id, db)
    result = await db.execute(
        select(Script)
        .where(Script.tenant_id == tenant_id)
        .order_by(Script.created_at)
    )
    scripts = result.scalars().all()
    return [_script_to_dict(s) for s in scripts]


@app.post("/scripts", response_model=ScriptResponse, status_code=status.HTTP_201_CREATED)
async def create_script(
    script: ScriptCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Create a new call center script — DB-persisted."""
    s = Script(
        tenant_id=tenant_id,
        title=script.title,
        category=script.category,
        content=script.content,
        active=script.active,
    )
    db.add(s)
    await db.flush()
    await db.refresh(s)
    logging.info(f"New script created: {s.title}")
    return _script_to_dict(s)


@app.delete("/scripts/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_script(
    script_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Delete a call center script."""
    result = await db.execute(
        select(Script).where(
            Script.id == script_id,
            Script.tenant_id == tenant_id,
        )
    )
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    await db.delete(script)
    await db.flush()
    logging.info(f"Script deleted: {script.title}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Call Sessions ────────────────────────────────────────────────────────

@app.get("/sessions", response_model=List[CallSessionResponse])
async def list_sessions(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """List all call sessions — DB-persisted with sample data seeding."""
    await _ensure_sample_data(tenant_id, db)
    result = await db.execute(
        select(CallSession)
        .where(CallSession.tenant_id == tenant_id)
        .order_by(desc(CallSession.start_time))
    )
    sessions = result.scalars().all()
    return [_session_to_dict(s) for s in sessions]


@app.post("/sessions", response_model=CallSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    session: CallSessionCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Log a new call session."""
    s = CallSession(
        tenant_id=tenant_id,
        agent_id=session.agent_id,
        customer_id=session.customer_id,
        start_time=session.start_time,
        sentiment_score=session.sentiment_score,
        recording_url=session.recording_url,
        transcript=session.transcript,
    )
    db.add(s)
    await db.flush()
    await db.refresh(s)
    logging.info(f"New call session logged: {s.id}")
    return _session_to_dict(s)


@app.get("/sessions/{session_id}", response_model=CallSessionResponse)
async def get_session(
    session_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Get a single call session by ID."""
    result = await db.execute(
        select(CallSession).where(
            CallSession.id == session_id,
            CallSession.tenant_id == tenant_id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")
    return _session_to_dict(session)


@app.put("/sessions/{session_id}/end", response_model=CallSessionResponse)
async def end_session(
    session_id: uuid.UUID,
    payload: CallSessionEnd,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """End a call session — set end_time and duration."""
    result = await db.execute(
        select(CallSession).where(
            CallSession.id == session_id,
            CallSession.tenant_id == tenant_id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")
    session.end_time = payload.end_time
    session.duration_seconds = payload.duration_seconds
    await db.flush()
    await db.refresh(session)
    logging.info(f"Call session ended: {session.id} (duration: {payload.duration_seconds}s)")
    return _session_to_dict(session)


@app.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Delete a call session"""
    result = await db.execute(
        select(CallSession).where(
            CallSession.id == session_id,
            CallSession.tenant_id == tenant_id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")

    await db.delete(session)
    await db.flush()


# ── Analytics ────────────────────────────────────────────────────────────

@app.get("/analytics/sentiment")
async def get_realtime_sentiment(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Return aggregated sentiment analysis computed from DB call session data."""
    from sqlalchemy import func

    await _ensure_sample_data(tenant_id, db)

    # Compute average sentiment from call sessions
    result = await db.execute(
        select(
            func.count(CallSession.id),
            func.avg(CallSession.sentiment_score),
        ).where(
            CallSession.tenant_id == tenant_id,
            CallSession.sentiment_score.isnot(None),
        )
    )
    count, avg_sentiment = result.one()

    if count == 0:
        return {
            "overall_sentiment": 0.0,
            "positive_mentions": [],
            "negative_mentions": [],
            "alerts_count": 0,
            "critical_escalations": 0,
        }

    overall = round(float(avg_sentiment), 2) if avg_sentiment else 0.0

    # Determine alerts based on sentiment threshold
    alerts_result = await db.execute(
        select(func.count(CallSession.id)).where(
            CallSession.tenant_id == tenant_id,
            CallSession.sentiment_score < 0.5,
        )
    )
    alerts_count = alerts_result.scalar() or 0

    # Critical escalations: very low sentiment
    critical_result = await db.execute(
        select(func.count(CallSession.id)).where(
            CallSession.tenant_id == tenant_id,
            CallSession.sentiment_score < 0.3,
        )
    )
    critical_escalations = critical_result.scalar() or 0

    return {
        "overall_sentiment": overall,
        "total_sessions_analyzed": count,
        "positive_mentions": ["fast service", "helpful agent", "easy upgrade"] if overall > 0.6 else [],
        "negative_mentions": ["high price", "load shedding outage", "waiting time"] if overall < 0.8 else [],
        "alerts_count": alerts_count,
        "critical_escalations": critical_escalations,
    }


# ── Reports ──────────────────────────────────────────────────────────────

@app.post("/reports/import")
async def import_external_report(file: UploadFile = File(...)):
    """Import reports from CSV, Excel or PDF (Mock)"""
    logging.info(f"Importing report: {file.filename}")
    return {
        "status": "SUCCESS",
        "processed_records": 1500,
        "anomalies_detected": 3,
        "message": f"Report '{file.filename}' successfully integrated into Hub Intelligence."
    }


@app.get("/reports/intelligence")
async def get_hub_intelligence(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Return high-level management reports"""
    return {
        "resolution_rate": 92.0,
        "avg_talk_time_seconds": 252,
        "closed_queries": 642,
        "peak_volume_period": "17:00 - 19:00",
        "health_status": "OPTIMAL"
    }


# =========================================================================
# Deepgram Voice AI  —  Speech-to-Text  /  Text-to-Speech  /  Audio Intel
# =========================================================================

# --- Request / response schemas ---

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


# ---------- Speech-to-Text (Nova) ----------

@app.post("/ai/speech-to-text", response_model=TranscriptionResponse)
async def speech_to_text(
    file: UploadFile = File(...),
    language: str = Form("en"),
    model: str = Form("nova-2"),
    diarize: bool = Form(False),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Transcribe an uploaded audio file using Deepgram Nova STT."""
    try:
        audio_bytes = await file.read()
        result = await transcribe_audio(
            audio_bytes=audio_bytes,
            language=language,
            model=model,
            diarize=diarize,
        )
        return TranscriptionResponse(**result)
    except Exception as exc:
        logging.error(f"STT error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ai/speech-to-text/url", response_model=TranscriptionResponse)
async def speech_to_text_url(
    url: str = Form(...),
    language: str = Form("en"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Transcribe audio from a remote URL."""
    try:
        result = await transcribe_url(url=url, language=language)
        return TranscriptionResponse(**result)
    except Exception as exc:
        logging.error(f"STT URL error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------- Text-to-Speech (Aura) ----------

@app.post("/ai/text-to-speech")
async def text_to_speech(
    request: TTSRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Convert text to speech using Deepgram Aura TTS. Returns audio/mpeg."""
    try:
        audio_bytes = await synthesize_speech_simple(
            text=request.text,
            model=request.model,
        )
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "attachment; filename=speech.mp3"},
        )
    except Exception as exc:
        logging.error(f"TTS error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------- Audio Intelligence ----------

@app.post("/ai/audio-intelligence", response_model=AudioIntelligenceResponse)
async def audio_intelligence(
    file: UploadFile = File(...),
    language: str = Form("en"),
    summarize: bool = Form(True),
    sentiment: bool = Form(True),
    intents: bool = Form(True),
    topics: bool = Form(True),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """
    Full Audio Intelligence analysis: summarization, sentiment,
    intent detection, and topic detection on an uploaded audio file.
    """
    try:
        audio_bytes = await file.read()
        result = await analyze_audio(
            audio_bytes=audio_bytes,
            language=language,
            summarize=summarize,
            detect_sentiment=sentiment,
            detect_intents=intents,
            detect_topics=topics,
        )
        return AudioIntelligenceResponse(**result)
    except Exception as exc:
        logging.error(f"Audio Intelligence error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ai/audio-intelligence/url", response_model=AudioIntelligenceResponse)
async def audio_intelligence_url(
    url: str = Form(...),
    language: str = Form("en"),
    summarize: bool = Form(True),
    sentiment: bool = Form(True),
    intents: bool = Form(True),
    topics: bool = Form(True),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Run Audio Intelligence on a remote audio URL."""
    try:
        result = await analyze_audio_url(
            url=url,
            language=language,
            summarize=summarize,
            detect_sentiment=sentiment,
            detect_intents=intents,
            detect_topics=topics,
        )
        return AudioIntelligenceResponse(**result)
    except Exception as exc:
        logging.error(f"Audio Intelligence URL error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------- Summarization (standalone) ----------

@app.post("/ai/summarize")
async def summarize_call(
    file: UploadFile = File(...),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Quick call summarization endpoint."""
    try:
        audio_bytes = await file.read()
        result = await analyze_audio(
            audio_bytes=audio_bytes,
            summarize=True,
            detect_sentiment=False,
            detect_intents=False,
            detect_topics=False,
        )
        return {
            "summary": result["summary"],
            "transcript": result["transcript"],
            "confidence": result["confidence"],
        }
    except Exception as exc:
        logging.error(f"Summarize error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------- Sentiment Analysis (standalone) ----------

@app.post("/ai/sentiment")
async def sentiment_analysis(
    file: UploadFile = File(...),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Analyze sentiment of a call recording."""
    try:
        audio_bytes = await file.read()
        result = await analyze_audio(
            audio_bytes=audio_bytes,
            summarize=False,
            detect_sentiment=True,
            detect_intents=False,
            detect_topics=False,
        )
        return {
            "sentiments": result["sentiments"],
            "transcript": result["transcript"],
        }
    except Exception as exc:
        logging.error(f"Sentiment error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------- Intent Detection (standalone) ----------

@app.post("/ai/intents")
async def intent_detection(
    file: UploadFile = File(...),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Detect caller intents from a recording."""
    try:
        audio_bytes = await file.read()
        result = await analyze_audio(
            audio_bytes=audio_bytes,
            summarize=False,
            detect_sentiment=False,
            detect_intents=True,
            detect_topics=False,
        )
        return {
            "intents": result["intents"],
            "transcript": result["transcript"],
        }
    except Exception as exc:
        logging.error(f"Intent error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------- Topic Detection (standalone) ----------

@app.post("/ai/topics")
async def topic_detection(
    file: UploadFile = File(...),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Detect topics discussed in a call."""
    try:
        audio_bytes = await file.read()
        result = await analyze_audio(
            audio_bytes=audio_bytes,
            summarize=False,
            detect_sentiment=False,
            detect_intents=False,
            detect_topics=True,
        )
        return {
            "topics": result["topics"],
            "transcript": result["transcript"],
        }
    except Exception as exc:
        logging.error(f"Topic error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
