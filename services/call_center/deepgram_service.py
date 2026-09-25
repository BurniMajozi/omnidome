"""Deepgram Voice AI Service for OmniDome Call Center.

Provides full alignment with Deepgram's Speech-to-Text (Nova-3, Nova-2),
Text-to-Speech (Aura), Audio Intelligence (summarization, sentiment, intents, topics),
and streaming transcription capabilities.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("call_center.deepgram")

DEEPGRAM_BASE_URL = os.getenv("DEEPGRAM_BASE_URL", "https://api.deepgram.com/v1")
DEEPGRAM_TIMEOUT_SECONDS = float(os.getenv("DEEPGRAM_TIMEOUT_SECONDS", "60.0"))


class DeepgramError(RuntimeError):
    """Raised when a Deepgram API call fails or is unconfigured."""
    pass


def get_deepgram_api_key() -> str:
    key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    if not key:
        raise DeepgramError("DEEPGRAM_API_KEY is not configured in the environment.")
    return key


def _get_headers(content_type: str = "application/json") -> Dict[str, str]:
    return {
        "Authorization": f"Token {get_deepgram_api_key()}",
        "Content-Type": content_type,
    }


# Voice model mappings for backwards compatibility and easy selection
VOICE_MAP = {
    "voicebox-nova": "aura-asteria-en",
    "voicebox-orion": "aura-orion-en",
    "voicebox-luna": "aura-luna-en",
    "voicebox-atlas": "aura-helios-en",
    "nova": "aura-asteria-en",
    "orion": "aura-orion-en",
    "luna": "aura-luna-en",
    "atlas": "aura-helios-en",
}

STT_MODEL_MAP = {
    "whisper-large-v3": "nova-3",
    "whisper-medium": "nova-2",
    "whisper-base": "nova-2",
    "nova": "nova-3",
}

AURA_VOICES = [
    {
        "id": "aura-asteria-en",
        "name": "Aura Asteria",
        "gender": "female",
        "language": "en",
        "description": "Warm, conversational, natural American English female",
        "voice_type": "preset",
        "status": "ready",
    },
    {
        "id": "aura-luna-en",
        "name": "Aura Luna",
        "gender": "female",
        "language": "en",
        "description": "Playful, friendly, casual American English female",
        "voice_type": "preset",
        "status": "ready",
    },
    {
        "id": "aura-stella-en",
        "name": "Aura Stella",
        "gender": "female",
        "language": "en",
        "description": "Expressive, upbeat, energetic female",
        "voice_type": "preset",
        "status": "ready",
    },
    {
        "id": "aura-athena-en",
        "name": "Aura Athena",
        "gender": "female",
        "language": "en",
        "description": "Professional, calm, authoritative British English female",
        "voice_type": "preset",
        "status": "ready",
    },
    {
        "id": "aura-hera-en",
        "name": "Aura Hera",
        "gender": "female",
        "language": "en",
        "description": "Authoritative, polished, executive female",
        "voice_type": "preset",
        "status": "ready",
    },
    {
        "id": "aura-orion-en",
        "name": "Aura Orion",
        "gender": "male",
        "language": "en",
        "description": "Calm, confident, natural American English male",
        "voice_type": "preset",
        "status": "ready",
    },
    {
        "id": "aura-arcas-en",
        "name": "Aura Arcas",
        "gender": "male",
        "language": "en",
        "description": "Casual, conversational, relatable American English male",
        "voice_type": "preset",
        "status": "ready",
    },
    {
        "id": "aura-perseus-en",
        "name": "Aura Perseus",
        "gender": "male",
        "language": "en",
        "description": "Energetic, dynamic, enthusiastic male",
        "voice_type": "preset",
        "status": "ready",
    },
    {
        "id": "aura-angus-en",
        "name": "Aura Angus",
        "gender": "male",
        "language": "en",
        "description": "Deep, formal, resonant Scottish English male",
        "voice_type": "preset",
        "status": "ready",
    },
    {
        "id": "aura-orpheus-en",
        "name": "Aura Orpheus",
        "gender": "male",
        "language": "en",
        "description": "Smooth, confident, charismatic American English male",
        "voice_type": "preset",
        "status": "ready",
    },
    {
        "id": "aura-helios-en",
        "name": "Aura Helios",
        "gender": "male",
        "language": "en",
        "description": "Warm, reassuring, empathetic male",
        "voice_type": "preset",
        "status": "ready",
    },
    {
        "id": "aura-zeus-en",
        "name": "Aura Zeus",
        "gender": "male",
        "language": "en",
        "description": "Deep, strong, authoritative American English male",
        "voice_type": "preset",
        "status": "ready",
    },
]


def list_voices() -> List[Dict[str, Any]]:
    """Return available Deepgram Aura voices for UI selection."""
    return AURA_VOICES


async def transcribe_audio(
    audio_bytes: bytes,
    tenant_id: str = "",
    language: str = "en",
    model: str = "nova-3",
    smart_format: bool = True,
    punctuate: bool = True,
    diarize: bool = False,
    user_id: Optional[str] = None,
    **_kwargs,
) -> Dict[str, Any]:
    """Transcribe an audio buffer using Deepgram Nova-3 / Nova-2 STT."""
    resolved_model = STT_MODEL_MAP.get(model, model)
    headers = _get_headers(content_type="audio/*")
    params = {
        "model": resolved_model,
        "language": language,
        "smart_format": str(smart_format).lower(),
        "punctuate": str(punctuate).lower(),
        "diarize": str(diarize).lower(),
    }

    try:
        async with httpx.AsyncClient(timeout=DEEPGRAM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{DEEPGRAM_BASE_URL}/listen",
                params=params,
                headers=headers,
                content=audio_bytes,
            )
            if resp.status_code != 200:
                logger.error(f"Deepgram STT failed [{resp.status_code}]: {resp.text}")
                raise DeepgramError(f"Deepgram STT error: {resp.text}")

            data = resp.json()
    except httpx.TimeoutException as exc:
        raise DeepgramError("Deepgram STT request timed out.") from exc
    except httpx.RequestError as exc:
        raise DeepgramError(f"Deepgram STT network error: {exc}") from exc

    channels = data.get("results", {}).get("channels", [])
    transcript = ""
    confidence = 0.0
    words: List[Dict[str, Any]] = []

    if channels:
        alt = channels[0].get("alternatives", [{}])[0]
        transcript = alt.get("transcript", "")
        confidence = float(alt.get("confidence", 0.0))
        for w in alt.get("words", []):
            words.append({
                "word": w.get("word", ""),
                "start": float(w.get("start", 0.0)),
                "end": float(w.get("end", 0.0)),
                "confidence": float(w.get("confidence", 0.0)),
                "speaker": w.get("speaker"),
            })

    metadata = data.get("metadata", {})
    return {
        "transcript": transcript,
        "confidence": confidence,
        "words": words,
        "metadata": {
            "duration": metadata.get("duration"),
            "channels": metadata.get("channels"),
            "models": metadata.get("models"),
            "model_info": metadata.get("model_info"),
        },
    }


async def transcribe_url(
    url: str,
    language: str = "en",
    model: str = "nova-3",
    smart_format: bool = True,
    punctuate: bool = True,
    diarize: bool = False,
) -> Dict[str, Any]:
    """Transcribe audio from a remote URL via Deepgram."""
    resolved_model = STT_MODEL_MAP.get(model, model)
    headers = _get_headers(content_type="application/json")
    params = {
        "model": resolved_model,
        "language": language,
        "smart_format": str(smart_format).lower(),
        "punctuate": str(punctuate).lower(),
        "diarize": str(diarize).lower(),
    }

    try:
        async with httpx.AsyncClient(timeout=DEEPGRAM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{DEEPGRAM_BASE_URL}/listen",
                params=params,
                headers=headers,
                json={"url": url},
            )
            if resp.status_code != 200:
                raise DeepgramError(f"Deepgram transcribe_url failed: {resp.text}")
            data = resp.json()
    except Exception as exc:
        raise DeepgramError(f"Deepgram transcribe_url error: {exc}") from exc

    channels = data.get("results", {}).get("channels", [])
    transcript = ""
    confidence = 0.0

    if channels:
        alt = channels[0].get("alternatives", [{}])[0]
        transcript = alt.get("transcript", "")
        confidence = float(alt.get("confidence", 0.0))

    return {
        "transcript": transcript,
        "confidence": confidence,
        "metadata": data.get("metadata", {}),
    }


async def synthesize_speech(
    text: str,
    tenant_id: str = "",
    model: str = "aura-asteria-en",
    encoding: str = "mp3",
    voice_profile_id: Optional[str] = None,
    scope_ref: Optional[str] = None,
    user_id: Optional[str] = None,
    **_kwargs,
) -> bytes:
    """Convert text to speech via Deepgram Aura TTS. Returns audio bytes."""
    # Resolve voice profile or voice ID if supplied
    voice = model
    if voice_profile_id:
        voice = VOICE_MAP.get(str(voice_profile_id), str(voice_profile_id))
    elif scope_ref:
        voice = VOICE_MAP.get(str(scope_ref), str(scope_ref))

    # Ensure voice has valid aura format
    if not voice.startswith("aura-"):
        voice = VOICE_MAP.get(voice, "aura-asteria-en")

    headers = _get_headers(content_type="application/json")
    params = {
        "model": voice,
        "encoding": encoding,
    }

    try:
        async with httpx.AsyncClient(timeout=DEEPGRAM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{DEEPGRAM_BASE_URL}/speak",
                params=params,
                headers=headers,
                json={"text": text},
            )
            if resp.status_code != 200:
                logger.error(f"Deepgram TTS failed [{resp.status_code}]: {resp.text}")
                raise DeepgramError(f"Deepgram TTS error: {resp.text}")
            return resp.content
    except httpx.TimeoutException as exc:
        raise DeepgramError("Deepgram TTS request timed out.") from exc
    except httpx.RequestError as exc:
        raise DeepgramError(f"Deepgram TTS network error: {exc}") from exc


async def analyze_audio(
    audio_bytes: bytes,
    tenant_id: str = "",
    language: str = "en",
    summarize: bool = True,
    sentiment: bool = True,
    intents: bool = True,
    topics: bool = True,
    user_id: Optional[str] = None,
    **_kwargs,
) -> Dict[str, Any]:
    """Run full Deepgram Audio Intelligence analysis on an audio buffer.
    
    Produces:
    - Accurate Nova-2 transcript
    - Native summarization (summary text)
    - Sentiment analysis (overall average score and segmented timeline)
    - Intent detection (segmented intent classifications and confidence)
    - Topic detection (segmented conversation topics and confidence)
    """
    headers = _get_headers(content_type="audio/*")
    params: Dict[str, Any] = {
        "model": "nova-2",  # Audio Intelligence models run on Nova-2
        "language": language,
        "smart_format": "true",
        "punctuate": "true",
        "diarize": "true",
    }
    if summarize:
        params["summarize"] = "v2"
    if sentiment:
        params["sentiment"] = "true"
    if intents:
        params["intents"] = "true"
    if topics:
        params["topics"] = "true"

    try:
        async with httpx.AsyncClient(timeout=DEEPGRAM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{DEEPGRAM_BASE_URL}/listen",
                params=params,
                headers=headers,
                content=audio_bytes,
            )
            if resp.status_code != 200:
                logger.error(f"Deepgram Audio Intelligence failed [{resp.status_code}]: {resp.text}")
                raise DeepgramError(f"Deepgram Audio Intelligence error: {resp.text}")
            data = resp.json()
    except httpx.TimeoutException as exc:
        raise DeepgramError("Deepgram Audio Intelligence request timed out.") from exc
    except httpx.RequestError as exc:
        raise DeepgramError(f"Deepgram Audio Intelligence network error: {exc}") from exc

    results = data.get("results", {})

    # Extract transcript & confidence
    channels = results.get("channels", [])
    transcript = ""
    confidence = 0.0
    words = []
    if channels:
        alt = channels[0].get("alternatives", [{}])[0]
        transcript = alt.get("transcript", "")
        confidence = float(alt.get("confidence", 0.0))
        for w in alt.get("words", []):
            words.append({
                "word": w.get("word", ""),
                "start": float(w.get("start", 0.0)),
                "end": float(w.get("end", 0.0)),
                "confidence": float(w.get("confidence", 0.0)),
                "speaker": w.get("speaker"),
            })

    # Summary
    summary_data = results.get("summary", {})
    summary_text = summary_data.get("short", "") if isinstance(summary_data, dict) else str(summary_data)

    # Sentiments
    sentiments_data = results.get("sentiments", {})
    avg_sentiment = sentiments_data.get("average", {}) if isinstance(sentiments_data, dict) else {}
    sentiment_segments = sentiments_data.get("segments", []) if isinstance(sentiments_data, dict) else []

    # Intents
    intents_data = results.get("intents", {})
    intent_segments = intents_data.get("segments", []) if isinstance(intents_data, dict) else []

    # Topics
    topics_data = results.get("topics", {})
    topic_segments = topics_data.get("segments", []) if isinstance(topics_data, dict) else []

    return {
        "transcript": transcript,
        "confidence": confidence,
        "words": words,
        "summary": summary_text,
        "sentiments": {
            "average": {
                "sentiment": avg_sentiment.get("sentiment", "neutral"),
                "sentiment_score": float(avg_sentiment.get("sentiment_score", 0.0)),
            },
            "segments": [
                {
                    "text": s.get("text", ""),
                    "sentiment": s.get("sentiment", "neutral"),
                    "sentiment_score": float(s.get("sentiment_score", 0.0)),
                }
                for s in sentiment_segments
            ],
        },
        "intents": {
            "segments": [
                {
                    "text": s.get("text", ""),
                    "intents": [
                        {
                            "intent": it.get("intent", ""),
                            "confidence_score": float(it.get("confidence_score", 0.0)),
                        }
                        for it in s.get("intents", [])
                    ],
                }
                for s in intent_segments
            ],
        },
        "topics": {
            "segments": [
                {
                    "text": s.get("text", ""),
                    "topics": [
                        {
                            "topic": tp.get("topic", ""),
                            "confidence_score": float(tp.get("confidence_score", 0.0)),
                        }
                        for tp in s.get("topics", [])
                    ],
                }
                for s in topic_segments
            ],
        },
        "metadata": data.get("metadata", {}),
    }
