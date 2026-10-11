"""OmniDome's monthly tax invoice to the tenant for gateway and payout fees (see services/billing/fee_invoicing.py).

GET  /fee-invoices            the tenant's invoices (platform admins: ?all=true for every tenant)
GET  /fee-invoices/{id}       one invoice as JSON, or ?format=html for the printable document
POST /fee-invoices/generate   platform admin: issue the invoice for a period (default: last month) for one tenant or all of them
Issued invoices are immutable: there is no update or delete.
"""

import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from services.billing import calc, document_render as render, fee_invoicing as fi
from services.billing.access import require_tier
from services.billing.database import get_session
from services.billing.models_fee_invoices import FeeInvoice
from services.billing.routes import gateway as gw
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("billing.fee_invoices")

router = APIRouter(prefix="/fee-invoices", tags=["Fee invoices"])

HTML_HEADERS = {"Content-Security-Policy": render.CSP, "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}


class GenerateIn(BaseModel):
    period: Optional[str] = Field(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    tenant_id: Optional[uuid.UUID] = None


def _summary(inv: FeeInvoice) -> dict:
    return {"id": str(inv.id), "tenant_id": str(inv.tenant_id), "number": inv.number, "period": inv.period,
            "issue_date": inv.issue_date.isoformat(), "doc_type": inv.doc_type, "complete": inv.complete,
            "subtotal_zar": inv.subtotal_cents / 100, "vat_zar": inv.vat_cents / 100, "total_zar": inv.total_cents / 100}


@router.get("", dependencies=[Depends(require_tier("reader"))])
async def list_invoices(all: bool = False, ctx: AuthContext = Depends(get_auth_context)):
    if all and not gw._is_platform_admin(ctx):
        raise HTTPException(status_code=403, detail="Platform admin only")
    with get_session() as session:
        q = select(FeeInvoice) if all else select(FeeInvoice).where(FeeInvoice.tenant_id == ctx.tenant_id)
        rows = session.execute(q.order_by(FeeInvoice.issue_date.desc(), FeeInvoice.number.desc()).limit(500)).scalars().all()
        return {"invoices": [_summary(r) for r in rows]}


@router.get("/{invoice_id}", dependencies=[Depends(require_tier("reader"))])
async def get_invoice(invoice_id: uuid.UUID, format: str = Query("json", pattern="^(json|html)$"), ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        inv = session.execute(select(FeeInvoice).where(FeeInvoice.id == invoice_id)).scalar_one_or_none()
        # a tenant sees only its own; the same 404 for "not yours" and "does not exist"
        if inv is None or (inv.tenant_id != ctx.tenant_id and not gw._is_platform_admin(ctx)):
            raise HTTPException(status_code=404, detail="Invoice not found")
        if format == "html":
            return HTMLResponse(render.render_html(fi.render_view(inv)), headers=HTML_HEADERS)
        return fi.to_dict(inv)


@router.post("/generate", dependencies=[Depends(require_tier("admin"))])
async def generate(body: GenerateIn = GenerateIn(), ctx: AuthContext = Depends(get_auth_context)):
    if not gw._is_platform_admin(ctx):
        raise HTTPException(status_code=403, detail="Platform admin only")
    return {"period": body.period or fi.previous_period(), "issued": generate_for(body.period or fi.previous_period(), body.tenant_id)}


def generate_for(period: str, tenant_id: Optional[uuid.UUID] = None) -> list:
    """Issue the invoice for each tenant that has fees to bill (each in its own transaction, so one failure never blocks the rest)."""
    with get_session() as session:
        tenants = [tenant_id] if tenant_id else fi.tenants_with_fees(session, period)
    issued = []
    for t in tenants:
        try:
            with get_session() as session:
                existing = session.execute(select(FeeInvoice.id).where(FeeInvoice.tenant_id == t, FeeInvoice.period == period)).first()
                inv = fi.generate(session, t, period)
                if inv is not None and existing is None:
                    issued.append(_summary(inv))
        except Exception:  # noqa: BLE001
            logger.exception("fee invoice failed tenant=%s period=%s", t, period)
    return issued


# ---------------------------------------------------------------------------
# Scheduler (opt-in): FEE_INVOICE_WORKER_ENABLED=true; from the 2nd of the month it issues last month's invoices (idempotent)
# ---------------------------------------------------------------------------

def worker_enabled() -> bool:
    return os.getenv("FEE_INVOICE_WORKER_ENABLED", "false").strip().lower() == "true"


async def worker_loop(interval_seconds: int = 6 * 3600) -> None:
    import asyncio
    logger.info("fee invoice worker started (interval %ss)", interval_seconds)
    while True:
        try:
            today = calc.today_sast()
            if today.day >= 2:
                out = generate_for(fi.previous_period(today))
                if out:
                    logger.info("fee invoices issued: %d", len(out))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("fee invoice worker pass failed")
        await asyncio.sleep(interval_seconds)
