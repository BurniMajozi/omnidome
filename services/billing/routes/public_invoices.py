"""PUBLIC (unauthenticated) document routes, reached with an unguessable share token.

Security rules: every route is per-IP rate limited (services.common.rate_limiter, IP from
trusted_client_ip); an unknown / wrong-type / revoked / expired token yields the SAME generic 404; repeated
bad tokens from one IP are throttled (429) so tokens cannot be guessed; responses are sanitised (no tenant,
customer, subscription or internal ids, no billing-account data, no customer email/phone); HTML is escaped
and served with a strict CSP. These paths are public to the entitlement middleware
(main.py: public_prefixes=("/public/",)).
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select

from services.common.auth import AuthContext
from services.common.rate_limiter import RateLimiter, trusted_client_ip
from services.billing import doc_service as ds, document_render as render, finance_posting as fp, quotes as ql
from services.billing.database import get_session
from services.billing.models_invoicing import DocumentDeliveryEvent, Quote
from services.billing.routes.invoice_documents import HTML_HEADERS
from services.billing.schemas import PaystackInitializeRequest
from services.billing.schemas_invoicing import PublicPayRequest, QuoteDecision

logger = logging.getLogger("billing.public")

router = APIRouter(prefix="/public", tags=["Public documents"])

PAYABLE = ("sent", "partially_paid", "overdue")
VIEW_EVENT_DEDUPE = timedelta(minutes=10)

view_limiter = RateLimiter(max_requests=60, window_seconds=60)
action_limiter = RateLimiter(max_requests=10, window_seconds=60)


class BadTokenThrottle:
    """Blocks an IP after ``max_bad`` unknown-token lookups in ``window`` seconds (even for good tokens)."""

    def __init__(self, max_bad: int = 20, window: float = 600.0):
        self.max_bad, self.window = max_bad, window
        self._hits: dict = defaultdict(list)

    def _prune(self, ip: str) -> list:
        cutoff = time.monotonic() - self.window
        self._hits[ip] = [t for t in self._hits[ip] if t > cutoff]
        return self._hits[ip]

    def blocked(self, ip: str) -> bool:
        return len(self._prune(ip)) >= self.max_bad

    def record(self, ip: str) -> None:
        self._prune(ip).append(time.monotonic())


bad_tokens = BadTokenThrottle()


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not found")


def _guard(request: Request, limiter: RateLimiter) -> str:
    ip = trusted_client_ip(request)
    limiter.check_key("pub:" + ip)
    if bad_tokens.blocked(ip):
        raise HTTPException(status_code=429, detail="Too many invalid requests. Please try again later.",
                            headers={"Retry-After": "600"})
    return ip


def _resolve(session, ip: str, token: str, doc_type: str):
    link = ds.resolve_link(session, token, doc_type)
    if link is None:
        bad_tokens.record(ip)
        raise _not_found()
    return link


def sanitise_view(view: dict) -> dict:
    """What a link holder may see: no customer email/phone, no internal ids (the views carry none)."""
    out = dict(view)
    bt = view.get("bill_to") or {}
    out["bill_to"] = {"name": bt.get("name"), "address": bt.get("address")}
    return out


def _record_view(session, link, doc_type: str) -> None:
    now = ds.utcnow()
    last = ds.aware(link.last_viewed_at)
    link.view_count = (link.view_count or 0) + 1
    link.last_viewed_at = now
    if last is None or now - last > VIEW_EVENT_DEDUPE:
        ds.add_event(session, link.tenant_id, doc_type, link.doc_id, "viewed", actor="public-link",
                     detail={"link_id": str(link.id)})


def _respond(view: dict, fmt: str, extra: dict):
    if fmt == "html":
        return HTMLResponse(render.render_html(sanitise_view(view)), headers=HTML_HEADERS)
    if fmt != "json":
        raise HTTPException(422, "format must be json or html")
    body = render.view_to_json(sanitise_view(view))
    body.update(extra)
    return JSONResponse(body, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


# ── invoices ─────────────────────────────────────────────────────────────────

@router.get("/invoices/{token}")
async def public_invoice(token: str, request: Request, format: str = Query("json")):
    ip = _guard(request, view_limiter)
    with get_session() as session:
        link = _resolve(session, ip, token, "invoice")
        try:
            inv = ds.load_invoice(session, link.tenant_id, link.doc_id)
        except HTTPException:
            raise _not_found()
        if inv.status == "draft":
            raise _not_found()
        view = ds.invoice_document(session, link.tenant_id, inv)
        _record_view(session, link, "invoice")
        payable = inv.status in PAYABLE and inv.credit_note_of is None and inv.total_zar > inv.amount_paid_zar
    return _respond(view, format.lower(), {"payable": payable,
                                           "pay_path": f"/public/invoices/{token}/pay" if payable else None})


@router.post("/invoices/{token}/pay")
async def public_invoice_pay(token: str, request: Request, body: PublicPayRequest = PublicPayRequest()):
    """Start a Paystack checkout for the invoice balance (or a smaller ``amount_zar``) using the same logic
    as POST /payments/paystack/initialize. The customer's email always comes from their record."""
    ip = _guard(request, action_limiter)
    with get_session() as session:
        link = _resolve(session, ip, token, "invoice")
        try:
            inv = ds.load_invoice(session, link.tenant_id, link.doc_id)
        except HTTPException:
            raise _not_found()
        if inv.status not in PAYABLE or inv.credit_note_of is not None or inv.total_zar <= inv.amount_paid_zar:
            raise HTTPException(status_code=409, detail="This invoice cannot be paid online")
        tenant_id, invoice_id = link.tenant_id, inv.id
    from services.billing.routes import paystack as ps
    callback = os.getenv("BILLING_PUBLIC_PAY_CALLBACK_URL", "").strip() or None
    if callback and not ps.callback_allowed(callback):
        callback = None
    ctx = AuthContext(user_id=uuid.UUID(fp.service_user_id()), tenant_id=tenant_id, roles=["billing_admin"],
                      auth_mode="public-link")
    try:
        result = await ps.initialize_paystack(
            PaystackInitializeRequest(invoice_id=invoice_id, amount_zar=body.amount_zar, callback_url=callback), ctx)
    except HTTPException as exc:
        logger.info("public pay refused for %s: HTTP %s", invoice_id, exc.status_code)
        if exc.status_code in (502, 503):
            raise HTTPException(status_code=exc.status_code, detail="Online payment is not available right now")
        raise HTTPException(status_code=409, detail="Payment could not be started for this invoice")
    return {"authorization_url": result.authorization_url, "reference": result.reference}


# ── quotes ───────────────────────────────────────────────────────────────────

def _quote_for(session, ip: str, token: str) -> tuple:
    link = _resolve(session, ip, token, "quote")
    try:
        q = ds.load_quote(session, link.tenant_id, link.doc_id, lock=True)
    except HTTPException:
        raise _not_found()
    if q.status == "draft":
        raise _not_found()
    return link, q


@router.get("/quotes/{token}")
async def public_quote(token: str, request: Request, format: str = Query("json")):
    ip = _guard(request, view_limiter)
    with get_session() as session:
        link, q = _quote_for(session, ip, token)
        ql.mark_viewed(q)
        view = ds.quote_document(session, link.tenant_id, q)
        _record_view(session, link, "quote")
        actionable = q.status in ("sent", "viewed")
    return _respond(view, format.lower(), {
        "actionable": actionable,
        "accept_path": f"/public/quotes/{token}/accept" if actionable else None,
        "decline_path": f"/public/quotes/{token}/decline" if actionable else None})


def _decide(token: str, request: Request, body: QuoteDecision, decision: str) -> dict:
    ip = _guard(request, action_limiter)
    with get_session() as session:
        link, q = _quote_for(session, ip, token)
        ql.apply_decision(q, decision, body.note, internal=False)
        return {"status": q.status, "number": q.number}


@router.post("/quotes/{token}/accept")
async def public_quote_accept(token: str, request: Request, body: QuoteDecision = QuoteDecision()):
    return _decide(token, request, body, "accept")


@router.post("/quotes/{token}/decline")
async def public_quote_decline(token: str, request: Request, body: QuoteDecision = QuoteDecision()):
    return _decide(token, request, body, "decline")
