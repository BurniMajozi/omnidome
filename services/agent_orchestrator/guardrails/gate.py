"""Policy gate: strict (block) / standard (mask) / audit (allow, log only)."""

from __future__ import annotations

from typing import Dict, List, Optional

try:  # production: PYTHONPATH=/app, repo-root-absolute imports
    from services.agent_orchestrator.guardrails.pii import mask_text, scan_pii
    from services.agent_orchestrator.guardrails.validate import validate_json
    from services.agent_orchestrator.guardrails.injection import scan_injection
except ImportError:  # pytest: service-dir-relative imports
    from guardrails.pii import mask_text, scan_pii
    from guardrails.validate import validate_json
    from guardrails.injection import scan_injection


def run_gate(
    text: Optional[str],
    policy: str = "standard",
    require_json: bool = False,
    check_injection: bool = True,
) -> Dict:
    """Run the guardrail gate over *text*.

    Checks:
    1. Prompt injection / jailbreak attempts (blocks immediately if detected).
    2. JSON validity (if require_json=True).
    3. PII scanning & policy-based masking or blocking.

    Returns {hits, injection_hits, text, action} where action is allow|mask|block.
    """
    safe_text = text or ""

    # 1. Prompt Injection Shield
    if check_injection and safe_text:
        injection_hits = scan_injection(safe_text)
        if injection_hits:
            return {
                "hits": [],
                "injection_hits": injection_hits,
                "text": safe_text,
                "action": "block",
                "error": f"Blocked prompt injection attempt ({len(injection_hits)} threat pattern detected)",
            }

    # 2. JSON Validation
    if require_json:
        ok, err = validate_json(text)
        if not ok:
            return {"hits": [], "injection_hits": [], "text": safe_text, "action": "block", "error": err}

    # 3. PII Scanning
    hits: List[Dict] = scan_pii(safe_text)
    if not hits:
        return {"hits": hits, "injection_hits": [], "text": safe_text, "action": "allow"}
    if policy == "strict":
        return {"hits": hits, "injection_hits": [], "text": safe_text, "action": "block"}
    if policy == "audit":
        return {"hits": hits, "injection_hits": [], "text": safe_text, "action": "allow"}
    # standard (default + unknown policies fall through to mask-and-continue)
    return {"hits": hits, "injection_hits": [], "text": mask_text(safe_text, hits), "action": "mask"}
