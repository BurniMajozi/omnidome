"""Finance outbox + dunning cron endpoints (internal key, or a billing admin for their own tenant).

These two paths are public to the entitlement middleware (so an internal-key-only scheduler can
call them without identity headers); authorization is enforced HERE.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from services.common.auth import AuthContext, get_auth_context
from services.billing import dunning, finance_posting as fp
from services.billing.access import internal_key_ok, require, require_tier
from services.billing.database import get_session
from services.billing.models import BillingFinanceOutbox

logger = logging.getLogger("billing.outbox")

router = APIRouter(tags=["Finance outbox", "Dunning"])

PUBLIC_PATHS = {"/dunning/process", "/billing/finance-outbox/retry"}


@router.post("/billing/finance-outbox/retry")
async def retry_finance_outbox(request: Request, limit: int = 100):
    """Re-deliver pending/failed journal entries now (ignores backoff).
    Internal key: every tenant. Billing admin: their own tenant only."""
    limit = max(1, min(limit, 500))
    if internal_key_ok(request):
        return await fp.deliver(None, force=True, limit=limit)
    ctx: AuthContext = await get_auth_context(request)
    await require(ctx, "admin")
    return await fp.deliver(ctx.tenant_id, force=True, limit=limit)


@router.get("/billing/finance-outbox", dependencies=[Depends(require_tier("admin"))])
async def list_finance_outbox(ctx: AuthContext = Depends(get_auth_context), status: Optional[str] = None):
    with get_session() as session:
        q = session.query(BillingFinanceOutbox).filter(BillingFinanceOutbox.tenant_id == ctx.tenant_id)
        if status:
            q = q.filter(BillingFinanceOutbox.status == status)
        rows = q.order_by(BillingFinanceOutbox.created_at.desc()).limit(200).all()
        return [{"id": str(r.id), "source": r.source, "source_id": r.source_id, "status": r.status,
                 "attempts": r.attempts, "last_error": r.last_error} for r in rows]


@router.post("/dunning/process")
async def run_dunning(request: Request):
    """Cron entry point: process due dunning actions for EVERY tenant. Internal key only."""
    if not internal_key_ok(request):
        raise HTTPException(status_code=403, detail="internal service key required")
    return await dunning.process_pending_dunning()


@router.post("/dunning/process-tenant", dependencies=[Depends(require_tier("admin"))])
async def run_dunning_for_tenant(ctx: AuthContext = Depends(get_auth_context)):
    """Billing admins: process due dunning actions for their own tenant only."""
    return await dunning.process_pending_dunning(ctx.tenant_id)
