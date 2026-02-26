from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid
from datetime import datetime
import logging
from services.common.entitlements import EntitlementGuard
from services.common.auth import get_current_tenant_id

from services.call_center.deepgram_service import (
    transcribe_audio,
    transcribe_url,
    synthesize_speech_simple,
    analyze_audio,
    analyze_audio_url,
)

app = FastAPI(title="CoreConnect Call Center Service", version="0.1.0")
guard = EntitlementGuard(module_id="call_center")


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)

# --- Models ---
class Agent(BaseModel):
    id: uuid.UUID
    name: str
    extension: str
    status: str
    daily_sales: float
    mttr_minutes: float
    csat_score: float

class Script(BaseModel):
    id: Optional[uuid.UUID]
    title: str
    category: str
    content: str
    active: bool = True

class CallSession(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    start_time: datetime
    end_time: Optional[datetime]
    sentiment_score: float # 0.0 to 1.0
    duration_seconds: int

# --- Routes ---
@app.get("/")
async def root():
    return {"message": "CoreConnect Call Center Service is active"}

@app.get("/agents", response_model=List[Agent])
async def list_agents(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return [
        Agent(id=uuid.uuid4(), name="Sipho Nkosi", extension="1001", status="ON_CALL", daily_sales=12400.0, mttr_minutes=5.2, csat_score=4.8),
        Agent(id=uuid.uuid4(), name="Jane Doe", extension="1005", status="IDLE", daily_sales=8500.0, mttr_minutes=4.8, csat_score=4.9)
    ]

@app.post("/scripts", status_code=status.HTTP_201_CREATED)
async def create_script(script: Script, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    script.id = uuid.uuid4()
    logging.info(f"New script created: {script.title}")
    return script

@app.get("/scripts", response_model=List[Script])
async def list_scripts(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return [
        Script(id=uuid.uuid4(), title="Sales: Fiber Upgrade", category="Sales", content="Targeting existing customers...", active=True),
        Script(id=uuid.uuid4(), title="Support: Troubleshooting", category="Support", content="Step-by-step guide...", active=True)
    ]

@app.get("/analytics/sentiment")
async def get_realtime_sentiment(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Return aggregated sentiment analysis for the last 60 minutes"""
    return {
        "overall_sentiment": 0.78,
        "positive_mentions": ["fast service", "helpful agent", "easy upgrade"],
        "negative_mentions": ["high price", "load shedding outage", "waiting time"],
        "alerts_count": 2,
        "critical_escalations": 1
    }

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

# --- Request / Response schemas ---
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
