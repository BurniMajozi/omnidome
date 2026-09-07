"""
Agent Mail Router for OmniDome Communication Service.
Handles mailboxes for agents, inbound emails, automated LLM dispatch, and outbound mail tracking.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Any, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from services.common.auth import AuthContext, get_auth_context
from services.communication.database import get_session
from services.communication.models import AgentEmail, AgentMailbox, Message

logger = logging.getLogger("communication.mail")

router = APIRouter(prefix="/mail", tags=["agent-mail"])

ORCHESTRATOR_URL = os.getenv("AGENT_ORCHESTRATOR_URL", "http://agent_orchestrator:8006")


# ── Pydantic Schemas ────────────────────────────────────────────────────────

class MailboxCreate(BaseModel):
    agent_type: str = Field(..., max_length=80)
    email_address: str = Field(..., max_length=255)
    display_name: str = Field(..., max_length=120)
    inbound_channel_id: Optional[uuid.UUID] = None
    auto_reply_enabled: bool = True


class MailboxRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    agent_type: str
    email_address: str
    display_name: str
    is_active: bool
    inbound_channel_id: Optional[uuid.UUID] = None
    auto_reply_enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InboundEmailPayload(BaseModel):
    sender: str = Field(..., max_length=255)
    recipient: str = Field(..., max_length=255)
    subject: str = Field(..., max_length=500)
    body_text: str
    body_html: Optional[str] = None
    headers: dict[str, Any] = Field(default_factory=dict)
    message_id: Optional[str] = None


class AgentEmailRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    mailbox_id: uuid.UUID
    direction: str
    sender: str
    recipient: str
    subject: str
    body_text: str
    body_html: Optional[str] = None
    status: str
    agent_response: Optional[str] = None
    headers: dict[str, Any]
    message_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Mailbox Endpoints ───────────────────────────────────────────────────────

@router.post("/mailboxes", response_model=MailboxRead, status_code=status.HTTP_201_CREATED)
async def create_mailbox(
    payload: MailboxCreate,
    auth: AuthContext = Depends(get_auth_context),
):
    """Register or activate a mailbox for an agent type."""
    async with get_session() as session:
        stmt = select(AgentMailbox).where(
            AgentMailbox.tenant_id == auth.tenant_id,
            AgentMailbox.email_address == payload.email_address.lower().strip(),
        )
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            existing.agent_type = payload.agent_type
            existing.display_name = payload.display_name
            existing.is_active = True
            existing.auto_reply_enabled = payload.auto_reply_enabled
            if payload.inbound_channel_id:
                existing.inbound_channel_id = payload.inbound_channel_id
            await session.commit()
            await session.refresh(existing)
            return existing

        mb = AgentMailbox(
            id=uuid.uuid4(),
            tenant_id=auth.tenant_id,
            agent_type=payload.agent_type,
            email_address=payload.email_address.lower().strip(),
            display_name=payload.display_name,
            inbound_channel_id=payload.inbound_channel_id,
            auto_reply_enabled=payload.auto_reply_enabled,
            is_active=True,
        )
        session.add(mb)
        await session.commit()
        await session.refresh(mb)
        return mb


@router.get("/mailboxes", response_model=List[MailboxRead])
async def list_mailboxes(
    auth: AuthContext = Depends(get_auth_context),
):
    """List active agent mailboxes for tenant."""
    async with get_session() as session:
        stmt = (
            select(AgentMailbox)
            .where(AgentMailbox.tenant_id == auth.tenant_id, AgentMailbox.is_active == True)
            .order_by(AgentMailbox.created_at.asc())
        )
        res = await session.execute(stmt)
        return res.scalars().all()


# ── Email Ingestion & Processing ───────────────────────────────────────────

@router.post("/inbound", response_model=AgentEmailRead)
async def handle_inbound_email(
    payload: InboundEmailPayload,
    auth: AuthContext = Depends(get_auth_context),
):
    """
    Inbound Agent Mail webhook/entrypoint.
    1. Matches recipient email to an AgentMailbox.
    2. Stores email record.
    3. Posts summary to linked Communication Channel (if configured).
    4. Invokes target Agent Orchestrator to generate response/action.
    """
    recipient_clean = payload.recipient.lower().strip()

    async with get_session() as session:
        stmt = select(AgentMailbox).where(
            AgentMailbox.tenant_id == auth.tenant_id,
            AgentMailbox.email_address == recipient_clean,
            AgentMailbox.is_active == True,
        )
        res = await session.execute(stmt)
        mailbox = res.scalar_one_or_none()

        if not mailbox:
            stmt_catch = select(AgentMailbox).where(
                AgentMailbox.tenant_id == auth.tenant_id,
                AgentMailbox.is_active == True,
            ).order_by(AgentMailbox.created_at.asc())
            res_catch = await session.execute(stmt_catch)
            mailbox = res_catch.scalars().first()

        if not mailbox:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active Agent Mailbox found for recipient '{payload.recipient}'",
            )

        email_record = AgentEmail(
            id=uuid.uuid4(),
            tenant_id=auth.tenant_id,
            mailbox_id=mailbox.id,
            direction="inbound",
            sender=payload.sender,
            recipient=payload.recipient,
            subject=payload.subject,
            body_text=payload.body_text,
            body_html=payload.body_html,
            status="received",
            headers=payload.headers,
            message_id=payload.message_id or str(uuid.uuid4()),
        )
        session.add(email_record)
        await session.commit()
        await session.refresh(email_record)

        if mailbox.inbound_channel_id:
            msg_content = (
                f"📧 **New Inbound Email**\n"
                f"**From:** {payload.sender}\n"
                f"**Subject:** {payload.subject}\n\n"
                f"{payload.body_text[:300]}..."
            )
            channel_msg = Message(
                id=uuid.uuid4(),
                tenant_id=auth.tenant_id,
                channel_id=mailbox.inbound_channel_id,
                sender_id=auth.user_id,
                sender_name=f"{mailbox.display_name} (Mail)",
                sender_avatar=None,
                content=msg_content,
                is_agent=True,
                agent_name=mailbox.display_name,
            )
            session.add(channel_msg)
            await session.commit()

        if mailbox.auto_reply_enabled:
            try:
                agent_prompt = (
                    f"You received an inbound email from {payload.sender}.\n"
                    f"Subject: {payload.subject}\n\n"
                    f"Content:\n{payload.body_text}\n\n"
                    f"Please analyze this email, perform any necessary lookups, and draft an authoritative professional reply."
                )
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{ORCHESTRATOR_URL}/api/agents/invoke",
                        json={
                            "agent_type": mailbox.agent_type,
                            "prompt": agent_prompt,
                            "session_id": f"email_{email_record.id}",
                        },
                        headers={"X-Tenant-ID": str(auth.tenant_id), "X-User-ID": str(auth.user_id)},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        agent_reply = data.get("response") or data.get("output") or ""
                        email_record.agent_response = agent_reply
                        email_record.status = "processed"
                        session.add(email_record)
                        await session.commit()
                        await session.refresh(email_record)
                    else:
                        logger.warning("Orchestrator returned %d for email reply: %s", resp.status_code, resp.text)
            except Exception as e:
                logger.error("Failed to trigger agent orchestrator for inbound email: %s", e)

        return email_record


@router.get("/emails", response_model=List[AgentEmailRead])
async def list_emails(
    mailbox_id: Optional[uuid.UUID] = Query(None),
    direction: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    auth: AuthContext = Depends(get_auth_context),
):
    """Query recent agent emails."""
    async with get_session() as session:
        stmt = select(AgentEmail).where(AgentEmail.tenant_id == auth.tenant_id)
        if mailbox_id:
            stmt = stmt.where(AgentEmail.mailbox_id == mailbox_id)
        if direction:
            stmt = stmt.where(AgentEmail.direction == direction)
        if status_filter:
            stmt = stmt.where(AgentEmail.status == status_filter)
        stmt = stmt.order_by(AgentEmail.created_at.desc()).limit(100)
        res = await session.execute(stmt)
        return res.scalars().all()
