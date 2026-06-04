"""Seed data for billing collections — sample debit orders, EFT payments, and batch runs."""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from services.billing_collections.models import (
    Base,
    BillingBatchRun,
    CollectionEvent,
    DebitOrderMandate,
    EFTPayment,
    InvoiceMovement,
    SubscriptionPaymentMethod,
)
from services.billing_collections.database import get_async_engine, get_session_factory


SAMPLE_TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
SAMPLE_CUSTOMER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
SAMPLE_SUBSCRIPTION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


async def ensure_sample_data():
    """Insert sample billing collection data if tenant has none."""
    engine = get_async_engine()
    factory = get_session_factory()
    async with factory() as session:
        from sqlalchemy import select, func
        result = await session.execute(
            select(func.count(DebitOrderMandate.id)).where(
                DebitOrderMandate.tenant_id == SAMPLE_TENANT_ID
            )
        )
        if result.scalar() > 0:
            return

        # 1. Debit order mandate
        mandate = DebitOrderMandate(
            tenant_id=SAMPLE_TENANT_ID,
            customer_id=SAMPLE_CUSTOMER_ID,
            account_number="ACC-001",
            mandate_type="debit_order",
            bank_name="First National Bank",
            branch_code="250655",
            branch_name="FNB Sandton City",
            account_holder="John Doe",
            account_number_bank="62000000001",
            account_type="cheque",
            debit_day=1,
            first_debit_date=date.today().replace(day=1) + timedelta(days=32),
            max_amount_zar=Decimal("1499.00"),
            status="active",
            signature_method="digital",
            signature_date=date.today(),
            is_notedo=True,
        )
        session.add(mandate)
        await session.flush()

        # 2. Stop order mandate
        stop_mandate = DebitOrderMandate(
            tenant_id=SAMPLE_TENANT_ID,
            customer_id=SAMPLE_CUSTOMER_ID,
            account_number="ACC-001",
            mandate_type="stop_order",
            bank_name="Standard Bank",
            branch_code="051001",
            branch_name="SB Rosebank",
            account_holder="John Doe",
            account_number_bank="0000000001",
            account_type="savings",
            debit_day=25,
            fixed_amount_zar=Decimal("999.00"),
            status="active",
            signature_method="paper",
            signature_date=date.today() - timedelta(days=30),
            is_notedo=False,
        )
        session.add(stop_mandate)

        # 3. Subscription payment method mapping
        sub_pm = SubscriptionPaymentMethod(
            tenant_id=SAMPLE_TENANT_ID,
            customer_id=SAMPLE_CUSTOMER_ID,
            subscription_id=SAMPLE_SUBSCRIPTION_ID,
            instrument_type="debit_order",
            mandate_id=mandate.id,
            priority=1,
            is_active=True,
        )
        session.add(sub_pm)

        # 4. EFT payments (unmatched)
        for i in range(3):
            eft = EFTPayment(
                tenant_id=SAMPLE_TENANT_ID,
                customer_id=SAMPLE_CUSTOMER_ID,
                account_number="ACC-001",
                amount_zar=Decimal("999.00") + (i * Decimal("100")),
                bank_reference=f"FNB{2024001 + i}",
                customer_reference=f" REF 0{i}ACC001 ",
                bank_name="FNB",
                branch_code="250655",
                payment_date=date.today() - timedelta(days=i),
                status="unmatched",
            )
            session.add(eft)

        # 5. Reference cleaning examples
        from services.billing_collections.models import ReferenceCleanup
        references = [
            (" REF 001ACC001 ", "strip_spaces"),
            ("PAY-ACC-001-2024", "remove_dashes"),
            ("INV001234", "strip_prefix"),
        ]
        for original, method in references:
            cleaned = original.strip()
            if method == "strip_spaces":
                cleaned = cleaned.replace(" ", "")
            elif method == "remove_dashes":
                cleaned = cleaned.replace("-", "")
            elif method == "strip_prefix":
                for prefix in ["INV"]:
                    if cleaned.upper().startswith(prefix):
                        cleaned = cleaned[len(prefix):]
                        break

            rc = ReferenceCleanup(
                tenant_id=SAMPLE_TENANT_ID,
                original_reference=original,
                cleaned_reference=cleaned,
                cleaning_method=method,
                matched_customer_id=SAMPLE_CUSTOMER_ID,
                matched_account_number="ACC-001",
                match_confidence="high",
                auto_matched=True,
            )
            session.add(rc)

        # 6. Collection events
        events = [
            ("invoice_generated", "info", "Invoice INV-2026-001 generated for R999.00", Decimal("999.00")),
            ("debit_order_submitted", "info", "Debit order submitted to FNB for R999.00", Decimal("999.00")),
            ("debit_order_success", "info", "Debit order collected successfully", Decimal("999.00")),
            ("payment_received", "info", "EFT payment received R999.00", Decimal("999.00")),
            ("payment_matched", "info", "Payment matched to invoice INV-2026-001", Decimal("999.00")),
        ]
        for event_type, severity, summary, amount in events:
            session.add(CollectionEvent(
                tenant_id=SAMPLE_TENANT_ID,
                customer_id=SAMPLE_CUSTOMER_ID,
                account_number="ACC-001",
                event_type=event_type,
                severity=severity,
                summary=summary,
                amount_zar=amount,
                source="billing_collections",
            ))

        await session.commit()
