"""Explicit request schemas for the compliance tables.

Replaces `Model(**body)` (mass assignment). A schema is derived from the model's
columns MINUS a protected set, and forbids unknown fields, so a client that sends
`tenant_id`, `id`, `created_at` or a server-controlled workflow field gets a 422
instead of silently writing it.
"""

from __future__ import annotations

import enum
import functools
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, create_model
from sqlalchemy import Boolean, Date, DateTime, Enum as SAEnum, Float, Integer, Numeric, String, Text

ALWAYS_PROTECTED = frozenset({"id", "tenant_id", "created_at", "updated_at", "created_by"})


def _py_type(col) -> Any:
    t = col.type
    if isinstance(t, SAEnum) and t.enum_class is not None:
        return t.enum_class
    if isinstance(t, Boolean):
        return bool
    if isinstance(t, Integer):
        return int
    if isinstance(t, Float):
        return float
    if isinstance(t, Numeric):
        return Decimal
    if isinstance(t, DateTime):
        return datetime
    if isinstance(t, Date):
        return date
    if isinstance(t, (String, Text)):
        return str
    return Any


@functools.lru_cache(maxsize=None)
def writable_schema(model: type, name: str, protected: tuple = (), partial: bool = False) -> type[BaseModel]:
    """Pydantic model of the writable columns of `model`.

    protected: extra column names clients may not set (workflow/status fields the
    server controls). partial=True makes every field optional (PUT/PATCH).
    """
    blocked = ALWAYS_PROTECTED | set(protected)
    fields: dict[str, Any] = {}
    for col in model.__table__.columns:
        if col.name in blocked:
            continue
        typ = _py_type(col)
        required = (
            not partial
            and not col.nullable
            and col.default is None
            and col.server_default is None
            and not col.primary_key
        )
        if required:
            fields[col.name] = (typ, ...)
        else:
            fields[col.name] = (Optional[typ], None)
    return create_model(name, __config__=ConfigDict(extra="forbid"), **fields)


def create_schema(model: type, *, protected: tuple = ()) -> type[BaseModel]:
    return writable_schema(model, f"{model.__name__}Create", tuple(sorted(protected)), False)


def update_schema(model: type, *, protected: tuple = ()) -> type[BaseModel]:
    return writable_schema(model, f"{model.__name__}Update", tuple(sorted(protected)), True)


def dump_set(body: BaseModel) -> dict:
    """Only the fields the client actually sent (None for nullable fields allowed)."""
    return body.model_dump(exclude_unset=True)


def dump_create(body: BaseModel) -> dict:
    return {k: v for k, v in body.model_dump(exclude_unset=True).items()}
