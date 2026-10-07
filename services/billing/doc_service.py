"""DB helpers shared by the invoicing-suite routers: templates, meta, share links, delivery events,
customer snapshots, quote numbering. Sync sessions (billing's pattern); callers own the transaction."""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select

from services.billing import document_render as render
from services.billing.models import Invoice
from services.billing.models_invoicing import (
    DocumentDeliveryEvent, DocumentShareLink, InvoiceMeta, InvoiceTemplate, Quote, QuoteSequence,
)

logger = logging.getLogger("billing.docs")

MAX_ACTIVE_LINKS_PER_DOC = 20


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite returns naive datetimes; treat them as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ── templates ────────────────────────────────────────────────────────────────

def get_template(session, tenant_id: uuid.UUID, template_id: Optional[uuid.UUID] = None) -> Optional[InvoiceTemplate]:
    """Requested template (tenant-scoped), else the tenant's default, else None (built-in defaults)."""
    if template_id:
        t = session.execute(select(InvoiceTemplate).where(
            InvoiceTemplate.id == template_id, InvoiceTemplate.tenant_id == tenant_id)).scalar_one_or_none()
        if t is not None:
            return t
    return session.execute(select(InvoiceTemplate).where(
        InvoiceTemplate.tenant_id == tenant_id, InvoiceTemplate.is_default.is_(True))).scalars().first()


def template_dict(session, tenant_id: uuid.UUID, template_id: Optional[uuid.UUID] = None) -> dict:
    return render.template_to_dict(get_template(session, tenant_id, template_id))


def require_template(session, tenant_id: uuid.UUID, template_id: Optional[uuid.UUID]) -> None:
    if template_id is None:
        return
    ok = session.execute(select(InvoiceTemplate.id).where(
        InvoiceTemplate.id == template_id, InvoiceTemplate.tenant_id == tenant_id)).first()
    if ok is None:
        raise HTTPException(422, "Unknown template_id")


# ── invoices ────────────────────────────────────────────────────────────────

def load_invoice(session, tenant_id: uuid.UUID, invoice_id: uuid.UUID, lock: bool = False) -> Invoice:
    stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
    if lock:
        stmt = stmt.with_for_update()
    inv = session.execute(stmt).scalar_one_or_none()
    if inv is None:
        raise HTTPException(404, "Invoice not found")
    return inv


def get_meta(session, invoice_id: uuid.UUID) -> Optional[InvoiceMeta]:
    return session.get(InvoiceMeta, invoice_id)


def invoice_document(session, tenant_id: uuid.UUID, inv: Invoice) -> dict:
    meta = get_meta(session, inv.id)
    tdict = template_dict(session, tenant_id, meta.template_id if meta else None)
    return render.invoice_view(inv, meta, tdict)


def quote_document(session, tenant_id: uuid.UUID, q: Quote) -> dict:
    return render.quote_view(q, template_dict(session, tenant_id, q.template_id))


# ── quotes ──────────────────────────────────────────────────────────────────

def next_quote_number(session, tenant_id: uuid.UUID) -> str:
    seq = session.query(QuoteSequence).filter(QuoteSequence.tenant_id == tenant_id).with_for_update().first()
    if seq is None:
        seq = QuoteSequence(tenant_id=tenant_id, last_number=0)
        session.add(seq)
        session.flush()
    seq.last_number += 1
    session.flush()
    return f"QUO-{str(tenant_id).split('-')[0].upper()[:4]}-{seq.last_number:06d}"


def load_quote(session, tenant_id: uuid.UUID, quote_id: uuid.UUID, lock: bool = False) -> Quote:
    stmt = select(Quote).where(Quote.id == quote_id, Quote.tenant_id == tenant_id)
    if lock:
        stmt = stmt.with_for_update()
    q = session.execute(stmt).scalar_one_or_none()
    if q is None:
        raise HTTPException(404, "Quote not found")
    refresh_expiry(q)
    return q


def refresh_expiry(q: Quote, today: Optional[date] = None) -> bool:
    """Lazy expiry: a sent/viewed quote past valid_until becomes 'expired'. Returns True if changed."""
    from services.billing import calc
    today = today or calc.today_sast()
    if q.status in ("sent", "viewed") and q.valid_until < today:
        q.status = "expired"
        return True
    return False


# ── share links ─────────────────────────────────────────────────────────────

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def default_link_ttl_days() -> int:
    try:
        return max(1, min(365, int(os.getenv("BILLING_SHARE_LINK_TTL_DAYS", "30"))))
    except ValueError:
        return 30


def mint_link(session, tenant_id: uuid.UUID, doc_type: str, doc_id: uuid.UUID, created_by: Optional[str],
              ttl_days: Optional[int] = None) -> tuple[str, DocumentShareLink]:
    """New unguessable token (only its hash is stored). Raises 409 past MAX_ACTIVE_LINKS_PER_DOC."""
    now = utcnow()
    active = session.execute(select(func.count(DocumentShareLink.id)).where(
        DocumentShareLink.tenant_id == tenant_id, DocumentShareLink.doc_type == doc_type,
        DocumentShareLink.doc_id == doc_id, DocumentShareLink.revoked_at.is_(None),
        DocumentShareLink.expires_at > now)).scalar_one()
    if active >= MAX_ACTIVE_LINKS_PER_DOC:
        raise HTTPException(409, "Too many active share links for this document: revoke some first")
    token = secrets.token_urlsafe(32)
    row = DocumentShareLink(
        tenant_id=tenant_id, doc_type=doc_type, doc_id=doc_id, token_hash=hash_token(token),
        expires_at=now + timedelta(days=ttl_days or default_link_ttl_days()), created_by=created_by)
    session.add(row)
    session.flush()
    return token, row


def resolve_link(session, token: str, doc_type: str) -> Optional[DocumentShareLink]:
    """The live link for this token, or None for unknown / wrong type / revoked / expired (all alike)."""
    if not token or len(token) > 128:
        return None
    row = session.execute(select(DocumentShareLink).where(
        DocumentShareLink.token_hash == hash_token(token))).scalar_one_or_none()
    if row is None or row.doc_type != doc_type or row.revoked_at is not None:
        return None
    if aware(row.expires_at) <= utcnow():
        return None
    return row


def public_url(token: str, doc_type: str) -> Optional[str]:
    base = (os.getenv("BILLING_PUBLIC_BASE_URL") or os.getenv("APP_PUBLIC_URL") or "").rstrip("/")
    if not base:
        return None
    path = "/public/invoices/" if doc_type == "invoice" else "/public/quotes/"
    return f"{base}{path}{token}"


def link_payload(token: str, row: DocumentShareLink) -> dict:
    return {
        "id": str(row.id), "token": token, "doc_type": row.doc_type, "doc_id": str(row.doc_id),
        "url": public_url(token, row.doc_type),
        "api_path": f"/public/{'invoices' if row.doc_type == 'invoice' else 'quotes'}/{token}",
        "expires_at": aware(row.expires_at).isoformat(),
        "note": "The token is shown once; only its hash is stored.",
    }


# ── delivery events ─────────────────────────────────────────────────────────

def add_event(session, tenant_id: uuid.UUID, doc_type: str, doc_id: uuid.UUID, event_type: str, *,
              kind: str = "document", recipient: Optional[str] = None, subject: Optional[str] = None,
              message_id: Optional[str] = None, idempotency_key: Optional[str] = None,
              actor: Optional[str] = None, detail: Optional[dict] = None) -> DocumentDeliveryEvent:
    ev = DocumentDeliveryEvent(
        tenant_id=tenant_id, doc_type=doc_type, doc_id=doc_id, event_type=event_type, kind=kind,
        recipient=recipient, subject=subject, message_id=message_id, idempotency_key=idempotency_key,
        actor=actor, detail=detail)
    session.add(ev)
    session.flush()
    return ev


# ── customer snapshot (best effort, CRM) ────────────────────────────────────

async def customer_snapshot(tenant_id: uuid.UUID, customer_id: uuid.UUID) -> dict:
    """{name,email,phone,address} for 'Bill to'. Never raises: a CRM outage yields {}."""
    from services.common.http_client import service_get
    from services.billing import finance_posting as fp
    try:
        data = await service_get("crm", f"/customers/{customer_id}", tenant_id=tenant_id,
                                 user_id=uuid.UUID(fp.service_user_id()), timeout=5.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("customer snapshot lookup failed for %s: %s", customer_id, type(exc).__name__)
        return {}
    if not isinstance(data, dict):
        return {}
    name = " ".join(x for x in (data.get("first_name"), data.get("last_name")) if x) or data.get("name")
    return {"name": name, "email": data.get("email"), "phone": data.get("phone"), "address": data.get("address")}


def actor_of(ctx) -> str:
    return str(ctx.user_id)
