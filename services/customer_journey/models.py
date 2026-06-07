"""Customer Journey service — unified data model for the fiber customer lifecycle.

Owns cross-cutting tables that span multiple services:
- coverage_areas: FNO coverage by geography
- orders / order_items: full order lifecycle
- delivery_tracking: courier and delivery status
- technician_visits: dispatch, GPS tracking, completion
- activity_timeline: unified customer event log
- promotions / customer_promotions: promo codes, referrals
- announcements: service notifications by area/segment
- customer_addresses: service + physical addresses with GPS
- payment_methods: stored payment instruments
"""

import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum as SAEnum, ForeignKey,
    Index, Integer, Numeric, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ════════════════════════════════════════════════════════════════════════
# ENUMS
# ════════════════════════════════════════════════════════════════════════

COVERAGE_STATUS = SAEnum(
    "available", "coming_soon", "unavailable", "construction",
    name="coverage_status", create_type=True,
)

FNO_TECHNOLOGY = SAEnum(
    "FTTH", "FTTB", "LTE", "5G", "fixed_wireless",
    name="fno_technology", create_type=True,
)

ORDER_STATUS = SAEnum(
    "cart", "pending", "confirmed", "processing", "shipped",
    "delivered", "installed", "completed", "cancelled", "refunded",
    name="order_status", create_type=True,
)

ORDER_ITEM_TYPE = SAEnum(
    "package", "hardware", "vas", "installation", "delivery",
    name="order_item_type", create_type=True,
)

DELIVERY_STATUS = SAEnum(
    "pending", "courier_assigned", "picked_up", "in_transit",
    "out_for_delivery", "delivered", "failed", "returned",
    name="delivery_status", create_type=True,
)

TECH_VISIT_STATUS = SAEnum(
    "scheduled", "dispatched", "en_route", "on_site",
    "in_progress", "completed", "cancelled", "no_access", "rescheduled",
    name="tech_visit_status", create_type=True,
)

TECH_VISIT_TYPE = SAEnum(
    "installation", "repair", "maintenance", "survey",
    "move_house_install", "router_collection", "fiber_repair",
    name="tech_visit_type", create_type=True,
)

PROMO_TYPE = SAEnum(
    "percentage_discount", "fixed_discount", "free_months",
    "referral_bonus", "loyalty_reward", "bundle_deal",
    name="promo_type", create_type=True,
)

PROMO_STATUS = SAEnum(
    "active", "paused", "expired", "depleted",
    name="promo_status", create_type=True,
)

ANNOUNCEMENT_TYPE = SAEnum(
    "outage", "maintenance", "promotion", "general", "urgent",
    name="announcement_type", create_type=True,
)

ANNOUNCEMENT_AUDIENCE = SAEnum(
    "all", "area", "segment", "individual",
    name="announcement_audience", create_type=True,
)

CONTACT_CHANNEL = SAEnum(
    "sms", "whatsapp", "email", "push", "phone",
    name="contact_channel", create_type=True,
)


# ════════════════════════════════════════════════════════════════════════
# BASE
# ════════════════════════════════════════════════════════════════════════

class Base(DeclarativeBase):
    pass


# ════════════════════════════════════════════════════════════════════════
# COVERAGE AREAS
# ════════════════════════════════════════════════════════════════════════

class CoverageArea(Base):
    __tablename__ = "coverage_areas"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # FNO details
    fno_name: Mapped[str] = mapped_column(String(100), nullable=False)
    technology: Mapped[str] = mapped_column(FNO_TECHNOLOGY, nullable=False)

    # Geography
    area_name: Mapped[str] = mapped_column(String(200), nullable=False)
    suburb: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    province: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    gps_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    gps_lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)
    geo_boundary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # GeoJSON polygon

    # Availability
    status: Mapped[str] = mapped_column(COVERAGE_STATUS, nullable=False, default="available")
    max_speed_mbps: Mapped[int] = mapped_column(Integer, default=1000)
    available_packages: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    estimated_install_days: Mapped[int] = mapped_column(Integer, default=14)

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_coverage_fno", "fno_name", "technology"),
        Index("ix_coverage_city", "city", "suburb"),
        Index("ix_coverage_postal", "postal_code"),
        Index("ix_coverage_status", "status"),
    )


# ════════════════════════════════════════════════════════════════════════
# CUSTOMER ADDRESSES
# ════════════════════════════════════════════════════════════════════════

class CustomerAddress(Base):
    __tablename__ = "customer_addresses"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    address_type: Mapped[str] = mapped_column(String(20), nullable=False, default="service")  # service, physical, billing
    line1: Mapped[str] = mapped_column(String(255), nullable=False)
    line2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    province: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    gps_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    gps_lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)
    coverage_area_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_cust_addr_customer", "customer_id", "address_type"),
    )


# ════════════════════════════════════════════════════════════════════════
# PAYMENT METHODS
# ════════════════════════════════════════════════════════════════════════

class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    method_type: Mapped[str] = mapped_column(String(20), nullable=False)  # card, bank_account, paystack
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # paystack, stripe
    token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # encrypted token
    last_four: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    card_brand: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # visa, mastercard
    expiry_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expiry_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bank_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    account_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # cheque, savings
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_paymethods_customer", "customer_id", "is_active"),
    )


# ════════════════════════════════════════════════════════════════════════
# ORDERS
# ════════════════════════════════════════════════════════════════════════

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    account_number: Mapped[str] = mapped_column(String(50), nullable=False)

    order_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(ORDER_STATUS, nullable=False, default="cart")

    # Addresses
    service_address_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    billing_address_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Totals
    subtotal_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    vat_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    discount_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    # Payment
    payment_method_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")
    payment_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Promotion
    promotion_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    promo_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Contact preference
    preferred_contact_channel: Mapped[str] = mapped_column(CONTACT_CHANNEL, default="sms")
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Notes
    customer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    internal_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_orders_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_number", "order_number"),
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)

    item_type: Mapped[str] = mapped_column(ORDER_ITEM_TYPE, nullable=False)
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("inventory_products.id", ondelete="SET NULL"), nullable=True)
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_price_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # For packages
    package_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    monthly_recurring_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    once_off_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    # For hardware
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    imei: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_order_items_order", "order_id"),
        Index("ix_order_items_product", "product_id"),
    )


# ════════════════════════════════════════════════════════════════════════
# DELIVERY TRACKING
# ════════════════════════════════════════════════════════════════════════

class DeliveryTracking(Base):
    __tablename__ = "delivery_tracking"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)

    # Courier
    courier: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tracking_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    courier_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Status
    status: Mapped[Optional[str]] = mapped_column(DELIVERY_STATUS, nullable=True, default="pending")

    # Address
    delivery_address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    delivery_address_line2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    delivery_city: Mapped[str] = mapped_column(String(100), nullable=False)
    delivery_postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    delivery_gps_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    delivery_gps_lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)

    # Scheduling
    scheduled_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    scheduled_time_slot: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # "08:00-12:00"
    estimated_delivery: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Actual
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_by: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    signature_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Contact
    recipient_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    recipient_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Notes
    delivery_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_delivery_order", "order_id"),
        Index("ix_delivery_tracking_no", "tracking_number"),
        Index("ix_delivery_status", "status"),
    )


# ════════════════════════════════════════════════════════════════════════
# TECHNICIAN VISITS
# ════════════════════════════════════════════════════════════════════════

class TechnicianVisit(Base):
    __tablename__ = "technician_visits"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    ticket_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    visit_type: Mapped[str] = mapped_column(TECH_VISIT_TYPE, nullable=False, default="installation")
    status: Mapped[str] = mapped_column(TECH_VISIT_STATUS, nullable=False, default="scheduled")

    # Scheduling
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_time_slot: Mapped[str] = mapped_column(String(50), nullable=False)  # "08:00-12:00", "12:00-16:00", "16:00-20:00"
    estimated_duration_minutes: Mapped[int] = mapped_column(Integer, default=120)

    # Address
    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    gps_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    gps_lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)

    # Technician
    technician_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    technician_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    technician_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # GPS Tracking
    dispatch_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    en_route_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    on_site_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_gps_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    current_gps_lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)
    last_gps_update: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Work details
    work_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    work_completed: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parts_used: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    photos: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)  # URLs

    # Customer interaction
    customer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    customer_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5
    customer_signature_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # FNO
    fno_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fno_ticket_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Reschedule tracking
    reschedule_count: Mapped[int] = mapped_column(Integer, default=0)
    original_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_tech_visits_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_tech_visits_technician", "technician_id", "scheduled_date"),
        Index("ix_tech_visits_status", "status"),
        Index("ix_tech_visits_date", "scheduled_date"),
        Index("ix_tech_visits_order", "order_id"),
        Index("ix_tech_visits_ticket", "ticket_id"),
    )


# ════════════════════════════════════════════════════════════════════════
# ACTIVITY TIMELINE
# ════════════════════════════════════════════════════════════════════════

class ActivityTimeline(Base):
    __tablename__ = "activity_timeline"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    account_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Event classification
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    # lead_created, order_placed, order_confirmed, delivery_scheduled, delivery_completed,
    # installation_scheduled, installation_completed, subscription_activated,
    # payment_received, invoice_sent, ticket_created, ticket_resolved,
    # pause_requested, pause_activated, move_house_initiated, move_house_completed,
    # cancellation_requested, cancellation_completed, retention_offered, retention_accepted,
    # promotion_applied, referral_made, announcement_sent, note_added

    event_category: Mapped[str] = mapped_column(String(30), nullable=False)
    # sales, billing, support, fulfillment, lifecycle, marketing, system

    # Content
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Source
    source_service: Mapped[str] = mapped_column(String(50), nullable=False)  # crm, sales, billing, support, etc.
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)  # ID in source service
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)  # user who triggered
    actor_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # customer, agent, system

    # Related entities
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    ticket_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_timeline_customer", "tenant_id", "customer_id", "created_at"),
        Index("ix_timeline_type", "tenant_id", "event_type"),
        Index("ix_timeline_category", "tenant_id", "event_category"),
        Index("ix_timeline_source", "source_service", "source_id"),
    )


# ════════════════════════════════════════════════════════════════════════
# PROMOTIONS
# ════════════════════════════════════════════════════════════════════════

class Promotion(Base):
    __tablename__ = "promotions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    promo_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, unique=True)

    promo_type: Mapped[str] = mapped_column(PROMO_TYPE, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # percentage_discount: {"percent": 15, "max_discount_zar": 500}
    # fixed_discount: {"amount_zar": 200}
    # free_months: {"months": 2}
    # referral_bonus: {"referrer_discount_zar": 100, "referee_discount_zar": 100, "max_referrals": 10}

    # Limits
    max_total_redemptions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_redemptions: Mapped[int] = mapped_column(Integer, default=0)
    max_per_customer: Mapped[int] = mapped_column(Integer, default=1)

    # Validity
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Targeting
    target_segments: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    target_packages: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)

    status: Mapped[str] = mapped_column(PROMO_STATUS, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_promos_tenant_status", "tenant_id", "status"),
        Index("ix_promos_code", "promo_code"),
        Index("ix_promos_valid", "valid_from", "valid_until"),
    )


class CustomerPromotion(Base):
    __tablename__ = "customer_promotions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    promotion_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("promotions.id", ondelete="CASCADE"), nullable=False)

    # Usage
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    discount_applied_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    # Referral tracking
    referred_by_customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    referral_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_cust_promos_customer", "customer_id"),
        Index("ix_cust_promos_promo", "promotion_id"),
    )


# ════════════════════════════════════════════════════════════════════════
# ANNOUNCEMENTS
# ════════════════════════════════════════════════════════════════════════

class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    announcement_type: Mapped[str] = mapped_column(ANNOUNCEMENT_TYPE, nullable=False, default="general")
    audience: Mapped[str] = mapped_column(ANNOUNCEMENT_AUDIENCE, nullable=False, default="all")

    # Targeting
    target_areas: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)  # area names
    target_segments: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)  # customer segments
    target_customer_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)

    # Channels
    channels: Mapped[list] = mapped_column(JSONB, nullable=False, default=["sms"])  # sms, whatsapp, email, push

    # Scheduling
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    delivered_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_announcements_tenant_type", "tenant_id", "announcement_type"),
        Index("ix_announcements_active", "tenant_id", "is_active"),
    )


# ════════════════════════════════════════════════════════════════════════
# STORE: HARDWARE + VAS
# ════════════════════════════════════════════════════════════════════════

class StoreCategory(Base):
    """Product category for the store (hardware, VAS, accessories)."""
    __tablename__ = "store_categories"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    icon_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_store_cat_tenant", "tenant_id", "slug", unique=True),
        Index("ix_store_cat_parent", "parent_id"),
    )


class StoreProduct(Base):
    """Sellable product — hardware (routers, ONTs) or VAS (static IP, antivirus, etc.)."""
    __tablename__ = "store_products"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Classification
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    short_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    product_type: Mapped[str] = mapped_column(String(20), nullable=False)  # hardware, vas, accessory
    # hardware: router, ont, cable, mesh_node
    # vas: static_ip, antivirus, parental_control, cloud_storage, vpn
    # accessory: ethernet_cable, power_adapter, wall_bracket

    # Pricing
    once_off_price_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    monthly_price_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    # once_off_price_zar: for hardware purchases
    # monthly_price_zar: for VAS recurring charges

    # Inventory
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5)
    track_inventory: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_backorder: Mapped[bool] = mapped_column(Boolean, default=False)

    # Attributes
    image_urls: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    specs: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default=dict)
    # e.g. {"Manufacturer": "TP-Link", "Model": "Archer AX55", "Speed": "AX3000", "Ports": 4}

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Subscription link (for VAS that requires a base subscription)
    requires_subscription: Mapped[bool] = mapped_column(Boolean, default=False)
    compatible_packages: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_store_prod_tenant_sku", "tenant_id", "sku", unique=True),
        Index("ix_store_prod_tenant_slug", "tenant_id", "slug"),
        Index("ix_store_prod_tenant_category", "tenant_id", "category_id"),
        Index("ix_store_prod_tenant_type", "tenant_id", "product_type"),
        Index("ix_store_prod_active", "tenant_id", "is_active"),
        Index("ix_store_prod_featured", "tenant_id", "is_featured"),
    )


class ShoppingCart(Base):
    """Active shopping cart per customer. One cart per customer."""
    __tablename__ = "shopping_carts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Cart status
    status: Mapped[str] = mapped_column(String(20), default="active")
    # active, converted_to_order, abandoned, expired

    # Summary (denormalized for quick reads)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    subtotal_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    discount_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    # Promotion
    promo_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    promotion_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Expiry (abandonment handling)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_cart_tenant_customer", "tenant_id", "customer_id", unique=True),
        Index("ix_cart_status", "status"),
        Index("ix_cart_expires", "expires_at"),
    )


class ShoppingCartItem(Base):
    """Line item in a shopping cart."""
    __tablename__ = "shopping_cart_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cart_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("shopping_carts.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    product_type: Mapped[str] = mapped_column(String(20), nullable=False)  # hardware, vas, accessory

    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_price_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Snapshot of product at time of add
    product_name_snapshot: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    product_sku_snapshot: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # VAS-specific: link to subscription being added to
    target_subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_cart_item_cart", "cart_id"),
        Index("ix_cart_item_product", "product_id"),
        UniqueConstraint("cart_id", "product_id", "target_subscription_id", name="uq_cart_item"),
    )


class StoreWishlist(Base):
    """Customer wishlist for store products."""
    __tablename__ = "store_wishlists"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_wishlist_tenant_customer", "tenant_id", "customer_id"),
        UniqueConstraint("customer_id", "product_id", name="uq_wishlist_item"),
    )


class ProductReview(Base):
    """Customer product reviews for store items."""
    __tablename__ = "product_reviews"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_verified_purchase: Mapped[bool] = mapped_column(Boolean, default=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_review_product", "product_id", "is_published"),
        Index("ix_review_customer", "customer_id"),
        UniqueConstraint("customer_id", "product_id", "order_id", name="uq_review"),
    )


class StoreBundle(Base):
    """Product bundles (e.g. 'Complete WiFi Package' = router + mesh node + installation)."""
    __tablename__ = "store_bundles"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Pricing
    total_once_off_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_monthly_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    bundle_discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_bundle_tenant_active", "tenant_id", "is_active"),
    )


class StoreBundleItem(Base):
    """Products within a bundle."""
    __tablename__ = "store_bundle_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bundle_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("store_bundles.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    quantity: Mapped[int] = mapped_column(Integer, default=1)
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)  # optional add-on

    __table_args__ = (
        Index("ix_bundle_item_bundle", "bundle_id"),
        UniqueConstraint("bundle_id", "product_id", name="uq_bundle_item"),
    )


# ════════════════════════════════════════════════════════════════════════
# RICA INTEGRATION FLOWS
# ════════════════════════════════════════════════════════════════════════

class RicaFlow(Base):
    """Orchestrates RICA verification within the customer journey.
    
    Tracks the end-to-end RICA flow: trigger → session creation → 
    verification → result → post-verification actions.
    """
    __tablename__ = "rica_flows"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    account_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Source of the RICA trigger
    trigger_source: Mapped[str] = mapped_column(String(30), nullable=False)
    # order_placed, manual, admin, self_service, bulk_import
    source_order_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Personal info (captured at time of RICA)
    id_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Address (for RICA proof of address)
    physical_address_line1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    physical_address_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    physical_address_postal_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Smile ID integration
    smile_id_job_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    smile_id_partner_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Verification status
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    # pending, session_created, in_progress, completed, failed, expired, manual_review

    # Result
    result_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    result_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_type: Mapped[str] = mapped_column(String(50), default="DOCUMENT_VERIFICATION")

    # Document info
    document_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # south_african_id, passport, smart_id
    document_country: Mapped[str] = mapped_column(String(5), default="ZA")

    # Post-verification actions
    auto_activate: Mapped[bool] = mapped_column(Boolean, default=True)
    activation_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    activation_order_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Failure handling
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    last_failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # RICA regulation tracking
    rica_regulation: Mapped[str] = mapped_column(String(50), default="RICA_2002")
    proof_of_address_provided: Mapped[bool] = mapped_column(Boolean, default=False)
    proof_of_address_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # utility_bank_statement, lease_agreement, municipal_account

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_rica_flow_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_rica_flow_tenant_status", "tenant_id", "status"),
        Index("ix_rica_flow_smile_job", "smile_id_job_id"),
        Index("ix_rica_flow_order", "source_order_id"),
        Index("ix_rica_flow_id_number", "id_number"),
    )


class RicaFlowEvent(Base):
    """Audit trail of every event in a RICA flow."""
    __tablename__ = "rica_flow_events"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rica_flow_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("rica_flows.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # flow_created, session_initiated, callback_received, verification_completed,
    # verification_failed, retry_scheduled, manual_review_needed, activation_triggered

    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    source: Mapped[str] = mapped_column(String(30), nullable=False)
    # rica_service, callback, customer_journey, cron, manual

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_rica_event_flow", "rica_flow_id", "created_at"),
        Index("ix_rica_event_type", "tenant_id", "event_type"),
    )


class RicaBulkImport(Base):
    """Bulk RICA import batch for migrating existing customers."""
    __tablename__ = "rica_bulk_imports"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Import details
    filename: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending, processing, completed, failed

    # Error log
    error_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_rica_bulk_tenant", "tenant_id", "status"),
    )
