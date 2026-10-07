"""Quotes: create/edit/send/accept/decline/convert, documents, share links and email delivery.

Quotes carry NO ledger effect (nothing is posted to finance); only the invoice a quote converts to does,
once that draft invoice is issued with POST /invoices/{id}/send.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.billing import calc, delivery, doc_service as ds, document_render as render, invoicing_math as im, quotes as ql
from services.billing.access import require, require_tier
from services.billing.database import get_session
from services.billing.models_invoicing import DocumentShareLink, Quote
from services.billing.routes.invoice_documents import (
    HTML_HEADERS, _check_catalog, _safe_filename, create_link_response, delivery_events_out, enforce_discount,
    export_response, invoice_detail, link_out,
)
from services.billing.schemas_invoicing import (
    EmailRequest, QuoteConvert, QuoteCreate, QuoteDecision, QuoteUpdate, ShareLinkRequest,
)

logger = logging.getLogger("billing.quotes")

router = APIRouter(prefix="/quotes", tags=["Quotes"])


def _valid_days() -> int:
    import os
    try:
        return max(1, int(os.getenv("BILLING_QUOTE_VALID_DAYS", str(ql.DEFAULT_VALID_DAYS))))
    except ValueError:
        return ql.DEFAULT_VALID_DAYS


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_tier("clerk"))])
async def create_quote(body: QuoteCreate, ctx: AuthContext = Depends(get_auth_context)):
    """Quote for an existing customer (``customer_id``) OR a prospect (``prospect_name`` + email/phone),
    e.g. a field-sales lead. ``source``: field_sales | technician | web | other."""
    if body.customer_id is None and not (body.prospect_name or "").strip():
        raise HTTPException(422, "Provide customer_id or prospect_name")
    lines, totals = im.build_lines(body.lines)
    await enforce_discount(ctx, totals)
    snap = {}
    if body.customer_id and not (body.prospect_name and body.prospect_email):
        snap = await ds.customer_snapshot(ctx.tenant_id, body.customer_id)
    with get_session() as session:
        _check_catalog(session, ctx.tenant_id, body.lines)
        ds.require_template(session, ctx.tenant_id, body.template_id)
        issue = body.issue_date or calc.today_sast()
        valid = body.valid_until or issue + timedelta(days=_valid_days())
        if valid < issue:
            raise HTTPException(422, "valid_until cannot be before issue_date")
        q = Quote(
            id=uuid.uuid4(), tenant_id=ctx.tenant_id, number=ds.next_quote_number(session, ctx.tenant_id),
            status="draft", customer_id=body.customer_id,
            prospect_name=body.prospect_name or snap.get("name"), prospect_email=body.prospect_email or snap.get("email"),
            prospect_phone=body.prospect_phone or snap.get("phone"),
            prospect_address=body.prospect_address or snap.get("address"),
            issue_date=issue, valid_until=valid, notes=body.notes, terms=body.terms, po_number=body.po_number,
            source=body.source, created_by=body.created_by or ds.actor_of(ctx), template_id=body.template_id)
        session.add(q)
        session.flush()
        ql.replace_lines(q, lines, totals)
        session.flush()
        session.refresh(q)
        return ql.quote_out(q)


@router.get("", dependencies=[Depends(require_tier("reader"))])
async def list_quotes(ctx: AuthContext = Depends(get_auth_context), status_filter: Optional[str] = Query(None, alias="status"),
                      customer_id: Optional[uuid.UUID] = None, source: Optional[str] = None,
                      created_by: Optional[str] = Query(None, max_length=120),
                      page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    with get_session() as session:
        stmt = select(Quote).where(Quote.tenant_id == ctx.tenant_id)
        cnt = select(func.count(Quote.id)).where(Quote.tenant_id == ctx.tenant_id)
        for col, val in ((Quote.customer_id, customer_id), (Quote.source, source), (Quote.created_by, created_by)):
            if val is not None:
                stmt, cnt = stmt.where(col == val), cnt.where(col == val)
        rows = session.execute(stmt.order_by(Quote.created_at.desc()).limit(500)).scalars().all()
        for q in rows:
            ds.refresh_expiry(q)
        if status_filter:
            rows = [q for q in rows if q.status == status_filter]
        total = len(rows)
        page_rows = rows[(page - 1) * page_size: page * page_size]
        return {"items": [ql.quote_out(q) for q in page_rows], "total": total, "page": page, "page_size": page_size}


@router.get("/{quote_id}", dependencies=[Depends(require_tier("reader"))])
async def get_quote(quote_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        return ql.quote_out(ds.load_quote(session, ctx.tenant_id, quote_id))


@router.put("/{quote_id}", dependencies=[Depends(require_tier("clerk"))])
async def update_quote(quote_id: uuid.UUID, body: QuoteUpdate, ctx: AuthContext = Depends(get_auth_context)):
    """Edit a DRAFT quote. ``lines`` replaces all lines; totals are recomputed."""
    lines = totals = None
    if body.lines is not None:
        lines, totals = im.build_lines(body.lines)
        await enforce_discount(ctx, totals)
    with get_session() as session:
        q = ds.load_quote(session, ctx.tenant_id, quote_id, lock=True)
        if q.status != "draft":
            raise HTTPException(409, "Only draft quotes can be edited")
        if body.lines is not None:
            _check_catalog(session, ctx.tenant_id, body.lines)
            ql.replace_lines(q, lines, totals)
        if body.template_id is not None:
            ds.require_template(session, ctx.tenant_id, body.template_id)
            q.template_id = body.template_id
        for field in ("customer_id", "prospect_name", "prospect_email", "prospect_phone", "prospect_address",
                      "issue_date", "valid_until", "notes", "terms", "po_number"):
            val = getattr(body, field)
            if val is not None:
                setattr(q, field, val)
        if q.valid_until < q.issue_date:
            raise HTTPException(422, "valid_until cannot be before issue_date")
        session.flush()
        session.refresh(q)
        return ql.quote_out(q)


@router.post("/{quote_id}/send", dependencies=[Depends(require_tier("clerk"))])
async def mark_quote_sent(quote_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    """Mark a draft quote as sent without emailing (hand-delivered / shown on a device).
    POST /quotes/{id}/email sends AND marks it sent."""
    with get_session() as session:
        q = ds.load_quote(session, ctx.tenant_id, quote_id, lock=True)
        ql.mark_sent(q)
        return ql.quote_out(q)


@router.post("/{quote_id}/accept", dependencies=[Depends(require_tier("clerk"))])
async def accept_quote(quote_id: uuid.UUID, body: QuoteDecision = QuoteDecision(), ctx: AuthContext = Depends(get_auth_context)):
    """Staff records the customer's acceptance (e.g. signed on a technician's device)."""
    with get_session() as session:
        q = ds.load_quote(session, ctx.tenant_id, quote_id, lock=True)
        ql.apply_decision(q, "accept", body.note, internal=True)
        return ql.quote_out(q)


@router.post("/{quote_id}/decline", dependencies=[Depends(require_tier("clerk"))])
async def decline_quote(quote_id: uuid.UUID, body: QuoteDecision = QuoteDecision(), ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        q = ds.load_quote(session, ctx.tenant_id, quote_id, lock=True)
        ql.apply_decision(q, "decline", body.note, internal=True)
        return ql.quote_out(q)


@router.post("/{quote_id}/convert", dependencies=[Depends(require_tier("clerk"))])
async def convert_quote(quote_id: uuid.UUID, body: QuoteConvert = QuoteConvert(), ctx: AuthContext = Depends(get_auth_context)):
    """Create the DRAFT invoice for an ACCEPTED quote. Idempotent: calling again returns the same invoice
    (``created: false``). ``force`` (billing admin only) converts a quote that is not accepted yet.
    The invoice is issued separately with POST /invoices/{id}/send."""
    if body.force:
        await require(ctx, "admin")
    with get_session() as session:
        q = ds.load_quote(session, ctx.tenant_id, quote_id, lock=True)
        inv, meta, created = ql.convert_to_invoice(
            session, q, customer_id=body.customer_id, due_date=body.due_date, created_by=ds.actor_of(ctx),
            force=body.force)
        session.flush()
        session.refresh(inv)
        return {"created": created, "quote": ql.quote_out(q), "invoice": invoice_detail(inv, meta)}


@router.get("/{quote_id}/document", response_class=HTMLResponse, dependencies=[Depends(require_tier("reader"))])
async def quote_document(quote_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        view = ds.quote_document(session, ctx.tenant_id, ds.load_quote(session, ctx.tenant_id, quote_id))
    return HTMLResponse(render.render_html(view), headers=HTML_HEADERS)


@router.get("/{quote_id}/export", dependencies=[Depends(require_tier("reader"))])
async def quote_export(quote_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), format: str = Query("json")):
    with get_session() as session:
        q = ds.load_quote(session, ctx.tenant_id, quote_id)
        view, name = ds.quote_document(session, ctx.tenant_id, q), _safe_filename(q.number)
    return export_response(view, format.lower(), name)


@router.post("/{quote_id}/share-link", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_tier("clerk"))])
async def create_quote_share_link(quote_id: uuid.UUID, body: ShareLinkRequest = ShareLinkRequest(),
                                  ctx: AuthContext = Depends(get_auth_context)):
    """Public accept/decline link (token returned once). Marks a draft quote as sent."""
    with get_session() as session:
        q = ds.load_quote(session, ctx.tenant_id, quote_id, lock=True)
        if q.status in ("declined", "expired", "converted"):
            raise HTTPException(409, f"A {q.status} quote cannot be shared")
        ql.mark_sent(q)
    return create_link_response(ctx, "quote", quote_id, body.expires_in_days)


@router.get("/{quote_id}/share-links", dependencies=[Depends(require_tier("reader"))])
async def list_quote_share_links(quote_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        ds.load_quote(session, ctx.tenant_id, quote_id)
        rows = session.execute(select(DocumentShareLink).where(
            DocumentShareLink.tenant_id == ctx.tenant_id, DocumentShareLink.doc_type == "quote",
            DocumentShareLink.doc_id == quote_id).order_by(DocumentShareLink.created_at.desc())).scalars().all()
        return [link_out(r) for r in rows]


@router.post("/{quote_id}/email", dependencies=[Depends(require_tier("clerk"))])
async def email_quote(quote_id: uuid.UUID, body: EmailRequest = EmailRequest(), ctx: AuthContext = Depends(get_auth_context),
                      idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", max_length=128)):
    """Email the quote (document + public accept link). Success marks a draft quote as sent."""
    return await delivery.send_document_email(ctx=ctx, doc_type="quote", doc_id=quote_id, body=body,
                                              idempotency_key=idempotency_key)


@router.get("/{quote_id}/delivery-events", dependencies=[Depends(require_tier("reader"))])
async def quote_delivery_events(quote_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        ds.load_quote(session, ctx.tenant_id, quote_id)
        return delivery_events_out(session, ctx.tenant_id, "quote", quote_id)
