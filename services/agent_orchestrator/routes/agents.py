"""Agent invocation routes — with conversation persistence."""

import json
import uuid
import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope as get_session
from services.agent_orchestrator.agents import Agent
from services.agent_orchestrator.tools import tool_registry
from services.agent_orchestrator.config import settings
from services.agent_orchestrator.hermes_client import hermes_client
from services.agent_orchestrator.protocols import AGUIEvent
from services.agent_orchestrator.schemas import AgentInvokeRequest, AgentInvokeResponse, AgentInfo, ToolPolicyInfo
from services.common import openrouter
from services.agent_orchestrator.conversation.models import (
    AgentConversation,
    AgentMessage,
    AgentAction,
)
from services.agent_orchestrator.guardrails.gate import run_gate
from services.agent_orchestrator.audit_actions import GUARDRAILS_INPUT, GUARDRAILS_OUTPUT

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Intent-based agent router — classifies user message → best specialist
# ---------------------------------------------------------------------------

# Each entry: (agent_type, keyword_patterns)
# Checked in priority order; first match wins.
_INTENT_ROUTES: list[tuple[str, list[str]]] = [
    # 1. Creative drafting, editing & revisions -> OmniAssist
    ("assistant", [
        "draft", "write an email", "write a", "compose", "revise", "rewrite",
        "create a template", "proposal draft", "document draft", "canvas",
    ]),
    # 2. Executive, revenue, pipeline, forecasting, C-suite insights -> InsightBot
    ("executive", [
        "executive", "briefing", "summary", "mrr", "arr", "arpu", "churn rate",
        "revenue", "pipeline", "forecast", "financial summary", "kpi",
        "performance", "scorecard", "strategy", "board", "c-suite",
        "quarterly", "monthly report", "insights", "variance", "target",
        "closed won", "win rate", "deal", "lead", "access to",
    ]),
    # 3. Retention & churn prevention -> ChurnGuard
    ("retention", [
        "churn", "at risk", "retention", "save customer", "cancel",
        "downgrade", "loyalty", "winback", "risk score", "churn predict",
    ]),
    # 4. Technical support & tickets -> SupportBot
    ("support", [
        "ticket", "escalat", "fault", "outage", "diagnostic", "troubleshoot",
        "complaint", "sla", "resolve", "incident", "issue",
    ]),
    # 5. Call center queues & agent metrics -> CallBot
    ("call_center", [
        "call center", "call centre", "queue", "wait time", "agent metrics",
        "call volume", "abandon rate", "aht", "average handle",
    ]),
    # 6. Coverage feasibility, RICA, installation & provisioning -> ProvisionBot
    ("provisioning", [
        "coverage", "feasibility", "provision", "onboard", "activate",
        "install", "rica", "check coverage", "new customer", "signup", "sign up",
    ]),
    # 7. HR, payroll, leave & staff wellness -> StaffBot
    ("talent", [
        "employee", "staff", "hr ", "human resource", "leave", "payroll",
        "hiring", "recruit", "attrition", "wellness", "overtime",
        "schedule", "shift", "training", "onboarding task",
    ]),
    # 8. Safe SQL queries & data exploration -> MetricBot
    ("analytics", [
        "analytics", "sql", "query", "data", "metric", "trend",
        "network health", "conversion", "funnel",
    ]),
    # 9. Fibre plans, bundles & pricing catalog -> ProductBot
    ("products", [
        "product", "plan", "bundle", "pricing", "package",
        "catalogue", "catalog",
    ]),
    # 10. Billing balances, invoices & payments -> DomeBot
    ("customer_facing", [
        "balance", "invoice", "payment", "account", "customer",
        "billing", "service status",
    ]),
    # assistant is the default fallback
]


# On /invoke these hand the request to the specialist _classify_agent picks.
# On the AG-UI and A2A paths "auto" runs itself as the Master Orchestrator
# (all tools), so it is listed in the Agent Manager like any other agent.
ROUTER_AGENT_TYPES = ("auto", "orchestrator", "router", "")
# Same agent, second name: listed once, under its canonical type.
PROMPT_ALIASES = {"orchestrator": "auto"}


def _classify_agent(message: str) -> str:
    """Classify a user message to the best agent type. Returns agent_type string."""
    msg_lower = message.lower()
    for agent_type, patterns in _INTENT_ROUTES:
        for pattern in patterns:
            if pattern in msg_lower:
                return agent_type
    # Default: assistant (most versatile, has strategy + drafting + memory tools)
    return "assistant"


def _hermes_system_note(agent_type: str, tenant_id, context: dict, skills: str = "") -> str:
    """Short domain/tenant context note for Hermes — it has its own persona
    (SOUL.md) and reaches business tools itself via MCP (ask_<agent_type>_agent),
    so this intentionally doesn't replicate the qwen/llama personas in llm.py.
    `skills` is the agent's OKF skills section (spec M2), if any."""
    note = (
        f"This conversation is happening inside OmniDome's '{agent_type}' context "
        f"for tenant {tenant_id}. Use your ask_{agent_type}_agent tool (or other "
        f"ask_*_agent tools) for anything requiring real CRM/billing/network/etc. data. "
        f"Extra context: {json.dumps(context)}"
    )
    return f"{note}\n\n{skills}" if skills else note


def _json_safe(obj: Any) -> Any:
    """Recursively convert Decimal, UUID, date, and other non-JSON types for JSONB storage."""
    from decimal import Decimal
    from datetime import date, datetime
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    return obj


# ---------------------------------------------------------------------------
# Helper: persist messages to a conversation
# ---------------------------------------------------------------------------

async def _persist_messages(
    session,
    conversation_id: uuid.UUID,
    agent_type: str,
    user_message: str,
    assistant_content: str,
    tool_calls: list,
    gate_verdicts: list | None = None,
):
    """Persist user message, tool calls, and assistant response to the conversation."""
    # User message
    user_msg = AgentMessage(
        conversation_id=conversation_id,
        role="user",
        content=user_message,
    )
    session.add(user_msg)

    # Tool call messages (if any)
    for tc in tool_calls:
        safe_args = _json_safe(tc.get("arguments", {}))
        safe_res = _json_safe(tc.get("result", {}))
        tool_msg = AgentMessage(
            conversation_id=conversation_id,
            role="tool",
            content=str(tc.get("result", "")),
            tool_calls=[{
                "name": tc.get("name", ""),
                "arguments": safe_args,
            }],
            tool_results=[safe_res],
        )
        session.add(tool_msg)

        # Also persist to AgentAction for audit trail
        action = AgentAction(
            conversation_id=conversation_id,
            agent_type=agent_type,
            tool_name=tc.get("name", ""),
            tool_input=safe_args,
            tool_output=safe_res,
            success=tc.get("result", {}).get("success", True) if isinstance(tc.get("result"), dict) else True,
        )
        session.add(action)

    # If no tools were called, record a chat_interaction action so conversational turns appear in audit trail
    if not tool_calls and assistant_content:
        action = AgentAction(
            conversation_id=conversation_id,
            agent_type=agent_type,
            tool_name="chat_interaction",
            tool_input={"prompt": user_message[:500]},
            tool_output={"response": assistant_content[:500]},
            success=True,
        )
        session.add(action)

    # Assistant response
    assistant_msg = AgentMessage(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
    )
    session.add(assistant_msg)

    # Guardrail gate verdicts (if any) — audit trail of PII hits on either side.
    # TODO(Task 4+): forward PII hits to compliance breach register.
    for verdict in gate_verdicts or []:
        side = verdict.get("side", "")
        hits = verdict.get("hits", [])
        action = verdict.get("action", "")
        tool_name = GUARDRAILS_INPUT if side == "input" else GUARDRAILS_OUTPUT
        session.add(AgentAction(
            conversation_id=conversation_id,
            agent_type=agent_type,
            tool_name=tool_name,
            tool_input={"hits": hits},
            tool_output={"action": action},
            success=(action != "block"),
        ))

    # Update conversation timestamp
    conv_result = await session.execute(
        select(AgentConversation).where(AgentConversation.id == conversation_id)
    )
    conv = conv_result.scalar_one_or_none()
    if conv:
        conv.updated_at = __import__("datetime").datetime.now(
            tz=__import__("datetime").timezone.utc
        )


async def _store_compaction(session, conversation_id: uuid.UUID, update: Optional[dict]) -> None:
    """Save a new compaction summary on the conversation (spec M4)."""
    if not update:
        return
    conv = (await session.execute(
        select(AgentConversation).where(AgentConversation.id == conversation_id)
    )).scalar_one_or_none()
    if conv:
        conv.context = {**(conv.context or {}), **update}   # new dict so the JSONB change is saved


async def _load_compaction_state(conversation_id: Optional[uuid.UUID], tenant_id) -> Optional[dict]:
    if not conversation_id:
        return None
    async with get_session() as session:
        conv = (await session.execute(
            select(AgentConversation).where(AgentConversation.id == conversation_id,
                                            AgentConversation.tenant_id == tenant_id)
        )).scalar_one_or_none()
        return dict(conv.context or {}) if conv else None


# ---------------------------------------------------------------------------
# In-memory registry of custom HR-created agents
# ---------------------------------------------------------------------------
_custom_agents: dict[str, dict] = {}


@router.post("/register")
async def register_custom_agent(body: dict = Body(...)):
    """Register an HR-created AI agent so it appears in list_agents and Agent Manager."""
    emp_id = body.get("employee_id", "")
    agent_key = body.get("agent_type") or f"custom_{emp_id[:8]}"
    _custom_agents[agent_key] = {
        "agent_type": agent_key,
        "name": body.get("full_name", agent_key),
        "role": body.get("job_title", "Custom AI Agent"),
        "department": body.get("department", "General"),
        "llm_model": body.get("llm_model", "qwen2.5:7b"),
        "financial_limit": body.get("financial_limit", 0),
        "scope": body.get("scope", ""),
        "is_subagent": body.get("is_subagent", False),
        "parent_agent_id": body.get("parent_agent_id"),
        "employee_id": emp_id,
        "employee_code": body.get("employee_code", ""),
    }
    logger.info(f"Registered custom agent: {agent_key} ({body.get('full_name')})")
    return {"status": "registered", "agent_type": agent_key}


# ---------------------------------------------------------------------------
# GET /api/agents — List agents
# ---------------------------------------------------------------------------

@router.get("", response_model=list[AgentInfo])
async def list_agents():
    """List all available agents and their tool sets."""
    legacy_llm = {
        "customer_facing": "qwen2.5:7b",
        "retention": "llama3.1:70b",
        "provisioning": "qwen2.5:7b",
        "executive": "llama3.1:70b",
        "support": "qwen2.5:7b",
    }
    hermes_llm = "hermes-agent (gemma3:4b via Ollama)"

    def _llm(agent_type: str) -> str:
        return hermes_llm if settings.chat_backend == "hermes" else legacy_llm.get(agent_type, "qwen2.5:7b")

    specialist_models = openrouter.model_chain()

    def _info(agent_type: str, description: str) -> AgentInfo:
        agent = Agent(agent_type)
        from services.agent_orchestrator.safe_sql import get_allowlist_for_agent
        allowlist = sorted(list(get_allowlist_for_agent(agent_type))) if "analytics.query" in agent.available_tool_names else []
        return AgentInfo(
            agent_type=agent_type,
            description=description,
            llm=_llm(agent_type),
            tools=agent.available_tool_names,
            tool_policies=[
                ToolPolicyInfo(name=t.name, mutates=t.mutates, requires_approval=t.requires_approval,
                               timeout_s=t.timeout_s, max_output_chars=t.max_output_chars)
                for t in agent.tools
            ],
            specialist_models=specialist_models,
            sql_table_allowlist=allowlist,
        )

    agents = [
        _info("auto", "Master Orchestrator — chat agent with every tool (AG-UI/A2A); on /invoke it routes to a specialist"),
        _info("customer_facing", "DomeBot — assists customers with balances, invoices, coverage, tickets"),
        _info("retention", "ChurnGuard — autonomous churn prediction and retention campaigns"),
        _info("provisioning", "ProvisionBot — automates new customer provisioning workflow"),
        _info("executive", "InsightBot — executive briefings and analytics"),
        _info("support", "SupportBot — ticket management and diagnostics"),
        # Not exposed to Hermes over MCP, but they run: OmniAssist drafts in the
        # lead-warming flows; the specialists are reached via consult_specialist
        # and workflow agent steps.
        _info("assistant", "OmniAssist — drafts messages, documents and plans for staff (agent flows)"),
        _info("analytics", "MetricBot — MRR, conversion and network analytics"),
        _info("call_center", "CallBot — call-centre queues, wait times and SLAs"),
        _info("products", "ProductBot — fibre plans, bundles and pricing"),
        _info("talent", "StaffBot — HR rosters, attrition risk and leave"),
    ]

    # ── Append HR-created custom agents ──────────────────────────────
    for key, meta in _custom_agents.items():
        agents.append(AgentInfo(
            agent_type=key,
            description=f"{meta['name']} — {meta.get('role', 'Custom AI Agent')} ({meta.get('department', '')})",
            llm=meta.get("llm_model", "qwen2.5:7b"),
            tools=[],
            tool_policies=[],
            specialist_models=[],
            sql_table_allowlist=[],
        ))

    return agents


# ---------------------------------------------------------------------------
# GET /api/agents/actions — Audit-trail query (Task 4 / D2)
# ---------------------------------------------------------------------------

def _parse_since(since: Optional[str]):
    """Parse an ISO-8601 datetime string; None in → None out, bad → ValueError."""
    if since is None:
        return None
    try:
        return __import__("datetime").datetime.fromisoformat(since)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid ISO datetime for 'since': {since!r}") from exc


class FeedbackRequest(BaseModel):
    conversation_id: Optional[uuid.UUID] = None
    agent_type: str = "assistant"
    satisfaction: str = Field(..., description="'thumbs_up' or 'thumbs_down'")
    prompt: Optional[str] = None
    response: Optional[str] = None


@router.post("/feedback")
async def record_feedback(
    body: FeedbackRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Record user satisfaction rating (thumbs up / thumbs down) for an agent response."""
    if body.satisfaction not in ("thumbs_up", "thumbs_down"):
        raise HTTPException(status_code=400, detail="Satisfaction must be 'thumbs_up' or 'thumbs_down'")

    async with get_session() as session:
        conv_id = body.conversation_id
        if not conv_id:
            # Create a lightweight conversation to anchor the action
            conv = AgentConversation(
                tenant_id=ctx.tenant_id,
                agent_type=body.agent_type,
                channel="feedback",
                context={"feedback": True},
            )
            session.add(conv)
            await session.flush()
            conv_id = conv.id

        action = AgentAction(
            conversation_id=conv_id,
            agent_type=body.agent_type,
            tool_name="user_feedback",
            tool_input={
                "satisfaction": body.satisfaction,
                "prompt": body.prompt or "",
                "user_id": str(ctx.user_id) if ctx.user_id else None,
            },
            tool_output={
                "response": body.response or "",
                "recorded": True,
            },
            success=True,
        )
        session.add(action)
        await session.flush()

    return {"status": "recorded", "action_id": str(action.id), "satisfaction": body.satisfaction}


@router.get("/actions")
async def list_actions(
    agent_type: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=500),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Newest-first audit trail of AgentAction rows for this tenant.

    AgentAction has no tenant_id column, so tenant scoping goes through the
    conversation join (same ctx.tenant_id pattern as invoke_agent).
    Enriched with the user prompt, assistant response, and user satisfaction rating.
    """
    try:
        since_dt = _parse_since(since)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    async with get_session() as session:
        stmt = (
            select(AgentAction)
            .join(
                AgentConversation,
                AgentAction.conversation_id == AgentConversation.id,
            )
            .where(AgentConversation.tenant_id == ctx.tenant_id)
            .order_by(AgentAction.created_at.desc())
            .limit(limit)
        )
        if agent_type:
            stmt = stmt.where(AgentAction.agent_type == agent_type)
        if since_dt is not None:
            stmt = stmt.where(AgentAction.created_at >= since_dt)
        result = await session.execute(stmt)
        actions = result.scalars().all()

        # Batch fetch conversation messages and feedback to attach prompt, response, satisfaction
        conv_ids = list({a.conversation_id for a in actions if a.conversation_id})
        msg_map: dict[uuid.UUID, dict[str, str]] = {}
        satisfaction_map: dict[uuid.UUID, str] = {}

        if conv_ids:
            # Query messages for prompt and response
            msg_stmt = (
                select(AgentMessage)
                .where(AgentMessage.conversation_id.in_(conv_ids))
                .order_by(AgentMessage.created_at.asc())
            )
            msg_res = await session.execute(msg_stmt)
            for m in msg_res.scalars().all():
                if m.conversation_id not in msg_map:
                    msg_map[m.conversation_id] = {"prompt": "", "response": ""}
                if m.role == "user" and not msg_map[m.conversation_id]["prompt"]:
                    msg_map[m.conversation_id]["prompt"] = m.content or ""
                elif m.role == "assistant":
                    msg_map[m.conversation_id]["response"] = m.content or ""

            # Check if any user_feedback action exists for these conversations
            fb_stmt = (
                select(AgentAction)
                .where(
                    AgentAction.conversation_id.in_(conv_ids),
                    AgentAction.tool_name == "user_feedback",
                )
            )
            fb_res = await session.execute(fb_stmt)
            for fb in fb_res.scalars().all():
                if isinstance(fb.tool_input, dict) and "satisfaction" in fb.tool_input:
                    satisfaction_map[fb.conversation_id] = fb.tool_input["satisfaction"]

    items = []
    for a in actions:
        conv_info = msg_map.get(a.conversation_id, {})
        prompt = conv_info.get("prompt", "")
        response = conv_info.get("response", "")
        satisfaction = satisfaction_map.get(a.conversation_id)

        # If this action is itself a user_feedback action, extract its values directly
        if a.tool_name == "user_feedback" and isinstance(a.tool_input, dict):
            satisfaction = a.tool_input.get("satisfaction", satisfaction)
            if not prompt and a.tool_input.get("prompt"):
                prompt = a.tool_input.get("prompt", "")
            if not response and isinstance(a.tool_output, dict) and a.tool_output.get("response"):
                response = a.tool_output.get("response", "")

        items.append({
            "id": str(a.id),
            "conversation_id": str(a.conversation_id),
            "agent_type": a.agent_type,
            "tool_name": a.tool_name,
            "tool_input": a.tool_input,
            "tool_output": a.tool_output,
            "success": a.success,
            "prompt": prompt,
            "response": response,
            "satisfaction": satisfaction,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })

    return {"items": items}


# ---------------------------------------------------------------------------
# POST /api/agents/invoke — Synchronous agent invocation with persistence
# ---------------------------------------------------------------------------

@router.post("/invoke", response_model=AgentInvokeResponse)
async def invoke_agent(
    body: AgentInvokeRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Synchronous agent invocation. Waits for full response.

    If conversation_id is provided, the agent loads history from that conversation
    and appends new messages to it. If not provided, a new conversation is created.
    """
    conversation_id = body.conversation_id
    skip_db = __import__("os").getenv("VOICE_DEV_SKIP_DB", "").lower() in {"1", "true", "yes", "on"}

    # Intent-based auto routing if agent_type is 'auto' or unspecified
    effective_agent_type = body.agent_type
    route_meta = None
    triage_meta = None
    if effective_agent_type in ROUTER_AGENT_TYPES:
        from services.agent_orchestrator.jev_gate import triage_inbound_inquiry
        triage_decision = await triage_inbound_inquiry(body.message or "", context=body.context)
        effective_agent_type = triage_decision.target_agent
        route_meta = triage_decision.to_dict()
        triage_meta = triage_decision.to_dict()

        # Enrich conversation context with triage metrics for specialist agent & audit
        if body.context is None:
            body.context = {}
        body.context["inbound_triage"] = {
            "frustration_score": triage_decision.frustration_score,
            "churn_risk_score": triage_decision.churn_risk_score,
            "requires_immediate_escalation": triage_decision.requires_immediate_escalation,
            "confidence": triage_decision.confidence,
        }

        logger.info(
            "Orchestrator inbound triage: agent='%s' (conf=%.2f, direct=%s, jev=%s, frust=%.1f, churn=%.1f, escal=%s) for message: %s",
            effective_agent_type,
            triage_decision.confidence,
            triage_decision.is_direct_lookup,
            triage_decision.evaluated_by_jev,
            triage_decision.frustration_score or 0.0,
            triage_decision.churn_risk_score or 0.0,
            triage_decision.requires_immediate_escalation,
            (body.message or "")[:60],
        )

    # Guardrails pre-gate on the inbound user message (before any DB/agent work
    # so a blocked input leaves no stray conversation or LLM call behind).
    policy = settings.guardrails_policy
    gate_in = run_gate(body.message, policy)
    if gate_in["action"] == "block":
        error_msg = gate_in.get("error", "Input blocked by security guardrails")
        logger.warning("Security gate blocked input for agent %s: %s", effective_agent_type, error_msg)
        raise HTTPException(
            status_code=422,
            detail={
                "error": error_msg,
                "hits": gate_in.get("hits", []),
                "injection_hits": gate_in.get("injection_hits", []),
            },
        )
    safe_message = gate_in["text"]

    history = None
    compaction_state = None
    if skip_db:
        if not conversation_id:
            conversation_id = uuid.uuid4()
    else:
        async with get_session() as session:
            # Load history if continuing a conversation
            if conversation_id:
                # Verify conversation exists and belongs to tenant
                conv_result = await session.execute(
                    select(AgentConversation).where(
                        AgentConversation.id == conversation_id,
                        AgentConversation.tenant_id == ctx.tenant_id,
                    )
                )
                conv = conv_result.scalar_one_or_none()
                if not conv:
                    raise HTTPException(status_code=404, detail="Conversation not found")

                # Load message history
                msg_result = await session.execute(
                    select(AgentMessage)
                    .where(AgentMessage.conversation_id == conversation_id)
                    .order_by(AgentMessage.created_at.asc())
                )
                messages = msg_result.scalars().all()
                history = [
                    {"role": m.role, "content": m.content or "", "id": str(m.id)}
                    for m in messages
                    if m.role in ("user", "assistant")
                ]
                compaction_state = dict(conv.context or {})

            # Create new conversation if not continuing
            if not conversation_id:
                conv = AgentConversation(
                    tenant_id=ctx.tenant_id,
                    agent_type=effective_agent_type,
                    channel="api",
                    context=body.context,
                )
                session.add(conv)
                await session.flush()
                conversation_id = conv.id

    # Run the agent (outside the DB session to avoid long-held locks)
    tenant_id = body.tenant_id or ctx.tenant_id
    agent = Agent(
        agent_type=effective_agent_type,
        tenant_id=tenant_id,
        context=body.context,
    )

    if settings.chat_backend == "hermes":
        try:
            messages = await agent.prepare_turn(safe_message, history, compaction_state)
            if not skip_db and conversation_id and agent.compaction_update:
                try:
                    async with get_session() as session:
                        await _store_compaction(session, conversation_id, agent.compaction_update)
                        await session.flush()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Early compaction store failed for %s: %s", conversation_id, exc)
            messages.insert(0, {"role": "system", "content": _hermes_system_note(body.agent_type, tenant_id, body.context, agent.skills_prompt)})
            content = await hermes_client.chat(messages)
            result = {"content": content, "tool_calls": [], "conversation_id": conversation_id}
        except Exception as exc:
            logger.warning("Hermes chat failed (%s); falling back to native agent reasoning loop: %s", settings.hermes_base_url, exc)
            result = await agent.run(
                user_message=safe_message,
                history=history,
                conversation_id=conversation_id,
                compaction_state=compaction_state,
            )
    else:
        result = await agent.run(
            user_message=safe_message,
            history=history,
            conversation_id=conversation_id,
            compaction_state=compaction_state,
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

    # Persist messages
    if not skip_db:
        async with get_session() as session:
            await _persist_messages(
                session=session,
                conversation_id=conversation_id,
                agent_type=effective_agent_type,
                user_message=safe_message,
                assistant_content=final_content,
                tool_calls=result.get("tool_calls", []),
                gate_verdicts=gate_verdicts,
            )
            await _store_compaction(session, conversation_id, agent.compaction_update)
            await session.flush()

    tool_calls = result.get("tool_calls", [])
    pending = [
        tc["result"]
        for tc in tool_calls
        if isinstance(tc.get("result"), dict) and tc["result"].get("requires_approval")
    ]
    hitl_status = "awaiting_hitl" if pending else "completed"

    return AgentInvokeResponse(
        conversation_id=conversation_id,
        message=final_content,
        tool_calls=tool_calls,
        agent_type=effective_agent_type,
        status=hitl_status,
        pending_approvals=pending if pending else None,
        route_decision=route_meta,
        verification=result.get("verification"),
        triage=triage_meta,
    )


# ---------------------------------------------------------------------------
# POST /api/agents/invoke/stream — Streaming agent invocation
# ---------------------------------------------------------------------------

@router.post("/invoke/stream")
async def invoke_agent_stream(
    body: AgentInvokeRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Streaming agent invocation — returns an SSE stream of AGUIEvent JSON
    (matching packages/agent-chat's invokeAgentStreaming parser)."""
    tenant_id = body.tenant_id or ctx.tenant_id
    conversation_id = body.conversation_id

    skip_db = __import__("os").getenv("VOICE_DEV_SKIP_DB", "").lower() in {"1", "true", "yes", "on"}

    # Intent-based auto routing if agent_type is 'auto' or unspecified
    effective_agent_type = body.agent_type
    if effective_agent_type in ROUTER_AGENT_TYPES:
        effective_agent_type = _classify_agent(body.message or "")
        logger.info(
            "Orchestrator stream auto-routed prompt to specialist agent '%s' for message: %s",
            effective_agent_type,
            (body.message or "")[:60],
        )

    async def _ensure_conversation() -> uuid.UUID:
        if conversation_id:
            return conversation_id
        if skip_db:
            return uuid.uuid4()
        async with get_session() as session:
            conv = AgentConversation(
                tenant_id=tenant_id,
                agent_type=effective_agent_type,
                channel="api",
                context=body.context,
            )
            session.add(conv)
            await session.flush()
            return conv.id

    async def event_stream():
        run_id = uuid.uuid4()

        def emit(event: AGUIEvent) -> str:
            return f"data: {event.model_dump_json()}\n\n"

        # Guardrails pre-gate on the inbound user message. On block, emit
        # RUN_ERROR without creating a conversation or calling the LLM.
        policy = settings.guardrails_policy
        gate_in = run_gate(body.message, policy)
        if gate_in["action"] == "block":
            conv_id = conversation_id or uuid.uuid4()
            yield emit(AGUIEvent(
                type="RUN_ERROR", run_id=run_id, tenant_id=tenant_id,
                conversation_id=conv_id,
                data={"error": gate_in.get("error", "Input blocked by guardrails"),
                      "hits": gate_in["hits"]},
            ))
            return
        safe_message = gate_in["text"]

        conv_id = await _ensure_conversation()

        yield emit(AGUIEvent(
            type="RUN_STARTED",
            run_id=run_id,
            tenant_id=tenant_id,
            conversation_id=conv_id,
            data={
                "agent_type": effective_agent_type,
                "auto_routed": body.agent_type in ROUTER_AGENT_TYPES,
            },
        ))

        agent = Agent(agent_type=effective_agent_type, tenant_id=tenant_id, context=body.context)
        history = body.context.get("history", [])
        if not skip_db and conv_id:
            try:
                async with get_session() as session:
                    msg_stmt = (
                        select(AgentMessage)
                        .where(AgentMessage.conversation_id == conv_id)
                        .order_by(AgentMessage.created_at.asc())
                    )
                    msg_res = await session.execute(msg_stmt)
                    db_messages = msg_res.scalars().all()
                    if db_messages:
                        history = [
                            {"role": m.role, "content": m.content or "", "id": str(m.id)}
                            for m in db_messages
                            if m.role in ("user", "assistant")
                        ]
            except Exception as exc:
                logger.warning("Failed to load message history for conversation %s: %s", conv_id, exc)

        full_content = ""
        compaction_state = None
        if not skip_db and body.conversation_id:
            try:
                compaction_state = await _load_compaction_state(conv_id, tenant_id)
            except Exception as exc:  # noqa: BLE001 - compaction is an optimisation
                logger.warning("Compaction state not loaded for %s: %s", conv_id, exc)

        used_hermes = False
        if settings.chat_backend == "hermes":
            try:
                messages = await agent.prepare_turn(safe_message, history, compaction_state)
                if not skip_db and conv_id and agent.compaction_update:
                    try:
                        async with get_session() as session:
                            await _store_compaction(session, conv_id, agent.compaction_update)
                            await session.flush()
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Early compaction store failed for %s: %s", conv_id, exc)
                messages.insert(0, {"role": "system", "content": _hermes_system_note(effective_agent_type, tenant_id, body.context, agent.skills_prompt)})
                async for delta in hermes_client.chat_stream(messages):
                    full_content += delta
                    yield emit(AGUIEvent(
                        type="TEXT_MESSAGE_CONTENT", run_id=run_id, tenant_id=tenant_id,
                        conversation_id=conv_id, data={"delta": delta},
                    ))
                if full_content.strip():
                    used_hermes = True
                else:
                    logger.warning("Hermes yielded empty stream; falling back to native agent stream")
                    used_hermes = False
            except Exception as exc:
                logger.warning("Hermes stream failed (%s); falling back to native agent stream: %s", settings.hermes_base_url, exc)
                used_hermes = False

        executed_tool_calls = []
        if not used_hermes:
            try:
                import asyncio

                result = await agent.run(
                    user_message=safe_message,
                    history=history,
                    conversation_id=conv_id,
                    compaction_state=compaction_state,
                )
                full_content = result.get("content") or ""
                executed_tool_calls = result.get("tool_calls", [])

                for tc in executed_tool_calls:
                    tool_name = tc.get("name")
                    yield emit(AGUIEvent(
                        type="TOOL_CALL_START",
                        run_id=run_id,
                        tenant_id=tenant_id,
                        conversation_id=conv_id,
                        data={
                            "tool_name": tool_name,
                            "arguments": tc.get("arguments"),
                        },
                    ))
                    yield emit(AGUIEvent(
                        type="TOOL_CALL_RESULT",
                        run_id=run_id,
                        tenant_id=tenant_id,
                        conversation_id=conv_id,
                        data={
                            "tool_name": tool_name,
                            "result": tc.get("result"),
                        },
                    ))
                    yield emit(AGUIEvent(
                        type="TOOL_CALL_END",
                        run_id=run_id,
                        tenant_id=tenant_id,
                        conversation_id=conv_id,
                        data={
                            "tool_name": tool_name,
                        },
                    ))

                words = full_content.split(" ")
                chunk_size = 5
                for i in range(0, len(words), chunk_size):
                    chunk = " ".join(words[i:i + chunk_size])
                    if i > 0:
                        chunk = " " + chunk
                    yield emit(AGUIEvent(
                        type="TEXT_MESSAGE_CONTENT",
                        run_id=run_id,
                        tenant_id=tenant_id,
                        conversation_id=conv_id,
                        data={"delta": chunk},
                    ))
                    await asyncio.sleep(0.01)
            except Exception as exc:
                logger.error("Agent stream failed: %s", exc)
                yield emit(AGUIEvent(
                    type="RUN_ERROR", run_id=run_id, tenant_id=tenant_id,
                    conversation_id=conv_id, data={"error": str(exc)},
                ))
                return

        # Guardrails post-gate on the accumulated assistant output.
        gate_out = run_gate(full_content, policy)
        if gate_out["action"] == "mask":
            full_content = gate_out["text"]
        elif gate_out["action"] == "block":
            full_content = "[Response withheld by guardrails]"
        gate_verdicts = [
            {"side": "input", "hits": gate_in["hits"], "action": gate_in["action"]},
            {"side": "output", "hits": gate_out["hits"], "action": gate_out["action"]},
        ]

        if not skip_db:
            async with get_session() as session:
                await _persist_messages(
                    session=session,
                    conversation_id=conv_id,
                    agent_type=effective_agent_type,
                    user_message=safe_message,
                    assistant_content=full_content,
                    tool_calls=executed_tool_calls,
                    gate_verdicts=gate_verdicts,
                )
                await _store_compaction(session, conv_id, agent.compaction_update)
                await session.flush()

        yield emit(AGUIEvent(type="RUN_FINISHED", run_id=run_id, tenant_id=tenant_id, conversation_id=conv_id))

    return StreamingResponse(event_stream(), media_type="text/event-stream")
