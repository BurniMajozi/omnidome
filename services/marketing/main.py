"""
OmniDome Marketing Service
===========================
Campaign management · Email delivery · Lead scoring · Automation · Attribution

Port: 8014
"""

from datetime import datetime, timedelta
from decimal import Decimal
import os
from typing import Any, Dict, List, Optional
import uuid

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from services.common.auth import AuthContext, get_auth_context, get_current_tenant_id
from services.common.db import get_engine
from services.common.entitlements import EntitlementGuard

app = FastAPI(title="OmniDome Marketing Service", version="1.0.0")
guard = EntitlementGuard(module_id="marketing")


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


# ─────────────────────────────── Pydantic Models ───────────────────────────────


class CampaignCreate(BaseModel):
    name: str
    channel: str = Field(..., description="email | social | search | display | sms")
    description: Optional[str] = None
    budget_zar: Decimal = Decimal("0")
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    audience_segment_id: Optional[uuid.UUID] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    channel: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    budget_zar: Optional[Decimal] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class CampaignOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    channel: str
    status: str
    description: Optional[str]
    budget_zar: Decimal
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    total_sent: int
    total_delivered: int
    total_opened: int
    total_clicked: int
    total_conversions: int
    created_at: datetime


class EmailSendRequest(BaseModel):
    campaign_id: uuid.UUID
    template_id: Optional[uuid.UUID] = None
    subject: str
    body_html: str
    recipients: List[str] = Field(..., description="List of email addresses")
    from_name: Optional[str] = "OmniDome"
    from_email: Optional[str] = None
    reply_to: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class EmailSendResponse(BaseModel):
    batch_id: uuid.UUID
    campaign_id: uuid.UUID
    total_queued: int
    status: str


class LeadScoreUpdate(BaseModel):
    contact_id: uuid.UUID
    score_delta: int = Field(..., description="Points to add (positive) or remove (negative)")
    reason: str


class AudienceSegmentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    rules: Dict[str, Any] = Field(default_factory=dict, description="JSON filter rules")


class AutomationCreate(BaseModel):
    name: str
    trigger_type: str = Field(..., description="event | schedule | lead_score")
    trigger_config: Dict[str, Any] = Field(default_factory=dict)
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True


class TemplateCreate(BaseModel):
    name: str
    subject: str
    body_html: str
    category: str = "promotional"


class ABTestCreate(BaseModel):
    campaign_id: uuid.UUID
    variant_a: Dict[str, Any] = Field(..., description="Subject/body for variant A")
    variant_b: Dict[str, Any] = Field(..., description="Subject/body for variant B")
    split_pct: int = Field(50, ge=10, le=90)
    metric: str = Field("open_rate", description="open_rate | ctr | conversions")
    duration_hours: int = 24


class DashboardMetrics(BaseModel):
    active_campaigns: int
    email_delivery_rate: float
    lead_conversion_rate: float
    marketing_roi: float
    total_leads: int
    total_mql: int
    total_sql: int
    emails_sent_mtd: int
    emails_delivered_mtd: int
    emails_opened_mtd: int
    bounce_rate: float
    open_rate: float


# ─────────────────────────── Helper ───────────────────────────


def _ensure_marketing_tables(engine) -> None:
    """Create marketing tables if they don't exist (idempotent)."""
    ddl = """
    CREATE TABLE IF NOT EXISTS marketing_campaigns (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        name VARCHAR(255) NOT NULL,
        channel VARCHAR(50) NOT NULL DEFAULT 'email',
        status VARCHAR(30) NOT NULL DEFAULT 'draft',
        description TEXT,
        budget_zar NUMERIC(14,2) DEFAULT 0,
        start_date TIMESTAMPTZ,
        end_date TIMESTAMPTZ,
        audience_segment_id UUID,
        total_sent INT DEFAULT 0,
        total_delivered INT DEFAULT 0,
        total_opened INT DEFAULT 0,
        total_clicked INT DEFAULT 0,
        total_conversions INT DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS marketing_email_batches (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        campaign_id UUID NOT NULL REFERENCES marketing_campaigns(id),
        subject VARCHAR(500),
        from_name VARCHAR(255),
        from_email VARCHAR(255),
        total_queued INT DEFAULT 0,
        total_sent INT DEFAULT 0,
        total_delivered INT DEFAULT 0,
        total_bounced INT DEFAULT 0,
        total_opened INT DEFAULT 0,
        total_clicked INT DEFAULT 0,
        status VARCHAR(30) DEFAULT 'queued',
        created_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS marketing_email_events (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        batch_id UUID NOT NULL REFERENCES marketing_email_batches(id),
        recipient_email VARCHAR(320),
        event_type VARCHAR(30) NOT NULL,
        event_data JSONB DEFAULT '{}',
        created_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS marketing_templates (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        name VARCHAR(255) NOT NULL,
        subject VARCHAR(500),
        body_html TEXT,
        category VARCHAR(50) DEFAULT 'promotional',
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS marketing_audience_segments (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        name VARCHAR(255) NOT NULL,
        description TEXT,
        rules JSONB DEFAULT '{}',
        member_count INT DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS marketing_lead_scores (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        contact_id UUID NOT NULL,
        score INT DEFAULT 0,
        last_scored_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (tenant_id, contact_id)
    );

    CREATE TABLE IF NOT EXISTS marketing_automations (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        name VARCHAR(255) NOT NULL,
        trigger_type VARCHAR(50) NOT NULL,
        trigger_config JSONB DEFAULT '{}',
        actions JSONB DEFAULT '[]',
        is_active BOOLEAN DEFAULT TRUE,
        total_triggered INT DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS marketing_ab_tests (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        campaign_id UUID NOT NULL REFERENCES marketing_campaigns(id),
        variant_a JSONB NOT NULL,
        variant_b JSONB NOT NULL,
        split_pct INT DEFAULT 50,
        metric VARCHAR(30) DEFAULT 'open_rate',
        duration_hours INT DEFAULT 24,
        status VARCHAR(30) DEFAULT 'running',
        winner VARCHAR(10),
        created_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_mkt_campaigns_tenant ON marketing_campaigns(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_mkt_batches_campaign ON marketing_email_batches(campaign_id);
    CREATE INDEX IF NOT EXISTS idx_mkt_events_batch ON marketing_email_events(batch_id);
    CREATE INDEX IF NOT EXISTS idx_mkt_lead_scores_tenant ON marketing_lead_scores(tenant_id, contact_id);
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))


# ─────────────────────────── Campaigns ─────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "service": "marketing"}


@app.get("/campaigns", response_model=List[CampaignOut])
async def list_campaigns(
    channel: Optional[str] = None,
    campaign_status: Optional[str] = Query(None, alias="status"),
    limit: int = 50,
    offset: int = 0,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    filters = "WHERE tenant_id = :tid"
    params: Dict[str, Any] = {"tid": str(tenant_id), "lim": limit, "off": offset}
    if channel:
        filters += " AND channel = :ch"
        params["ch"] = channel
    if campaign_status:
        filters += " AND status = :st"
        params["st"] = campaign_status
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT * FROM marketing_campaigns {filters} ORDER BY created_at DESC LIMIT :lim OFFSET :off"),
            params,
        ).mappings().all()
    return [dict(r) for r in rows]


@app.post("/campaigns", response_model=CampaignOut, status_code=201)
async def create_campaign(
    body: CampaignCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    cid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_campaigns
                    (id, tenant_id, name, channel, description, budget_zar, start_date, end_date, audience_segment_id)
                VALUES
                    (:id, :tid, :name, :ch, :desc, :budget, :sd, :ed, :asid)
            """),
            {
                "id": str(cid),
                "tid": str(tenant_id),
                "name": body.name,
                "ch": body.channel,
                "desc": body.description,
                "budget": float(body.budget_zar),
                "sd": body.start_date,
                "ed": body.end_date,
                "asid": str(body.audience_segment_id) if body.audience_segment_id else None,
            },
        )
        row = conn.execute(
            text("SELECT * FROM marketing_campaigns WHERE id = :id"), {"id": str(cid)}
        ).mappings().first()
    return dict(row)


@app.patch("/campaigns/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    sets = []
    params: Dict[str, Any] = {"cid": str(campaign_id), "tid": str(tenant_id)}
    for field, val in body.dict(exclude_unset=True).items():
        sets.append(f"{field} = :{field}")
        params[field] = float(val) if isinstance(val, Decimal) else val
    if not sets:
        raise HTTPException(400, "No fields to update")
    sets.append("updated_at = now()")
    with engine.begin() as conn:
        result = conn.execute(
            text(f"UPDATE marketing_campaigns SET {', '.join(sets)} WHERE id = :cid AND tenant_id = :tid RETURNING *"),
            params,
        ).mappings().first()
    if not result:
        raise HTTPException(404, "Campaign not found")
    return dict(result)


@app.delete("/campaigns/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM marketing_campaigns WHERE id = :cid AND tenant_id = :tid"),
            {"cid": str(campaign_id), "tid": str(tenant_id)},
        )


# ─────────────────────── Email Delivery ───────────────────────


@app.post("/email/send", response_model=EmailSendResponse, status_code=202)
async def send_email_batch(
    body: EmailSendRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Queue a batch of emails for delivery (transactional or bulk)."""
    engine = get_engine()
    _ensure_marketing_tables(engine)
    batch_id = uuid.uuid4()
    total = len(body.recipients)
    with engine.begin() as conn:
        # Verify campaign exists
        camp = conn.execute(
            text("SELECT id FROM marketing_campaigns WHERE id = :cid AND tenant_id = :tid"),
            {"cid": str(body.campaign_id), "tid": str(tenant_id)},
        ).first()
        if not camp:
            raise HTTPException(404, "Campaign not found")

        conn.execute(
            text("""
                INSERT INTO marketing_email_batches
                    (id, tenant_id, campaign_id, subject, from_name, from_email, total_queued, status)
                VALUES (:bid, :tid, :cid, :subj, :fn, :fe, :tq, 'queued')
            """),
            {
                "bid": str(batch_id),
                "tid": str(tenant_id),
                "cid": str(body.campaign_id),
                "subj": body.subject,
                "fn": body.from_name,
                "fe": body.from_email,
                "tq": total,
            },
        )

        # Update campaign counters
        conn.execute(
            text("UPDATE marketing_campaigns SET total_sent = total_sent + :cnt, updated_at = now() WHERE id = :cid"),
            {"cnt": total, "cid": str(body.campaign_id)},
        )

    return EmailSendResponse(
        batch_id=batch_id,
        campaign_id=body.campaign_id,
        total_queued=total,
        status="queued",
    )


@app.get("/email/batches/{batch_id}")
async def get_email_batch(
    batch_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM marketing_email_batches WHERE id = :bid AND tenant_id = :tid"),
            {"bid": str(batch_id), "tid": str(tenant_id)},
        ).mappings().first()
    if not row:
        raise HTTPException(404, "Batch not found")
    return dict(row)


@app.post("/email/webhook")
async def email_webhook(event: Dict[str, Any]):
    """Webhook endpoint for email provider callbacks (delivery, bounce, open, click)."""
    # In production this would be called by the email provider (UniOne / SendGrid / etc.)
    engine = get_engine()
    _ensure_marketing_tables(engine)
    event_type = event.get("event_type", "unknown")
    batch_id = event.get("batch_id")
    if not batch_id:
        raise HTTPException(400, "batch_id required")

    counter_map = {
        "delivered": "total_delivered",
        "bounced": "total_bounced",
        "opened": "total_opened",
        "clicked": "total_clicked",
    }
    col = counter_map.get(event_type)
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_email_events (tenant_id, batch_id, recipient_email, event_type, event_data)
                SELECT tenant_id, id, :email, :etype, :edata::jsonb
                FROM marketing_email_batches WHERE id = :bid
            """),
            {
                "bid": batch_id,
                "email": event.get("email", ""),
                "etype": event_type,
                "edata": "{}",
            },
        )
        if col:
            conn.execute(
                text(f"UPDATE marketing_email_batches SET {col} = {col} + 1 WHERE id = :bid"),
                {"bid": batch_id},
            )
    return {"status": "accepted"}


# ────────────────────── Templates ──────────────────────────────


@app.get("/templates")
async def list_templates(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM marketing_templates WHERE tenant_id = :tid ORDER BY created_at DESC"),
            {"tid": str(tenant_id)},
        ).mappings().all()
    return [dict(r) for r in rows]


@app.post("/templates", status_code=201)
async def create_template(
    body: TemplateCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_templates (id, tenant_id, name, subject, body_html, category)
                VALUES (:id, :tid, :name, :subj, :body, :cat)
            """),
            {
                "id": str(tid),
                "tid": str(tenant_id),
                "name": body.name,
                "subj": body.subject,
                "body": body.body_html,
                "cat": body.category,
            },
        )
        row = conn.execute(text("SELECT * FROM marketing_templates WHERE id = :id"), {"id": str(tid)}).mappings().first()
    return dict(row)


# ──────────────────── Audience Segments ────────────────────────


@app.get("/segments")
async def list_segments(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM marketing_audience_segments WHERE tenant_id = :tid ORDER BY created_at DESC"),
            {"tid": str(tenant_id)},
        ).mappings().all()
    return [dict(r) for r in rows]


@app.post("/segments", status_code=201)
async def create_segment(
    body: AudienceSegmentCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    sid = uuid.uuid4()
    import json

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_audience_segments (id, tenant_id, name, description, rules)
                VALUES (:id, :tid, :name, :desc, :rules::jsonb)
            """),
            {
                "id": str(sid),
                "tid": str(tenant_id),
                "name": body.name,
                "desc": body.description,
                "rules": json.dumps(body.rules),
            },
        )
        row = conn.execute(
            text("SELECT * FROM marketing_audience_segments WHERE id = :id"), {"id": str(sid)}
        ).mappings().first()
    return dict(row)


# ──────────────────── Lead Scoring ─────────────────────────────


@app.post("/leads/score")
async def update_lead_score(
    body: LeadScoreUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_lead_scores (tenant_id, contact_id, score, last_scored_at)
                VALUES (:tid, :cid, :delta, now())
                ON CONFLICT (tenant_id, contact_id)
                DO UPDATE SET score = marketing_lead_scores.score + :delta, last_scored_at = now()
            """),
            {"tid": str(tenant_id), "cid": str(body.contact_id), "delta": body.score_delta},
        )
        row = conn.execute(
            text("SELECT * FROM marketing_lead_scores WHERE tenant_id = :tid AND contact_id = :cid"),
            {"tid": str(tenant_id), "cid": str(body.contact_id)},
        ).mappings().first()
    return dict(row)


@app.get("/leads/scores")
async def list_lead_scores(
    min_score: int = 0,
    limit: int = 50,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT * FROM marketing_lead_scores
                WHERE tenant_id = :tid AND score >= :ms
                ORDER BY score DESC LIMIT :lim
            """),
            {"tid": str(tenant_id), "ms": min_score, "lim": limit},
        ).mappings().all()
    return [dict(r) for r in rows]


# ──────────────────── Automations ──────────────────────────────


@app.get("/automations")
async def list_automations(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM marketing_automations WHERE tenant_id = :tid ORDER BY created_at DESC"),
            {"tid": str(tenant_id)},
        ).mappings().all()
    return [dict(r) for r in rows]


@app.post("/automations", status_code=201)
async def create_automation(
    body: AutomationCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    import json

    aid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_automations
                    (id, tenant_id, name, trigger_type, trigger_config, actions, is_active)
                VALUES (:id, :tid, :name, :tt, :tc::jsonb, :acts::jsonb, :active)
            """),
            {
                "id": str(aid),
                "tid": str(tenant_id),
                "name": body.name,
                "tt": body.trigger_type,
                "tc": json.dumps(body.trigger_config),
                "acts": json.dumps(body.actions),
                "active": body.is_active,
            },
        )
        row = conn.execute(
            text("SELECT * FROM marketing_automations WHERE id = :id"), {"id": str(aid)}
        ).mappings().first()
    return dict(row)


# ──────────────────── A/B Testing ──────────────────────────────


@app.post("/ab-tests", status_code=201)
async def create_ab_test(
    body: ABTestCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    import json

    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_ab_tests
                    (id, tenant_id, campaign_id, variant_a, variant_b, split_pct, metric, duration_hours)
                VALUES (:id, :tid, :cid, :va::jsonb, :vb::jsonb, :sp, :met, :dur)
            """),
            {
                "id": str(tid),
                "tid": str(tenant_id),
                "cid": str(body.campaign_id),
                "va": json.dumps(body.variant_a),
                "vb": json.dumps(body.variant_b),
                "sp": body.split_pct,
                "met": body.metric,
                "dur": body.duration_hours,
            },
        )
        row = conn.execute(
            text("SELECT * FROM marketing_ab_tests WHERE id = :id"), {"id": str(tid)}
        ).mappings().first()
    return dict(row)


@app.get("/ab-tests")
async def list_ab_tests(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM marketing_ab_tests WHERE tenant_id = :tid ORDER BY created_at DESC"),
            {"tid": str(tenant_id)},
        ).mappings().all()
    return [dict(r) for r in rows]


# ──────────────────── Dashboard Metrics ────────────────────────


@app.get("/dashboard", response_model=DashboardMetrics)
async def dashboard_metrics(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        camp = conn.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE status IN ('active','running')) AS active,
                    COALESCE(SUM(total_sent), 0) AS sent,
                    COALESCE(SUM(total_delivered), 0) AS delivered,
                    COALESCE(SUM(total_opened), 0) AS opened,
                    COALESCE(SUM(total_conversions), 0) AS conversions,
                    COALESCE(SUM(budget_zar), 0) AS budget
                FROM marketing_campaigns
                WHERE tenant_id = :tid
            """),
            {"tid": str(tenant_id)},
        ).mappings().first()

        leads_row = conn.execute(
            text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE score >= 50) AS mql,
                    COUNT(*) FILTER (WHERE score >= 80) AS sql_q
                FROM marketing_lead_scores
                WHERE tenant_id = :tid
            """),
            {"tid": str(tenant_id)},
        ).mappings().first()

    sent = int(camp["sent"]) if camp["sent"] else 0
    delivered = int(camp["delivered"]) if camp["delivered"] else 0
    opened = int(camp["opened"]) if camp["opened"] else 0
    conversions = int(camp["conversions"]) if camp["conversions"] else 0
    budget = float(camp["budget"]) if camp["budget"] else 0
    total_leads = int(leads_row["total"]) if leads_row else 0

    delivery_rate = (delivered / sent * 100) if sent > 0 else 0
    open_rate = (opened / delivered * 100) if delivered > 0 else 0
    bounce_rate = ((sent - delivered) / sent * 100) if sent > 0 else 0
    conversion_rate = (conversions / sent * 100) if sent > 0 else 0
    roi = (conversions * 500 / budget) if budget > 0 else 0  # Simplified

    return DashboardMetrics(
        active_campaigns=int(camp["active"]) if camp["active"] else 0,
        email_delivery_rate=round(delivery_rate, 2),
        lead_conversion_rate=round(conversion_rate, 2),
        marketing_roi=round(roi, 2),
        total_leads=total_leads,
        total_mql=int(leads_row["mql"]) if leads_row else 0,
        total_sql=int(leads_row["sql_q"]) if leads_row else 0,
        emails_sent_mtd=sent,
        emails_delivered_mtd=delivered,
        emails_opened_mtd=opened,
        bounce_rate=round(bounce_rate, 2),
        open_rate=round(open_rate, 2),
    )


# ─────────────────────────── Start ─────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8014)
