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


async def transcribe(audio_bytes: bytes, tenant_id: str, language: Optional[str] = None) -> dict:
    try:
        async with httpx.AsyncClient(base_url=_voicebox_url(), timeout=60.0) as client:
            data = {"language": language} if language else {}
            resp = await client.post(
                "/transcribe",
                files={"file": ("audio.wav", audio_bytes)},
                data=data,
                headers={"x-tenant-id": tenant_id},
            )
            resp.raise_for_status()
            result = resp.json()
            return {"text": result.get("text", ""), "duration": result.get("duration")}
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 503:
            raise VoiceboxUnavailable(exc.response.json().get("detail", str(exc))) from exc
        raise


async def speak(text: str, tenant_id: str, agent_type: str) -> tuple[bytes, str]:
    """Synthesize speech using the voice bound to this orchestrator agent
    type (scope=orchestrator_agent_type, scope_ref=agent_type) — set via
    PUT /svc/voicebox/bindings."""
    try:
        async with httpx.AsyncClient(base_url=_voicebox_url(), timeout=120.0) as client:
            resp = await client.post(
                "/speak",
                json={
                    "text": text,
                    "scope": "orchestrator_agent_type",
                    "scope_ref": agent_type,
                    "requested_by_service": "agent_orchestrator",
                },
                headers={"x-tenant-id": tenant_id},
            )
            resp.raise_for_status()
            return resp.content, resp.headers.get("content-type", "audio/wav")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (503, 404, 409):
            raise VoiceboxUnavailable(exc.response.json().get("detail", str(exc))) from exc
        raise
