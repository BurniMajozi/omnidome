"""Prompt injection and jailbreak detection for customer-facing and internal agents."""

from __future__ import annotations

import base64
import binascii
import re
from typing import Dict, List, Optional

INJECTION_PATTERNS: Dict[str, re.Pattern] = {
    "override_instructions": re.compile(
        r"(?i)\b(?:ignore|disregard|forget|bypass|override)\s+(?:all\s+)?(?:previous|prior|above|system)\s+(?:instructions|prompts|rules|commands|directives)",
    ),
    "system_leak": re.compile(
        r"(?i)\b(?:show|reveal|display|output|print|repeat|give\s+me)\s+(?:your\s+)?(?:system\s+prompt|initial\s+prompt|hidden\s+instructions|base\s+instructions|secret\s+key|api\s+key)",
    ),
    "jailbreak_personas": re.compile(
        r"(?i)\b(?:dan|developer\s+mode|unrestricted\s+mode|jailbreak|evil\s+twin|always\s+say\s+yes|bypass\s+safety|do\s+anything\s+now)\b",
    ),
    "mode_switch": re.compile(
        r"(?i)\b(?:you\s+are\s+now|act\s+as\s+a|pretend\s+to\s+be)\s+(?:unfiltered|unrestricted|hacker|root|admin|god\s+mode)\b",
    ),
    "format_escape": re.compile(
        r"(?i)(?:<\s*script\b|javascript:|onerror\s*=|onload\s*=|eval\s*\(|system\s*\(\s*['\"]|os\.system|child_process)",
    ),
    "boundary_tampering": re.compile(
        r"(?i)(?:<\s*/?\s*(?:system|instructions|untrusted_user_input|context|agent_guidelines)\s*>)",
    ),
}

BASE64_SUSPECT_PATTERN = re.compile(r"(?:[A-Za-z0-9+/]{4}){6,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?")


def _check_base64_payloads(text: str) -> List[Dict]:
    """Inspect base64 segments that might smuggle injection payloads."""
    findings = []
    for match in BASE64_SUSPECT_PATTERN.finditer(text):
        token = match.group(0)
        try:
            decoded = base64.b64decode(token).decode("utf-8", errors="ignore")
            for category, pattern in INJECTION_PATTERNS.items():
                if pattern.search(decoded):
                    findings.append({
                        "category": f"base64_encoded_{category}",
                        "matched": token[:30] + "...",
                        "span": match.span(),
                    })
                    break
        except (binascii.Error, UnicodeDecodeError):
            continue
    return findings


def scan_injection(text: Optional[str]) -> List[Dict]:
    """Scan input text for prompt injection, jailbreak attempts, or prompt leaks.

    Returns a list of detected threats with category, matched text, and span.
    """
    if not text:
        return []

    hits: List[Dict] = []
    for category, pattern in INJECTION_PATTERNS.items():
        for match in pattern.finditer(text):
            hits.append({
                "category": category,
                "matched": match.group(0),
                "span": match.span(),
            })

    base64_hits = _check_base64_payloads(text)
    hits.extend(base64_hits)
    return hits

