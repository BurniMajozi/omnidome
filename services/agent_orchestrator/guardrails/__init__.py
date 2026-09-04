"""Guardrails package — PII scanning/masking and policy enforcement.

Import tolerant of both layouts: service-dir-relative (``from guardrails…``,
used by pytest run from the service dir) and repo-root-absolute
(``from services.agent_orchestrator.guardrails…``, used in production where
PYTHONPATH=/app). The try/except keeps one package working in both.
"""

try:  # production: PYTHONPATH=/app, repo-root-absolute imports
    from services.agent_orchestrator.guardrails.gate import run_gate
    from services.agent_orchestrator.guardrails.pii import PATTERNS, mask_text, scan_pii
    from services.agent_orchestrator.guardrails.validate import validate_json
except ImportError:  # pytest: service-dir-relative imports
    from guardrails.gate import run_gate
    from guardrails.pii import PATTERNS, mask_text, scan_pii
    from guardrails.validate import validate_json

__all__ = ["PATTERNS", "mask_text", "run_gate", "scan_pii", "validate_json"]
