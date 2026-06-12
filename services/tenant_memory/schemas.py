from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


Visibility = Literal["private", "team", "tenant", "system"]
Importance = Literal["low", "normal", "high", "critical"]


class MemoryEntryCreate(BaseModel):
    source_type: str = Field(..., max_length=80)
    source_id: Optional[str] = Field(None, max_length=160)
    module: Optional[str] = Field(None, max_length=80)
    scope_key: Optional[str] = Field(None, max_length=160)
    title: str = Field(..., min_length=1, max_length=240)
    content: str = Field(..., min_length=1)
    summary: Optional[str] = Field(None, max_length=1000)
    visibility: Visibility = "tenant"
    importance: Importance = "normal"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: Optional[datetime] = None


class MemoryEntryUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=240)
    content: Optional[str] = Field(None, min_length=1)
    summary: Optional[str] = Field(None, max_length=1000)
    visibility: Optional[Visibility] = None
    importance: Optional[Importance] = None
    tags: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None
    archived: Optional[bool] = None


class MemoryEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    source_type: str
    source_id: Optional[str] = None
    module: Optional[str] = None
    scope_key: Optional[str] = None
    title: str
    content: str
    summary: Optional[str] = None
    visibility: str
    importance: str
    tags: list[str]
    metadata: dict[str, Any]
    created_by: Optional[uuid.UUID] = None
    occurred_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class MemoryListResponse(BaseModel):
    items: list[MemoryEntryRead]
    limit: int


class MemorySummaryUpsert(BaseModel):
    scope_key: str = Field(..., max_length=160)
    module: Optional[str] = Field(None, max_length=80)
    title: str = Field(..., min_length=1, max_length=240)
    summary: str = Field(..., min_length=1)
    source_entry_ids: list[uuid.UUID] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemorySummaryRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    scope_key: str
    module: Optional[str] = None
    title: str
    summary: str
    source_entry_ids: list[uuid.UUID]
    metadata: dict[str, Any]
    updated_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class MemoryRecallResponse(BaseModel):
    summaries: list[MemorySummaryRead]
    entries: list[MemoryEntryRead]

