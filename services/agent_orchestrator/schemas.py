"""Pydantic schemas for the Agent Orchestrator Service."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Agent Invocation ─────────────────────────────────────────────────────

class AgentInvokeRequest(BaseModel):
    agent_type: str = Field(..., description="Agent type: customer_facing, retention, provisioning, executive, support")
    message: str = Field(..., min_length=1)
    context: Dict[str, Any] = Field(default_factory=dict)
    tenant_id: Optional[uuid.UUID] = None
    conversation_id: Optional[uuid.UUID] = Field(
        None,
        description="Existing conversation ID to continue. If omitted, a new conversation is created."
    )


class AgentInvokeResponse(BaseModel):
    conversation_id: uuid.UUID
    message: str
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    agent_type: str


class AgentInfo(BaseModel):
    agent_type: str
    description: str
    llm: str
    tools: List[str]


# ── Conversation ─────────────────────────────────────────────────────────

class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    agent_type: str
    channel: str
    external_id: Optional[str]
    status: str
    context: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: Optional[str]
    tool_calls: Optional[Dict[str, Any]]
    tool_results: Optional[Dict[str, Any]]
    created_at: datetime


class ConversationWithMessages(ConversationRead):
    messages: List[MessageRead]


# ── Tool ─────────────────────────────────────────────────────────────────

class ToolInfo(BaseModel):
    name: str
    description: str
    service: str
    method: str
    endpoint: str


class ToolInvokeRequest(BaseModel):
    tool_name: str
    tool_input: Dict[str, Any] = Field(default_factory=dict)
    tenant_id: Optional[uuid.UUID] = None
    user_id: Optional[uuid.UUID] = None


class ToolInvokeResponse(BaseModel):
    tool_name: str
    result: Any
    success: bool
    error: Optional[str] = None


# ── Chat Deployments (Task 7: per-agent deployable public chat) ──────────

VALID_AGENT_TYPES = ("customer_facing", "retention", "provisioning", "executive", "support")


class ChatDeploymentCreate(BaseModel):
    agent_type: str = Field(..., description="Agent type: customer_facing, retention, provisioning, executive, support")
    identifier: str = Field(..., min_length=4, max_length=64)
    display_name: Optional[str] = Field(default=None, max_length=120)
    access_key: Optional[str] = Field(default=None, min_length=8, max_length=256)

    @field_validator("agent_type")
    @classmethod
    def _check_agent_type(cls, v: str) -> str:
        if v not in VALID_AGENT_TYPES:
            raise ValueError(f"Invalid agent_type: {v!r}. Must be one of {', '.join(VALID_AGENT_TYPES)}")
        return v


class ChatDeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    agent_type: str
    identifier: str
    display_name: Optional[str] = None
    is_active: bool = True
    has_key: bool = False  # NEVER expose the hash
    created_at: datetime
    updated_at: datetime


class ChatPublicRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    conversation_id: Optional[uuid.UUID] = None
    key: Optional[str] = None


class ChatPublicResponse(BaseModel):
    identifier: str
    conversation_id: uuid.UUID
    message: str
    agent_type: str
