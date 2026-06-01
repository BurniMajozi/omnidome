"""Pydantic schemas for the Agent Orchestrator Service."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Agent Invocation ─────────────────────────────────────────────────────

class AgentInvokeRequest(BaseModel):
    agent_type: str = Field(..., description="Agent type: customer_facing, retention, provisioning, executive, support")
    message: str = Field(..., min_length=1)
    context: Dict[str, Any] = Field(default_factory=dict)
    tenant_id: Optional[uuid.UUID] = None


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
