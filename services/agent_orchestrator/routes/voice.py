"""Voice routes for agent orchestrator — STT input + TTS output for
Hermes/legacy agents. /voice/invoke wraps the existing text /invoke flow
so a caller can post audio in and get spoken audio back in one round trip.
"""

import base64
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from services.common.auth import AuthContext, get_auth_context
from services.agent_orchestrator.schemas import AgentInvokeRequest
from services.agent_orchestrator.routes.agents import invoke_agent
from services.agent_orchestrator.voice_client import speak, transcribe, VoiceboxUnavailable

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/{agent_type}/voice/transcribe")
async def voice_transcribe(
    agent_type: str,
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    """STT only — transcribe audio for use as agent input."""
    try:
        audio_bytes = await file.read()
        return await transcribe(audio_bytes, tenant_id=str(ctx.tenant_id), language=language)
    except VoiceboxUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/{agent_type}/voice/speak")
async def voice_speak(
    agent_type: str,
    text: str = Form(...),
    ctx: AuthContext = Depends(get_auth_context),
):
    """TTS only — speak arbitrary text in this agent type's bound voice."""
    try:
        audio_bytes, content_type = await speak(text, tenant_id=str(ctx.tenant_id), agent_type=agent_type)
        return Response(content=audio_bytes, media_type=content_type)
    except VoiceboxUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/{agent_type}/voice/invoke")
async def voice_invoke(
    agent_type: str,
    file: UploadFile = File(...),
    conversation_id: Optional[uuid.UUID] = Form(None),
    language: Optional[str] = Form(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Full voice round-trip: audio in -> transcript -> agent reply -> spoken audio out.

    Returns JSON with the transcript, the agent's text reply, and the
    reply audio base64-encoded (so a single response carries everything
    a voice UI needs without a second round trip).
    """
    try:
        audio_bytes = await file.read()
        transcription = await transcribe(audio_bytes, tenant_id=str(ctx.tenant_id), language=language)
    except VoiceboxUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    transcript = transcription.get("text", "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="No speech detected in audio")

    body = AgentInvokeRequest(agent_type=agent_type, message=transcript, conversation_id=conversation_id)
    invoke_result = await invoke_agent(body=body, ctx=ctx)

    response = {
        "conversation_id": str(invoke_result.conversation_id),
        "transcript": transcript,
        "message": invoke_result.message,
    }

    try:
        audio_reply, content_type = await speak(invoke_result.message, tenant_id=str(ctx.tenant_id), agent_type=agent_type)
        response["audio_base64"] = base64.b64encode(audio_reply).decode("ascii")
        response["audio_content_type"] = content_type
    except VoiceboxUnavailable as exc:
        # Text reply still succeeded — surface that even if speech synthesis is down.
        response["audio_unavailable"] = str(exc)

    return response
