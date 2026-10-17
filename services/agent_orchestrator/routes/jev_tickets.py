"""Jev for tickets: the support service asks, this service holds the Jev credentials and the egress switches.

`POST /api/jev/tickets/route|review|stage` take an already-redacted ticket and return Jev's opinion
(jev_ticket.py). They store nothing. They are rate limited per tenant because every call costs Jev credit.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.agent_orchestrator import jev_ticket
from services.common.auth import AuthContext, get_auth_context
from services.common.rate_limiter import RateLimiter

router = APIRouter()
_limiter = RateLimiter(max_requests=120, window_seconds=60.0)


class TicketPayload(BaseModel):
    ref: Optional[str] = Field(default=None, max_length=40)
    subject: str = Field(default="", max_length=300)
    description: Optional[str] = Field(default=None, max_length=2500)
    resolution: Optional[str] = Field(default=None, max_length=2500)
    source: Optional[str] = Field(default=None, max_length=40)
    category: Optional[str] = Field(default=None, max_length=50)
    priority: Optional[str] = Field(default=None, max_length=20)
    queue: Optional[str] = Field(default=None, max_length=50)
    status: Optional[str] = Field(default=None, max_length=20)
    event_type: Optional[str] = Field(default=None, max_length=120)
    occurrence_count: Optional[int] = Field(default=None, ge=0, le=1_000_000)


class Candidate(BaseModel):
    id: str = Field(max_length=64)
    open: int = Field(default=0, ge=0, le=100_000)
    resolved_30d: int = Field(default=0, ge=0, le=1_000_000)
    top_categories: List[str] = Field(default_factory=list, max_length=3)


class RouteRequest(BaseModel):
    ticket: TicketPayload
    candidates: List[Candidate] = Field(default_factory=list, max_length=jev_ticket.MAX_CANDIDATES)


class ReviewRequest(BaseModel):
    ticket: TicketPayload


class Timing(BaseModel):
    hours_open: float = Field(ge=0, le=100_000)
    hours_since_activity: float = Field(ge=0, le=100_000)
    hours_past_deadline: float = Field(default=0, ge=0, le=100_000)
    times_reassigned: int = Field(default=0, ge=0, le=1000)
    escalated_already: bool = False


class StageRequest(BaseModel):
    ticket: TicketPayload
    timing: Timing


def _guard(ctx: AuthContext) -> None:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=401, detail="Tenant identity required")
    _limiter.check_key(f"jev-tickets:{ctx.tenant_id}")


@router.post("/route")
async def route(body: RouteRequest, ctx: AuthContext = Depends(get_auth_context)):
    _guard(ctx)
    return await jev_ticket.route_ticket(body.ticket.model_dump(exclude_none=True),
                                         [c.model_dump() for c in body.candidates], str(ctx.tenant_id))


@router.post("/review")
async def review(body: ReviewRequest, ctx: AuthContext = Depends(get_auth_context)):
    _guard(ctx)
    return await jev_ticket.review_closed_ticket(body.ticket.model_dump(exclude_none=True), str(ctx.tenant_id))


@router.post("/stage")
async def stage(body: StageRequest, ctx: AuthContext = Depends(get_auth_context)):
    _guard(ctx)
    return await jev_ticket.check_stage(body.ticket.model_dump(exclude_none=True), body.timing.model_dump(), str(ctx.tenant_id))
