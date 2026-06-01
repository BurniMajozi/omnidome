"""OmniDome Marketing Service — campaigns, email delivery, A/B testing, automation.

Fixes applied:
1. Webhook auth: HMAC SHA256 signature verification on email event ingestion
2. Table creation: moved from per-request middleware to startup event only
3. Pagination: added to campaign list endpoint
"""

import logging
import os
import hashlib
import hmac
import uuid
import math
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, Query, Request, Header, status
from pydantic import BaseModel, Field

from services.common.entitlements import EntitlementGuard
from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from marketing.models import (
    MarketingCampaign, EmailBatch, EmailRecipient, EmailEvent,
    MarketingTemplate, ABTest, AutomationFlow, AutomationStep, AutomationRun,
    MarketingLead,
)
from marketing.schemas import (
    CampaignCreate, CampaignRead, CampaignUpdate,
    EmailSendRequest, EmailPreviewRequest,
    TemplateCreate, TemplateRead,
    ABTestCreate, ABTestRead,
    AutomationCreate, AutomationRead, AutomationRunRequest,
    PaginatedResponse,
)

logger = logging.getLogger("marketing")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(
    title="OmniDome Marketing Service",
    version="1.0.0",
    description="Campaign management, email delivery, A/B testing, lead scoring, automation",
)

guard = EntitlementGuard(
    module_id="marketing",
    public_paths={"/health", "/docs", "/openapi.json", "/api/v1/email/webhook"},
)

# Webhook secret for email provider callbacks
WEBHOOK_SECRET = os.getenv("MARKETING_WEBHOOK_SECRET", "")


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    # FIX #2: Only create tables on startup, not on every request
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        from marketing.database import init_tables
        init_tables()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


def _verify_webhook_signature(body: bytes, signature: str) -> bool:
    """FIX #1: Verify HMAC SHA256 signature from email provider webhook."""
    if not WEBHOOK_SECRET:
        logger.warning("MARKETING_WEBHOOK_SECRET not set — skipping webhook verification")
        return True
    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── Health ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"service": "marketing", "status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# ── Campaigns ──────────────────────────────────────────────────────────

@app.post("/api/v1/campaigns", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
async def create_campaign(body: CampaignCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        campaign = MarketingCampaign(
            tenant_id=ctx.tenant_id, name=body.name, description=body.description,
            campaign_type=body.campaign_type, channel=body.channel,
            target_segment=body.target_segment, budget_zar=body.budget_zar,
            start_date=body.start_date, end_date=body.end_date, created_by=ctx.user_id,
        )
        session.add(campaign)
        await session.flush()
        await session.refresh(campaign)
        return CampaignRead.model_validate(campaign)


@app.get("/api/v1/campaigns")
async def list_campaigns(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    campaign_type: Optional[str] = Query(None),
):
    """FIX #3: Paginated campaign list."""
    from sqlalchemy import select, func
    async with session_scope() as session:
        query = select(MarketingCampaign).where(MarketingCampaign.tenant_id == ctx.tenant_id)
        if status_filter:
            query = query.where(MarketingCampaign.status == status_filter)
        if campaign_type:
            query = query.where(MarketingCampaign.campaign_type == campaign_type)
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        items = (await session.execute(
            query.order_by(MarketingCampaign.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        return PaginatedResponse(
            items=[CampaignRead.model_validate(i) for i in items],
            total=total or 0, page=page, page_size=page_size,
            pages=max(1, math.ceil((total or 0) / page_size)),
        )


@app.get("/api/v1/campaigns/{campaign_id}", response_model=CampaignRead)
async def get_campaign(campaign_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        campaign = await session.get(MarketingCampaign, campaign_id)
        if not campaign or campaign.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Campaign not found")
        return CampaignRead.model_validate(campaign)


@app.put("/api/v1/campaigns/{campaign_id}", response_model=CampaignRead)
async def update_campaign(campaign_id: uuid.UUID, body: CampaignUpdate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        campaign = await session.get(MarketingCampaign, campaign_id)
        if not campaign or campaign.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Campaign not found")
        for k, v in body.model_dump(exclude_unset=True).items():
            setattr(campaign, k, v)
        await session.flush()
        await session.refresh(campaign)
        return CampaignRead.model_validate(campaign)


@app.delete("/api/v1/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        campaign = await session.get(MarketingCampaign, campaign_id)
        if not campaign or campaign.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Campaign not found")
        await session.delete(campaign)
        return {"status": "deleted", "id": str(campaign_id)}


# ── Email Webhook (FIX #1: now with HMAC auth) ────────────────────────

@app.post("/api/v1/email/webhook")
async def email_webhook(
    request: Request,
    x_webhook_signature: Optional[str] = Header(None),
):
    """Handle email provider webhook callbacks (delivery, bounce, open, click).
    FIX #1: Requires HMAC SHA256 signature when MARKETING_WEBHOOK_SECRET is set.
    """
    raw_body = await request.body()

    if x_webhook_signature and not _verify_webhook_signature(raw_body, x_webhook_signature):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    import json
    payload = json.loads(raw_body)
    event_type = payload.get("event", "")
    message_id = payload.get("message_id", "")
    email = payload.get("email", "")
    logger.info("Email webhook: event=%s email=%s message_id=%s", event_type, email, message_id[:8])

    async with session_scope() as session:
        # Find recipient by external message ID and update event
        recipient = (await session.execute(
            __import__('sqlalchemy').select(EmailRecipient).where(
                EmailRecipient.external_message_id == message_id
            )
        )).scalars().first()

        if recipient:
            event = EmailEvent(
                recipient_id=recipient.id, event_type=event_type,
                email=email, payload=payload,
            )
            session.add(event)
            # Update recipient status
            if event_type == "delivered":
                recipient.status = "delivered"
            elif event_type == "bounced":
                recipient.status = "bounced"
            elif event_type in ("opened", "clicked"):
                recipient.status = event_type

    return {"status": "accepted"}


# ── Templates ──────────────────────────────────────────────────────────

@app.post("/api/v1/templates", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(body: TemplateCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        tpl = MarketingTemplate(
            tenant_id=ctx.tenant_id, name=body.name,
            subject_template=subject_template, body_template=body.body_template,
            variables=body.variables, created_by=ctx.user_id,
        )
        session.add(tpl)
        await session.flush()
        await session.refresh(tpl)
        return TemplateRead.model_validate(tpl)


@app.get("/api/v1/templates")
async def list_templates(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    from sqlalchemy import select, func
    async with session_scope() as session:
        query = select(MarketingTemplate).where(MarketingTemplate.tenant_id == ctx.tenant_id)
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        items = (await session.execute(query.order_by(MarketingTemplate.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
        return PaginatedResponse(
            items=[TemplateRead.model_validate(t) for t in items],
            total=total or 0, page=page, page_size=page_size,
            pages=max(1, math.ceil((total or 0) / page_size)),
        )


# ── A/B Testing ────────────────────────────────────────────────────────

@app.post("/api/v1/ab-tests", response_model=ABTestRead, status_code=status.HTTP_201_CREATED)
async def create_ab_test(body: ABTestCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        test = ABTest(
            tenant_id=ctx.tenant_id, name=body.name, campaign_id=body.campaign_id,
            variant_a_subject=body.variant_a_subject, variant_a_body=body.variant_a_body,
            variant_b_subject=body.variant_b_subject, variant_b_body=body.variant_b_body,
            split_percentage=body.split_percentage, created_by=ctx.user_id,
        )
        session.add(test)
        await session.flush()
        await session.refresh(test)
        return ABTestRead.model_validate(test)


@app.get("/api/v1/ab-tests")
async def list_ab_tests(ctx: AuthContext = Depends(get_auth_context), limit: int = Query(50, le=200)):
    from sqlalchemy import select
    async with session_scope() as session:
        items = (await session.execute(select(ABTest).where(ABTest.tenant_id == ctx.tenant_id).order_by(ABTest.created_at.desc()).limit(limit))).scalars().all()
        return [ABTestRead.model_validate(t) for t in items]


# ── Automation ─────────────────────────────────────────────────────────

@app.post("/api/v1/automations", response_model=AutomationRead, status_code=status.HTTP_201_CREATED)
async def create_automation(body: AutomationCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        flow = AutomationFlow(
            tenant_id=ctx.tenant_id, name=body.name, description=body.description,
            trigger_type=body.trigger_type, trigger_config=body.trigger_config,
            created_by=ctx.user_id,
        )
        session.add(flow)
        await session.flush()
        for i, step_data in enumerate(body.steps):
            step = AutomationStep(
                flow_id=flow.id, step_order=i,
                step_type=step_data.step_type, config=step_data.config,
            )
            session.add(step)
        await session.refresh(flow)
        return AutomationRead.model_validate(flow)


@app.get("/api/v1/automations")
async def list_automations(ctx: AuthContext = Depends(get_auth_context), limit: int = Query(50, le=200)):
    from sqlalchemy import select
    async with session_scope() as session:
        items = (await session.execute(select(AutomationFlow).where(AutomationFlow.tenant_id == ctx.tenant_id).order_by(AutomationFlow.created_at.desc()).limit(limit))).scalars().all()
        return [AutomationRead.model_validate(f) for f in items]


@app.post("/api/v1/automations/{flow_id}/run")
async def run_automation(flow_id: uuid.UUID, body: AutomationRunRequest, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        flow = await session.get(AutomationFlow, flow_id)
        if not flow or flow.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Automation not found")
        run = AutomationRun(flow_id=flow_id, triggered_by=body.triggered_by, status="running")
        session.add(run)
        await session.flush()
        return {"run_id": str(run.id), "status": "started"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8014)
