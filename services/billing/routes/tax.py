"""Tenant VAT profile: the tenant chooses whether it charges VAT, and the system tells it when SARS says it must.

GET  /tax/profile   the saved position (or the legacy default with `configured: false`)
PUT  /tax/profile   save it (admin): validated against SARS rules (VAT number format, name + address for a vendor)
GET  /tax/status    South African registration thresholds against what the tenant has invoiced in the last 12 months
GET  /tax/countries countries the UI offers
Changes apply to documents issued from then on; issued invoices keep the VAT they were issued with.
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from services.billing import calc, tax
from services.billing.access import require_tier
from services.billing.database import get_session
from services.billing.models import Invoice
from services.billing.models_tax import TaxProfileEvent, TaxProfileRow
from services.billing.tax_store import profile_for
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("billing.tax")

router = APIRouter(prefix="/tax", tags=["Tax"])


class TaxProfileIn(BaseModel):
    country: str = Field("ZA", min_length=2, max_length=2)
    vat_registered: bool
    vat_number: Optional[str] = Field(None, max_length=20)
    rate_percent: Optional[Decimal] = Field(None, ge=0, le=30, max_digits=5, decimal_places=2)
    prices_include_vat: bool = True
    legal_name: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = Field(None, max_length=500)
    registered_since: Optional[date] = None


@router.get("/countries", dependencies=[Depends(require_tier("reader"))])
async def countries():
    return {"countries": [{**c, "default_rate_percent": float(tax.za_rate_percent()) if c["code"] == "ZA" else None} for c in tax.COUNTRIES]}


@router.get("/profile", dependencies=[Depends(require_tier("reader"))])
async def get_profile(ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        return profile_for(session, ctx.tenant_id).public()


@router.put("/profile", dependencies=[Depends(require_tier("admin"))])
async def put_profile(body: TaxProfileIn, ctx: AuthContext = Depends(get_auth_context)):
    try:
        new = tax.validate_profile(country=body.country, vat_registered=body.vat_registered, vat_number=body.vat_number,
                                   rate_percent=body.rate_percent, prices_include_vat=body.prices_include_vat,
                                   legal_name=body.legal_name, address=body.address, registered_since=body.registered_since)
    except tax.TaxProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    with get_session() as session:
        before = profile_for(session, ctx.tenant_id)
        row = session.execute(select(TaxProfileRow).where(TaxProfileRow.tenant_id == ctx.tenant_id)).scalar_one_or_none()
        if row is None:
            row = TaxProfileRow(tenant_id=ctx.tenant_id)
            session.add(row)
        row.country, row.vat_registered, row.vat_number, row.rate_percent = new.country, new.vat_registered, new.vat_number, new.rate_percent
        row.prices_include_vat, row.legal_name, row.address = new.prices_include_vat, new.legal_name, new.address
        row.registered_since, row.updated_by = new.registered_since, ctx.user_id
        session.add(TaxProfileEvent(tenant_id=ctx.tenant_id, actor_id=ctx.user_id, before=before.public() if before.configured else None,
                                    after=new.public()))
        logger.info("AUDIT billing.tax_profile tenant=%s by=%s registered=%s country=%s", ctx.tenant_id, ctx.user_id, new.vat_registered, new.country)
        session.flush()
        return new.public()


def invoiced_ex_vat(session, tenant_id, since: date, until: date) -> Decimal:
    """Ex-VAT value invoiced in [since, until]: issued invoices count, credit notes net off, drafts and voids do not."""
    total = session.execute(select(func.coalesce(func.sum(Invoice.subtotal_zar), 0)).where(
        Invoice.tenant_id == tenant_id, Invoice.status.notin_(("draft", "voided")),
        func.date(Invoice.created_at) >= since, func.date(Invoice.created_at) <= until)).scalar_one()
    return Decimal(str(total))


@router.get("/status", dependencies=[Depends(require_tier("reader"))])
async def registration_status(ctx: AuthContext = Depends(get_auth_context)):
    today = calc.today_sast()
    year_ago, quarter_ago, _ = tax.twelve_month_window(today)
    with get_session() as session:
        profile = profile_for(session, ctx.tenant_id)
        twelve = invoiced_ex_vat(session, ctx.tenant_id, year_ago, today)
        three = invoiced_ex_vat(session, ctx.tenant_id, quarter_ago, today)
    return {**tax.registration_status(profile, twelve, three), "profile": profile.public(),
            "full_tax_invoice_above_zar": float(tax.FULL_INVOICE_ABOVE)}
