from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from services.agent_orchestrator.agents import Agent
from services.agent_orchestrator.config import settings
from services.agent_orchestrator.protocols import (
    A2AMessage,
    A2UIPayload,
    AGENT_SKILLS,
    AGUIEvent,
    AGUIRunRequest,
    AgentCard,
    IntentMandate,
    IntentMandateCreate,
    PaymentMandate,
    PaymentMandateCreate,
    PaymentReceipt,
    PaymentReceiptCreate,
    UCPCheckoutCreateRequest,
    UCPCheckoutSession,
)
from services.common.auth import AuthContext, get_auth_context
from services.agent_orchestrator.tools import tool_registry

router = APIRouter(tags=["Agent Protocols"])

_checkout_sessions: dict[uuid.UUID, UCPCheckoutSession] = {}
_intent_mandates: dict[uuid.UUID, IntentMandate] = {}
_payment_mandates: dict[uuid.UUID, PaymentMandate] = {}
_payment_receipts: dict[uuid.UUID, PaymentReceipt] = {}


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


async def _write_protocol_memory(
    ctx: AuthContext,
    title: str,
    content: str,
    metadata: dict[str, Any],
) -> None:
    url = f"{settings.tenant_memory_service_url.rstrip('/')}/api/v1/memories"
    headers = {"X-Tenant-Id": str(ctx.tenant_id), "X-User-Id": str(ctx.user_id)}
    payload = {
        "source_type": "agent_protocol",
        "module": "agents",
        "scope_key": "module:agents",
        "title": title,
        "content": content,
        "summary": title,
        "importance": "normal",
        "tags": ["agent-protocol", "audit"],
        "metadata": metadata,
    }
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(url, json=payload, headers=headers)
    except Exception:
        # Memory write must not block the protocol action.
        return


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
    agent = Agent(
        agent_type=body.agent_type,
        tenant_id=ctx.tenant_id,
        context={**body.context, "user_id": str(ctx.user_id)},
    )
    result = await agent.run(body.message, conversation_id=body.conversation_id)
    return {
        "kind": "message",
        "agent_type": body.agent_type,
        "conversation_id": result.get("conversation_id"),
        "content": result.get("content"),
        "artifacts": [{"type": "tool_calls", "data": result.get("tool_calls", [])}],
    }


@router.post("/api/protocols/ag-ui/run")
async def ag_ui_run(body: AGUIRunRequest, ctx: AuthContext = Depends(get_auth_context)):
    from services.agent_orchestrator.llm import llm_client

    run_id = uuid.uuid4()

    async def emit(event: AGUIEvent) -> str:
        return f"data: {event.model_dump_json()}\n\n"

    async def stream():
        try:
            yield await emit(AGUIEvent(type="RUN_STARTED", run_id=run_id, tenant_id=ctx.tenant_id, conversation_id=body.conversation_id, data={"agent_type": body.agent_type}))
            agent = Agent(
                agent_type=body.agent_type,
                tenant_id=ctx.tenant_id,
                context={**body.context, "user_id": str(ctx.user_id)},
            )
            messages = agent._build_messages(body.message, body.context.get("history", []))
            tools_for_llm = tool_registry.to_openai_format(agent.tools)
            async for token in llm_client.chat_stream(agent_type=body.agent_type, messages=messages, tools=tools_for_llm):
                yield await emit(AGUIEvent(type="TEXT_MESSAGE_CONTENT", run_id=run_id, tenant_id=ctx.tenant_id, conversation_id=body.conversation_id, data={"delta": token}))
            yield await emit(AGUIEvent(type="RUN_FINISHED", run_id=run_id, tenant_id=ctx.tenant_id, conversation_id=body.conversation_id))
        except Exception as exc:
            yield await emit(AGUIEvent(type="RUN_ERROR", run_id=run_id, tenant_id=ctx.tenant_id, conversation_id=body.conversation_id, data={"error": str(exc)}))

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/api/protocols/a2ui/validate")
async def validate_a2ui(payload: A2UIPayload):
    try:
        payload.validate_safe()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"status": "valid", "surface_id": payload.surface_id, "components": len(payload.components)}


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
async def create_checkout_session(body: UCPCheckoutCreateRequest, ctx: AuthContext = Depends(get_auth_context)):
    session = UCPCheckoutSession(
        status="requires_approval" if body.total > settings.ucp_auto_approve_limit_zar else "created",
        total=body.total,
        merchant=body.merchant,
        purpose=body.purpose,
        line_items=body.line_items,
        metadata=body.metadata,
    )
    _checkout_sessions[session.id] = session
    await _write_protocol_memory(ctx, "UCP checkout session created", f"Checkout for {body.merchant}: {body.purpose}", session.model_dump(mode="json"))
    return session


@router.post("/api/protocols/ucp/checkout-sessions/{session_id}/complete", response_model=UCPCheckoutSession)
async def complete_checkout_session(
    session_id: uuid.UUID,
    payment_mandate_id: str | None = None,
    ctx: AuthContext = Depends(get_auth_context),
):
    session = _checkout_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkout session not found")
    if session.status == "requires_approval" and not payment_mandate_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment mandate required")
    session.status = "completed"
    session.payment_mandate_id = payment_mandate_id
    await _write_protocol_memory(ctx, "UCP checkout session completed", f"Checkout completed for {session.merchant}: {session.purpose}", session.model_dump(mode="json"))
    return session


@router.post("/api/protocols/ap2/intent-mandates", response_model=IntentMandate)
async def create_intent_mandate(body: IntentMandateCreate, ctx: AuthContext = Depends(get_auth_context)):
    mandate = IntentMandate.from_create(body)
    _intent_mandates[mandate.id] = mandate
    await _write_protocol_memory(ctx, "AP2 intent mandate created", body.natural_language_description, mandate.model_dump(mode="json"))
    return mandate


@router.post("/api/protocols/ap2/intent-mandates/{mandate_id}/sign", response_model=IntentMandate)
async def sign_intent_mandate(mandate_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    mandate = _intent_mandates.get(mandate_id)
    if not mandate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intent mandate not found")
    mandate.signed = True
    await _write_protocol_memory(ctx, "AP2 intent mandate signed", mandate.natural_language_description, mandate.model_dump(mode="json"))
    return mandate


@router.post("/api/protocols/ap2/payment-mandates", response_model=PaymentMandate)
async def create_payment_mandate(body: PaymentMandateCreate, ctx: AuthContext = Depends(get_auth_context)):
    intent = _intent_mandates.get(body.intent_mandate_id)
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
    _payment_mandates[mandate.id] = mandate
    await _write_protocol_memory(ctx, "AP2 payment mandate created", body.label, mandate.model_dump(mode="json"))
    return mandate


@router.post("/api/protocols/ap2/payment-receipts", response_model=PaymentReceipt)
async def create_payment_receipt(body: PaymentReceiptCreate, ctx: AuthContext = Depends(get_auth_context)):
    mandate = _payment_mandates.get(body.payment_mandate_id)
    if not mandate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment mandate not found")
    if mandate.status != "signed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment mandate is not signed")
    receipt = PaymentReceipt(**body.model_dump())
    _payment_receipts[receipt.id] = receipt
    await _write_protocol_memory(ctx, "AP2 payment receipt created", f"Receipt {body.merchant_confirmation_id}", receipt.model_dump(mode="json"))
    return receipt
