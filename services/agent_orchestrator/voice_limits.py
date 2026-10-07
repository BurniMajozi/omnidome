"""Input limits and per-tenant rate limiting for the voice routes."""

from __future__ import annotations

import io
import os
import re
import time
import wave
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from fastapi import HTTPException, UploadFile


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def max_audio_bytes() -> int:
    return _int_env("VOICE_MAX_AUDIO_BYTES", 5 * 1024 * 1024)


def max_audio_seconds() -> int:
    return _int_env("VOICE_MAX_AUDIO_SECONDS", 60)


def max_tts_chars() -> int:
    return _int_env("VOICE_MAX_TTS_CHARS", 2000)


def rate_limit_per_minute() -> int:
    return _int_env("VOICE_RATE_LIMIT_PER_MINUTE", 20)


def third_party_fallback_enabled() -> bool:
    """OpenRouter STT/TTS sends tenant audio/text to a third party; off unless explicitly enabled."""
    return os.getenv("VOICE_ALLOW_THIRD_PARTY_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"}


_AGENT_TYPE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,50}$")
_hits: Dict[str, Deque[float]] = defaultdict(deque)


def check_agent_type(agent_type: str) -> None:
    if not _AGENT_TYPE_RE.match(agent_type or ""):
        raise HTTPException(status_code=400, detail="Invalid agent type")


def check_rate_limit(tenant_id: str, now: Optional[float] = None) -> None:
    """Sliding one-minute window per tenant (per process)."""
    limit = rate_limit_per_minute()
    if limit <= 0:
        return
    t = time.monotonic() if now is None else now
    window = _hits[str(tenant_id)]
    while window and t - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(status_code=429, detail="Voice rate limit exceeded; try again shortly",
                            headers={"Retry-After": "60"})
    window.append(t)


def wav_duration_seconds(data: bytes) -> Optional[float]:
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            rate = wf.getframerate()
            return wf.getnframes() / rate if rate else None
    except (wave.Error, EOFError):
        return None


def check_audio(data: bytes) -> None:
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    if len(data) > max_audio_bytes():
        raise HTTPException(status_code=413, detail=f"Audio exceeds {max_audio_bytes()} bytes")
    duration = wav_duration_seconds(data)
    if duration is not None and duration > max_audio_seconds():
        raise HTTPException(status_code=413, detail=f"Audio exceeds {max_audio_seconds()} seconds")


async def read_audio(file: UploadFile) -> bytes:
    """Read at most limit+1 bytes so an oversized upload is never fully buffered."""
    data = await file.read(max_audio_bytes() + 1)
    check_audio(data)
    return data


def check_tts_text(text: str) -> None:
    if not (text or "").strip():
        raise HTTPException(status_code=400, detail="Text is required")
    if len(text) > max_tts_chars():
        raise HTTPException(status_code=413, detail=f"Text exceeds {max_tts_chars()} characters")
