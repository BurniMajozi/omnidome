"""Inventory service database layer — SQLAlchemy async models and session management.

Full stock pipeline:
  Supplier → PurchaseOrder → GoodsReceipt → Warehouse → TechnicianStock → Customer
  Product hierarchy: ServiceType → Category → Range → Product (SKU)
  Pricing: base cost, markup, markdowns, promotional pricing
  Visibility: StockMovement audit trail across all pipeline stages
"""
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import AsyncGenerator, Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Computed, Date, DateTime, Enum as SAEnum, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint, func, select, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from services.common.db import get_async_engine, SoftDeleteMixin


class Base(DeclarativeBase):
    pass


# ════════════════════════════════════════════════════════════════════════
# ENUMERIES
# ════════════════════════════════════════════════════════════════════════

MOVEMENT_TYPE = SAEnum(
    "purchase_receipt",      # Supplier → Warehouse (goods received)
    "warehouse_transfer",    # Warehouse → Warehouse
    "technician_dispatch",   # Warehouse → Technician (van stock)
    "technician_return",     # Technician → Warehouse (unused stock)
    "customer_dispatch",     # Technician → Customer (installation)
    "customer_return",       # Customer → Technician/Warehouse (RMA)
    "adjustment",            # Inventory adjustment (count, damage, etc.)
    "write_off",             # Stock written off
    name="stock_movement_type", create_type=True,
)

# Purchase-order status is a plain VARCHAR(30) (it was the Postgres enum ``po_status``; the startup
# migration converts live columns). The state machine lives in routes/purchasing.py (PO_STATES).
# draft | pending_approval | approved | rejected | sent | partially_received | received | cancelled

GR_STATUS = SAEnum(
    "pending", "received", "inspected", "accepted", "rejected", "partially_accepted",
    name="gr_status", create_type=True,
)

TECH_STOCK_STATUS = SAEnum(
    "in_transit", "with_technician", "returned", "consumed",
    name="tech_stock_status", create_type=True,
)

PRICING_TYPE = SAEnum(
    "base", "markup", "markdown", "promotional", "clearance", "bundle",
    name="pricing_type", create_type=True,
)


# ════════════════════════════════════════════════════════════════════════
# 3-LEVEL PRODUCT HIERARCHY: Service → Category → Range → SKU
# ════════════════════════════════════════════════════════════════════════

class ServiceType(Base):
    """Level 1: Main service offering (Fibre, LTE, 5G, Fixed Wireless)."""
    __tablename__ = "inventory_service_types"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    code: Mapped[str] = mapped_column(String(50), nullable=False)  # fibre, lte, 5g, fw
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # "Fibre", "LTE", "5G"
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon: Mapped[Optional[str]] = mapped_column(String(64))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    categories = relationship("ProductCategory", back_populates="service_type", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_service_type_tenant_code"),
    )


class ProductCategory(Base):
    """Level 2: Billing category within a service (Prepaid Fibre, Postpaid Fibre)."""
    __tablename__ = "inventory_product_categories"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    service_type_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_service_types.id", ondelete="CASCADE"), nullable=False
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)  # prepaid_fibre, postpaid_fibre
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # "Prepaid Fibre", "Postpaid Fibre"
    description: Mapped[Optional[str]] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    service_type = relationship("ServiceType", back_populates="categories")
    ranges = relationship("ProductRange", back_populates="category", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_prod_category_tenant_code"),
    )


class ProductRange(Base):
    """Level 3: Speed/download range within a category (10Mbps, 50Mbps, 100Mbps, 1Gbps)."""
    __tablename__ = "inventory_product_ranges"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_product_categories.id", ondelete="CASCADE"), nullable=False
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)  # 10mbps, 50mbps, 1gbps
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # "10 Mbps", "100 Mbps", "1 Gbps"
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Speed profile
    download_speed_mbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    upload_speed_mbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_symmetrical: Mapped[bool] = mapped_column(Boolean, default=False)

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    category = relationship("ProductCategory", back_populates="ranges")
    products = relationship("Product", back_populates="range")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_prod_range_tenant_code"),
    )


# ════════════════════════════════════════════════════════════════════════
# PRODUCT (SKU Level)
# ════════════════════════════════════════════════════════════════════════

class Product(Base):
    """Level 4: Individual SKU (10/10 symmetrical ONT, 10/5 asymmetric router)."""
    __tablename__ = "inventory_products"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Hierarchy links
    range_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_product_ranges.id", ondelete="SET NULL"), nullable=True
    )
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_product_categories.id", ondelete="SET NULL"), nullable=True
    )
    service_type_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_service_types.id", ondelete="SET NULL"), nullable=True
    )

    # SKU identity
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    barcode: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    unit_of_measure: Mapped[str] = mapped_column(String(20), default="EA")
    weight_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 3))

    # Supplier link
    preferred_supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_suppliers.id", ondelete="SET NULL"), nullable=True
    )

    # Pricing (base)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    rrp: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    markup_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_serialized: Mapped[bool] = mapped_column(Boolean, default=False)  # track individual serial numbers

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_inventory_products_tenant_sku"),
    )

    # Relationships
    range = relationship("ProductRange", back_populates="products")
    category = relationship("ProductCategory")
    service_type = relationship("ServiceType")
    preferred_supplier = relationship("Supplier", back_populates="products")
    inventory_levels = relationship("InventoryLevel", back_populates="product", cascade="all, delete-orphan")
    stock_movements = relationship("StockMovement", back_populates="product", cascade="all, delete-orphan")
    pricing_rules = relationship("PricingRule", back_populates="product", cascade="all, delete-orphan")
    technician_stocks = relationship("TechnicianStock", back_populates="product", cascade="all, delete-orphan")
    purchase_order_items = relationship("PurchaseOrderItem", back_populates="product")
    goods_receipt_items = relationship("GoodsReceiptItem", back_populates="product")
    package_items = relationship("PackageItem", back_populates="product", cascade="all, delete-orphan")


# ════════════════════════════════════════════════════════════════════════
# PRICING ENGINE
# ════════════════════════════════════════════════════════════════════════

class PricingRule(Base):
    """Markdowns, promotional prices, clearance, bundle pricing per product or package."""
    __tablename__ = "inventory_pricing_rules"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Target: either a product or a package (one must be set)
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_products.id", ondelete="CASCADE"), nullable=True
    )
    package_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_packages.id", ondelete="CASCADE"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    pricing_type: Mapped[str] = mapped_column(PRICING_TYPE, nullable=False, default="base")

    # Price override
    price_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    discount_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    markup_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)

    # Validity
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Scope
    min_quantity: Mapped[int] = mapped_column(Integer, default=1)
    max_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    segment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Priority (higher = takes precedence)
    priority: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    product = relationship("Product", back_populates="pricing_rules")
    package = relationship("Package", back_populates="pricing_rules")

    __table_args__ = (
        Index("ix_pricing_rules_tenant_product", "tenant_id", "product_id"),
        Index("ix_pricing_rules_tenant_package", "tenant_id", "package_id"),
        Index("ix_pricing_rules_valid", "valid_from", "valid_to"),
    )


# ════════════════════════════════════════════════════════════════════════
# PACKAGE (Bundle) — sellable product that contains multiple hardware items
# ════════════════════════════════════════════════════════════════════════

PACKAGE_TYPE = SAEnum(
    "fibre_bundle",      # Fibre package with router, ONT, etc.
    "lte_bundle",        # LTE package with router, SIM, etc.
    "hardware_only",     # Standalone hardware (no service)
    "add_on",            # Add-on to existing package (WiFi extender, camera)
    "promotional",       # Promotional bundle (discounted hardware + service)
    name="package_type", create_type=True,
)


class Package(Base):
    """A sellable package/bundle that contains one or more hardware products.

    Examples:
    - "Fibre 100Mbps Home Bundle" → ONT + Router + WiFi Extender
    - "LTE Starter Kit" → LTE Router + SIM Card
    - "Standalone Router" → Just the router (no service)
    - "WiFi Extender Add-on" → Single add-on item

    A package has its own SKU, pricing, and hierarchy placement.
    When sold, the technician dispatches the constituent items from van stock.
    """
    __tablename__ = "inventory_packages"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Hierarchy placement (optional — packages can live in the hierarchy)
    service_type_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_service_types.id", ondelete="SET NULL"), nullable=True
    )
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_product_categories.id", ondelete="SET NULL"), nullable=True
    )
    range_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_product_ranges.id", ondelete="SET NULL"), nullable=True
    )

    # Package identity
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    package_type: Mapped[str] = mapped_column(PACKAGE_TYPE, nullable=False, default="fibre_bundle")

    # Pricing (package-level, may differ from sum of parts)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    rrp: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_sellable_standalone: Mapped[bool] = mapped_column(Boolean, default=True)
    # If False, this package can only be added to an order as part of another package

    # Versioning (product development — track changes to package contents)
    version: Mapped[int] = mapped_column(Integer, default=1)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Null effective_to = current version

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    service_type = relationship("ServiceType")
    category = relationship("ProductCategory")
    range = relationship("ProductRange")
    items = relationship("PackageItem", back_populates="package", cascade="all, delete-orphan")
    pricing_rules = relationship("PricingRule", back_populates="package", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", "version", name="uq_package_tenant_sku_version"),
        Index("ix_packages_tenant_type", "tenant_id", "package_type"),
        Index("ix_packages_hierarchy", "service_type_id", "category_id", "range_id"),
        Index("ix_packages_effective", "effective_from", "effective_to"),
    )


class PackageItem(Base):
    """Constituent items within a package — many-to-many with quantity.

    Example: "Fibre 100Mbps Home Bundle" contains:
    - 1x ONT (product_id: xxx, quantity: 1, is_required: true)
    - 1x Router (product_id: yyy, quantity: 1, is_required: true)
    - 1x WiFi Extender (product_id: zzz, quantity: 1, is_required: false) — optional add-on
    """
    __tablename__ = "inventory_package_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    package_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_packages.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_products.id", ondelete="CASCADE"), nullable=False
    )

    quantity: Mapped[int] = mapped_column(Integer, default=1)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    # If False, this item is optional (customer can choose to include/exclude)

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    package = relationship("Package", back_populates="items")
    product = relationship("Product", back_populates="package_items")

    __table_args__ = (
        UniqueConstraint("package_id", "product_id", name="uq_package_item"),
        Index("ix_package_items_product", "product_id"),
    )


# ════════════════════════════════════════════════════════════════════════
# SUPPLIER
# ════════════════════════════════════════════════════════════════════════

class Supplier(Base, SoftDeleteMixin):
    """Supplier/vendor for stock procurement."""
    __tablename__ = "inventory_suppliers"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    code: Mapped[str] = mapped_column(String(50), nullable=False)  # huawei, tp_link, fs_com
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_person: Mapped[Optional[str]] = mapped_column(String(200))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(30))
    address: Mapped[Optional[str]] = mapped_column(Text)
    tax_id: Mapped[Optional[str]] = mapped_column(String(50))
    payment_terms: Mapped[Optional[str]] = mapped_column(String(100))  # "Net 30", "Net 60"
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7)
    # Optional per-PO spend ceiling (ZAR, incl. VAT). NULL = no limit. Enforced when a PO is submitted.
    spend_limit: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    products = relationship("Product", back_populates="preferred_supplier")
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_supplier_tenant_code"),
    )


# ════════════════════════════════════════════════════════════════════════
# PURCHASE ORDER (Finance places order)
# ════════════════════════════════════════════════════════════════════════

class PurchaseOrder(Base, SoftDeleteMixin):
    """Purchase order for stock procurement — created by finance."""
    __tablename__ = "inventory_purchase_orders"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_warehouses.id", ondelete="RESTRICT"), nullable=False
    )

    po_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")

    # Totals
    subtotal_zar: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    tax_zar: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    total_zar: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))

    # Dates
    order_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    expected_delivery: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="ZAR")

    # Actor
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    submitted_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_mode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)   # manual | auto
    approval_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)    # sha256 of what was approved
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Dispatch to the supplier
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_to: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    sent_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    send_claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    send_idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # dedicated send replay key
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    supplier = relationship("Supplier", back_populates="purchase_orders")
    warehouse = relationship("Warehouse", back_populates="purchase_orders")
    items = relationship("PurchaseOrderItem", back_populates="purchase_order", cascade="all, delete-orphan")
    goods_receipts = relationship("GoodsReceipt", back_populates="purchase_order")

    __table_args__ = (
        UniqueConstraint("tenant_id", "po_number", name="uq_po_tenant_number"),
        Index("ix_po_tenant_status", "tenant_id", "status"),
        Index("ix_po_supplier", "supplier_id"),
    )


class PurchaseOrderItem(Base):
    """Line items on a purchase order."""
    __tablename__ = "inventory_purchase_order_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    po_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_purchase_orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_products.id", ondelete="RESTRICT"), nullable=False
    )

    quantity_ordered: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_received: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_cost_zar: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    purchase_order = relationship("PurchaseOrder", back_populates="items")
    product = relationship("Product", back_populates="purchase_order_items")

    __table_args__ = (
        Index("ix_poi_po", "po_id"),
        Index("ix_poi_product", "product_id"),
    )


# ════════════════════════════════════════════════════════════════════════
# GOODS RECEIPT (Stock controller receives from supplier)
# ════════════════════════════════════════════════════════════════════════

class GoodsReceipt(Base):
    """Goods receipt — stock controller receives stock from supplier into warehouse."""
    __tablename__ = "inventory_goods_receipts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    po_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_purchase_orders.id", ondelete="SET NULL"), nullable=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_warehouses.id", ondelete="RESTRICT"), nullable=False
    )

    gr_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(GR_STATUS, nullable=False, default="pending")

    # Receipt details
    received_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    inspected_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    inspected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Supplier delivery
    supplier_delivery_note: Mapped[Optional[str]] = mapped_column(String(100))
    supplier_invoice_number: Mapped[Optional[str]] = mapped_column(String(100))
    # Caller-supplied idempotency key: a replay of the same (tenant, PO, receipt_ref) returns the
    # original receipt instead of receiving the goods twice.
    receipt_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # Dedicated idempotency key (Idempotency-Key header, else receipt_ref); never overloads other fields.
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    value_ex_vat_zar: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    vat_zar: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))

    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    purchase_order = relationship("PurchaseOrder", back_populates="goods_receipts")
    warehouse = relationship("Warehouse", back_populates="goods_receipts")
    items = relationship("GoodsReceiptItem", back_populates="goods_receipt", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "gr_number", name="uq_gr_tenant_number"),
        Index("ix_gr_tenant_status", "tenant_id", "status"),
        Index("uq_gr_tenant_po_receipt_ref", "tenant_id", "po_id", "receipt_ref", unique=True,
              postgresql_where=text("receipt_ref IS NOT NULL"), sqlite_where=text("receipt_ref IS NOT NULL")),
        Index("uq_gr_tenant_po_idempotency_key", "tenant_id", "po_id", "idempotency_key", unique=True,
              postgresql_where=text("idempotency_key IS NOT NULL"), sqlite_where=text("idempotency_key IS NOT NULL")),
    )


class GoodsReceiptItem(Base):
    """Line items on a goods receipt."""
    __tablename__ = "inventory_goods_receipt_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gr_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_goods_receipts.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_products.id", ondelete="RESTRICT"), nullable=False
    )

    quantity_ordered: Mapped[int] = mapped_column(Integer, default=0)
    quantity_received: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_accepted: Mapped[int] = mapped_column(Integer, default=0)
    quantity_rejected: Mapped[int] = mapped_column(Integer, default=0)

    unit_cost_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Serialized items
    serial_numbers: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)

    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    goods_receipt = relationship("GoodsReceipt", back_populates="items")
    product = relationship("Product", back_populates="goods_receipt_items")

    __table_args__ = (
        Index("ix_gri_gr", "gr_id"),
        Index("ix_gri_product", "product_id"),
    )


# ════════════════════════════════════════════════════════════════════════
# WAREHOUSE
# ════════════════════════════════════════════════════════════════════════

class Warehouse(Base, SoftDeleteMixin):
    __tablename__ = "inventory_warehouses"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255))
    is_external: Mapped[bool] = mapped_column(Boolean, default=False)
    partner_name: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    inventory_levels = relationship("InventoryLevel", back_populates="warehouse", cascade="all, delete-orphan")
    purchase_orders = relationship("PurchaseOrder", back_populates="warehouse")
    goods_receipts = relationship("GoodsReceipt", back_populates="warehouse")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_warehouse_tenant_code"),
    )


# ════════════════════════════════════════════════════════════════════════
# INVENTORY LEVEL (per warehouse)
# ════════════════════════════════════════════════════════════════════════

class InventoryLevel(Base):
    """Stock of one product in one warehouse.

    Single source of truth: ``soh`` (physical on hand), ``allocated`` (promised to jobs/orders) and
    ``reserved`` (safety stock) are the only stored quantities. ``available`` is a GENERATED column
    (``soh - allocated - reserved``) so it can never drift; never write to it. Every write is a delta
    in SQL (``soh = soh + :n``), never read-modify-write.
    """
    __tablename__ = "inventory_levels"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_warehouses.id", ondelete="CASCADE")
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_products.id", ondelete="CASCADE")
    )

    soh: Mapped[int] = mapped_column(Integer, default=0, nullable=False)           # Stock on hand
    sit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)           # Stock in transit
    allocated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)     # Allocated to orders
    reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)      # Reserved (safety stock)
    available: Mapped[int] = mapped_column(
        Integer, Computed("soh - allocated - reserved", persisted=True)
    )                                                                              # derived, read-only
    min_threshold: Mapped[int] = mapped_column(Integer, default=10)
    max_threshold: Mapped[Optional[int]] = mapped_column(Integer, default=100)
    reorder_point: Mapped[int] = mapped_column(Integer, default=20)
    reorder_quantity: Mapped[int] = mapped_column(Integer, default=50)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    product = relationship("Product", back_populates="inventory_levels")
    warehouse = relationship("Warehouse", back_populates="inventory_levels")

    __table_args__ = (
        UniqueConstraint("warehouse_id", "product_id"),
        Index("uq_inv_level_tenant_wh_product", "tenant_id", "warehouse_id", "product_id", unique=True),
        Index("ix_inv_level_tenant_product", "tenant_id", "product_id"),
        Index("ix_inv_level_low_stock", "tenant_id", "available", "reorder_point"),
        CheckConstraint("soh >= 0", name="ck_inv_level_soh_nonneg"),
        CheckConstraint("allocated >= 0", name="ck_inv_level_allocated_nonneg"),
        CheckConstraint("reserved >= 0", name="ck_inv_level_reserved_nonneg"),
        CheckConstraint("soh >= allocated + reserved", name="ck_inv_level_available_nonneg"),
    )


# ════════════════════════════════════════════════════════════════════════
# TECHNICIAN STOCK (Van Stock)
# ════════════════════════════════════════════════════════════════════════

class TechnicianStock(Base):
    """Stock assigned to a technician's van — for field installations and safety stock."""
    __tablename__ = "inventory_technician_stocks"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    technician_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_products.id", ondelete="CASCADE"), nullable=False
    )
    warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_warehouses.id", ondelete="SET NULL"), nullable=True
    )

    quantity: Mapped[int] = mapped_column(Integer, default=0)
    safety_stock: Mapped[int] = mapped_column(Integer, default=0)  # minimum to keep in van
    status: Mapped[str] = mapped_column(TECH_STOCK_STATUS, nullable=False, default="with_technician")

    # Dispatch tracking
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    returned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Serialized items
    serial_numbers: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)

    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    product = relationship("Product", back_populates="technician_stocks")

    __table_args__ = (
        Index("ix_tech_stock_tenant_tech", "tenant_id", "technician_id"),
        Index("ix_tech_stock_product", "product_id"),
        Index("ix_tech_stock_status", "status"),
    )


# ════════════════════════════════════════════════════════════════════════
# STOCK MOVEMENT (Full pipeline audit trail)
# ════════════════════════════════════════════════════════════════════════

class StockMovement(Base):
    """Audit trail for every stock movement across the entire pipeline.

    Pipeline stages:
      Supplier → (purchase_receipt) → Warehouse
      Warehouse → (warehouse_transfer) → Warehouse
      Warehouse → (technician_dispatch) → Technician
      Technician → (technician_return) → Warehouse
      Technician → (customer_dispatch) → Customer
      Customer → (customer_return) → Technician/Warehouse
      Any → (adjustment/write_off) → Adjustment
    """
    __tablename__ = "inventory_stock_movements"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_products.id"), nullable=False
    )

    movement_type: Mapped[str] = mapped_column(MOVEMENT_TYPE, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # Source / Destination
    from_location_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # supplier, warehouse, technician, customer
    from_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    to_location_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # References
    po_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_purchase_orders.id", ondelete="SET NULL"), nullable=True
    )
    gr_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_goods_receipts.id", ondelete="SET NULL"), nullable=True
    )
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    technician_visit_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Actor
    performed_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    performed_by_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # stock_controller, finance, technician, system

    # Serialized items
    serial_numbers: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)

    # Idempotency + audit (added by the startup migration for pre-existing tables)
    client_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)   # PO number / job id / ...
    before_soh: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)      # on-hand at the primary location
    after_soh: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dest_before_soh: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # transfers: destination
    dest_after_soh: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    product = relationship("Product", back_populates="stock_movements")

    __table_args__ = (
        Index("uq_stock_move_tenant_client_ref", "tenant_id", "client_ref", unique=True,
              postgresql_where=text("client_ref IS NOT NULL"), sqlite_where=text("client_ref IS NOT NULL")),
        Index("ix_stock_move_tenant", "tenant_id", "created_at"),
        Index("ix_stock_move_product", "product_id", "created_at"),
        Index("ix_stock_move_type", "movement_type"),
        Index("ix_stock_move_from", "from_location_type", "from_location_id"),
        Index("ix_stock_move_to", "to_location_type", "to_location_id"),
    )


# ════════════════════════════════════════════════════════════════════════
# STOCK PIPELINE VISIBILITY (Dashboard/Aggregation)
# ════════════════════════════════════════════════════════════════════════

class StockPipelineSnapshot(Base):
    """Aggregated stock pipeline visibility — refreshed periodically for dashboards.

    Shows stock at each pipeline stage per product per tenant.
    """
    __tablename__ = "inventory_pipeline_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_products.id", ondelete="CASCADE"), nullable=False
    )
    warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_warehouses.id", ondelete="SET NULL"), nullable=True
    )

    # Pipeline stage quantities
    at_supplier: Mapped[int] = mapped_column(Integer, default=0)       # Ordered, not yet received
    in_transit: Mapped[int] = mapped_column(Integer, default=0)         # Received, not yet inspected
    in_warehouse: Mapped[int] = mapped_column(Integer, default=0)       # Available in warehouse
    with_technicians: Mapped[int] = mapped_column(Integer, default=0)   # Dispatched to vans
    at_customer: Mapped[int] = mapped_column(Integer, default=0)        # Installed at customer
    in_return: Mapped[int] = mapped_column(Integer, default=0)          # RMA / return pipeline

    # Financial
    total_value_zar: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))

    # Snapshot metadata
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    product = relationship("Product")

    __table_args__ = (
        Index("ix_pipeline_tenant_date", "tenant_id", "snapshot_date"),
        Index("ix_pipeline_product", "product_id"),
    )


# ════════════════════════════════════════════════════════════════════════
# SETTINGS / APPROVALS / FINANCE OUTBOX
# ════════════════════════════════════════════════════════════════════════

class InventorySettings(Base):
    """Per-tenant inventory settings. ``auto_approve_limit`` (ZAR incl. VAT): purchase orders whose
    total is at or below it skip human approval; 0 (default) disables auto-approval."""
    __tablename__ = "inventory_settings"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    auto_approve_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("tenant_id", name="uq_inventory_settings_tenant"),)


class PurchaseOrderApproval(Base):
    """Immutable record of each approve/reject decision, with the approver's drawn signature and a
    hash of exactly what was decided on (supplier, currency, lines). Auto-approvals are recorded too
    (signature_data NULL, signer_name 'auto-approval')."""
    __tablename__ = "purchase_order_approvals"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    po_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_purchase_orders.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(10), nullable=False)       # approved | rejected
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")  # manual | auto
    signature_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)       # data:image/png;base64,...
    signer_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    signer_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    po_total_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    po_total_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_po_approvals_po", "po_id", "decided_at"),)


class InventoryFinanceOutbox(Base):
    """Journal entries owed to finance. Written in the SAME transaction as the stock change and
    delivered after commit (mirrors billing_finance_outbox); finance de-duplicates on (source, source_id)."""
    __tablename__ = "inventory_finance_outbox"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")  # pending|sent|failed
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "source_id", name="uq_inventory_outbox_source"),
    )


# ════════════════════════════════════════════════════════════════════════
# DOCUMENT NUMBERING
# ════════════════════════════════════════════════════════════════════════

class InventorySequence(Base):
    """Per-tenant, per-document-type counter for auto-generated reference numbers.

    Same convention as services.billing.database.InvoiceSequence and
    services.finance.database.JournalEntrySequence, generalized across
    doc_type so PO/GR numbering don't need a separate table each.
    """
    __tablename__ = "inventory_sequences"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "po", "gr"
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("tenant_id", "doc_type", name="uq_inventory_sequence_tenant_doctype"),
    )


async def next_sequence_number(session: AsyncSession, tenant_id: uuid.UUID, doc_type: str, prefix: str) -> str:
    """Generate the next sequential reference number for a tenant + doc_type.

    Uses a `FOR UPDATE` lock on the sequence row to prevent duplicates under
    concurrent generation. Format: <prefix>-<TENANT4>-<seq:06d>.
    """
    if session.get_bind().dialect.name == "postgresql":
        # FOR UPDATE cannot lock an absent sequence row on the first request.
        import hashlib
        from sqlalchemy import text
        key = int.from_bytes(hashlib.sha256(f"inventory-sequence:{tenant_id}:{doc_type}".encode()).digest()[:8], "big", signed=True)
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    result = await session.execute(
        select(InventorySequence)
        .where(InventorySequence.tenant_id == tenant_id, InventorySequence.doc_type == doc_type)
        .with_for_update()
    )
    seq = result.scalar_one_or_none()
    if seq is None:
        seq = InventorySequence(tenant_id=tenant_id, doc_type=doc_type, last_number=0)
        session.add(seq)
        await session.flush()

    seq.last_number += 1
    await session.flush()

    short_tenant = str(tenant_id).split("-")[0].upper()[:4]
    return f"{prefix}-{short_tenant}-{seq.last_number:06d}"


# ════════════════════════════════════════════════════════════════════════
# SESSION FACTORY
# ════════════════════════════════════════════════════════════════════════

_session_factory: Optional[async_sessionmaker] = None


def _get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        engine = get_async_engine()
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_tables():
    """Create missing tables and bring pre-existing (legacy-shaped) ones to the ORM shape.

    Delegates to services.inventory.schema: create_all + idempotent statements under a Postgres
    advisory lock, wrapped in run_with_db_retry. Never raises for data problems (duplicates are logged)."""
    from services.inventory.schema import init_schema
    await init_schema(Base)
