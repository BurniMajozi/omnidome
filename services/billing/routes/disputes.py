"""Paystack disputes (chargebacks): record the charge.dispute.* webhooks and list them for the tenant.

This is step one of dispute handling: nothing is lost silently any more. Each event upserts a billing_disputes
row matched to the original charge (so tenant + invoice are known), open disputes freeze dunning/autopay for
the invoice, and platform ops is alerted because the evidence deadline is short and an unanswered dispute is
lost automatically. The evidence workflow (POST /dispute/{id}/evidence, uploads, accept/decline) and the
finance posting (hold / chargeback expense / receivable from the tenant) come with the reconciliation step.
Commission on a charge that is later lost is NOT refunded to the tenant (the processing happened).
"""

import asyncio
import logging
import os
import re
import uuid
from urllib.parse import quote
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from services.billing import finance_posting as fp
from services.billing.access import require_tier
from services.billing.contacts import resolve_customer_profile
from services.billing.database import get_session
from services.billing.models import BillingWebhookEvent, Invoice, PaystackInitialization, Payment, Subscription
from services.billing.models_gateway import GatewayCharge, GatewayDispute, GatewayLiability
from services.billing.routes import gateway as gw
from services.billing.routes.paystack_recurring import _paystack, _secret
from services.common import url_safety
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("billing.disputes")

router = APIRouter(prefix="/disputes", tags=["Disputes"])

CLOSED = ("resolved", "archived")
LOST_RESOLUTIONS = ("merchant-accepted", "accepted")      # we conceded (or the bank upheld it): the money is gone
WON_RESOLUTIONS = ("declined", "won")                     # the dispute was rejected: we keep the money


def outcome(d: GatewayDispute) -> Optional[str]:
    """'lost' | 'won' | None (still open, or a resolution value we do not recognise: never guessed)."""
    if d.status not in CLOSED:
        return None
    res = (d.resolution or "").lower()
    return "lost" if res in LOST_RESOLUTIONS else "won" if res in WON_RESOLUTIONS else None


def _dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def event_key(event: str, data: dict) -> str:
    # remind events repeat for the same dispute, so the status/updated time is part of the key
    return f"{event}:{data.get('id')}:{data.get('status')}:{data.get('updatedAt') or data.get('updated_at') or ''}"[:200]


async def handle_event(event: str, data: dict) -> str:
    """charge.dispute.create | .remind | .resolve. Returns 'accepted' | 'duplicate' | 'ignored'."""
    dispute_id = str(data.get("id") or "")
    if not dispute_id:
        logger.warning("dispute webhook without id (%s)", event)
        return "ignored"
    txn = data.get("transaction") or {}
    reference = txn.get("reference") or data.get("transaction_reference")
    alert = None
    with get_session() as session:
        try:
            with session.begin_nested():
                session.add(BillingWebhookEvent(provider="paystack", event_key=event_key(event, data), event_type=event,
                                                reference=reference or None))
                session.flush()
        except IntegrityError:
            return "duplicate"

        tenant_id = invoice_id = customer_id = None
        if reference:
            charge = session.execute(select(GatewayCharge).where(GatewayCharge.reference == reference)).scalar_one_or_none()
            if charge is not None:
                tenant_id, invoice_id = charge.tenant_id, charge.invoice_id
            init = session.execute(select(PaystackInitialization).where(PaystackInitialization.reference == reference)).scalar_one_or_none()
            if init is not None:
                tenant_id, invoice_id, customer_id = init.tenant_id, init.invoice_id, init.customer_id

        row = session.execute(select(GatewayDispute).where(GatewayDispute.paystack_dispute_id == dispute_id)).scalar_one_or_none()
        if row is None:
            row = GatewayDispute(paystack_dispute_id=dispute_id, status="unknown")
            session.add(row)
        row.tenant_id = row.tenant_id or tenant_id
        row.invoice_id = row.invoice_id or invoice_id
        row.customer_id = row.customer_id or customer_id
        row.reference = reference or row.reference
        row.amount_cents = int(data.get("refund_amount") or txn.get("amount") or row.amount_cents or 0)
        row.status = str(data.get("status") or row.status)
        row.category = data.get("category") or row.category
        row.resolution = data.get("resolution") or row.resolution
        row.due_at = _dt(data.get("dueAt") or data.get("due_at")) or row.due_at
        row.last_event = event
        lost_entry = None
        if outcome(row) == "lost" and row.tenant_id is not None and row.amount_cents > 0:
            lost_entry = post_lost(session, row)
        if row.tenant_id is None:
            logger.error("ALERT: Paystack dispute %s on %s matches no charge of ours", dispute_id, reference)
        if event.endswith(".create") or (event.endswith(".remind") and row.status not in CLOSED) or event.endswith(".resolve"):
            alert = (event, dispute_id, reference, row.amount_cents, row.status, row.due_at, row.tenant_id)
        session.flush()
        lost_tenant = row.tenant_id
    if lost_entry is not None:
        await fp.deliver_after_commit(lost_tenant, [lost_entry])
    if alert:
        ev, did, ref, cents, status, due, tenant = alert
        await gw._alert_ops(
            f"Paystack dispute {ev.rsplit('.', 1)[-1]}: R{cents / 100:.2f}",
            f"<p>Dispute <b>{did}</b> on transaction {ref or '(unknown)'} for R{cents / 100:.2f}, status <b>{status}</b>"
            f"{', respond by ' + due.strftime('%Y-%m-%d %H:%M UTC') if due else ''}. Tenant: {tenant or 'unmatched'}.</p>")
    return "accepted"


def post_lost(session, d: GatewayDispute) -> Optional[dict]:
    """A lost dispute is money taken from OmniDome's balance for a charge the tenant was already settled: open a
    liability against the tenant and post the chargeback to the tenant's books. Idempotent per dispute. The
    commission on the charge is kept (the processing happened)."""
    if session.execute(select(GatewayLiability.id).where(GatewayLiability.tenant_id == d.tenant_id, GatewayLiability.kind == "chargeback",
                                                         GatewayLiability.source_id == str(d.id))).first():
        return None
    session.add(GatewayLiability(tenant_id=d.tenant_id, kind="chargeback", source_id=str(d.id), amount_cents=d.amount_cents,
                                 note=f"Lost dispute {d.paystack_dispute_id} on {d.reference}"))
    entry = fp.chargeback_entry(d.id, d.reference or d.paystack_dispute_id, fp.sast_today(), Decimal(d.amount_cents) / 100)
    return entry if fp.enqueue(session, d.tenant_id, entry) is not None else None


def public(d: GatewayDispute) -> dict:
    return {"id": str(d.id), "dispute_id": d.paystack_dispute_id, "reference": d.reference,
            "invoice_id": str(d.invoice_id) if d.invoice_id else None, "amount_zar": d.amount_cents / 100,
            "status": d.status, "category": d.category, "resolution": d.resolution,
            "due_at": d.due_at.isoformat() if d.due_at else None, "open": d.status not in CLOSED, "outcome": outcome(d),
            "updated_at": d.updated_at.isoformat() if d.updated_at else None}


@router.get("", dependencies=[Depends(require_tier("reader"))])
async def list_disputes(ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        rows = session.execute(select(GatewayDispute).where(GatewayDispute.tenant_id == ctx.tenant_id)
                               .order_by(GatewayDispute.created_at.desc()).limit(200)).scalars().all()
        items = [public(d) for d in rows]
    due = sorted(i["due_at"] for i in items if i["open"] and i["due_at"])
    return {"disputes": items, "open": sum(1 for i in items if i["open"]), "next_due_at": due[0] if due else None}


# ---------------------------------------------------------------------------
# Detail, evidence, accept / decline
# ---------------------------------------------------------------------------

class EvidenceRequest(BaseModel):
    customer_email: str = Field(max_length=200)
    customer_name: str = Field(max_length=200)
    customer_phone: str = Field(max_length=40)
    service_details: str = Field(min_length=3, max_length=2000)
    delivery_address: str = Field(max_length=500)
    delivery_date: Optional[date] = None


class ResolveRequest(BaseModel):
    resolution: str = Field(pattern="^(merchant-accepted|declined)$")
    message: str = Field(min_length=3, max_length=1000)
    refund_amount_zar: Optional[Decimal] = Field(None, gt=0, max_digits=12, decimal_places=2)
    uploaded_filename: Optional[str] = Field(None, max_length=200)


def _own(session, tenant_id, dispute_id: uuid.UUID) -> GatewayDispute:
    d = session.execute(select(GatewayDispute).where(GatewayDispute.id == dispute_id, GatewayDispute.tenant_id == tenant_id)).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="Dispute not found")
    return d


async def build_evidence_pack(tenant_id, d: GatewayDispute) -> dict:
    """What we already know that answers the questions Paystack asks, from our own records. Editable before sending."""
    pack = {"customer_name": None, "customer_email": None, "customer_phone": None, "service_details": None,
            "delivery_address": None, "delivery_date": None, "invoice_numbers": [], "payments": [], "activity": []}
    customer_id = d.customer_id
    with get_session() as session:
        inv = session.get(Invoice, d.invoice_id) if d.invoice_id else None
        if inv is not None:
            customer_id = customer_id or inv.customer_id
            pack["invoice_numbers"] = [inv.number]
            pack["activity"].append({"at": inv.created_at.isoformat() if inv.created_at else None,
                                     "text": f"Invoice {inv.number} for R{inv.total_zar:.2f} issued"})
            for p in session.execute(select(Payment).where(Payment.tenant_id == tenant_id, Payment.invoice_id == inv.id)
                                     .order_by(Payment.created_at)).scalars():
                pack["payments"].append({"reference": p.paystack_ref or p.reference, "amount_zar": float(p.amount_zar),
                                         "paid_at": p.created_at.isoformat() if p.created_at else None})
        if customer_id:
            sub = session.execute(select(Subscription).where(Subscription.tenant_id == tenant_id, Subscription.customer_id == customer_id)
                                  .order_by(Subscription.billing_anchor)).scalars().first()
            if sub is not None:
                pack["service_details"] = f"{sub.plan or 'Fibre internet'} subscription, billed {str(sub.billing_interval).lower()}"
                pack["delivery_date"] = sub.billing_anchor.isoformat() if sub.billing_anchor else None
                pack["activity"].append({"at": pack["delivery_date"], "text": f"Service started ({sub.plan})"})
    if customer_id:
        profile = await resolve_customer_profile(tenant_id, customer_id)
        pack.update(customer_name=profile["name"], customer_email=profile["email"], customer_phone=profile["phone"],
                    delivery_address=profile["address"])
    return pack


@router.get("/{dispute_id}", dependencies=[Depends(require_tier("reader"))])
async def dispute_detail(dispute_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        d = _own(session, ctx.tenant_id, dispute_id)
        base = public(d)
    return {**base, "evidence_pack": await build_evidence_pack(ctx.tenant_id, d)}


@router.post("/{dispute_id}/evidence", dependencies=[Depends(require_tier("admin"))])
async def submit_evidence(dispute_id: uuid.UUID, body: EvidenceRequest, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        d = _own(session, ctx.tenant_id, dispute_id)
        if d.status in CLOSED:
            raise HTTPException(status_code=409, detail="This dispute is already closed")
        pid = d.paystack_dispute_id
    if not _secret():
        raise HTTPException(status_code=503, detail="Paystack not configured")
    payload = {"customer_email": body.customer_email, "customer_name": body.customer_name, "customer_phone": body.customer_phone,
               "service_details": body.service_details, "delivery_address": body.delivery_address}
    if body.delivery_date:
        payload["delivery_date"] = body.delivery_date.isoformat()
    res = await _paystack("POST", f"/dispute/{pid}/evidence", payload)
    if not res.get("status"):
        raise HTTPException(status_code=502, detail=res.get("message", "Paystack rejected the evidence"))
    logger.info("dispute evidence submitted dispute=%s tenant=%s by=%s", pid, ctx.tenant_id, ctx.user_id)
    return {"submitted": True, "dispute_id": pid}


@router.post("/{dispute_id}/resolve", dependencies=[Depends(require_tier("admin"))])
async def resolve_dispute(dispute_id: uuid.UUID, body: ResolveRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Accept (we concede; the refund amount is returned to the customer) or decline (we contest). The final state
    arrives with the charge.dispute.resolve webhook, which is what posts a lost dispute to the books."""
    with get_session() as session:
        d = _own(session, ctx.tenant_id, dispute_id)
        if d.status in CLOSED:
            raise HTTPException(status_code=409, detail="This dispute is already closed")
        pid, default_cents = d.paystack_dispute_id, d.amount_cents
    if not _secret():
        raise HTTPException(status_code=503, detail="Paystack not configured")
    payload = {"resolution": body.resolution, "message": body.message}
    if body.resolution == "merchant-accepted":
        payload["refund_amount"] = int((body.refund_amount_zar * 100).to_integral_value()) if body.refund_amount_zar else default_cents
    if body.uploaded_filename:
        payload["uploaded_filename"] = body.uploaded_filename
    res = await _paystack("PUT", f"/dispute/{pid}/resolve", payload)
    if not res.get("status"):
        raise HTTPException(status_code=502, detail=res.get("message", "Paystack rejected the resolution"))
    logger.info("dispute %s %s tenant=%s by=%s", pid, body.resolution, ctx.tenant_id, ctx.user_id)
    return {"resolution": body.resolution, "dispute_id": pid, "note": "Final status arrives from Paystack"}


# ---------------------------------------------------------------------------
# Evidence attachments (Paystack signed-URL upload)
# ---------------------------------------------------------------------------

ATTACHMENT_TYPES = {".pdf": (b"%PDF",), ".png": (b"\x89PNG",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",)}
CONTENT_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def max_attachment_bytes() -> int:
    return int(float(os.getenv("DISPUTE_ATTACHMENT_MAX_MB", "5")) * 1024 * 1024)


def _safe_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(name or "evidence"))[:80].strip("._") or "evidence"
    return base


@router.post("/{dispute_id}/attachments", dependencies=[Depends(require_tier("admin"))])
async def upload_attachment(dispute_id: uuid.UUID, file: UploadFile = File(...), ctx: AuthContext = Depends(get_auth_context)):
    """Upload one evidence file (PDF/PNG/JPG, size-capped, content checked) to the signed URL Paystack issues, and return the
    `uploaded_filename` to pass to POST /disputes/{id}/resolve. The file is held in memory only; nothing is stored here."""
    with get_session() as session:
        d = _own(session, ctx.tenant_id, dispute_id)
        if d.status in CLOSED:
            raise HTTPException(status_code=409, detail="This dispute is already closed")
        pid = d.paystack_dispute_id
    if not _secret():
        raise HTTPException(status_code=503, detail="Paystack not configured")
    name = _safe_name(file.filename or "")
    ext = os.path.splitext(name)[1].lower()
    if ext not in ATTACHMENT_TYPES:
        raise HTTPException(status_code=415, detail="Only PDF, PNG or JPG files can be uploaded")
    limit = max_attachment_bytes()
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"File is larger than {limit // (1024 * 1024)} MB")
    if not data or not any(data.startswith(magic) for magic in ATTACHMENT_TYPES[ext]):
        raise HTTPException(status_code=415, detail="The file content does not match its type")
    res = await _paystack("GET", f"/dispute/{pid}/upload_url?upload_filename={quote(name)}")
    info = res.get("data") or {}
    signed, stored = info.get("signedUrl"), info.get("fileName")
    if not res.get("status") or not signed or not stored:
        raise HTTPException(status_code=502, detail=res.get("message") or "Paystack did not return an upload URL")
    try:
        await asyncio.to_thread(url_safety.validate_public_url, signed)       # never PUT to a non-public address
    except url_safety.UnsafeUrl:
        logger.error("dispute upload URL for %s rejected by url_safety", pid)
        raise HTTPException(status_code=502, detail="Paystack returned an unusable upload URL")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            put = await client.put(signed, content=data, headers={"Content-Type": CONTENT_TYPES[ext]})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Upload to the payment provider failed") from exc
    if put.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"The payment provider rejected the upload (HTTP {put.status_code})")
    logger.info("dispute evidence uploaded dispute=%s tenant=%s by=%s bytes=%d", pid, ctx.tenant_id, ctx.user_id, len(data))
    return {"uploaded_filename": stored, "size_bytes": len(data)}
