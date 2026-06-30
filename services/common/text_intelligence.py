"""Lightweight LLM-based text analysis (summary/sentiment/intents/topics).

Used by services that need call/chat intelligence (e.g. call_center, which
previously got this from Deepgram's Audio Intelligence) without taking a
dependency on the agent orchestrator — calls the shared Ollama instance
directly. Best-effort: returns empty/neutral fields if Ollama isn't
reachable or its output can't be parsed, rather than raising, since this
is supplementary to the transcript callers always have regardless.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemma3:4b"

_ANALYSIS_PROMPT = """Analyze the following call/conversation transcript. Respond with ONLY a JSON object (no markdown fences, no commentary) with these exact keys:
- "summary": a one or two sentence summary
- "sentiment": a number from -1.0 (very negative) to 1.0 (very positive)
- "intents": a list of short intent labels (e.g. "billing_inquiry", "complaint")
- "topics": a list of short topic labels

Transcript:
{transcript}
"""

_EMPTY_RESULT = {"summary": "", "sentiment": 0.0, "intents": [], "topics": []}


def _ollama_url() -> str:
    return os.getenv("OLLAMA_URL", "http://ollama:11434")


def _extract_json(text: str) -> Optional[dict]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


async def analyze_transcript(transcript: str, model: str = DEFAULT_MODEL) -> dict:
    """Best-effort summary/sentiment/intent/topic extraction via the local LLM."""
    if not transcript.strip():
        return dict(_EMPTY_RESULT)

    try:
        async with httpx.AsyncClient(base_url=_ollama_url(), timeout=30.0) as client:
            resp = await client.post(
                "/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": _ANALYSIS_PROMPT.format(transcript=transcript[:6000])}],
                    "stream": False,
                    "options": {"temperature": 0.2},
                },
            )
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "")
    except Exception as exc:
        logger.warning("Text intelligence (Ollama) unavailable: %s", exc)
        return dict(_EMPTY_RESULT)

    parsed = _extract_json(content)
    if not parsed:
        return dict(_EMPTY_RESULT)

    return {
        "summary": str(parsed.get("summary", ""))[:1000],
        "sentiment": max(-1.0, min(1.0, float(parsed.get("sentiment", 0.0) or 0.0))),
        "intents": [str(i) for i in parsed.get("intents", []) if isinstance(i, (str, int, float))][:10],
        "topics": [str(t) for t in parsed.get("topics", []) if isinstance(t, (str, int, float))][:10],
    }
