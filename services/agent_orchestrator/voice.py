"""Voice Input (STT) and Voice Output (TTS) services for OmniDome Agents.

Follows OpenRouter Multimodal STT/TTS API specifications:
- STT: POST https://openrouter.ai/api/v1/audio/transcriptions
- TTS: POST https://openrouter.ai/api/v1/audio/speech
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from services.agent_orchestrator.config import settings

logger = logging.getLogger("agent_orchestrator.voice")

OPENROUTER_STT_URL = "https://openrouter.ai/api/v1/audio/transcriptions"
OPENROUTER_TTS_URL = "https://openrouter.ai/api/v1/audio/speech"


async def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "voice-input.wav",
    content_type: str = "audio/wav",
    model: str = "openai/whisper-1",
) -> str:
    """Transcribe speech audio to text via OpenRouter Speech-to-Text API."""
    api_key = (
        getattr(settings, "openrouter_api_key", "")
        or os.getenv("OPENROUTER_API_KEY", "")
    ).strip().strip("'\"")

    if not api_key:
        logger.warning("OPENROUTER_API_KEY missing for voice transcription; returning empty.")
        return ""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "OmniDome-Agent-Orchestrator/1.0",
    }

    files = {
        "file": (filename, audio_bytes, content_type),
    }
    data = {
        "model": model,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                OPENROUTER_STT_URL,
                headers=headers,
                files=files,
                data=data,
            )

        if resp.status_code == 200:
            res_json = resp.json()
            return res_json.get("text", "").strip()
        logger.error("OpenRouter STT returned %d: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.exception("Voice transcription failed: %s", exc)

    return ""


async def synthesize_speech(
    text: str,
    voice: str = "alloy",
    model: str = "openai/gpt-4o-mini-tts-2025-12-15",
    response_format: str = "mp3",
) -> bytes:
    """Synthesize text into speech audio bytes via OpenRouter Text-to-Speech API."""
    api_key = (
        getattr(settings, "openrouter_api_key", "")
        or os.getenv("OPENROUTER_API_KEY", "")
    ).strip().strip("'\"")

    if not api_key:
        logger.warning("OPENROUTER_API_KEY missing for voice synthesis.")
        return b""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "OmniDome-Agent-Orchestrator/1.0",
    }

    payload = {
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": response_format,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                OPENROUTER_TTS_URL,
                headers=headers,
                json=payload,
            )

        if resp.status_code == 200:
            return resp.content
        logger.error("OpenRouter TTS returned %d: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.exception("Voice synthesis failed: %s", exc)

    return b""
