"""Supply-base sourcing: discovered prospects, RFI/RFQ requests, invitees and their replies, and the tenant's procurement protocol.

Kept in its own tables (additive) so supplier master and purchasing stay as they are. Portable column types keep the
service testable on SQLite while using JSONB/UUID on Postgres.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from services.inventory.catalogue_models import JsonType
from services.inventory.database import Base


class ProcurementProtocol(Base):
    """The tenant's rules for how agents and people go to market for stock. One row per tenant, edited in Admin → Protocols."""
    __tablename__ = "sourcing_protocols"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    config: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SupplierProfile(Base):
    """Whether a supplier is outside the company or an internal source (another business unit, own warehouse, in-house build)."""
    __tablename__ = "sourcing_supplier_profiles"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="external")      # external | internal


class SourcingDiscovery(Base):
    """One web search for suppliers of a product (runs as a metered research job)."""
    __tablename__ = "sourcing_discoveries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="running")     # running | done | failed
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    prospects: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SupplierProspect(Base):
    """A possible supplier found on the web, not yet in the supplier master. Contact details are only what the source shows."""
    __tablename__ = "sourcing_prospects"
    __table_args__ = (UniqueConstraint("tenant_id", "domain", "product_id", name="uq_prospect_domain_product"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    discovery_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    website: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    country: Mapped[str | None] = mapped_column(String(60), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fit: Mapped[int | None] = mapped_column(Integer, nullable=True)                       # 0-100, how well the page matches the product
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="new")         # new | invited | converted | dismissed
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)             # set once converted into the supplier master
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SourcingRequest(Base):
    """A request for information (RFI) or for a quotation (RFQ) about one product, sent to several suppliers."""
    __tablename__ = "sourcing_requests"
    __table_args__ = (UniqueConstraint("tenant_id", "number", name="uq_sourcing_number"), Index("ix_sourcing_tenant_status", "tenant_id", "status"))

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    number: Mapped[str] = mapped_column(String(24), nullable=False)
    kind: Mapped[str] = mapped_column(String(3), nullable=False)                            # RFI | RFQ
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)                # catalogue product
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)       # internal only, never sent unless the protocol says so
    needed_by: Mapped[date | None] = mapped_column(Date, nullable=True)
    subject: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    drafted_by: Mapped[str] = mapped_column(String(10), nullable=False, default="template")  # ai | template | user
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # draft | pending_approval | approved | sent | awarded | closed | cancelled
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by_agent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    awarded_invitee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    award_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")       # manual | reorder_scan | agent
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SourcingInvitee(Base):
    __tablename__ = "sourcing_invitees"
    __table_args__ = (Index("ix_invitee_request", "request_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    prospect_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="external")       # external | internal
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="invited")      # invited | sent | failed | replied | declined
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SourcingResponse(Base):
    __tablename__ = "sourcing_responses"
    __table_args__ = (Index("ix_response_request", "request_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    invitee_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    unit_price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)         # ex VAT, ZAR
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    moq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")       # manual | parsed
    declined: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
