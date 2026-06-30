"""Voicebox-backed Voice AI for OmniDome Call Center.

Replaces the prior Deepgram integration (Aura TTS / Nova-2 STT / Audio
Intelligence). STT and TTS now go through the `voicebox` service — see
services/voicebox — which proxies cloning/synthesis/transcription to the
vendored voicebox ML engine. Audio Intelligence (summary/sentiment/intent/
topic) doesn't exist in voicebox, so it's reconstructed here from the
transcript via the shared local-LLM text analyzer.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from services.common.text_intelligence import analyze_transcript

logger = logging.getLogger(__name__)


class VoiceboxUnavailable(RuntimeError):
    pass


def _voicebox_url() -> str:
    return os.getenv("VOICEBOX_SERVICE_URL", "http://voicebox:8027")


async def transcribe_audio(
    audio_bytes: bytes,
    tenant_id: str,
    language: str = "en",
    **_ignored,
) -> dict:
    """Transcribe an audio buffer via the voicebox service."""
    try:
        async with httpx.AsyncClient(base_url=_voicebox_url(), timeout=60.0) as client:
            resp = await client.post(
                "/transcribe",
                files={"file": ("audio.wav", audio_bytes)},
                data={"language": language},
                headers={"x-tenant-id": tenant_id},
            )
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 503:
            raise VoiceboxUnavailable(exc.response.json().get("detail", str(exc))) from exc
        raise

    return {
        "transcript": result.get("text", ""),
        "confidence": 1.0,
        "words": [],
        "metadata": {"duration": result.get("duration")},
    }


async def synthesize_speech(
    text: str,
    tenant_id: str,
    voice_profile_id: Optional[str] = None,
    scope: str = "call_center_agent",
    scope_ref: Optional[str] = None,
) -> bytes:
    """Synthesize speech via the voicebox service. Requires either a
    voice_profile_id or a scope_ref (e.g. a call_center_agent id) with a
    voice bound to it via PUT /svc/voicebox/bindings."""
    payload: dict = {"text": text, "requested_by_service": "call_center"}
    if voice_profile_id:
        payload["voice_profile_id"] = voice_profile_id
    elif scope_ref:
        payload["scope"] = scope
        payload["scope_ref"] = scope_ref
    else:
        raise ValueError("synthesize_speech requires voice_profile_id or scope_ref")

    try:
        async with httpx.AsyncClient(base_url=_voicebox_url(), timeout=120.0) as client:
            resp = await client.post("/speak", json=payload, headers={"x-tenant-id": tenant_id})
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 503:
            raise VoiceboxUnavailable(exc.response.json().get("detail", str(exc))) from exc
        raise


def _sentiment_label(score: float) -> str:
    if score > 0.15:
        return "positive"
    if score < -0.15:
        return "negative"
    return "neutral"


async def analyze_audio(
    audio_bytes: bytes,
    tenant_id: str,
    language: str = "en",
    **_ignored,
) -> dict:
    """Transcribe then run the transcript through the local-LLM text
    analyzer to reconstruct Deepgram Audio Intelligence's shape
    (summary/sentiment/intents/topics). There's no per-segment breakdown
    (the LLM analyzes the whole transcript at once), so segments carry a
    single entry covering the full transcript rather than Deepgram's
    multiple timestamped segments."""
    transcription = await transcribe_audio(audio_bytes, tenant_id=tenant_id, language=language)
    transcript = transcription["transcript"]
    intelligence = await analyze_transcript(transcript)
    sentiment_score = intelligence["sentiment"]

    return {
        "transcript": transcript,
        "confidence": transcription["confidence"],
        "words": transcription["words"],
        "summary": intelligence["summary"],
        "sentiments": {
            "average": {"sentiment": _sentiment_label(sentiment_score), "sentiment_score": sentiment_score},
            "segments": [{"text": transcript, "sentiment": _sentiment_label(sentiment_score), "sentiment_score": sentiment_score}] if transcript else [],
        },
        "intents": {
            "segments": [{"text": transcript, "intents": [{"intent": i, "confidence_score": 1.0} for i in intelligence["intents"]]}] if intelligence["intents"] else [],
        },
        "topics": {
            "segments": [{"text": transcript, "topics": [{"topic": t, "confidence_score": 1.0} for t in intelligence["topics"]]}] if intelligence["topics"] else [],
        },
        "metadata": transcription["metadata"],
    }
