"""Input limits and per-tenant rate limiting for the voice routes.

Rate limit: shared across workers/replicas through the DB (agent_rate_limits, one
atomic upsert per tenant+bucket+one-minute window; table created lazily). Only when
the DB is unavailable does it fall back, with a warning, to the in-process sliding
window. Duration: WAV is measured exactly; other formats use `mutagen` if importable,
else a size ceiling of max_seconds * a conservative max bitrate for the format.
Nothing shells out.
"""

from __future__ import annotations

import io
import logging
import os
import re
import time
import wave
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy import text

logger = logging.getLogger(__name__)


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


RATE_BUCKET = "voice"
RATE_WINDOW_SECONDS = 60
RATE_SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS agent_rate_limits (
    tenant_id VARCHAR(64) NOT NULL,
    bucket VARCHAR(40) NOT NULL,
    window_start BIGINT NOT NULL,
    hits INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, bucket, window_start)
)"""
RATE_HIT_SQL = """INSERT INTO agent_rate_limits (tenant_id, bucket, window_start, hits)
VALUES (:t, :b, CAST(floor(extract(epoch FROM now()) / :w) AS BIGINT), 1)
ON CONFLICT (tenant_id, bucket, window_start) DO UPDATE SET hits = agent_rate_limits.hits + 1
RETURNING hits, :w - (CAST(extract(epoch FROM now()) AS BIGINT) % :w)"""
_rate_schema_ready = False
_calls_since_prune = 0


async def check_rate_limit_shared(tenant_id: str, bucket: str = RATE_BUCKET) -> None:
    """Fixed one-minute window per tenant+bucket, counted in the DB so every replica
    shares it. Raises 429 over the limit. DB unavailable -> per-process limiter."""
    global _rate_schema_ready, _calls_since_prune
    limit = rate_limit_per_minute()
    if limit <= 0:
        return
    try:
        from services.common.db import session_scope

        params = {"t": str(tenant_id), "b": bucket, "w": RATE_WINDOW_SECONDS}
        async with session_scope() as session:
            if not _rate_schema_ready:
                await session.execute(text(RATE_SCHEMA_SQL))
                _rate_schema_ready = True
            hits, retry_after = (await session.execute(text(RATE_HIT_SQL), params)).one()
            _calls_since_prune += 1
            if _calls_since_prune >= 200:  # drop windows older than ten minutes
                _calls_since_prune = 0
                await session.execute(text(
                    "DELETE FROM agent_rate_limits WHERE window_start < "
                    "CAST(floor(extract(epoch FROM now()) / :w) AS BIGINT) - 10"), params)
    except Exception as exc:  # noqa: BLE001 - DB down must not take voice down, but must be visible
        logger.warning("shared voice rate limit unavailable, using in-process limiter: %s", exc)
        check_rate_limit(tenant_id)
        return
    if int(hits) > limit:
        raise HTTPException(status_code=429, detail="Voice rate limit exceeded; try again shortly",
                            headers={"Retry-After": str(max(1, int(retry_after)))})


def wav_duration_seconds(data: bytes) -> Optional[float]:
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            rate = wf.getframerate()
            return wf.getnframes() / rate if rate else None
    except (wave.Error, EOFError):
        return None


# Conservative (high) ceiling on bits/second per container, so a clip is only rejected
# when it is too big to possibly fit in max_seconds. Not a duration measurement.
MAX_BITRATE_BPS = {
    "mp3": 320_000,
    "ogg": 510_000,
    "webm": 510_000,
    "m4a": 512_000,
    "flac": 3_000_000,
}
_EXT_FORMAT = {"mp3": "mp3", "mpeg": "mp3", "mpga": "mp3", "ogg": "ogg", "oga": "ogg", "opus": "ogg",
               "webm": "webm", "weba": "webm", "m4a": "m4a", "mp4": "m4a", "aac": "m4a", "flac": "flac",
               "wav": "wav", "wave": "wav", "x-wav": "wav"}


def sniff_format(data: bytes) -> Optional[str]:
    head = data[:12]
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"fLaC":
        return "flac"
    if head[:4] == bytes([0x1A, 0x45, 0xDF, 0xA3]):
        return "webm"
    if head[4:8] == b"ftyp":
        return "m4a"
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "mp3"
    return None


def declared_format(content_type: Optional[str] = None, filename: Optional[str] = None) -> Optional[str]:
    ctype = (content_type or "").split(";")[0].strip().lower()
    if "/" in ctype:
        fmt = _EXT_FORMAT.get(ctype.split("/", 1)[1].replace("x-", ""))
        if fmt:
            return fmt
    ext = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    return _EXT_FORMAT.get(ext)


def mutagen_duration_seconds(data: bytes) -> Optional[float]:
    """Real duration via mutagen when it happens to be installed; None otherwise."""
    try:
        import mutagen  # type: ignore
    except ImportError:
        return None
    try:
        parsed = mutagen.File(io.BytesIO(data))
        length = getattr(getattr(parsed, "info", None), "length", None)
        return float(length) if length else None
    except Exception:  # noqa: BLE001 - unparseable audio falls back to the size ceiling
        return None


def check_audio(data: bytes, fmt: Optional[str] = None) -> None:
    """`fmt` is the declared format (see declared_format); the sniffed container wins."""
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    if len(data) > max_audio_bytes():
        raise HTTPException(status_code=413, detail=f"Audio exceeds {max_audio_bytes()} bytes")
    limit_s = max_audio_seconds()
    fmt = sniff_format(data) or fmt
    duration = wav_duration_seconds(data) if fmt in (None, "wav") else mutagen_duration_seconds(data)
    if duration is not None:
        if duration > limit_s:
            raise HTTPException(status_code=413, detail=f"Audio exceeds {limit_s} seconds")
        return
    bitrate = MAX_BITRATE_BPS.get(fmt or "")
    if bitrate and len(data) > limit_s * bitrate // 8:
        raise HTTPException(status_code=413, detail=f"Audio exceeds {limit_s} seconds")


async def read_audio(file: UploadFile) -> bytes:
    """Read at most limit+1 bytes so an oversized upload is never fully buffered."""
    data = await file.read(max_audio_bytes() + 1)
    check_audio(data, declared_format(getattr(file, "content_type", None), getattr(file, "filename", None)))
    return data


def check_tts_text(text: str) -> None:
    if not (text or "").strip():
        raise HTTPException(status_code=400, detail="Text is required")
    if len(text) > max_tts_chars():
        raise HTTPException(status_code=413, detail=f"Text exceeds {max_tts_chars()} characters")
