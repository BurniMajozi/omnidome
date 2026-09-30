"""Logging filter that redacts credentials from log records (uvicorn access logs print the
full request URL, including query strings such as ?token=<jwt> on the WebSocket upgrade)."""

import logging
import re

_SECRET_KEYS = r"(?:token|access_token|refresh_token|id_token|apikey|api_key|key|authorization|auth|jwt|password|secret)"
# query/form style:  token=abc   &apikey=abc
_QS_RE = re.compile(r"(?i)([?&;\s]" + _SECRET_KEYS + r"=)[^&\s\"'#]*")
# header style:  Authorization: Bearer abc / Authorization=Bearer abc
_HDR_RE = re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;\"']+")
# bare JWTs (three base64url segments) anywhere
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*")


def redact(text: str) -> str:
    text = _QS_RE.sub(lambda m: m.group(1) + "REDACTED", text)
    text = _HDR_RE.sub(lambda m: m.group(1) + "REDACTED", text)
    return _JWT_RE.sub("REDACTED", text)


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: redact(v) if isinstance(v, str) else v for k, v in record.args.items()}
                else:
                    record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        except Exception:  # never break logging
            pass
        return True


def install(*logger_names: str) -> None:
    for name in logger_names or ("uvicorn.access", "uvicorn.error", "uvicorn"):
        lg = logging.getLogger(name)
        if not any(isinstance(f, RedactSecretsFilter) for f in lg.filters):
            lg.addFilter(RedactSecretsFilter())
