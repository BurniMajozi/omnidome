"""Database models for protocol persistence — UCP checkout sessions, AP2 mandates, and payment receipts."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    Boolean,
)
from sqlalchemy.dialects.postgresql import JSONB

from services.common.db import Base


class UCPCheckoutSessionRecord(Base):
    """Persisted UCP checkout session."""
    __tablename__ = "ucp_checkout_sessions"

    # Override Base.id to use UUID default
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(String(20), nullable=False, default="created")
    currency = Column(String(3), nullable=False, default="ZAR")
    total = Column(Float, nullable=False)
    merchant = Column(String(200), nullable=False)
    purpose = Column(String(500), nullable=False)
    line_items = Column(JSONB, nullable=False, default=[])
    payment_mandate_id = Column(String(200), nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=False, default={})


class AP2IntentMandateRecord(Base):
    """Persisted AP2 intent mandate."""
    __tablename__ = "ap2_intent_mandates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    natural_language_description = Column(Text, nullable=False)
    merchants = Column(JSONB, nullable=False, default=[])
    max_amount = Column(Float, nullable=False)
    currency = Column(String(3), nullable=False, default="ZAR")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    requires_user_confirmation = Column(Boolean, nullable=False, default=True)
    signed = Column(Boolean, nullable=False, default=False)
    metadata_ = Column("metadata", JSONB, nullable=False, default={})


class AP2PaymentMandateRecord(Base):
    """Persisted AP2 payment mandate."""
    __tablename__ = "ap2_payment_mandates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    intent_mandate_id = Column(String(36), nullable=False)
    payment_details_id = Column(String(200), nullable=False)
    merchant_agent = Column(String(200), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), nullable=False, default="ZAR")
    label = Column(String(500), nullable=False)
    signed_authorization = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending_signature")
    metadata_ = Column("metadata", JSONB, nullable=False, default={})


class AP2PaymentReceiptRecord(Base):
    """Persisted AP2 payment receipt."""
    __tablename__ = "ap2_payment_receipts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    payment_mandate_id = Column(String(36), nullable=False)
    payment_id = Column(String(200), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), nullable=False, default="ZAR")
    merchant_confirmation_id = Column(String(200), nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=False, default={})
