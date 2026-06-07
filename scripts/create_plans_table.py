"""Plans reference table and Subscription FK migration patch.

This creates a `plans` table that serves as the authoritative mapping
between plan names (used in billing) and inventory products.
Each plan maps to exactly one product SKU, enabling:
  - Revenue reporting by product
  - Stock-aware subscription management
  - Plan price changes that propagate correctly

Run this as a standalone script to add the plans table to Supabase:
  PYTHONPATH=/opt/data/workspace/omnidome .venv/bin/python scripts/create_plans_table.py
"""
import asyncio
import os
from decimal import Decimal

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import uuid


class Base(DeclarativeBase):
    pass


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )

    # Plan identity
    plan_code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Link to inventory product
    product_sku: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("inventory_products.sku", ondelete="SET NULL"), nullable=True
    )

    # Pricing
    base_price_zar: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    billing_interval: Mapped[str] = mapped_column(
        String(20), nullable=False, default="monthly"
    )  # monthly, quarterly, semi_annual, annual

    # Speed profile (for FTTH plans)
    download_speed_mbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    upload_speed_mbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)

    # Metadata
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB_from_sqlalchemy := None)

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "plan_code", name="uq_plans_tenant_code"),
    )


async def main():
    # Load .env
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

    from urllib.parse import quote, unquote
    from sqlalchemy.engine import make_url

    raw = os.environ.get("DATABASE_URL", "")
    url = make_url(raw)
    safe = quote(unquote(url.password or ""), safe="")
    async_url = f"postgresql+asyncpg://{url.username}:{safe}@{url.host}:{url.port}/{url.database}"

    engine = create_async_engine(async_url, pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print(f"✅ plans table created in Supabase ({url.host})")

    # Verify
    from sqlalchemy import text
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'plans'"
        ))
        row = result.fetchone()
        if row:
            print(f"   Verified: {row[0]} exists")
        else:
            print("   ⚠️  Table not found — check connection")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
