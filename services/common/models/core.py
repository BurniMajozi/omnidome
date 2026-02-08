from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from services.common.db import Base


class Tenant(Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String, nullable=False)
    subdomain: Mapped[Optional[str]] = mapped_column(String, unique=True)
    domain: Mapped[Optional[str]] = mapped_column(String, unique=True)
    settings: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    branding: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[Optional[str]] = mapped_column(String, default="ACTIVE")


class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String)
    roles: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)


class Role(Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String, nullable=False)
    permissions: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)


class ModuleEntitlement(Base):
    __tablename__ = "tenant_modules"

    module_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
