"""Communication session routes for chat, voice, and video starts."""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.communication.models import Channel, CommunicationSession, Event
from services.communication.schemas import (
    CommunicationSessionCreate,
    CommunicationSessionEnd,
    CommunicationSessionRead,
    PaginatedResponse,
)

router = APIRouter(prefix="/sessions", tags=["Communication Sessions"])


def _provider_url(session_type: str) -> Optional[str]:
    if session_type == "voice":
        return os.getenv("CALL_PROVIDER_BASE_URL")
    if session_type == "video":
        return os.getenv("VIDEO_PROVIDER_BASE_URL")
    return os.getenv("CHAT_PROVIDER_BASE_URL")


async def _create_provider_session(session_type: str, payload: dict) -> dict:
    base_url = _provider_url(session_type)
    if not base_url:
        return {"provider_name": "local", "provider_session_id": None, "status": "local"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{base_url.rstrip('/')}/sessions", json=payload)
        response.raise_for_status()
        data = response.json()
        return {
            "provider_name": data.get("provider_name") or data.get("provider") or base_url,
            "provider_session_id": data.get("id") or data.get("session_id"),
            "status": data.get("status") or "active",
        }


@router.post("", response_model=CommunicationSessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CommunicationSessionCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        ch_stmt = select(Channel).where(Channel.id == body.channel_id, Channel.tenant_id == ctx.tenant_id)
        ch_result = await session.execute(ch_stmt)
        channel = ch_result.scalar_one_or_none()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        event = Event(
            tenant_id=ctx.tenant_id,
            channel_id=body.channel_id,
            user_id=ctx.user_id,
            event_type=f"start_{body.session_type}_session",
            payload={
                "participants": body.participants,
                "metadata": body.metadata,
                "provider_name": body.provider_name,
            },
        )
        session.add(event)
        await session.flush()

        provider_result = {"provider_name": body.provider_name or "local", "provider_session_id": None, "status": "created"}
        try:
            provider_result = await _create_provider_session(
                body.session_type,
                {
                    "tenant_id": str(ctx.tenant_id),
                    "channel_id": str(body.channel_id),
                    "started_by": str(ctx.user_id),
                    "participants": body.participants,
                    "metadata": body.metadata,
                },
            )
        except Exception:
            provider_result = {"provider_name": body.provider_name or "local", "provider_session_id": None, "status": "provider_unavailable"}

        comm_session = CommunicationSession(
            tenant_id=ctx.tenant_id,
            channel_id=body.channel_id,
            event_id=event.id,
            session_type=body.session_type,
            provider_name=provider_result["provider_name"],
            provider_session_id=provider_result["provider_session_id"],
            status=provider_result["status"],
            started_by=ctx.user_id,
            participants={"items": body.participants},
            metadata=body.metadata,
            started_at=datetime.now(timezone.utc),
        )
        session.add(comm_session)
        await session.flush()
        await session.refresh(comm_session)
        return comm_session


@router.get("", response_model=PaginatedResponse)
async def list_sessions(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    channel_id: Optional[uuid.UUID] = Query(None),
    session_type: Optional[str] = Query(None),
):
    async with session_scope() as session:
        stmt = select(CommunicationSession).where(CommunicationSession.tenant_id == ctx.tenant_id)
        count_stmt = select(func.count(CommunicationSession.id)).where(CommunicationSession.tenant_id == ctx.tenant_id)
        if channel_id:
            stmt = stmt.where(CommunicationSession.channel_id == channel_id)
            count_stmt = count_stmt.where(CommunicationSession.channel_id == channel_id)
        if session_type:
            stmt = stmt.where(CommunicationSession.session_type == session_type)
            count_stmt = count_stmt.where(CommunicationSession.session_type == session_type)
        total = (await session.execute(count_stmt)).scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)
        stmt = stmt.order_by(CommunicationSession.started_at.desc()).offset((page - 1) * page_size).limit(page_size)
        items = (await session.execute(stmt)).scalars().all()
        return PaginatedResponse(
            items=[CommunicationSessionRead.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


@router.post("/{session_id}/end", response_model=CommunicationSessionRead)
async def end_session(
    session_id: uuid.UUID,
    body: CommunicationSessionEnd,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(CommunicationSession).where(
            CommunicationSession.id == session_id,
            CommunicationSession.tenant_id == ctx.tenant_id,
        )
        result = await session.execute(stmt)
        comm_session = result.scalar_one_or_none()
        if not comm_session:
            raise HTTPException(status_code=404, detail="Communication session not found")
        comm_session.status = body.status
        comm_session.metadata = {**(comm_session.metadata or {}), **body.metadata}
        comm_session.ended_at = datetime.now(timezone.utc)
        await session.flush()
        await session.refresh(comm_session)
        return comm_session
