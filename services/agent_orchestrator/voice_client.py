"""HTTP client for the `voicebox` service — gives Hermes/legacy agents
voice output (TTS, via a per-agent-type voice binding) and STT input.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class VoiceboxUnavailable(RuntimeError):
    pass


def _voicebox_url() -> str:
    return os.getenv("VOICEBOX_SERVICE_URL", "http://voicebox:8027")


# Generous timeout: the first transcribe/speak call for a given engine/voice
# combination also triggers a (slow) model download+load on the voicebox
# engine side — too-short timeouts here surface as a confusing empty-message
# error since str(httpx.TimeoutException()) is empty.
_VOICEBOX_CALL_TIMEOUT_SECONDS = 600.0


async def transcribe(audio_bytes: bytes, tenant_id: str, user_id: Optional[str] = None, language: Optional[str] = None) -> dict:
    try:
        async with httpx.AsyncClient(base_url=_voicebox_url(), timeout=_VOICEBOX_CALL_TIMEOUT_SECONDS) as client:
            data = {"language": language} if language else {}
            resp = await client.post(
                "/transcribe",
                files={"file": ("audio.wav", audio_bytes)},
                data=data,
                headers={"x-tenant-id": tenant_id, "x-user-id": user_id or tenant_id},
            )
            resp.raise_for_status()
            result = resp.json()
            return {"text": result.get("text", ""), "duration": result.get("duration")}
    except Exception as exc:
        logger.info("Voicebox unavailable (%s); falling back to OpenRouter STT", exc)
        try:
            from services.agent_orchestrator.voice import transcribe_audio
            text = await transcribe_audio(audio_bytes)
            if text:
                return {"text": text, "duration": None}
        except Exception as fallback_exc:
            logger.error("OpenRouter STT fallback failed: %s", fallback_exc)
        raise VoiceboxUnavailable(f"Voicebox service unavailable and fallback failed: {exc}") from exc


async def speak(text: str, tenant_id: str, agent_type: str, user_id: Optional[str] = None) -> tuple[bytes, str]:
    """Synthesize speech using the voice bound to this orchestrator agent
    type (scope=orchestrator_agent_type, scope_ref=agent_type) — set via
    PUT /svc/voicebox/bindings."""
    try:
        async with httpx.AsyncClient(base_url=_voicebox_url(), timeout=_VOICEBOX_CALL_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                "/speak",
                json={
                    "text": text,
                    "scope": "orchestrator_agent_type",
                    "scope_ref": agent_type,
                    "requested_by_service": "agent_orchestrator",
                },
                headers={"x-tenant-id": tenant_id, "x-user-id": user_id or tenant_id},
            )
            resp.raise_for_status()
            return resp.content, resp.headers.get("content-type", "audio/wav")
    except Exception as exc:
        logger.info("Voicebox unavailable (%s); falling back to OpenRouter TTS", exc)
        try:
            from services.agent_orchestrator.voice import synthesize_speech
            audio_content = await synthesize_speech(text)
            if audio_content:
                return audio_content, "audio/mpeg"
        except Exception as fallback_exc:
            logger.error("OpenRouter TTS fallback failed: %s", fallback_exc)
        raise VoiceboxUnavailable(f"Voicebox service unavailable and fallback failed: {exc}") from exc
