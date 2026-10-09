"""Tables for BI Studio's Deck Studio: brand kits, decks, insert-only deck versions and data snapshots.

New tables only (create_all never ALTERs). Portable types so unit tests run on SQLite. All rows are
tenant scoped. The AI credit/call ledger is the existing analytics_credit_ledger (feature='bi_ai').
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from services.fno_intelligence.analytics_models import JSONType
from services.fno_intelligence.models import Base


def _id():
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _tenant():
    return mapped_column(Uuid(as_uuid=True), nullable=False, index=True)


def _ts():
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class BiBrandKit(Base):
    __tablename__ = "analytics_brand_kits"

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)  # validated BrandKitConfig
    logo_data_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # sanitised, <= 512KB decoded
    logo_mime: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_analytics_brand_kit_tenant_name"),
        Index("uq_analytics_brand_kit_default", "tenant_id", unique=True,
              postgresql_where=text("is_default"), sqlite_where=text("is_default")),
    )


class BiDeck(Base):
    __tablename__ = "analytics_decks"

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="draft")  # draft|published
    brand_kit_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    doc: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    published_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BiDeckVersion(Base):
    """Insert-only history: one row per saved version of a deck."""
    __tablename__ = "analytics_deck_versions"

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    deck_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    doc: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = _ts()

    __table_args__ = (UniqueConstraint("deck_id", "version", name="uq_analytics_deck_version"),)


class BiDeckRun(Base):
    """A data snapshot of every block's query for one deck ("data as of ...")."""
    __tablename__ = "analytics_deck_runs"

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    deck_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    doc_version: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)    # {query_key: result}
    errors: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)  # {query_key: message}
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


BI_TABLES = [BiBrandKit.__table__, BiDeck.__table__, BiDeckVersion.__table__, BiDeckRun.__table__]
