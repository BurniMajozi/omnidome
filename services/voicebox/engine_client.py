"""HTTP client for the vendored voicebox ML engine (services/voicebox/engine).

The engine is a heavy, separately-deployed container (PyTorch + several
TTS/STT models) that is NOT started by default — see the `voicebox-engine`
service in docker-compose.yaml. Every call here can legitimately fail with
"connection refused" until that container is brought up and its models are
downloaded; callers should surface that as a clear 503, not a stack trace.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# /generate/{id}/status is a Server-Sent Events stream (one `data: {...}`
# event per second) that the engine itself closes once status reaches a
# terminal state — not a one-shot JSON endpoint. We read it to completion
# rather than poll it. Generous timeout because the *first* call for a
# given engine/voice combination also downloads+loads that model (can take
# minutes); once loaded, subsequent calls finish in seconds.
GENERATION_STREAM_TIMEOUT_SECONDS = 600.0


class VoiceboxEngineUnavailable(RuntimeError):
    """Raised when the voicebox-engine container isn't reachable."""


def _engine_url() -> str:
    return os.getenv("VOICEBOX_ENGINE_URL", "http://voicebox-engine:17493")


def _client(timeout: float = 30.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=_engine_url(), timeout=timeout)


async def _request(method: str, path: str, timeout: float = 30.0, **kwargs) -> httpx.Response:
    try:
        async with _client(timeout=timeout) as client:
            resp = await client.request(method, path, **kwargs)
            resp.raise_for_status()
            return resp
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise VoiceboxEngineUnavailable(
            "voicebox-engine is not reachable. Bring it up with "
            "`docker compose --profile voicebox-engine up -d voicebox-engine` "
            "(first run downloads multi-GB models into VOICEBOX_MODELS_DIR)."
        ) from exc
    except httpx.TimeoutException as exc:
        raise VoiceboxEngineUnavailable(
            f"voicebox-engine timed out after {timeout}s on {method} {path} — likely still "
            "downloading/loading a model on its first use of this engine/voice. Retrying "
            "after it finishes loading should be fast."
        ) from exc


async def health() -> bool:
    try:
        async with _client(timeout=3.0) as client:
            resp = await client.get("/health")
            return resp.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Voice profiles (cloning / presets)
# ---------------------------------------------------------------------------

async def create_profile(
    name: str,
    description: Optional[str],
    language: str,
    voice_type: str,
    preset_engine: Optional[str] = None,
    preset_voice_id: Optional[str] = None,
    design_prompt: Optional[str] = None,
    default_engine: Optional[str] = None,
    personality: Optional[str] = None,
) -> dict:
    resp = await _request(
        "POST",
        "/profiles",
        json={
            "name": name,
            "description": description,
            "language": language,
            "voice_type": voice_type,
            "preset_engine": preset_engine,
            "preset_voice_id": preset_voice_id,
            "design_prompt": design_prompt,
            "default_engine": default_engine,
            "personality": personality,
        },
    )
    return resp.json()


async def add_profile_sample(
    engine_profile_id: str,
    audio_bytes: bytes,
    filename: str,
    reference_text: str,
) -> dict:
    """Upload a voice sample for cloning. This is the actual cloning step."""
    resp = await _request(
        "POST",
        f"/profiles/{engine_profile_id}/samples",
        files={"file": (filename, audio_bytes)},
        data={"reference_text": reference_text},
    )
    return resp.json()


async def delete_profile(engine_profile_id: str) -> None:
    try:
        await _request("DELETE", f"/profiles/{engine_profile_id}")
    except VoiceboxEngineUnavailable:
        # Engine already gone / never came up — local row deletion still proceeds.
        logger.warning("voicebox-engine unreachable while deleting profile %s; "
                        "deleting local record only", engine_profile_id)


async def list_presets(engine: str) -> dict:
    resp = await _request("GET", f"/profiles/presets/{engine}")
    return resp.json()


# ---------------------------------------------------------------------------
# Speech synthesis
# ---------------------------------------------------------------------------

async def _await_generation(generation_id: str) -> dict:
    """Read the /generate/{id}/status SSE stream to its terminal event.

    The engine emits one `data: {...}` event per second and closes the
    stream itself once status is "completed" or "failed" — so this reads
    to completion rather than polling a one-shot endpoint.
    """
    last_payload: dict = {}
    try:
        async with httpx.AsyncClient(
            base_url=_engine_url(), timeout=GENERATION_STREAM_TIMEOUT_SECONDS
        ) as client:
            async with client.stream("GET", f"/generate/{generation_id}/status") as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = json.loads(line[len("data: "):])
                    last_payload = payload
                    if payload.get("status") in ("completed", "failed", "not_found"):
                        return payload
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise VoiceboxEngineUnavailable(
            "voicebox-engine is not reachable. Bring it up with "
            "`docker compose --profile voicebox-engine up -d voicebox-engine` "
            "(first run downloads multi-GB models into VOICEBOX_MODELS_DIR)."
        ) from exc
    return last_payload


async def speak(
    text: str,
    profile: str,
    engine: Optional[str] = None,
    personality: Optional[bool] = None,
    language: str = "en",
) -> tuple[bytes, str]:
    """Synthesize speech. `profile` is the voicebox engine's profile id or name.

    Returns (audio_bytes, content_type). The first call for a given
    engine/voice combination also triggers a (slow) model download+load
    on the engine side; subsequent calls reuse the loaded model.
    """
    resp = await _request(
        "POST",
        "/speak",
        json={"text": text, "profile": profile, "engine": engine, "personality": personality, "language": language},
    )
    generation = resp.json()
    generation_id = generation["id"]
    status = generation.get("status", "generating")

    if status not in ("completed", "failed"):
        generation = await _await_generation(generation_id)
        status = generation.get("status", "generating")

    if status != "completed":
        raise RuntimeError(f"voicebox generation {generation_id} did not complete (status={status}): {generation.get('error')}")

    async with _client(timeout=30.0) as client:
        audio_resp = await client.get(f"/audio/{generation_id}")
        audio_resp.raise_for_status()
        content_type = audio_resp.headers.get("content-type", "audio/wav")
        return audio_resp.content, content_type


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

async def transcribe(audio_bytes: bytes, filename: str = "audio.wav", language: Optional[str] = None) -> dict:
    """Transcribe audio. The first call for a given Whisper model size also
    triggers a (slow) model download+load on the engine side — same
    generous timeout rationale as speak()."""
    data = {}
    if language:
        data["language"] = language
    resp = await _request(
        "POST",
        "/transcribe",
        timeout=GENERATION_STREAM_TIMEOUT_SECONDS,
        files={"file": (filename, audio_bytes)},
        data=data,
    )
    return resp.json()
