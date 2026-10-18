"""Product catalogue tables (additive; the legacy inventory_products/billing_plans tables are untouched).

The definition (descriptions, costs, components, fees, media/document metadata, research, launch readiness)
lives in one JSON document per product with an optimistic-concurrency ``revision``. Identity, classification,
lifecycle and the tenant-unique product number are real columns so they can be constrained and indexed.
Portable column types keep the API testable on SQLite while using JSONB/UUID on Postgres.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, JSON, LargeBinary, String, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from services.inventory.database import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


class CatalogueProduct(Base):
    __tablename__ = "catalogue_products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "product_number", name="uq_catalogue_product_number"),
        Index("ix_catalogue_products_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    product_number: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    range: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    family: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    nature: Mapped[str] = mapped_column(String(40), nullable=False, default="Digital service")
    usage: Mapped[str] = mapped_column(String(40), nullable=False, default="Customer-facing")
    owner: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")  # draft | in_review | active | archived
    definition: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The stock item (inventory_products.id) this catalogue product is bought, held and issued as.
    inventory_product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CatalogueList(Base):
    """Managed lists: categories, ranges (parent = category name) and service families."""
    __tablename__ = "catalogue_lists"
    __table_args__ = (UniqueConstraint("tenant_id", "kind", "parent", "name", name="uq_catalogue_list_value"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)       # category | range | family
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    parent: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CatalogueReservedNumber(Base):
    """Product numbers are never reused, including those of deleted drafts."""
    __tablename__ = "catalogue_reserved_numbers"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    product_number: Mapped[str] = mapped_column(String(32), primary_key=True)
    released_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CatalogueEvent(Base):
    """Append-only history: who did what to which product, with the evidence snapshot for launches."""
    __tablename__ = "catalogue_events"
    __table_args__ = (Index("ix_catalogue_events_product", "tenant_id", "product_id", "at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    actor: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    detail: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CatalogueAsset(Base):
    """Uploaded product pictures and documents (bytes kept in the database for now; swap for object storage later
    without changing the API: assets are only ever referenced by id)."""
    __tablename__ = "catalogue_assets"
    __table_args__ = (Index("ix_catalogue_assets_product", "tenant_id", "product_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SupplierReturn(Base):
    """Stock returned to a supplier (fault, wrong item, damage after receipt). Feeds the supplier scorecard."""
    __tablename__ = "inventory_supplier_returns"
    __table_args__ = (Index("ix_supplier_returns_supplier", "tenant_id", "supplier_id", "returned_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)      # inventory_products.id
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    po_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    gr_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="returned")   # returned | credited
    credit_note_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stock_adjusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    returned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SupplierEvaluation(Base):
    """The receiver's rating of one delivery (goods receipt). One per receipt."""
    __tablename__ = "inventory_supplier_evaluations"
    __table_args__ = (UniqueConstraint("tenant_id", "gr_id", name="uq_supplier_eval_gr"),
                      Index("ix_supplier_eval_supplier", "tenant_id", "supplier_id"))

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    gr_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    po_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)            # 1 (poor) .. 5 (excellent)
    late_reason: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    comment: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    evaluated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
