"""SQLAlchemy models for the CRM service."""

import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from services.common.db import register_tenant_scoped_base


class Base(DeclarativeBase):
    pass


# Every model below carries tenant_id; opt this Base into the automatic
# tenant filter in services.common.db so a missed manual .where() clause
# can no longer leak rows across tenants.
register_tenant_scoped_base(Base)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

CUSTOMER_STATUS = SAEnum(
    "active", "suspended", "churned", name="customer_status", create_type=True
)

SA_PROVINCES = SAEnum(
    "eastern_cape",
    "free_state",
    "gauteng",
    "kwazulu_natal",
    "limpopo",
    "mpumalanga",
    "north_west",
    "northern_cape",
    "western_cape",
    name="sa_province",
    create_type=True,
)


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------

class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    id_number: Mapped[Optional[str]] = mapped_column(String(13), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    province: Mapped[Optional[str]] = mapped_column(SA_PROVINCES, nullable=True)
    account_number: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(CUSTOMER_STATUS, nullable=False, default="active")
    rica_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Company link (for employees whose company pays)
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    company_role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # employee, manager, director, etc.

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # relationships
    notes: Mapped[list["CustomerNote"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    tags: Mapped[list["CustomerTag"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    company = relationship("Company", back_populates="members")
    properties: Mapped[list["PropertyAccount"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan",
        foreign_keys="[PropertyAccount.customer_id]",
    )
    outgoing_handovers: Mapped[list["AccountHandover"]] = relationship(
        "AccountHandover", foreign_keys="[AccountHandover.from_customer_id]", back_populates="from_customer"
    )
    incoming_handovers: Mapped[list["AccountHandover"]] = relationship(
        "AccountHandover", foreign_keys="[AccountHandover.to_customer_id]", back_populates="to_customer"
    )

    __table_args__ = (
        Index("ix_customers_tenant_status", "tenant_id", "status"),
        Index("ix_customers_fulltext", "first_name", "last_name", "email", "phone", "account_number"),
        Index("ix_customers_company", "company_id"),
    )


# ---------------------------------------------------------------------------
# Company (for corporate accounts where company pays for employees)
# ---------------------------------------------------------------------------

class Company(Base):
    """A business entity that pays for employee internet services.

    When a company signs up for corporate accounts, each employee gets
    their own customer record and service account, but the company is
    the billing entity. The company can have multiple members (employees),
    each with their own service at potentially different addresses.
    """
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # Company identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    registration_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tax_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Contact
    contact_person: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Billing
    billing_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payment_method_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    payment_terms: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # "Net 30", "Net 60"
    credit_limit_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    members: Mapped[list["Customer"]] = relationship(back_populates="company", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_companies_tenant", "tenant_id"),
        Index("ix_companies_name", "name"),
    )


# ---------------------------------------------------------------------------
# Property (physical house/address that can have service accounts)
# ---------------------------------------------------------------------------

class Property(Base):
    """A physical property/address that can have one or more service accounts.

    A customer can own or rent multiple properties. Each property can have
    one active service account at a time. For rental properties, the
    account can be handed over from one tenant to the next.
    """
    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # Property identity
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # "123 Main St", "Beach House", "Office Unit 4B"

    # Address
    line1: Mapped[str] = mapped_column(String(255), nullable=False)
    line2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    province: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    gps_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    gps_lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)

    # Property type
    property_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="residential"
    )
    # residential, commercial, industrial, mixed_use

    # Ownership
    owner_customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    # The property owner (may differ from the service account holder)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    owner = relationship("Customer", foreign_keys=[owner_customer_id])
    accounts: Mapped[list["PropertyAccount"]] = relationship(back_populates="property", cascade="all, delete-orphan")
    handovers: Mapped[list["AccountHandover"]] = relationship(back_populates="property", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_properties_tenant", "tenant_id"),
        Index("ix_properties_owner", "owner_customer_id"),
        Index("ix_properties_postal", "postal_code"),
    )


# ---------------------------------------------------------------------------
# PropertyAccount (links a customer's service account to a property)
# ---------------------------------------------------------------------------

class PropertyAccount(Base):
    """Links a customer's service account to a specific property.

    Tracks the relationship between a customer, their service account,
    and the property where service is installed. Supports:
    - Owner-occupier (customer = owner)
    - Tenant (customer ≠ owner, owner is landlord)
    - Multiple accounts per property (e.g., home + office at same address)
    """
    __tablename__ = "property_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )

    # Account reference
    account_number: Mapped[str] = mapped_column(String(50), nullable=False)
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationship type
    relationship_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="owner"
    )
    # owner, tenant, family_member, employee

    # Billing responsibility
    billing_customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    # Who pays the bill (may differ from account holder, e.g., company pays for employee)
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    # Primary account for this property (only one active primary per property)

    # Dates
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    property = relationship("Property", back_populates="accounts")
    customer = relationship("Customer", foreign_keys=[customer_id], back_populates="properties")
    billing_customer = relationship("Customer", foreign_keys=[billing_customer_id])
    billing_company = relationship("Company")

    __table_args__ = (
        Index("ix_prop_accounts_property", "property_id"),
        Index("ix_prop_accounts_customer", "customer_id"),
        Index("ix_prop_accounts_number", "account_number"),
        Index("ix_prop_accounts_company", "company_id"),
    )


# ---------------------------------------------------------------------------
# AccountHandover (tenant-to-tenant transfer for rental properties)
# ---------------------------------------------------------------------------

HANDOVER_STATUS = SAEnum(
    "pending", "in_progress", "completed", "cancelled", "disputed",
    name="handover_status", create_type=True,
)

HANDOVER_TRIGGER = SAEnum(
    "tenant_move_out",      # Tenant leaving, new tenant moving in
    "lease_renewal",        # Same tenant, new lease term
    "owner_take_back",      # Owner reclaiming property
    "new_tenant",           # New tenant, no previous tenant
    "account_correction",   # Admin correction
    name="handover_trigger", create_type=True,
)


class AccountHandover(Base):
    """Tracks the handover of a service account from one customer to another at a property.

    This is the core mechanism for rental property account transfers:
    1. Outgoing tenant initiates handover (or landlord initiates)
    2. New tenant is identified and verified
    3. Account is transferred: subscriptions, equipment, billing
    4. Equipment inspection (what stays, what goes, what's damaged)
    5. Handover completed or disputed

    The handover preserves the service history at the property level
    while changing the account holder.
    """
    __tablename__ = "account_handovers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
    )
    property_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property_accounts.id", ondelete="CASCADE"), nullable=False
    )

    # From / To
    from_customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    to_customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )

    # Handover details
    status: Mapped[str] = mapped_column(HANDOVER_STATUS, nullable=False, default="pending")
    trigger: Mapped[str] = mapped_column(HANDOVER_TRIGGER, nullable=False, default="tenant_move_out")

    # Equipment handling
    equipment_stays: Mapped[bool] = mapped_column(Boolean, default=True)
    # If True, ONT/router stays installed (typical for fibre)
    # If False, equipment is returned (typical for LTE router)
    equipment_inspection_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    equipment_condition: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # good, fair, damaged, missing

    # Financial settlement
    outstanding_balance_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    deposit_transfer_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    settlement_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Dates
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    scheduled_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Actor
    initiated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    initiated_by_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # customer, landlord, agent, admin

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    property = relationship("Property", back_populates="handovers")
    property_account = relationship("PropertyAccount")
    from_customer = relationship("Customer", foreign_keys=[from_customer_id], back_populates="outgoing_handovers")
    to_customer = relationship("Customer", foreign_keys=[to_customer_id], back_populates="incoming_handovers")

    __table_args__ = (
        Index("ix_handovers_tenant_status", "tenant_id", "status"),
        Index("ix_handovers_property", "property_id"),
        Index("ix_handovers_from", "from_customer_id"),
        Index("ix_handovers_to", "to_customer_id"),
        Index("ix_handovers_scheduled", "scheduled_date"),
    )


# ---------------------------------------------------------------------------
# Customer Note
# ---------------------------------------------------------------------------

class CustomerNote(Base):
    __tablename__ = "customer_notes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    customer: Mapped["Customer"] = relationship(back_populates="notes")


# ---------------------------------------------------------------------------
# Customer Tag
# ---------------------------------------------------------------------------

class CustomerTag(Base):
    __tablename__ = "customer_tags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    tag: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    customer: Mapped["Customer"] = relationship(back_populates="tags")

    __table_args__ = (
        Index("ix_customer_tags_unique", "tenant_id", "customer_id", "tag", unique=True),
    )


# ---------------------------------------------------------------------------
# Lead
# ---------------------------------------------------------------------------

class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    coverage_area: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    interested_package: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    # Plain string, not the LEAD_STATUS Postgres enum: the `leads` table is shared
    # with services.sales (deals/quotes FK into it), which writes uppercase status
    # values ('NEW', 'CONVERTED', ...) — a strict enum column would reject those.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    coverage_check_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    converted_customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_leads_tenant_status", "tenant_id", "status"),
    )


# ---------------------------------------------------------------------------
# Segment
# ---------------------------------------------------------------------------

class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    auto_refresh: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Activity Timeline
# ---------------------------------------------------------------------------

class ActivityEvent(Base):
    """Generic timeline event for a customer."""

    __tablename__ = "activity_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_activity_events_customer", "tenant_id", "customer_id", "created_at"),
    )
