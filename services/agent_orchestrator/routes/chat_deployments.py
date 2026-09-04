"""Per-agent deployable public chat (Task 7).

Admin router (`router`, mounted at /api/chat-deployments, auth required):
  POST ""              — create identifier + optional access key for an agent
  GET ""               — list my tenant's deployments
  DELETE "/{identifier}" — deactivate (is_active=False, tenant-scoped)

Public router (`public_router`, mounted at /api/chat, NO auth):
  POST "/{identifier}" — chat via identifier; tenant resolved from the
                         deployment row itself.

Key handling: only the sha256 hex digest is stored (access_key_hash);
plaintext is never persisted. See validate_identifier/hash_key/verify_key.
"""

import hashlib
import hmac
import os
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

try:  # production: PYTHONPATH=/app (repo root), repo-root-absolute imports
    from services.common.auth import AuthContext, get_auth_context
    from services.common.db import session_scope as get_session
    from services.agent_orchestrator.agents import Agent
    from services.agent_orchestrator.config import settings
    from services.agent_orchestrator.hermes_client import hermes_client
    from services.agent_orchestrator.guardrails.gate import run_gate
    from services.agent_orchestrator.conversation.models import (
        AgentConversation,
        AgentMessage,
        ChatDeployment,
    )
    from services.agent_orchestrator.routes.agents import (
        _hermes_system_note,
        _persist_messages,
    )
    from services.agent_orchestrator.schemas import (
        VALID_AGENT_TYPES,
        ChatDeploymentCreate,
        ChatDeploymentRead,
        ChatPublicRequest,
        ChatPublicResponse,
    )
except ImportError:  # pytest: service-dir-relative imports (pure helpers only)
    from conversation.models import (  # noqa: F401
        AgentConversation,
        AgentMessage,
        ChatDeployment,
    )
    from guardrails.gate import run_gate  # noqa: F401
    from schemas import (  # noqa: F401
        VALID_AGENT_TYPES,
        ChatDeploymentCreate,
        ChatDeploymentRead,
        ChatPublicRequest,
        ChatPublicResponse,
    )

    class AuthContext:  # minimal stub so route signatures import w/o services.*
        tenant_id = None
        user_id = None

    async def get_auth_context():  # stub dependency (never called in unit tests)
        raise RuntimeError("auth unavailable in unit-test import mode")

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def get_session():  # stub (never entered in unit tests)
        raise RuntimeError("db unavailable in unit-test import mode")
        yield None

    class Agent:  # stub (instantiated only inside endpoints)
        def __init__(self, *a, **k):
            raise RuntimeError("agent unavailable in unit-test import mode")

    class _SettingsStub:
        chat_backend = "hermes"
        guardrails_policy = "standard"

    settings = _SettingsStub()

    class _HermesStub:
        async def chat(self, messages):
            raise RuntimeError("hermes unavailable in unit-test import mode")

    hermes_client = _HermesStub()

    def _hermes_system_note(agent_type, tenant_id, context):
        return ""

    async def _persist_messages(**kwargs):
        raise RuntimeError("db unavailable in unit-test import mode")

router = APIRouter()
public_router = APIRouter()


# ---------------------------------------------------------------------------
# Pure helpers (unit-testable, no DB)
# ---------------------------------------------------------------------------

_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")


def validate_identifier(s: str) -> bool:
    """Public chat identifier: lowercase alnum + hyphens, 4-64 chars.

    Must start with [a-z0-9] and contain only [a-z0-9-]; the {2,63}
    tail keeps total length within 3..64 while the Field(min_length=4)
    on the schema enforces the 4-char minimum at the API boundary.
    """
    return bool(_IDENTIFIER_RE.fullmatch(s)) and len(s) >= 4


def hash_key(k: str) -> str:
    """sha256 hex digest of an access key. Plaintext is never stored."""
    return hashlib.sha256(k.encode("utf-8")).hexdigest()


def verify_key(k: str, h: str) -> bool:
    """Constant-time comparison of a candidate key against a stored digest."""
    return hmac.compare_digest(hash_key(k), h)


def _to_read(dep: ChatDeployment) -> ChatDeploymentRead:
    return ChatDeploymentRead(
        id=dep.id,
        tenant_id=dep.tenant_id,
        agent_type=dep.agent_type,
        identifier=dep.identifier,
        display_name=dep.display_name,
        is_active=dep.is_active,
        has_key=dep.access_key_hash is not None,
        created_at=dep.created_at,
        updated_at=dep.updated_at,
    )


def _skip_db() -> bool:
    return os.getenv("VOICE_DEV_SKIP_DB", "").lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Admin CRUD (auth required)
# ---------------------------------------------------------------------------


@router.post("", response_model=ChatDeploymentRead)
async def create_deployment(
    body: ChatDeploymentCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    if not validate_identifier(body.identifier):
        raise HTTPException(
            status_code=422,
            detail="Invalid identifier: lowercase alphanumerics and hyphens, 4-64 chars",
        )
    access_key_hash = hash_key(body.access_key) if body.access_key else None
    async with get_session() as session:
        existing = (
            await session.execute(
                select(ChatDeployment).where(ChatDeployment.identifier == body.identifier)
            )
        ).scalar_one_or_none()
        if existing:
            if existing.tenant_id == ctx.tenant_id and not existing.is_active:
                # Owner recycle: reactivate own soft-deleted row instead of
                # deadlocking on the global unique identifier.
                existing.is_active = True
                existing.agent_type = body.agent_type
                existing.display_name = body.display_name
                existing.access_key_hash = access_key_hash
                await session.flush()
                await session.refresh(existing)
                return _to_read(existing)
            raise HTTPException(status_code=409, detail="Identifier already taken")
        dep = ChatDeployment(
            tenant_id=ctx.tenant_id,
            agent_type=body.agent_type,
            identifier=body.identifier,
            display_name=body.display_name,
            access_key_hash=access_key_hash,
            is_active=True,
            created_by=ctx.user_id,
        )
        session.add(dep)
        await session.flush()
        await session.refresh(dep)
        return _to_read(dep)


@router.get("", response_model=list[ChatDeploymentRead])
async def list_deployments(ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        result = await session.execute(
            select(ChatDeployment)
            .where(ChatDeployment.tenant_id == ctx.tenant_id)
            .order_by(ChatDeployment.created_at.desc())
        )
        return [_to_read(d) for d in result.scalars().all()]


@router.delete("/{identifier}", response_model=ChatDeploymentRead)
async def deactivate_deployment(
    identifier: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        dep = (
            await session.execute(
                select(ChatDeployment).where(
                    ChatDeployment.identifier == identifier,
                    ChatDeployment.tenant_id == ctx.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if not dep:
            raise HTTPException(status_code=404, detail="Deployment not found")
        dep.is_active = False
        await session.flush()
        await session.refresh(dep)
        return _to_read(dep)


# ---------------------------------------------------------------------------
# Public identifier chat (NO auth — tenant comes from the deployment row)
# ---------------------------------------------------------------------------


@public_router.post("/{identifier}", response_model=ChatPublicResponse)
async def public_chat(identifier: str, body: ChatPublicRequest):
    conversation_id = body.conversation_id
    skip_db = _skip_db()

    if skip_db:
        # Dev mode: no DB — identifier/key checks are skipped; agent_type
        # defaults to support unless the identifier hints otherwise.
        tenant_id = uuid.uuid4()
        agent_type = "support"
    else:
        async with get_session() as session:
            dep = (
                await session.execute(
                    select(ChatDeployment).where(
                        ChatDeployment.identifier == identifier,
                        ChatDeployment.is_active == True,  # noqa: E712
                    )
                )
            ).scalar_one_or_none()
            if not dep:
                raise HTTPException(status_code=404, detail="Chat deployment not found")
            if dep.access_key_hash:
                if not body.key or not verify_key(body.key, dep.access_key_hash):
                    raise HTTPException(status_code=403, detail="Invalid access key")
            if dep.agent_type not in VALID_AGENT_TYPES:
                raise HTTPException(status_code=422, detail="Deployment has invalid agent_type")
            tenant_id = dep.tenant_id
            agent_type = dep.agent_type

    # Guardrails pre-gate (block → 422, before any DB writes / agent work).
    policy = settings.guardrails_policy
    gate_in = run_gate(body.message, policy)
    if gate_in["action"] == "block":
        raise HTTPException(
            status_code=422,
            detail={"error": gate_in.get("error", "Input blocked by guardrails"),
                    "hits": gate_in["hits"]},
        )
    safe_message = gate_in["text"]

    history = None
    if skip_db:
        if not conversation_id:
            conversation_id = uuid.uuid4()
    else:
        async with get_session() as session:
            if conversation_id:
                conv = (
                    await session.execute(
                        select(AgentConversation).where(
                            AgentConversation.id == conversation_id,
                            AgentConversation.tenant_id == tenant_id,
                            # Pin resume to this deployment: don't let one
                            # identifier continue another's conversation and
                            # mix histories across agents.
                            AgentConversation.external_id == identifier,
                            AgentConversation.agent_type == agent_type,
                        )
                    )
                ).scalar_one_or_none()
                if not conv:
                    raise HTTPException(status_code=404, detail="Conversation not found")
                msg_result = await session.execute(
                    select(AgentMessage)
                    .where(AgentMessage.conversation_id == conversation_id)
                    .order_by(AgentMessage.created_at.asc())
                )
                messages = msg_result.scalars().all()
                history = [
                    {"role": m.role, "content": m.content or ""}
                    for m in messages
                    if m.role in ("user", "assistant")
                ]
            else:
                conv = AgentConversation(
                    tenant_id=tenant_id,
                    agent_type=agent_type,
                    channel="chat_deploy",
                    external_id=identifier,
                )
                session.add(conv)
                await session.flush()
                conversation_id = conv.id

    # Run the agent — same hermes/legacy branch as invoke_agent.
    agent = Agent(agent_type=agent_type, tenant_id=tenant_id, context={})
    if settings.chat_backend == "hermes":
        messages = agent._build_messages(safe_message, history)
        messages.insert(
            0, {"role": "system", "content": _hermes_system_note(agent_type, tenant_id, {})}
        )
        content = await hermes_client.chat(messages)
        result = {"content": content, "tool_calls": [], "conversation_id": conversation_id}
    else:
        result = await agent.run(
            user_message=safe_message,
            history=history,
            conversation_id=conversation_id,
        )

    # Guardrails post-gate on the assistant output.
    gate_out = run_gate(result["content"], policy)
    if gate_out["action"] == "mask":
        final_content = gate_out["text"]
    elif gate_out["action"] == "block":
        final_content = "[Response withheld by guardrails]"
    else:
        final_content = result["content"]
    gate_verdicts = [
        {"side": "input", "hits": gate_in["hits"], "action": gate_in["action"]},
        {"side": "output", "hits": gate_out["hits"], "action": gate_out["action"]},
    ]

    if not skip_db:
        async with get_session() as session:
            await _persist_messages(
                session=session,
                conversation_id=conversation_id,
                agent_type=agent_type,
                user_message=safe_message,
                assistant_content=final_content,
                tool_calls=result.get("tool_calls", []),
                gate_verdicts=gate_verdicts,
            )
            await session.flush()

    return ChatPublicResponse(
        identifier=identifier,
        conversation_id=conversation_id,
        message=final_content,
        agent_type=agent_type,
    )
