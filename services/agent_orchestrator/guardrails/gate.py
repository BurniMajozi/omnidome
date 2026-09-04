"""Policy gate: strict (block) / standard (mask) / audit (allow, log only)."""

from __future__ import annotations

from typing import Dict, List, Optional

try:  # production: PYTHONPATH=/app, repo-root-absolute imports
    from services.agent_orchestrator.guardrails.pii import mask_text, scan_pii
    from services.agent_orchestrator.guardrails.validate import validate_json
except ImportError:  # pytest: service-dir-relative imports
    from guardrails.pii import mask_text, scan_pii
    from guardrails.validate import validate_json


def run_gate(
    text: Optional[str],
    policy: str = "standard",
    require_json: bool = False,
) -> Dict:
    """Run the guardrail gate over *text*.

    Returns {hits, text, action} where action is allow|mask|block.
    With require_json=True, invalid JSON blocks with an error field.
    """
    if require_json:
        ok, err = validate_json(text)
        if not ok:
            return {"hits": [], "text": text or "", "action": "block", "error": err}

    hits: List[Dict] = scan_pii(text)
    safe_text = text or ""
    if not hits:
        return {"hits": hits, "text": safe_text, "action": "allow"}
    if policy == "strict":
        return {"hits": hits, "text": safe_text, "action": "block"}
    if policy == "audit":
        return {"hits": hits, "text": safe_text, "action": "allow"}
    # standard (default + unknown policies fall through to mask-and-continue)
    return {"hits": hits, "text": mask_text(safe_text, hits), "action": "mask"}
