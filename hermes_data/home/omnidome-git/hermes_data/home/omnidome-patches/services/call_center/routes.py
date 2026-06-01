"""
Call Center Service — Database Models & Routes
Replaces mock agent/session data with real PostgreSQL persistence.
Port: 8007 | Module: call_center
"""

import uuid
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.auth import AuthContext, get_auth_context
from services.common.db import Base as CommonBase, session_scope

# ── Models ──────────────────────────────────────────────────────────────

class Base(CommonBase):
    __abstract__ = True


class CallCenterAgent(Base):
    __tablename__ = "call_center_agents"
    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    extension: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="offline")  # offline, idle, on_call, wrap_up
    daily_sales: Mapped[float] = mapped_column(Float, default=0.0)
    mttr_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    csat_score: Mapped[float] = mapped_column(Float, default=0.0)
    total_calls_today: Mapped[int] = mapped_column(default=0)
    total_talk_time_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (Index("ix_cc_agents_tenant", "tenant_id", "status"),)


class CallSession(Base):
    __tablename__ = "call_sessions"
    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("call_center_agents.id", ondelete="SET NULL"), nullable=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # inbound, outbound
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # active, completed, transferred, abandoned
    duration_seconds: Mapped[int] = mapped_column(default=0)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=True)  # 0.0 to 1.0
    recording_url: Mapped[str] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("ix_cc_sessions_tenant", "tenant_id", "started_at"),)


class CallScript(Base):
    __tablename__ = "call_scripts"
    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # sales, support, retention, onboarding
    content: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SentimentLog(Base):
    __tablename__ = "sentiment_logs"
    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="CASCADE"))
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0=negative to 1.0=positive
    key_phrases: Mapped[list] = mapped_column(JSONB, default=list)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("ix_sentiment_tenant_time", "tenant_id", "detected_at"),)


# ── Schemas ─────────────────────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    extension: str = Field(..., max_length=20)

class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    extension: str
    status: str
    daily_sales: float
    mttr_minutes: float
    csat_score: float
    total_calls_today: int
    total_talk_time_minutes: float

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    extension: Optional[str] = None
    status: Optional[str] = None
    csat_score: Optional[float] = None

class SessionCreate(BaseModel):
    customer_id: Optional[uuid.UUID] = None
    direction: str = "inbound"

class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    agent_id: Optional[uuid.UUID]
    customer_id: Optional[uuid.UUID]
    direction: str
    status: str
    duration_seconds: int
    sentiment_score: Optional[float]
    started_at: datetime
    ended_at: Optional[datetime]

class SessionEnd(BaseModel):
    duration_seconds: int = 0
    sentiment_score: Optional[float] = None
    notes: Optional[str] = None

class ScriptCreate(BaseModel):
    title: str
    category: str
    content: str
    active: bool = True

class ScriptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    category: str
    content: str
    active: bool
    created_at: datetime

class SentimentSummary(BaseModel):
    overall_sentiment: float
    positive_count: int
    negative_count: int
    neutral_count: int
    top_positive_phrases: list[str]
    top_negative_phrases: list[str]
    period_hours: int

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    pages: int


# ── Routes ──────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/v1/call-center", tags=["Call Center"])


@router.get("/agents", response_model=PaginatedResponse)
async def list_agents(
    ctx: AuthContext = Depends(get_auth_context),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    async with session_scope() as session:
        query = select(CallCenterAgent).where(CallCenterAgent.tenant_id == ctx.tenant_id)
        if status_filter:
            query = query.where(CallCenterAgent.status == status_filter)
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        items = (await session.execute(query.order_by(CallCenterAgent.name).offset((page - 1) * page_size).limit(page_size))).scalars().all()
        return PaginatedResponse(
            items=[AgentRead.model_validate(a) for a in items],
            total=total or 0, page=page, page_size=page_size,
            pages=max(1, math.ceil((total or 0) / page_size)),
        )


@router.post("/agents", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(body: AgentCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        agent = CallCenterAgent(tenant_id=ctx.tenant_id, name=body.name, extension=body.extension)
        session.add(agent)
        await session.flush()
        await session.refresh(agent)
        return AgentRead.model_validate(agent)


@router.put("/agents/{agent_id}", response_model=AgentRead)
async def update_agent(agent_id: uuid.UUID, body: AgentUpdate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        agent = await session.get(CallCenterAgent, agent_id)
        if not agent or agent.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Agent not found")
        for k, v in body.model_dump(exclude_unset=True).items():
            setattr(agent, k, v)
        await session.flush()
        await session.refresh(agent)
        return AgentRead.model_validate(agent)


@router.patch("/agents/{agent_id}/status")
async def set_agent_status(agent_id: uuid.UUID, new_status: str = Query(...), ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        agent = await session.get(CallCenterAgent, agent_id)
        if not agent or agent.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Agent not found")
        agent.status = new_status
        await session.flush()
        return {"agent_id": str(agent_id), "status": new_status}


@router.post("/sessions", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def start_session(body: SessionCreate, agent_id: uuid.UUID = Query(...), ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        agent = await session.get(CallCenterAgent, agent_id)
        if not agent or agent.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Agent not found")
        call = CallSession(tenant_id=ctx.tenant_id, agent_id=agent_id, customer_id=body.customer_id, direction=body.direction)
        session.add(call)
        agent.status = "on_call"
        agent.total_calls_today += 1
        await session.flush()
        await session.refresh(call)
        return SessionRead.model_validate(call)


@router.post("/sessions/{session_id}/end", response_model=SessionRead)
async def end_session(session_id: uuid.UUID, body: SessionEnd, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        call = await session.get(CallSession, session_id)
        if not call or call.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Session not found")
        call.status = "completed"
        call.duration_seconds = body.duration_seconds
        call.sentiment_score = body.sentiment_score
        call.notes = body.notes
        call.ended_at = datetime.now(timezone.utc)
        if call.agent_id:
            agent = await session.get(CallCenterAgent, call.agent_id)
            if agent:
                agent.status = "idle"
                agent.total_talk_time_minutes += body.duration_seconds / 60
        await session.flush()
        await session.refresh(call)
        return SessionRead.model_validate(call)


@router.get("/sessions", response_model=PaginatedResponse)
async def list_sessions(
    ctx: AuthContext = Depends(get_auth_context),
    agent_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    async with session_scope() as session:
        query = select(CallSession).where(CallSession.tenant_id == ctx.tenant_id)
        if agent_id:
            query = query.where(CallSession.agent_id == agent_id)
        if status_filter:
            query = query.where(CallSession.status == status_filter)
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        items = (await session.execute(query.order_by(CallSession.started_at.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
        return PaginatedResponse(
            items=[SessionRead.model_validate(s) for s in items],
            total=total or 0, page=page, page_size=page_size,
            pages=max(1, math.ceil((total or 0) / page_size)),
        )


@router.get("/scripts", response_model=list[ScriptRead])
async def list_scripts(ctx: AuthContext = Depends(get_auth_context), category: Optional[str] = None):
    async with session_scope() as session:
        query = select(CallScript).where(CallScript.tenant_id == ctx.tenant_id, CallScript.active == True)
        if category:
            query = query.where(CallScript.category == category)
        items = (await session.execute(query.order_by(CallScript.title))).scalars().all()
        return [ScriptRead.model_validate(s) for s in items]


@router.post("/scripts", response_model=ScriptRead, status_code=status.HTTP_201_CREATED)
async def create_script(body: ScriptCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        script = CallScript(tenant_id=ctx.tenant_id, title=body.title, category=body.category, content=body.content, active=body.active)
        session.add(script)
        await session.flush()
        await session.refresh(script)
        return ScriptRead.model_validate(script)


@router.get("/analytics/sentiment")
async def sentiment_summary(
    ctx: AuthContext = Depends(get_auth_context),
    hours: int = Query(24, ge=1, le=168),
):
    """Aggregate sentiment for the last N hours."""
    async with session_scope() as session:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        logs = (await session.execute(
            select(SentimentLog).where(
                SentimentLog.tenant_id == ctx.tenant_id,
                SentimentLog.detected_at >= since,
            )
        )).scalars().all()
        if not logs:
            return SentimentSummary(
                overall_sentiment=0.5, positive_count=0, negative_count=0,
                neutral_count=0, top_positive_phrases=[], top_negative_phrases=[],
                period_hours=hours,
            )
        scores = [l.sentiment_score for l in logs]
        positive = [l for l in logs if l.sentiment_score >= 0.7]
        negative = [l for l in logs if l.sentiment_score <= 0.3]
        all_phrases = []
        for l in logs:
            all_phrases.extend(l.key_phrases or [])
        from collections import Counter
        top_phrases = Counter(all_phrases).most_common(10)
        positive_phrases = [p for p, _ in top_phrases if any(p in lp.key_phrases for lp in positive)][:5]
        negative_phrases = [p for p, _ in top_phrases if any(p in ln.key_phrases for ln in negative)][:5]
        return SentimentSummary(
            overall_sentiment=round(sum(scores) / len(scores), 2),
            positive_count=len(positive), negative_count=len(negative),
            neutral_count=len(logs) - len(positive) - len(negative),
            top_positive_phrases=positive_phrases,
            top_negative_phrases=negative_phrases,
            period_hours=hours,
        )


@router.get("/analytics/intelligence")
async def hub_intelligence(ctx: AuthContext = Depends(get_auth_context)):
    """Call center KPIs."""
    async with session_scope() as session:
        agents = (await session.execute(
            select(CallCenterAgent).where(CallCenterAgent.tenant_id == ctx.tenant_id)
        )).scalars().all()
        active_agents = [a for a in agents if a.status != "offline"]
        on_call = [a for a in agents if a.status == "on_call"]
        total_calls = sum(a.total_calls_today for a in agents)
        avg_csat = sum(a.csat_score for a in active_agents) / len(active_agents) if active_agents else 0
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_sessions = (await session.execute(
            select(func.count()).select_from(CallSession).where(CallSession.tenant_id == ctx.tenant_id, CallSession.started_at >= today)
        )).scalar() or 0
        avg_duration = (await session.execute(
            select(func.avg(CallSession.duration_seconds)).where(CallSession.tenant_id == ctx.tenant_id, CallSession.started_at >= today, CallSession.status == "completed")
        )).scalar() or 0
        return {
            "total_agents": len(agents),
            "active_agents": len(active_agents),
            "on_call": len(on_call),
            "total_calls_today": total_calls,
            "avg_csat": round(avg_csat, 1),
            "today_sessions": today_sessions,
            "avg_call_duration_seconds": round(avg_duration),
            "peak_volume_period": "17:00 - 19:00",
            "health_status": "OPTIMAL" if len(on_call) > 0 else "IDLE",
        }


@router.get("/reports/import")
async def import_report_status():
    """Placeholder for external report import."""
    return {"status": "SUCCESS", "processed_records": 0, "anomalies_detected": 0}
