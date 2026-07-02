"""HTTP client for the vendored voicebox ML engine (services/voicebox/engine).

The engine is a heavy, separately-deployed container (PyTorch + several
TTS/STT models) that is NOT started by default -- see the `voicebox-engine`
service in docker-compose.yaml. Every call here can legitimately fail with
"connection refused" until that container is brought up and its models are
downloaded; callers should surface that as a clear 503, not a stack trace.

Connection pooling
------------------
A single module-level AsyncClient is initialised at startup and shared across
all coroutines.  Call `init_client()` in your FastAPI startup handler and
`close_client()` in your shutdown handler.  Concurrent use of a shared
AsyncClient is safe in asyncio (httpx guarantees this).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Maximum time to wait for the SSE generation-status stream to finish.
# First calls for a given engine/voice also download + load the model
# (can take minutes), so this is deliberately generous.
GENERATION_TOTAL_TIMEOUT_SECONDS = 600.0

# If the engine goes *silent* between SSE events for this long, raise a
# TimeoutException rather than hanging indefinitely.
_SSE_EVENT_TIMEOUT_SECONDS = 35.0


class VoiceboxEngineUnavailable(RuntimeError):
    """Raised when the voicebox-engine container is not reachable."""


# ---------------------------------------------------------------------------
# Module-level shared AsyncClient
# ---------------------------------------------------------------------------

_shared_client: Optional[httpx.AsyncClient] = None


def _engine_url() -> str:
    return os.getenv("VOICEBOX_ENGINE_URL", "http://voicebox-engine:17493")


def _default_timeout() -> httpx.Timeout:
    """Per-request timeout used for non-streaming calls."""
    return httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=5.0)


def _get_client() -> httpx.AsyncClient:
    """Return the shared client, lazily creating it if not yet initialised."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            base_url=_engine_url(),
            timeout=_default_timeout(),
        )
    return _shared_client


async def init_client() -> None:
    """Initialise the shared AsyncClient.  Call once at application startup."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            base_url=_engine_url(),
            timeout=_default_timeout(),
        )
    logger.info("voicebox engine client initialised (base_url=%s)", _engine_url())


async def close_client() -> None:
    """Close the shared AsyncClient.  Call once at application shutdown."""
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
        logger.info("voicebox engine client closed")
    _shared_client = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _wrap_unavailable(exc: Exception, method: str, path: str) -> VoiceboxEngineUnavailable:
    if isinstance(exc, httpx.TimeoutException):
        return VoiceboxEngineUnavailable(
            f"voicebox-engine timed out on {method} {path} -- the engine may still be "
            "downloading or loading a model on its first use. Retry after it finishes. "
            "Bring it up with: docker compose --profile voicebox-engine up -d voicebox-engine"
        )
    return VoiceboxEngineUnavailable(
        "voicebox-engine is not reachable. Bring it up with: "
        "docker compose --profile voicebox-engine up -d voicebox-engine "
        "(first run downloads multi-GB models into VOICEBOX_MODELS_DIR)."
    )


async def _request(
    method: str,
    path: str,
    timeout: Optional[httpx.Timeout] = None,
    **kwargs,
) -> httpx.Response:
    """Make a request using the shared client.

    Pass `timeout` to override the client's default for a specific call
    (e.g. transcription needs a longer read timeout).
    """
    client = _get_client()
    try:
        resp = await client.request(method, path, timeout=timeout, **kwargs)
        resp.raise_for_status()
        return resp
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise _wrap_unavailable(exc, method, path) from exc
    except httpx.TimeoutException as exc:
        raise _wrap_unavailable(exc, method, path) from exc


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

async def health() -> bool:
    try:
        client = _get_client()
        resp = await client.get("/health", timeout=httpx.Timeout(3.0))
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
    """Upload a voice sample for cloning.  This is the actual (slow) cloning step."""
    resp = await _request(
        "POST",
        f"/profiles/{engine_profile_id}/samples",
        timeout=httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=5.0),
        files={"file": (filename, audio_bytes)},
        data={"reference_text": reference_text},
    )
    return resp.json()


async def delete_profile(engine_profile_id: str) -> None:
    try:
        await _request("DELETE", f"/profiles/{engine_profile_id}")
    except VoiceboxEngineUnavailable:
        # Engine already gone / never came up -- local row deletion still proceeds.
        logger.warning(
            "voicebox-engine unreachable while deleting profile %s; "
            "deleting local record only", engine_profile_id
        )


async def list_presets(engine: str) -> dict:
    resp = await _request("GET", f"/profiles/presets/{engine}")
    return resp.json()


# ---------------------------------------------------------------------------
# Speech synthesis
# ---------------------------------------------------------------------------

async def _await_generation(generation_id: str) -> dict:
    """Read the /generate/{id}/status SSE stream until a terminal event.

    The engine emits one ``data: {...}`` event per second and closes the
    stream once status reaches "completed" or "failed".

    Per-event timeout: _SSE_EVENT_TIMEOUT_SECONDS (35 s) -- if the engine
    goes silent between events for longer than this, httpx raises a
    ReadTimeout.  Callers wrap this in asyncio.wait_for() for the overall
    GENERATION_TOTAL_TIMEOUT_SECONDS budget.
    """
    sse_timeout = httpx.Timeout(
        connect=10.0,
        read=_SSE_EVENT_TIMEOUT_SECONDS,
        write=5.0,
        pool=5.0,
    )
    last_payload: dict = {}
    client = _get_client()
    try:
        async with client.stream(
            "GET",
            f"/generate/{generation_id}/status",
            timeout=sse_timeout,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[len("data: "):])
                last_payload = payload
                if payload.get("status") in ("completed", "failed", "not_found"):
                    return payload
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise _wrap_unavailable(exc, "GET", f"/generate/{generation_id}/status") from exc
    return last_payload


async def speak(
    text: str,
    profile: str,
    engine: Optional[str] = None,
    personality: Optional[bool] = None,
    language: str = "en",
) -> tuple[bytes, str]:
    """Synthesize speech.

    `profile` is the voicebox engine's profile id or name.
    Returns ``(audio_bytes, content_type)``.

    The first call for a given engine/voice combination triggers a model
    download + load on the engine side; subsequent calls reuse the loaded
    model and finish in seconds.
    """
    resp = await _request(
        "POST",
        "/speak",
        json={
            "text": text,
            "profile": profile,
            "engine": engine,
            "personality": personality,
            "language": language,
        },
    )
    generation = resp.json()
    generation_id = generation["id"]
    gen_status = generation.get("status", "generating")

    if gen_status not in ("completed", "failed"):
        try:
            generation = await asyncio.wait_for(
                _await_generation(generation_id),
                timeout=GENERATION_TOTAL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                f"voicebox generation {generation_id} exceeded the "
                f"{GENERATION_TOTAL_TIMEOUT_SECONDS}s total timeout"
            ) from exc
        gen_status = generation.get("status", "generating")

    if gen_status != "completed":
        raise RuntimeError(
            f"voicebox generation {generation_id} did not complete "
            f"(status={gen_status}): {generation.get('error')}"
        )

    client = _get_client()
    audio_resp = await client.get(
        f"/audio/{generation_id}",
        timeout=httpx.Timeout(connect=10.0, read=60.0, write=5.0, pool=5.0),
    )
    audio_resp.raise_for_status()
    content_type = audio_resp.headers.get("content-type", "audio/wav")
    return audio_resp.content, content_type


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

async def transcribe(
    audio_bytes: bytes,
    filename: str = "audio.wav",
    language: Optional[str] = None,
) -> dict:
    """Transcribe audio.

    The first call for a given Whisper model size also triggers a model
    download + load on the engine side -- same generous timeout rationale
    as speak().
    """
    data = {}
    if language:
        data["language"] = language
    resp = await _request(
        "POST",
        "/transcribe",
        timeout=httpx.Timeout(
            connect=10.0,
            read=GENERATION_TOTAL_TIMEOUT_SECONDS,
            write=60.0,
            pool=5.0,
        ),
        files={"file": (filename, audio_bytes)},
        data=data,
    )
    return resp.json()
