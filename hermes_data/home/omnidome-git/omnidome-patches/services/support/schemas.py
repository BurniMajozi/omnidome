"""Pydantic schemas for the Support Service."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TicketCreate(BaseModel):
    customer_id: uuid.UUID
    subject: str = Field(..., min_length=1, max_length=300)
    description: str = Field(..., min_length=1)
    category: str = "general"
    priority: str = "normal"


class TicketUpdate(BaseModel):
    subject: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[uuid.UUID] = None
    resolution_notes: Optional[str] = None


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    subject: str
    description: str
    category: str
    priority: str
    status: str
    assigned_to: Optional[uuid.UUID]
    sla_deadline: Optional[datetime]
    resolved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class TicketNoteCreate(BaseModel):
    content: str = Field(..., min_length=1)
    is_internal: bool = True


class TicketNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID
    content: str
    is_internal: bool
    created_at: datetime


class SLABreachItem(BaseModel):
    ticket_id: uuid.UUID
    subject: str
    priority: str
    sla_deadline: datetime
    hours_overdue: float


class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int
