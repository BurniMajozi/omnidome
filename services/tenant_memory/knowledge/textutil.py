"""Chunking, token estimates and PII scrubbing of free text."""
from __future__ import annotations

import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_SA_ID = re.compile(r"\b\d{13}\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?27|0)[\s-]?\d{2}[\s-]?\d{3}[\s-]?\d{4}(?!\d)")
_SECRET = re.compile(r"(?i)\b(bearer\s+[a-z0-9._-]{12,}|sk[-_][a-z0-9_-]{10,}|(?:password|passwd|pwd|secret|api[_-]?key|token)\s*[:=]\s*\S+)")
_IBAN_ACC = re.compile(r"(?i)\b(?:acc(?:ount)?(?:\s*(?:no|number|#))?\s*[:#]?\s*)\d{8,}\b")


def scrub(text: str | None) -> str:
    """Redact contact details, ID/card/bank numbers and credentials from free text."""
    if not text:
        return ""
    out = _SECRET.sub("[redacted-secret]", text)
    out = _EMAIL.sub("[redacted-email]", out)
    out = _IBAN_ACC.sub("[redacted-account]", out)
    out = _SA_ID.sub("[redacted-id]", out)
    out = _CARD.sub("[redacted-number]", out)
    out = _PHONE.sub("[redacted-phone]", out)
    return out


def est_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars/token); good enough for budgeting."""
    return max(1, (len(text) + 3) // 4)


def clip(text: str | None, limit: int) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= limit else t[: max(0, limit - 1)].rstrip() + "…"


def split_frontmatter(markdown: str) -> tuple[str, str]:
    """('---\n...\n---\n', body). Frontmatter is repeated on every chunk so each stands alone."""
    if markdown.startswith("---\n"):
        end = markdown.find("\n---\n", 4)
        if end != -1:
            return markdown[: end + 5], markdown[end + 5:]
    return "", markdown


def chunk_markdown(markdown: str, max_chars: int = 1800, overlap: int = 150) -> list[str]:
    """Split on headings/paragraphs into <= max_chars pieces. Short cards stay whole.
    Each chunk after the first repeats the frontmatter so retrieval hits carry their source."""
    if len(markdown) <= max_chars:
        return [markdown]
    front, body = split_frontmatter(markdown)
    budget = max(200, max_chars - len(front))
    paras = [p for p in re.split(r"\n{2,}", body) if p.strip()]
    pieces: list[str] = []
    cur = ""
    for p in paras:
        while len(p) > budget:                      # a single huge paragraph: hard split
            head, p = p[:budget], p[budget - overlap:]
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(head)
        if len(cur) + len(p) + 2 > budget and cur:
            pieces.append(cur)
            tail = cur[-overlap:] if overlap else ""
            cur = (tail + "\n\n" + p) if tail else p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        pieces.append(cur)
    return [f"{front}{piece.strip()}\n" for piece in pieces]
