"""Emailing invoices/quotes through the Communication service (AgentMail) + delivery-event bookkeeping.

Same safety shape as inventory's purchase-order send:
  * the claim (a ``queued`` delivery-event row carrying the idempotency key) is committed BEFORE any I/O;
  * a DEFINITE refusal by the mail service (HTTP 4xx other than 408, or status failed/rejected/error)
    marks the row ``failed`` and CLEARS the key, so the caller can retry;
  * anything ambiguous (timeouts, 5xx, unconfirmed response) leaves the row ``queued`` with
    detail.ambiguous = true: a second send is refused (409) until an admin reconciles it;
  * recipients on the tenant suppression list are never mailed;
  * at most BILLING_EMAIL_MAX_PER_RECIPIENT_HOUR (default 3) mails per document per recipient per hour.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import timedelta
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from services.billing import doc_service as ds, document_render as render
from services.billing.contacts import resolve_customer_email
from services.billing.database import get_session
from services.billing.models_invoicing import DocumentDeliveryEvent, Quote
from services.billing.models import Invoice
from services.common.http_client import service_get, service_post

logger = logging.getLogger("billing.delivery")

# AgentMail webhook event -> event_type accepted by POST /delivery/webhook-event
AGENTMAIL_EVENT_MAP = {
    "message.delivered": "delivered", "message.bounced": "bounced", "message.complained": "complained",
    "message.rejected": "rejected", "message.received": "replied",
}
# webhook event_type -> stored delivery event_type
STORED_TYPE = {"delivered": "delivered", "bounced": "bounced", "complained": "complained",
               "rejected": "failed", "replied": "replied", "opened": "opened"}
DEFINITE_FAIL_STATUSES = {"failed", "rejected", "error"}


def is_definite_send_failure(exc: Exception) -> bool:
    """True only when the mail service positively refused the request (nothing was sent)."""
    code = getattr(getattr(exc, "response", None), "status_code", None)
    return isinstance(code, int) and 400 <= code < 500 and code != 408


def max_per_recipient_hour() -> int:
    try:
        return max(1, int(os.getenv("BILLING_EMAIL_MAX_PER_RECIPIENT_HOUR", "3")))
    except ValueError:
        return 3


def _split(recipient: Optional[str]) -> set:
    return {a.strip().lower() for a in (recipient or "").split(",") if a.strip()}


async def filter_suppressed_addresses(tenant_id: uuid.UUID, emails: list) -> tuple[list, list]:
    """(allowed, suppressed). Tests monkeypatch this; production uses the shared suppression list."""
    from services.common.db import session_scope
    from services.common.suppression import filter_suppressed
    async with session_scope(tenant_id) as db:
        allowed, suppressed = await filter_suppressed(db, tenant_id, emails)
    return list(allowed), list(suppressed)


async def add_suppression_best_effort(tenant_id: uuid.UUID, email: str, reason: str) -> None:
    try:
        from services.common.db import session_scope
        from services.common.suppression import add_suppression
        async with session_scope(tenant_id) as db:
            await add_suppression(db, tenant_id, email, reason, "billing.delivery")
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not add suppression for a bounced document email: %s", type(exc).__name__)


async def resolve_mailbox_id(tenant_id: uuid.UUID, user_id: uuid.UUID) -> str:
    configured = os.getenv("BILLING_MAILBOX_ID", "").strip()
    if configured:
        return configured
    mailboxes = await service_get("communication", "/api/v1/mail/mailboxes", tenant_id=tenant_id, user_id=user_id)
    active = [m for m in mailboxes if m.get("is_active", True)] if isinstance(mailboxes, list) else []
    if len(active) != 1:
        raise HTTPException(409, "Configure exactly one active mailbox (or BILLING_MAILBOX_ID) before emailing documents")
    return str(active[0]["id"])


def build_email(view: dict, message: Optional[str], url: Optional[str], kind: str) -> tuple[str, str]:
    """(plain text, html). The document is embedded in the HTML body (Communication accepts PDF
    attachments only); the signed view/pay link is the durable copy."""
    title = view["title"]
    intro = (message or "").strip()
    if not intro:
        if kind == "reminder":
            intro = f"This is a friendly reminder that {title.lower()} {view['number']} has a balance of {render.zar(view.get('balance'))}."
        else:
            intro = f"Please find your {title.lower()} {view['number']} below."
    text_body = intro + (f"\n\nView online: {url}\n" if url else "\n")
    link_html = (f'<p><a href="{render.esc(url)}" style="display:inline-block;background:#1d4ed8;color:#fff;'
                 f'padding:10px 22px;border-radius:6px;text-decoration:none">View '
                 f'{"and pay " if view["kind"] == "invoice" else ""}online</a></p>') if url else ""
    html_body = (f'<div style="font-family:Arial,sans-serif"><p>{render.esc(intro).replace(chr(10), "<br>")}</p>'
                 f'{link_html}</div><style>{render._CSS}</style>{render.render_fragment(view)}')
    return text_body, html_body


async def send_document_email(*, ctx, doc_type: str, doc_id: uuid.UUID, body, idempotency_key: Optional[str],
                              sender=None) -> dict:
    """Email an invoice or quote. ``sender`` is injectable for tests (defaults to the Communication service)."""
    tenant_id, user_id, actor = ctx.tenant_id, ctx.user_id, ds.actor_of(ctx)
    key = (idempotency_key or "").strip() or None
    kind = body.kind

    # ── 1. read + replay + preconditions ──────────────────────────────────────
    with get_session() as session:
        if key:
            prior = session.execute(select(DocumentDeliveryEvent).where(
                DocumentDeliveryEvent.tenant_id == tenant_id,
                DocumentDeliveryEvent.idempotency_key == key)).scalars().first()
            if prior is not None:
                if prior.doc_id != doc_id or prior.doc_type != doc_type:
                    raise HTTPException(409, "Idempotency key was already used for a different document")
                if prior.event_type == "sent":
                    return {"status": "sent", "message_id": prior.message_id, "event_id": str(prior.id), "replayed": True}
                raise HTTPException(409, "A send with this key is already pending; an admin must reconcile it")
        if doc_type == "invoice":
            inv = ds.load_invoice(session, tenant_id, doc_id)
            if inv.status == "draft":
                raise HTTPException(409, "Issue the invoice first (POST /invoices/{id}/send), then email it")
            if inv.status == "voided":
                raise HTTPException(409, "Cannot email a voided invoice")
            if kind == "reminder" and inv.status not in ("sent", "partially_paid", "overdue"):
                raise HTTPException(409, f"A reminder makes no sense for a {inv.status} invoice")
            view = ds.invoice_document(session, tenant_id, inv)
            customer_id, account_id = inv.customer_id, inv.billing_account_id
            default_to = None
            number = inv.number
        else:
            q = ds.load_quote(session, tenant_id, doc_id)
            if q.status in ("declined", "expired", "converted"):
                raise HTTPException(409, f"Cannot email a {q.status} quote")
            if kind == "reminder":
                raise HTTPException(422, "Reminders apply to invoices only")
            view = ds.quote_document(session, tenant_id, q)
            customer_id, account_id = q.customer_id, None
            default_to = q.prospect_email
            number = q.number
        pending = session.execute(select(DocumentDeliveryEvent.id).where(
            DocumentDeliveryEvent.tenant_id == tenant_id, DocumentDeliveryEvent.doc_type == doc_type,
            DocumentDeliveryEvent.doc_id == doc_id, DocumentDeliveryEvent.event_type == "queued")).first()
        if pending is not None:
            raise HTTPException(409, "A send is already pending; an admin must reconcile it before retrying")

    # ── 2. recipients, suppression, throttle ──────────────────────────────────
    to = [a.strip().lower() for a in (body.to or [])]
    if not to:
        resolved = default_to or (await resolve_customer_email(tenant_id, customer_id, account_id) if customer_id else None)
        if not resolved:
            raise HTTPException(422, "No recipient: pass 'to' or put an email on the customer/prospect")
        to = [resolved.strip().lower()]
    cc = [a.strip().lower() for a in (body.cc or [])]
    allowed, suppressed = await filter_suppressed_addresses(tenant_id, to + cc)
    if suppressed:
        with get_session() as session:
            ds.add_event(session, tenant_id, doc_type, doc_id, "suppressed", kind=kind,
                         recipient=",".join(suppressed), actor=actor, detail={"reason": "suppression list"})
    to = [a for a in to if a in allowed]
    cc = [a for a in cc if a in allowed]
    if not to:
        raise HTTPException(409, "All recipients are on the suppression list; nothing was sent")

    since = ds.utcnow() - timedelta(hours=1)
    with get_session() as session:
        recent = session.execute(select(DocumentDeliveryEvent.recipient, DocumentDeliveryEvent.created_at).where(
            DocumentDeliveryEvent.tenant_id == tenant_id, DocumentDeliveryEvent.doc_type == doc_type,
            DocumentDeliveryEvent.doc_id == doc_id, DocumentDeliveryEvent.event_type.in_(("sent", "queued")))).all()
    counts: dict = {}
    for rec, at in recent:
        if ds.aware(at) >= since:
            for a in _split(rec):
                counts[a] = counts.get(a, 0) + 1
    if any(counts.get(a, 0) >= max_per_recipient_hour() for a in to + cc):
        raise HTTPException(429, "This document was already emailed to that recipient several times in the last hour")

    mailbox_id = await resolve_mailbox_id(tenant_id, user_id)

    # ── 3. claim (committed before I/O): mint link + queued row ───────────────
    subject = (body.subject or "").strip() or (
        f"Reminder: invoice {number}" if kind == "reminder" else f"{view['title']} {number}")
    try:
        with get_session() as session:
            token, link = ds.mint_link(session, tenant_id, doc_type, doc_id, actor, body.link_expires_in_days)
            url = ds.public_url(token, doc_type)
            claim = ds.add_event(
                session, tenant_id, doc_type, doc_id, "queued", kind=kind, recipient=",".join(to + cc),
                subject=subject, idempotency_key=key or str(uuid.uuid4()), actor=actor,
                detail={"link_id": str(link.id), "to": to, "cc": cc})
            claim_id = claim.id
    except IntegrityError:
        raise HTTPException(409, "A send with this idempotency key is already in progress")

    text_body, html_body = build_email(view, body.message, url, kind)
    payload = {"mailbox_id": mailbox_id, "to": to, "cc": cc, "subject": subject,
               "body_text": text_body, "body_html": html_body}

    def settle(event_type: str, *, message_id: Optional[str] = None, clear_key: bool = False,
               ambiguous: bool = False, note: Optional[str] = None) -> None:
        with get_session() as session:
            ev = session.get(DocumentDeliveryEvent, claim_id)
            ev.event_type = event_type
            if message_id:
                ev.message_id = message_id
            if clear_key:
                ev.idempotency_key = None
            ev.detail = {**(ev.detail or {}), **({"ambiguous": True} if ambiguous else {}), **({"note": note} if note else {})}

    # ── 4. send ───────────────────────────────────────────────────────────────
    send = sender or (lambda p: service_post("communication", "/api/v1/mail/send", json=p,
                                             tenant_id=tenant_id, user_id=user_id, timeout=30, retries=0))
    try:
        delivery = await send(payload)
    except Exception as exc:  # noqa: BLE001
        if is_definite_send_failure(exc):
            settle("failed", clear_key=True, note="mail service rejected the request")
            raise HTTPException(502, "The mail service rejected the email; nothing was sent. You can retry")
        settle("queued", ambiguous=True, note=f"unconfirmed: {type(exc).__name__}")
        raise HTTPException(502, "Delivery could not be confirmed. Check the mailbox, then ask an admin to reconcile")
    status_text = str(delivery.get("status", "")).lower() if isinstance(delivery, dict) else ""
    if status_text in DEFINITE_FAIL_STATUSES:
        settle("failed", clear_key=True, note="mail service reported failure")
        raise HTTPException(502, "The mail service reported the email as failed; nothing was sent. You can retry")
    if not isinstance(delivery, dict) or status_text != "sent" or not delivery.get("message_id"):
        settle("queued", ambiguous=True, note="response did not confirm sending")
        raise HTTPException(502, "Email was not confirmed sent. Check the mailbox, then ask an admin to reconcile")

    settle("sent", message_id=str(delivery["message_id"]))
    if doc_type == "quote":
        with get_session() as session:
            q = ds.load_quote(session, tenant_id, doc_id, lock=True)
            if q.status == "draft":
                q.status, q.sent_at = "sent", ds.utcnow()
    return {"status": "sent", "message_id": str(delivery["message_id"]), "event_id": str(claim_id),
            "recipients": {"to": to, "cc": cc}, "link_expires_at": ds.aware(link.expires_at).isoformat(), "replayed": False}


def record_provider_event(tenant_id: uuid.UUID, message_id: str, event_type: str, detail: Optional[dict]) -> dict:
    """Append a delivered/bounced/... fact for every document sent under ``message_id``. Idempotent per
    (message, type): provider retries do not duplicate. Returns {matched, recorded, recipients}."""
    stored = STORED_TYPE[event_type]
    recorded, recipients = 0, set()
    with get_session() as session:
        sent = session.execute(select(DocumentDeliveryEvent).where(
            DocumentDeliveryEvent.tenant_id == tenant_id, DocumentDeliveryEvent.message_id == message_id,
            DocumentDeliveryEvent.event_type == "sent")).scalars().all()
        for row in sent:
            dup = session.execute(select(DocumentDeliveryEvent.id).where(
                DocumentDeliveryEvent.tenant_id == tenant_id, DocumentDeliveryEvent.message_id == message_id,
                DocumentDeliveryEvent.doc_id == row.doc_id, DocumentDeliveryEvent.event_type == stored)).first()
            recipients |= _split(row.recipient)
            if dup is not None:
                continue
            ds.add_event(session, tenant_id, row.doc_type, row.doc_id, stored, kind=row.kind,
                         recipient=row.recipient, message_id=message_id, actor="provider",
                         detail={"provider_event": event_type, **{k: v for k, v in (detail or {}).items()
                                                                  if isinstance(v, (str, int, float, bool))}})
            recorded += 1
        matched = len(sent)
    return {"matched": matched, "recorded": recorded, "recipients": sorted(recipients)}
