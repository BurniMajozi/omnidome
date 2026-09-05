"""Agent protocol routes — A2A, AG-UI, A2UI, UCP, AP2 with DB persistence and correlation IDs."""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text

from services.agent_orchestrator.agents import Agent
from services.agent_orchestrator.config import settings
from services.agent_orchestrator.protocols import (
    AGENT_SKILLS,
    AGUIEvent,
    AGUIRunRequest,
    A2AMessage,
    A2UIComponent,
    A2UIPayload,
    AgentCard,
    IntentMandate,
    IntentMandateCreate,
    PaymentMandate,
    PaymentMandateCreate,
    PaymentReceipt,
    PaymentReceiptCreate,
    UCPCheckoutCreateRequest,
    UCPCheckoutSession,
    UCPLineItem,
)
from services.agent_orchestrator.protocol_models import (
    AP2IntentMandateRecord,
    AP2PaymentMandateRecord,
    AP2PaymentReceiptRecord,
    UCPCheckoutSessionRecord,
)
from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_session
from services.agent_orchestrator.tools import tool_registry
from services.agent_orchestrator.hermes_client import hermes_client
from services.agent_orchestrator.routes.agents import _hermes_system_note

router = APIRouter(tags=["Agent Protocols"])


# ---------------------------------------------------------------------------
# Correlation ID helper — links protocol actions to tenant memory entries
# ---------------------------------------------------------------------------

def _correlation_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Memory write-back with correlation
# ---------------------------------------------------------------------------

async def _write_protocol_memory(
    ctx: AuthContext,
    title: str,
    content: str,
    metadata: dict[str, Any],
    correlation_id: str,
    session=None,
) -> None:
    """Write protocol event to tenant memory with correlation ID.

    Uses the tenant_memory service HTTP API (fire-and-forget).
    The correlation_id links the protocol action to its memory entry.
    """
    url = f"{settings.tenant_memory_service_url.rstrip('/')}/api/v1/memories"
    headers = {"X-Tenant-Id": str(ctx.tenant_id), "X-User-Id": str(ctx.user_id)}
    payload = {
        "source_type": "agent_protocol",
        "source_id": correlation_id,
        "module": "agents",
        "scope_key": f"protocol:{correlation_id}",
        "title": title,
        "content": content,
        "summary": title,
        "importance": "normal",
        "tags": ["agent-protocol", "audit"],
        "metadata": {**metadata, "correlation_id": correlation_id},
    }
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(url, json=payload, headers=headers)
    except Exception:
        # Memory write must not block the protocol action.
        return


# ---------------------------------------------------------------------------
# Agent Card helpers
# ---------------------------------------------------------------------------

def _agent_card(agent_type: str = "omnidome") -> AgentCard:
    if agent_type == "omnidome":
        skills = [skill for items in AGENT_SKILLS.values() for skill in items]
        description = "OmniDome multi-agent operating system for ISP operations."
    else:
        skills = AGENT_SKILLS.get(agent_type, [])
        description = f"OmniDome {agent_type} agent."
    return AgentCard(
        name=f"omnidome_{agent_type}",
        description=description,
        url=f"{settings.public_agent_url.rstrip('/')}/api/protocols/a2a/message",
        skills=skills,
    )


# ---------------------------------------------------------------------------
# A2A — Agent-to-Agent
# ---------------------------------------------------------------------------

@router.get("/.well-known/agent-card.json", response_model=AgentCard, include_in_schema=False)
async def well_known_agent_card():
    return _agent_card()


@router.get("/api/protocols/a2a/agents/{agent_type}/agent-card.json", response_model=AgentCard)
async def agent_card(agent_type: str):
    card = _agent_card(agent_type)
    if not card.skills:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent type not found")
    return card


@router.post("/api/protocols/a2a/message")
async def a2a_message(body: A2AMessage, ctx: AuthContext = Depends(get_auth_context)):
    correlation = _correlation_id()
    agent = Agent(
        agent_type=body.agent_type,
        tenant_id=ctx.tenant_id,
        context={**body.context, "user_id": str(ctx.user_id)},
    )
    result = await agent.run(body.message, conversation_id=body.conversation_id)
    await _write_protocol_memory(
        ctx,
        f"A2A message: {body.agent_type}",
        result.get("content", ""),
        {"correlation_id": correlation, "protocol": "a2a", "agent_type": body.agent_type},
        correlation,
    )
    return {
        "kind": "message",
        "agent_type": body.agent_type,
        "conversation_id": result.get("conversation_id"),
        "content": result.get("content"),
        "artifacts": [{"type": "tool_calls", "data": result.get("tool_calls", [])}],
        "correlation_id": correlation,
    }


# ---------------------------------------------------------------------------
# AG-UI — Typed streaming
# ---------------------------------------------------------------------------

@router.post("/api/protocols/ag-ui/run")
async def ag_ui_run(body: AGUIRunRequest, ctx: AuthContext = Depends(get_auth_context)):
    run_id = uuid.uuid4()
    correlation = _correlation_id()

    async def emit(event: AGUIEvent) -> str:
        return f"data: {event.model_dump_json()}\n\n"

    async def stream():
        try:
            yield await emit(AGUIEvent(
                type="RUN_STARTED",
                run_id=run_id,
                tenant_id=ctx.tenant_id,
                conversation_id=body.conversation_id,
                data={"agent_type": body.agent_type, "correlation_id": correlation},
            ))
            agent = Agent(
                agent_type=body.agent_type,
                tenant_id=ctx.tenant_id,
                context={**body.context, "user_id": str(ctx.user_id)},
            )
            history = body.context.get("history", [])

            # Stream tokens and emit AG-UI events
            full_content = ""
            if settings.chat_backend == "hermes":
                messages = agent._build_messages(body.message, history)
                messages.insert(0, {"role": "system", "content": _hermes_system_note(body.agent_type, ctx.tenant_id, body.context)})
                async for token in hermes_client.chat_stream(messages):
                    full_content += token
                    yield await emit(AGUIEvent(
                        type="TEXT_MESSAGE_CONTENT",
                        run_id=run_id,
                        tenant_id=ctx.tenant_id,
                        conversation_id=body.conversation_id,
                        data={"delta": token},
                    ))
            else:
                # Real tool-executing loop: agent.run() calls the LLM with the
                # agent's tools, executes them (CRM/billing/support/etc.) against
                # OmniDome services, and loops to a final answer. Non-streaming, so
                # we emit each tool call + the final text as AG-UI events.
                run_result = await agent.run(body.message, history)
                for tc in run_result.get("tool_calls", []):
                    yield await emit(AGUIEvent(
                        type="TOOL_CALL_START",
                        run_id=run_id,
                        tenant_id=ctx.tenant_id,
                        conversation_id=body.conversation_id,
                        data={"name": tc.get("name"), "arguments": tc.get("arguments")},
                    ))
                    yield await emit(AGUIEvent(
                        type="TOOL_CALL_RESULT",
                        run_id=run_id,
                        tenant_id=ctx.tenant_id,
                        conversation_id=body.conversation_id,
                        data={"name": tc.get("name"), "result": tc.get("result")},
                    ))
                full_content = run_result.get("content", "")
                if full_content:
                    yield await emit(AGUIEvent(
                        type="TEXT_MESSAGE_CONTENT",
                        run_id=run_id,
                        tenant_id=ctx.tenant_id,
                        conversation_id=body.conversation_id,
                        data={"delta": full_content},
                    ))

            # Write memory with correlation
            await _write_protocol_memory(
                ctx,
                f"AG-UI run: {body.agent_type}",
                full_content[:2000],
                {
                    "correlation_id": correlation,
                    "protocol": "ag-ui",
                    "agent_type": body.agent_type,
                    "run_id": str(run_id),
                },
                correlation,
            )

            yield await emit(AGUIEvent(
                type="MEMORY_WRITE",
                run_id=run_id,
                tenant_id=ctx.tenant_id,
                conversation_id=body.conversation_id,
                data={"correlation_id": correlation, "status": "written"},
            ))
            yield await emit(AGUIEvent(
                type="RUN_FINISHED",
                run_id=run_id,
                tenant_id=ctx.tenant_id,
                conversation_id=body.conversation_id,
            ))
        except Exception as exc:
            yield await emit(AGUIEvent(
                type="RUN_ERROR",
                run_id=run_id,
                tenant_id=ctx.tenant_id,
                conversation_id=body.conversation_id,
                data={"error": str(exc)},
            ))

    return StreamingResponse(stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# A2UI — Agent-composed UI validation
# ---------------------------------------------------------------------------

@router.post("/api/protocols/a2ui/validate")
async def validate_a2ui(payload: A2UIPayload):
    try:
        payload.validate_safe()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"status": "valid", "surface_id": payload.surface_id, "components": len(payload.components)}


# ---------------------------------------------------------------------------
# UCP — Universal Commerce Protocol (DB-persisted)
# ---------------------------------------------------------------------------

@router.get("/.well-known/ucp", include_in_schema=False)
async def ucp_profile():
    return {
        "name": "OmniDome Commerce",
        "version": "0.1",
        "capabilities": ["checkout.create", "checkout.complete", "payment_mandate.required"],
        "checkout_endpoint": f"{settings.public_agent_url.rstrip('/')}/api/protocols/ucp/checkout-sessions",
        "currency": "ZAR",
    }


@router.post("/api/protocols/ucp/checkout-sessions", response_model=UCPCheckoutSession)
async def create_checkout_session(
    body: UCPCheckoutCreateRequest,
    ctx: AuthContext = Depends(get_auth_context),
    session=Depends(get_async_session),
):
    correlation = _correlation_id()
    checkout = UCPCheckoutSession(
        status="requires_approval" if body.total > settings.ucp_auto_approve_limit_zar else "created",
        total=body.total,
        merchant=body.merchant,
        purpose=body.purpose,
        line_items=body.line_items,
        metadata=body.metadata,
    )

    # Persist to DB
    record = UCPCheckoutSessionRecord(
        id=str(checkout.id),
        tenant_id=ctx.tenant_id,
        status=checkout.status,
        currency=checkout.currency,
        total=checkout.total,
        merchant=checkout.merchant,
        purpose=checkout.purpose,
        line_items=[item.model_dump() for item in checkout.line_items],
        metadata_=checkout.metadata,
    )
    session.add(record)

    await _write_protocol_memory(
        ctx,
        "UCP checkout session created",
        f"Checkout for {body.merchant}: {body.purpose}",
        {
            "correlation_id": correlation,
            "protocol": "ucp",
            "session_id": str(checkout.id),
            "total": body.total,
            "currency": "ZAR",
        },
        correlation,
    )
    return checkout


@router.post("/api/protocols/ucp/checkout-sessions/{session_id}/complete", response_model=UCPCheckoutSession)
async def complete_checkout_session(
    session_id: uuid.UUID,
    payment_mandate_id: Optional[str] = None,
    ctx: AuthContext = Depends(get_auth_context),
    session=Depends(get_async_session),
):
    correlation = _correlation_id()

    # Fetch from DB
    result = await session.execute(
        select(UCPCheckoutSessionRecord).where(
            UCPCheckoutSessionRecord.id == str(session_id),
            UCPCheckoutSessionRecord.tenant_id == ctx.tenant_id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkout session not found")

    if record.status == "requires_approval" and not payment_mandate_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment mandate required")

    record.status = "completed"
    record.payment_mandate_id = payment_mandate_id

    checkout = UCPCheckoutSession(
        id=uuid.UUID(record.id),
        status=record.status,
        currency=record.currency,
        total=record.total,
        merchant=record.merchant,
        purpose=record.purpose,
        line_items=[UCPLineItem(**item) for item in record.line_items],
        payment_mandate_id=record.payment_mandate_id,
        metadata=record.metadata_,
    )

    await _write_protocol_memory(
        ctx,
        "UCP checkout session completed",
        f"Checkout completed for {record.merchant}: {record.purpose}",
        {
            "correlation_id": correlation,
            "protocol": "ucp",
            "session_id": str(session_id),
            "payment_mandate_id": payment_mandate_id,
        },
        correlation,
    )
    return checkout


@router.get("/api/protocols/ucp/checkout-sessions", response_model=list[UCPCheckoutSession])
async def list_checkout_sessions(
    ctx: AuthContext = Depends(get_auth_context),
    session=Depends(get_async_session),
    limit: int = Query(50, ge=1, le=200),
):
    result = await session.execute(
        select(UCPCheckoutSessionRecord)
        .where(UCPCheckoutSessionRecord.tenant_id == ctx.tenant_id)
        .order_by(UCPCheckoutSessionRecord.created_at.desc())
        .limit(limit)
    )
    records = result.scalars().all()
    return [
        UCPCheckoutSession(
            id=uuid.UUID(r.id),
            status=r.status,
            currency=r.currency,
            total=r.total,
            merchant=r.merchant,
            purpose=r.purpose,
            line_items=[UCPLineItem(**item) for item in r.line_items],
            payment_mandate_id=r.payment_mandate_id,
            metadata=r.metadata_,
        )
        for r in records
    ]


# ---------------------------------------------------------------------------
# AP2 — Agent Payments Protocol (DB-persisted)
# ---------------------------------------------------------------------------

@router.post("/api/protocols/ap2/intent-mandates", response_model=IntentMandate)
async def create_intent_mandate(
    body: IntentMandateCreate,
    ctx: AuthContext = Depends(get_auth_context),
    session=Depends(get_async_session),
):
    correlation = _correlation_id()
    mandate = IntentMandate.from_create(body)

    record = AP2IntentMandateRecord(
        id=str(mandate.id),
        tenant_id=ctx.tenant_id,
        natural_language_description=mandate.natural_language_description,
        merchants=mandate.merchants,
        max_amount=mandate.max_amount,
        currency=mandate.currency,
        expires_at=mandate.expires_at,
        requires_user_confirmation=mandate.requires_user_confirmation,
        signed=mandate.signed,
        metadata_=mandate.metadata,
    )
    session.add(record)

    await _write_protocol_memory(
        ctx,
        "AP2 intent mandate created",
        body.natural_language_description,
        {
            "correlation_id": correlation,
            "protocol": "ap2",
            "mandate_id": str(mandate.id),
            "max_amount": body.max_amount,
        },
        correlation,
    )
    return mandate


@router.post("/api/protocols/ap2/intent-mandates/{mandate_id}/sign", response_model=IntentMandate)
async def sign_intent_mandate(
    mandate_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session=Depends(get_async_session),
):
    correlation = _correlation_id()

    result = await session.execute(
        select(AP2IntentMandateRecord).where(
            AP2IntentMandateRecord.id == str(mandate_id),
            AP2IntentMandateRecord.tenant_id == ctx.tenant_id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intent mandate not found")

    record.signed = True

    mandate = IntentMandate(
        id=uuid.UUID(record.id),
        natural_language_description=record.natural_language_description,
        merchants=record.merchants,
        max_amount=record.max_amount,
        currency=record.currency,
        expires_at=record.expires_at,
        requires_user_confirmation=record.requires_user_confirmation,
        signed=record.signed,
        metadata=record.metadata_,
    )

    await _write_protocol_memory(
        ctx,
        "AP2 intent mandate signed",
        mandate.natural_language_description,
        {
            "correlation_id": correlation,
            "protocol": "ap2",
            "mandate_id": str(mandate_id),
        },
        correlation,
    )
    return mandate


@router.post("/api/protocols/ap2/payment-mandates", response_model=PaymentMandate)
async def create_payment_mandate(
    body: PaymentMandateCreate,
    ctx: AuthContext = Depends(get_auth_context),
    session=Depends(get_async_session),
):
    correlation = _correlation_id()

    # Validate intent mandate exists
    intent_result = await session.execute(
        select(AP2IntentMandateRecord).where(
            AP2IntentMandateRecord.id == str(body.intent_mandate_id),
            AP2IntentMandateRecord.tenant_id == ctx.tenant_id,
        )
    )
    intent = intent_result.scalar_one_or_none()
    if not intent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intent mandate not found")
    if body.amount > intent.max_amount:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Amount exceeds intent mandate guardrail")
    if intent.merchants and body.merchant_agent not in intent.merchants:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Merchant not allowed by intent mandate")

    mandate = PaymentMandate(
        intent_mandate_id=body.intent_mandate_id,
        payment_details_id=body.payment_details_id,
        merchant_agent=body.merchant_agent,
        amount=body.amount,
        currency=body.currency,
        label=body.label,
        signed_authorization=body.signed_authorization,
        status="signed" if body.signed_authorization else "pending_signature",
        metadata=body.metadata,
    )

    record = AP2PaymentMandateRecord(
        id=str(mandate.id),
        tenant_id=ctx.tenant_id,
        intent_mandate_id=str(mandate.intent_mandate_id),
        payment_details_id=mandate.payment_details_id,
        merchant_agent=mandate.merchant_agent,
        amount=mandate.amount,
        currency=mandate.currency,
        label=mandate.label,
        signed_authorization=mandate.signed_authorization,
        status=mandate.status,
        metadata_=mandate.metadata,
    )
    session.add(record)

    await _write_protocol_memory(
        ctx,
        "AP2 payment mandate created",
        body.label,
        {
            "correlation_id": correlation,
            "protocol": "ap2",
            "mandate_id": str(mandate.id),
            "amount": body.amount,
        },
        correlation,
    )
    return mandate


@router.post("/api/protocols/ap2/payment-receipts", response_model=PaymentReceipt)
async def create_payment_receipt(
    body: PaymentReceiptCreate,
    ctx: AuthContext = Depends(get_auth_context),
    session=Depends(get_async_session),
):
    correlation = _correlation_id()

    # Validate payment mandate exists and is signed
    mandate_result = await session.execute(
        select(AP2PaymentMandateRecord).where(
            AP2PaymentMandateRecord.id == str(body.payment_mandate_id),
            AP2PaymentMandateRecord.tenant_id == ctx.tenant_id,
        )
    )
    mandate = mandate_result.scalar_one_or_none()
    if not mandate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment mandate not found")
    if mandate.status != "signed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment mandate is not signed")

    receipt = PaymentReceipt(**body.model_dump())

    record = AP2PaymentReceiptRecord(
        id=str(receipt.id),
        tenant_id=ctx.tenant_id,
        payment_mandate_id=str(body.payment_mandate_id),
        payment_id=body.payment_id,
        amount=body.amount,
        currency=body.currency,
        merchant_confirmation_id=body.merchant_confirmation_id,
        metadata_=body.metadata,
    )
    session.add(record)

    await _write_protocol_memory(
        ctx,
        "AP2 payment receipt created",
        f"Receipt {body.merchant_confirmation_id}",
        {
            "correlation_id": correlation,
            "protocol": "ap2",
            "receipt_id": str(receipt.id),
            "amount": body.amount,
        },
        correlation,
    )
    return receipt


@router.get("/api/protocols/ap2/intent-mandates", response_model=list[IntentMandate])
async def list_intent_mandates(
    ctx: AuthContext = Depends(get_auth_context),
    session=Depends(get_async_session),
    limit: int = Query(50, ge=1, le=200),
):
    result = await session.execute(
        select(AP2IntentMandateRecord)
        .where(AP2IntentMandateRecord.tenant_id == ctx.tenant_id)
        .order_by(AP2IntentMandateRecord.created_at.desc())
        .limit(limit)
    )
    records = result.scalars().all()
    return [
        IntentMandate(
            id=uuid.UUID(r.id),
            natural_language_description=r.natural_language_description,
            merchants=r.merchants,
            max_amount=r.max_amount,
            currency=r.currency,
            expires_at=r.expires_at,
            requires_user_confirmation=r.requires_user_confirmation,
            signed=r.signed,
            metadata=r.metadata_,
        )
        for r in records
    ]


@router.get("/api/protocols/ap2/payment-mandates", response_model=list[PaymentMandate])
async def list_payment_mandates(
    ctx: AuthContext = Depends(get_auth_context),
    session=Depends(get_async_session),
    limit: int = Query(50, ge=1, le=200),
):
    result = await session.execute(
        select(AP2PaymentMandateRecord)
        .where(AP2PaymentMandateRecord.tenant_id == ctx.tenant_id)
        .order_by(AP2PaymentMandateRecord.created_at.desc())
        .limit(limit)
    )
    records = result.scalars().all()
    return [
        PaymentMandate(
            id=uuid.UUID(r.id),
            intent_mandate_id=uuid.UUID(r.intent_mandate_id),
            payment_details_id=r.payment_details_id,
            merchant_agent=r.merchant_agent,
            amount=r.amount,
            currency=r.currency,
            label=r.label,
            signed_authorization=r.signed_authorization,
            status=r.status,
            metadata=r.metadata_,
        )
        for r in records
    ]
