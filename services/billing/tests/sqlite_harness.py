"""In-memory SQLite stand-in for billing's Postgres tables, so money logic (idempotency, outbox,
webhook dedupe, credit notes, dunning) runs in the default test suite without TEST_DATABASE_URL.

Postgres-only column types are given SQLite renderings; partial-index WHERE clauses are ignored on
SQLite (the unique indexes become plain unique indexes, which is what the assertions need). Row locks
(FOR UPDATE) are no-ops. DB-gated suites against real Postgres remain the source of truth for those.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@compiles(JSONB, "sqlite")
def _jsonb(type_, compiler, **kw):  # noqa: ANN001
    return "JSON"


@compiles(PG_UUID, "sqlite")
def _uuid(type_, compiler, **kw):  # noqa: ANN001
    return "CHAR(36)"


def make_session_factory():
    from services.billing.models import Base
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def get_session():
        s = factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    return get_session


def patch_sessions(monkeypatch, get_session):
    """Point every billing module that imported get_session at the SQLite one."""
    import importlib
    for name in ("services.billing.database", "services.billing.finance_posting", "services.billing.dunning",
                 "services.billing.contacts", "services.billing.routes.invoices", "services.billing.routes.payments",
                 "services.billing.routes.paystack", "services.billing.routes.subscriptions",
                 "services.billing.routes.collections", "services.billing.routes.reports",
                 "services.billing.routes.finance_outbox", "services.billing.seat_runs"):
        mod = importlib.import_module(name)
        if hasattr(mod, "get_session"):
            monkeypatch.setattr(mod, "get_session", get_session)


def make_invoice(session, tenant_id, *, status="sent", subtotal="100.00", vat="15.00", paid="0.00",
                 customer_id=None, subscription_id=None, period_start=None, number=None, due=None):
    from services.billing.models import Invoice
    sub, v = Decimal(subtotal), Decimal(vat)
    inv = Invoice(
        id=uuid.uuid4(), tenant_id=tenant_id, customer_id=customer_id or uuid.uuid4(),
        subscription_id=subscription_id, number=number or f"INV-{uuid.uuid4().hex[:6]}", status=status,
        subtotal_zar=sub, vat_zar=v, total_zar=sub + v, amount_paid_zar=Decimal(paid),
        due_date=due or date(2026, 1, 31), billing_period_start=period_start,
        billing_period_end=None, line_items=[],
    )
    session.add(inv)
    session.flush()
    return inv
