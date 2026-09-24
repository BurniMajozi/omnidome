"""Send one email through AgentMail (api.agentmail.to).

Same provider and contract as marketing's email delivery (services/marketing/
main.py `_agentmail_send`), shared so other services (sales lead emails) don't
copy it. AgentMail sends from the inbox itself; `reply_to` is optional.
"""

from __future__ import annotations

import os
from typing import Optional
from urllib.parse import quote

import httpx


class EmailNotConfigured(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(os.getenv("AGENTMAIL_API_KEY"))


def inbox_address() -> str:
    return os.getenv("AGENTMAIL_INBOX") or os.getenv("AGENTMAIL_INBOX_ID") or "omnidome@agentmail.to"


async def send_email(to: str, subject: str, html: str, *, reply_to: Optional[str] = None,
                     timeout: float = 30.0) -> str:
    """Returns the provider message id. Raises on any failure (callers retry)."""
    api_key = os.getenv("AGENTMAIL_API_KEY")
    if not api_key:
        raise EmailNotConfigured("Email provider not configured — set AGENTMAIL_API_KEY")
    base = os.getenv("AGENTMAIL_BASE_URL", "https://api.agentmail.to/v0").rstrip("/")
    payload: dict = {"to": [to], "subject": subject, "html": html or ""}
    if reply_to:
        payload["reply_to"] = [reply_to]
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{base}/inboxes/{quote(inbox_address(), safe='')}/messages/send",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"AgentMail {resp.status_code}: {resp.text[:300]}")
    try:
        data = resp.json()
    except ValueError:
        data = {}
    return str(data.get("message_id") or data.get("id") or "")
