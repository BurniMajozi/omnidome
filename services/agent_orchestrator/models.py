"""SQLAlchemy models for the Agent Orchestrator Service."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.db import Base as CommonBase


class Base(CommonBase):
    __abstract__ = True


class AgentConversation(Base):
    __tablename__ = "agent_conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="api")
    external_id: Mapped[str] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_agent_conv_tenant", "tenant_id", "agent_type"),
        Index("ix_agent_conv_external", "external_id"),
    )


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[dict] = mapped_column(JSONB, nullable=True)
    tool_results: Mapped[dict] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_agent_msg_conversation", "conversation_id", "created_at"),
    )


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_conversations.id", ondelete="SET NULL"), nullable=True
    )
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=True)
    tool_input: Mapped[dict] = mapped_column(JSONB, nullable=True)
    tool_output: Mapped[dict] = mapped_column(JSONB, nullable=True)
    success: Mapped[bool] = mapped_column(default=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_agent_action_conversation", "conversation_id"),
    )


class RegisteredAgent(Base):
    """Tenant-owned roster entry linked to an HR employee, not a running process."""

    __tablename__ = "registered_agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(200), nullable=False, default="AI agent")
    department: Mapped[str] = mapped_column(String(120), nullable=False, default="General")
    llm_model: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    scope: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    financial_limit: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    monthly_budget_usd: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=25)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="registered")
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "employee_id", name="uq_registered_agent_employee"),
        UniqueConstraint("tenant_id", "agent_type", name="uq_registered_agent_type"),
    )


class AgentTenantBudget(Base):
    __tablename__ = "agent_tenant_budgets"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    monthly_budget_usd: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AgentJob(Base):
    """Durable work item. A worker claims and checkpoints one run at a time."""

    __tablename__ = "agent_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(String(80), nullable=False)
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    goal_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    checkpoint: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    max_cost_usd: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=5)
    estimated_cost_usd: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    actual_cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    cost_source: Mapped[str] = mapped_column(String(24), nullable=False, default="estimated")
    max_iterations: Mapped[int] = mapped_column(nullable=False, default=10)
    max_steps: Mapped[int] = mapped_column(nullable=False, default=25)
    total_steps: Mapped[int] = mapped_column(nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    iteration_history: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    lease_owner: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_agent_jobs_tenant_status", "tenant_id", "status", "created_at"),)


# ── Native workflow / DAG runner (Phase A) ─────────────────────────────────

class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {nodes:[], edges:[]}
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    schedule_cron: Mapped[str] = mapped_column(String(120), nullable=True)  # 5-field cron, e.g. "*/5 * * * *"
    schedule_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # Event trigger (SPEC-lead-automations.md): run when this event type arrives on the bus.
    trigger_event: Mapped[str] = mapped_column(String(120), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("ix_workflows_tenant", "tenant_id", "status"),)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    input: Mapped[dict] = mapped_column(JSONB, nullable=True)
    output: Mapped[dict] = mapped_column(JSONB, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_wfruns_wf", "workflow_id", "started_at"),)


class RunStep(Base):
    __tablename__ = "workflow_run_steps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(String(100), nullable=False)
    node_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    input: Mapped[dict] = mapped_column(JSONB, nullable=True)
    output: Mapped[dict] = mapped_column(JSONB, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_wfsteps_run", "run_id", "started_at"),)


# ── Approval Gate (Spec A8) ─────────────────────────────────────────────────

class AgentApproval(Base):
    __tablename__ = "agent_approvals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    requested_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending | approved | rejected | expired
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    execution_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_agent_approvals_tenant_status", "tenant_id", "status", "created_at"),
        Index("ix_agent_approvals_agent", "tenant_id", "agent_type", "status"),
    )
