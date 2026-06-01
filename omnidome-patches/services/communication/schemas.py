"""Pydantic v2 schemas for the Communication Service."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Channels ──────────────────────────────────────────────────────────────

class ChannelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_private: bool = False


class ChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: Optional[str]
    is_private: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_private: Optional[bool] = None


# ── Messages ──────────────────────────────────────────────────────────────

class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    thread_parent_id: Optional[uuid.UUID] = None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel_id: uuid.UUID
    user_id: uuid.UUID
    content: str
    thread_parent_id: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime


class MessageUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


# ── Tasks ─────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    channel_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    assignee_id: Optional[uuid.UUID] = None
    due_date: Optional[datetime] = None
    message_id: Optional[uuid.UUID] = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    channel_id: uuid.UUID
    message_id: Optional[uuid.UUID]
    user_id: uuid.UUID
    title: str
    description: Optional[str]
    status: str
    assignee_id: Optional[uuid.UUID]
    due_date: Optional[datetime]
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    assignee_id: Optional[uuid.UUID] = None
    due_date: Optional[datetime] = None


# ── Approvals ─────────────────────────────────────────────────────────────

class ApprovalCreate(BaseModel):
    channel_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    message_id: Optional[uuid.UUID] = None


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    channel_id: uuid.UUID
    message_id: Optional[uuid.UUID]
    user_id: uuid.UUID
    title: str
    description: Optional[str]
    status: str
    decided_by: Optional[uuid.UUID]
    decided_at: Optional[datetime]
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ApprovalDecision(BaseModel):
    status: str  # "approved" or "rejected"


# ── Escalations ──────────────────────────────────────────────────────────

class EscalationCreate(BaseModel):
    channel_id: uuid.UUID
    ticket_id: Optional[str] = None
    reason: str = Field(..., min_length=1)
    assigned_to: Optional[uuid.UUID] = None


class EscalationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    channel_id: uuid.UUID
    ticket_id: Optional[str]
    reason: Optional[str]
    status: str
    assigned_to: Optional[uuid.UUID]
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ── Events ───────────────────────────────────────────────────────────────

class EventCreate(BaseModel):
    channel_id: uuid.UUID
    event_type: str = Field(..., min_length=1, max_length=100)
    payload: Dict[str, Any] = Field(default_factory=dict)


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    channel_id: uuid.UUID
    user_id: uuid.UUID
    event_type: str
    payload: Dict[str, Any]
    created_at: datetime


# ── Module Data ──────────────────────────────────────────────────────────

class ModuleDataCreate(BaseModel):
    module_name: str = Field(..., min_length=1, max_length=100)
    payload: Dict[str, Any] = Field(default_factory=dict)


class ModuleDataUpdate(BaseModel):
    payload: Dict[str, Any]


class ModuleDataRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    module_name: str
    payload: Dict[str, Any]
    updated_by: Optional[uuid.UUID]
    updated_at: datetime


class ModuleDataResponse(BaseModel):
    data: Optional[Dict[str, Any]] = None
    updated_at: Optional[datetime] = None


# ── Pagination ───────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int
