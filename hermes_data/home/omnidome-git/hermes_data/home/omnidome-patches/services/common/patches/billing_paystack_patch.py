"""
Patch file: Replace synchronous httpx call in billing Paystack webhook handler
(auto-reinstate) with service_call() from the resilient http_client.

AFFECTED FILE: services/billing/routes/paystack.py

OLD CODE (commented out below):
    def _trigger_auto_reinstate(tenant_id, customer_id) -> None:
        \"\"\"Notify Network service to reinstate customer service after payment.\"\"\"
        network_url = os.getenv("NETWORK_SERVICE_URL", "http://network:8005")
        try:
            with httpx.Client(timeout=5.0) as client:
                client.post(
                    f\"{network_url}/services/reinstate-by-customer\",
                    json={\"customer_id\": str(customer_id)},
                    headers={
                        "X-User-Id": "00000000-0000-0000-0000-000000000000",
                        "X-Tenant-Id": str(tenant_id),
                    },
                )
        except Exception as exc:
            logger.error("Auto-reinstate failed for customer %s: %s", customer_id, exc)

NEW CODE (active below):
"""

# ---------------------------------------------------------------------------
# IMPORTS TO CHANGE in services/billing/routes/paystack.py
# ---------------------------------------------------------------------------
# REMOVE:
#   (no removal needed — os is already imported for PAYSTACK_SECRET etc.)
#
# ADD:
#   import asyncio
#   from services.common.http_client import service_post
#   import uuid as _uuid   (already imported locally in _handle_charge_success)

# ---------------------------------------------------------------------------
# Note: _trigger_auto_reinstate is called from _handle_charge_success,
# which is already an `async` function — so we can `await` service_post
# directly. No additional async changes needed.
# ---------------------------------------------------------------------------

import logging
import uuid

from services.common.http_client import service_post

logger = logging.getLogger("billing.paystack")


# ---------------------------------------------------------------------------
# Replacement function: _trigger_auto_reinstate
# ---------------------------------------------------------------------------

async def _trigger_auto_reinstate(tenant_id, customer_id) -> None:
    """Notify Network service to reinstate customer service after payment.

    Replaces:
        def _trigger_auto_reinstate(tenant_id, customer_id) -> None:
            network_url = os.getenv("NETWORK_SERVICE_URL", "http://network:8005")
            try:
                with httpx.Client(timeout=5.0) as client:
                    client.post(
                        f\"{network_url}/services/reinstate-by-customer\",
                        json={\"customer_id\": str(customer_id)},
                        headers={
                            "X-User-Id": "00000000-0000-0000-0000-000000000000",
                            "X-Tenant-Id": str(tenant_id),
                        },
                    )
            except Exception as exc:
                logger.error("Auto-reinstate failed for customer %s: %s", customer_id, exc)

    New: Uses service_post with circuit breaker + retry + structured logging.
    The caller (_handle_charge_success) is already async, so we just add `await`.
    """
    try:
        await service_post(
            "network",
            "/services/reinstate-by-customer",
            json={"customer_id": str(customer_id)},
            tenant_id=tenant_id,
            user_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            timeout=5.0,
        )
        logger.info("Auto-reinstate triggered for customer %s", customer_id)
    except Exception as exc:
        logger.error("Auto-reinstate failed for customer %s: %s", customer_id, exc)


# ---------------------------------------------------------------------------
# FULL REPLACEMENT for _handle_charge_success (copy-paste ready)
# The only change is `await` before the _trigger_auto_reinstate call.
# ---------------------------------------------------------------------------

# --- BEGIN FULL REPLACEMENT FUNCTION ---
#
# async def _handle_charge_success(data: dict) -> None:
#     \"\"\"Process a successful charge — record payment and update invoice.\"\"\"
#     metadata = data.get("metadata", {})
#     invoice_id_raw = metadata.get("invoice_id")
#     tenant_id_raw = metadata.get("tenant_id")
#     if not invoice_id_raw or not tenant_id_raw:
#         logger.warning("Webhook charge.success missing invoice/tenant metadata")
#         return
#
#     import uuid as _uuid
#     invoice_id = _uuid.UUID(invoice_id_raw)
#     tenant_id = _uuid.UUID(tenant_id_raw)
#     amount_zar = Decimal(str(data.get("amount", 0))) / 100
#     reference = data.get("reference", "")
#
#     with get_session() as session:
#         inv = (
#             session.query(Invoice)
#             .filter(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
#             .first()
#         )
#         if not inv:
#             logger.warning("Webhook: invoice %s not found", invoice_id)
#             return
#
#         payment = Payment(
#             tenant_id=tenant_id,
#             invoice_id=inv.id,
#             customer_id=inv.customer_id,
#             amount_zar=amount_zar,
#             method="card",
#             reference=reference,
#             paystack_ref=reference,
#             status="completed",
#         )
#         session.add(payment)
#
#         inv.amount_paid_zar += amount_zar
#         if inv.amount_paid_zar >= inv.total_zar:
#             inv.status = "paid"
#         elif inv.amount_paid_zar > 0:
#             inv.status = "partially_paid"
#
#         session.flush()
#         logger.info(
#             "Payment recorded: invoice=%s amount=R%.2f status=%s",
#             inv.number, amount_zar, inv.status,
#         )
#
#         # If fully paid and was overdue, trigger reinstatement
#         if inv.status == "paid":
#             await _trigger_auto_reinstate(tenant_id, inv.customer_id)
#
# --- END FULL REPLACEMENT FUNCTION ---
