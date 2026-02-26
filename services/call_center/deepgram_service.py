"""
Deepgram Voice AI Integration for OmniDome Call Center
-------------------------------------------------------
Provides: Speech-to-Text (Nova), Text-to-Speech (Aura),
          Voice Agent API, and Audio Intelligence
          (Summarization, Sentiment Analysis, Intent Detection, Topic Detection)
"""

from __future__ import annotations

import os
import io
import json
import logging
from typing import Optional

from deepgram import DeepgramClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------
_client: Optional[DeepgramClient] = None


def _get_client() -> DeepgramClient:
    global _client
    if _client is None:
        api_key = os.getenv("DEEPGRAM_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "DEEPGRAM_API_KEY environment variable is not set. "
                "Get a free key at https://console.deepgram.com/signup"
            )
        _client = DeepgramClient(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# 1. Speech-to-Text  (Nova-2)
# ---------------------------------------------------------------------------
async def transcribe_audio(
    audio_bytes: bytes,
    language: str = "en",
    model: str = "nova-2",
    smart_format: bool = True,
    diarize: bool = False,
    punctuate: bool = True,
) -> dict:
    """Transcribe an audio buffer using Deepgram Nova STT."""
    client = _get_client()

    response = client.listen.rest.v("1").transcribe_file(
        {"buffer": audio_bytes},
        model=model,
        language=language,
        smart_format=smart_format,
        diarize=diarize,
        punctuate=punctuate,
    )

    channels = response.get("results", {}).get("channels", [])
    transcript = ""
    words = []
    confidence = 0.0

    if channels:
        alt = channels[0].get("alternatives", [{}])[0]
        transcript = alt.get("transcript", "")
        words = alt.get("words", [])
        confidence = alt.get("confidence", 0.0)

    return {
        "transcript": transcript,
        "confidence": confidence,
        "words": words,
        "metadata": response.get("metadata", {}),
    }


async def transcribe_url(
    url: str,
    language: str = "en",
    model: str = "nova-2",
    smart_format: bool = True,
) -> dict:
    """Transcribe audio from a remote URL."""
    client = _get_client()

    response = client.listen.rest.v("1").transcribe_url(
        {"url": url},
        model=model,
        language=language,
        smart_format=smart_format,
    )

    channels = response.get("results", {}).get("channels", [])
    transcript = ""
    confidence = 0.0

    if channels:
        alt = channels[0].get("alternatives", [{}])[0]
        transcript = alt.get("transcript", "")
        confidence = alt.get("confidence", 0.0)

    return {
        "transcript": transcript,
        "confidence": confidence,
        "metadata": response.get("metadata", {}),
    }


# ---------------------------------------------------------------------------
# 2. Text-to-Speech  (Aura)
# ---------------------------------------------------------------------------
async def synthesize_speech(
    text: str,
    model: str = "aura-2-en",
    encoding: str = "mp3",
) -> bytes:
    """Convert text to speech via Deepgram Aura TTS. Returns audio bytes."""
    client = _get_client()

    response = client.speak.rest.v("1").save(
        "",  # empty path — we capture stream instead
        {"text": text},
        model=model,
        encoding=encoding,
    )

    # The SDK writes to a file path; use stream_memory instead
    response = client.speak.rest.v("1").stream_raw(
        {"text": text},
        model=model,
        encoding=encoding,
    )

    audio_bytes = b""
    if hasattr(response, "stream"):
        audio_bytes = response.stream.read()
    elif hasattr(response, "read"):
        audio_bytes = response.read()
    else:
        # Fallback: iterate response
        audio_bytes = response.stream_memory.getvalue() if hasattr(response, "stream_memory") else b""

    return audio_bytes


async def synthesize_speech_simple(
    text: str,
    model: str = "aura-2-en",
) -> bytes:
    """Simplified TTS that returns raw audio bytes using REST."""
    import httpx

    api_key = os.getenv("DEEPGRAM_API_KEY", "")
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            "https://api.deepgram.com/v1/speak",
            params={"model": model, "encoding": "mp3"},
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "application/json",
            },
            json={"text": text},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# 3. Audio Intelligence  (Summarization, Sentiment, Intent, Topics)
# ---------------------------------------------------------------------------
async def analyze_audio(
    audio_bytes: bytes,
    language: str = "en",
    summarize: bool = True,
    detect_sentiment: bool = True,
    detect_intents: bool = True,
    detect_topics: bool = True,
) -> dict:
    """
    Run full Audio Intelligence analysis on an audio file.
    Returns transcript + summarization + sentiment + intents + topics.
    """
    client = _get_client()

    response = client.listen.rest.v("1").transcribe_file(
        {"buffer": audio_bytes},
        model="nova-2",
        language=language,
        smart_format=True,
        punctuate=True,
        diarize=True,
        summarize="v2" if summarize else False,
        sentiment=detect_sentiment,
        intents=detect_intents,
        topics=detect_topics,
    )

    # Extract transcript
    channels = response.get("results", {}).get("channels", [])
    transcript = ""
    confidence = 0.0
    words = []

    if channels:
        alt = channels[0].get("alternatives", [{}])[0]
        transcript = alt.get("transcript", "")
        confidence = alt.get("confidence", 0.0)
        words = alt.get("words", [])

    # Extract summary
    summary_data = response.get("results", {}).get("summary", {})
    summary_text = summary_data.get("short", "") if summary_data else ""

    # Extract sentiments
    sentiments_data = response.get("results", {}).get("sentiments", {})
    sentiment_segments = sentiments_data.get("segments", []) if sentiments_data else []
    sentiment_average = sentiments_data.get("average", {}) if sentiments_data else {}

    # Extract intents
    intents_data = response.get("results", {}).get("intents", {})
    intent_segments = intents_data.get("segments", []) if intents_data else []

    # Extract topics
    topics_data = response.get("results", {}).get("topics", {})
    topic_segments = topics_data.get("segments", []) if topics_data else []

    return {
        "transcript": transcript,
        "confidence": confidence,
        "words": words,
        "summary": summary_text,
        "sentiments": {
            "average": sentiment_average,
            "segments": sentiment_segments,
        },
        "intents": {
            "segments": intent_segments,
        },
        "topics": {
            "segments": topic_segments,
        },
        "metadata": response.get("metadata", {}),
    }


async def analyze_audio_url(
    url: str,
    language: str = "en",
    summarize: bool = True,
    detect_sentiment: bool = True,
    detect_intents: bool = True,
    detect_topics: bool = True,
) -> dict:
    """Run Audio Intelligence on a remote URL."""
    client = _get_client()

    response = client.listen.rest.v("1").transcribe_url(
        {"url": url},
        model="nova-2",
        language=language,
        smart_format=True,
        punctuate=True,
        diarize=True,
        summarize="v2" if summarize else False,
        sentiment=detect_sentiment,
        intents=detect_intents,
        topics=detect_topics,
    )

    channels = response.get("results", {}).get("channels", [])
    transcript = ""
    confidence = 0.0

    if channels:
        alt = channels[0].get("alternatives", [{}])[0]
        transcript = alt.get("transcript", "")
        confidence = alt.get("confidence", 0.0)

    summary_data = response.get("results", {}).get("summary", {})
    summary_text = summary_data.get("short", "") if summary_data else ""

    sentiments_data = response.get("results", {}).get("sentiments", {})
    intents_data = response.get("results", {}).get("intents", {})
    topics_data = response.get("results", {}).get("topics", {})

    return {
        "transcript": transcript,
        "confidence": confidence,
        "summary": summary_text,
        "sentiments": {
            "average": sentiments_data.get("average", {}) if sentiments_data else {},
            "segments": sentiments_data.get("segments", []) if sentiments_data else [],
        },
        "intents": {
            "segments": intents_data.get("segments", []) if intents_data else [],
        },
        "topics": {
            "segments": topics_data.get("segments", []) if topics_data else [],
        },
        "metadata": response.get("metadata", {}),
    }
