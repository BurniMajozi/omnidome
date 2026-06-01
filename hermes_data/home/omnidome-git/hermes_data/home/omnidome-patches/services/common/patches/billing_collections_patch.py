"""
Patch file: Replace synchronous httpx calls in billing collections routes
with service_call() from the resilient http_client.

AFFECTED FILE: services/billing/routes/collections.py

OLD CODE (commented out below):
    def _suspend_customer(tenant_id, customer_id):
        \"\"\"Call network service to suspend all services for a customer.\"\"\"
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    f\"{NETWORK_URL}/services/suspend-by-customer\",
                    json={\"customer_id\": str(customer_id)},
                    headers=_forward_headers(tenant_id),
                )
                logger.info(
                    \"Suspend request for customer %s: status=%s\", customer_id, resp.status_code
                )
        except Exception as exc:
            logger.error(\"Suspend call failed for customer %s: %s\", customer_id, exc)

    def _reinstate_customer(tenant_id, customer_id):
        \"\"\"Call network service to reinstate all services for a customer.\"\"\"
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    f\"{NETWORK_URL}/services/reinstate-by-customer\",
                    json={\"customer_id\": str(customer_id)},
                    headers=_forward_headers(tenant_id),
                )
                logger.info(
                    \"Reinstate request for customer %s: status=%s\", customer_id, resp.status_code
                )
        except Exception as exc:
            logger.error(\"Reinstate call failed for customer %s: %s\", customer_id, exc)

NEW CODE (active below):
"""

# ---------------------------------------------------------------------------
# IMPORTS TO CHANGE in services/billing/routes/collections.py
# ---------------------------------------------------------------------------
# REMOVE:
#   import httpx
#   NETWORK_URL = os.getenv("NETWORK_SERVICE_URL", "http://network:8005")
#
# ADD:
#   import asyncio
#   from services.common.http_client import service_post

# ---------------------------------------------------------------------------
# Also add `import asyncio` at the top if not already present,
# since the replacement functions are async.
# ---------------------------------------------------------------------------

import logging
import uuid
from typing import Optional

from services.common.http_client import service_post

logger = logging.getLogger("billing.collections")


# ---------------------------------------------------------------------------
# Replacement helper: _forward_headers
# ---------------------------------------------------------------------------
# OLD:
#   def _forward_headers(tenant_id: uuid.UUID) -> dict:
#       return {
#           "X-User-Id": "00000000-0000-0000-0000-000000000000",
#           "X-Tenant-Id": str(tenant_id),
#       }
#
# NEW: _forward_headers is no longer needed here since service_post
# accepts tenant_id and user_id directly. Remove it.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Replacement function: _suspend_customer
# ---------------------------------------------------------------------------

async def _suspend_customer(tenant_id: uuid.UUID, customer_id: uuid.UUID) -> None:
    """Call network service to suspend all services for a customer.

    Replaces:
        def _suspend_customer(tenant_id: uuid.UUID, customer_id: uuid.UUID) -> None:
            try:
                with httpx.Client(timeout=5.0) as client:
                    resp = client.post(
                        f\"{NETWORK_URL}/services/suspend-by-customer\",
                        json={\"customer_id\": str(customer_id)},
                        headers=_forward_headers(tenant_id),
                    )
                    logger.info(\"Suspend request ...\", ...)
            except Exception as exc:
                logger.error(\"Suspend call failed ...\", ...)

    New: Uses service_post with circuit breaker + retry.
    """
    try:
        result = await service_post(
            "network",
            "/services/suspend-by-customer",
            json={"customer_id": str(customer_id)},
            tenant_id=tenant_id,
            user_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            timeout=5.0,
        )
        logger.info("Suspend request for customer %s: OK", customer_id)
    except Exception as exc:
        logger.error("Suspend call failed for customer %s: %s", customer_id, exc)


# ---------------------------------------------------------------------------
# Replacement function: _reinstate_customer
# ---------------------------------------------------------------------------

async def _reinstate_customer(tenant_id: uuid.UUID, customer_id: uuid.UUID) -> None:
    """Call network service to reinstate all services for a customer.

    Replaces:
        def _reinstate_customer(tenant_id: uuid.UUID, customer_id: uuid.UUID) -> None:
            try:
                with httpx.Client(timeout=5.0) as client:
                    resp = client.post(
                        f\"{NETWORK_URL}/services/reinstate-by-customer\",
                        json={\"customer_id\": str(customer_id)},
                        headers=_forward_headers(tenant_id),
                    )
                    logger.info(\"Reinstate request ...\", ...)
            except Exception as exc:
                logger.error(\"Reinstate call failed ...\", ...)

    New: Uses service_post with circuit breaker + retry.
    """
    try:
        result = await service_post(
            "network",
            "/services/reinstate-by-customer",
            json={"customer_id": str(customer_id)},
            tenant_id=tenant_id,
            user_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            timeout=5.0,
        )
        logger.info("Reinstate request for customer %s: OK", customer_id)
    except Exception as exc:
        logger.error("Reinstate call failed for customer %s: %s", customer_id, exc)


# ---------------------------------------------------------------------------
# NOTE: The callers of _suspend_customer and _reinstate_customer must
# also be made async because these helpers are now async.
#
# In services/billing/routes/collections.py:
#
# OLD (synchronous):
#   @router.post("/collections/{customer_id}/suspend")
#   def manual_suspend(customer_id, ctx):
#       _suspend_customer(ctx.tenant_id, customer_id)
#       ...
#
#   @router.post("/collections/{customer_id}/reinstate")
#   def reinstate_customer(customer_id, ctx):
#       _reinstate_customer(ctx.tenant_id, customer_id)
#       ...
#
#   # In process_pending_dunning:
#   _suspend_customer(action.tenant_id, action.customer_id)
#
# NEW (async):
#   @router.post("/collections/{customer_id}/suspend")
#   async def manual_suspend(customer_id, ctx):
#       await _suspend_customer(ctx.tenant_id, customer_id)
#       ...
#
#   @router.post("/collections/{customer_id}/reinstate")
#   async def reinstate_customer(customer_id, ctx):
#       await _reinstate_customer(ctx.tenant_id, customer_id)
#       ...
#
#   # In process_pending_dunning (must be async or use asyncio.run):
#   loop = asyncio.get_event_loop()
#   loop.run_until_complete(
#       _suspend_customer(action.tenant_id, action.customer_id)
#   )
#   # OR make process_pending_dunning async if the scheduler supports it.
#
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# FULL REPLACEMENT for _suspend_customer and _reinstate_customer callers
# (copy-paste ready)
# ---------------------------------------------------------------------------

# --- Replace the manual_suspend endpoint ---
#
# @router.post("/collections/{customer_id}/suspend")
# async def manual_suspend(
#     customer_id: uuid.UUID,
#     ctx: AuthContext = Depends(get_auth_context),
# ):
#     await _suspend_customer(ctx.tenant_id, customer_id)
#
#     # Mark overdue invoices
#     with get_session() as session:
#         (
#             session.query(Invoice)
#             .filter(
#                 Invoice.tenant_id == ctx.tenant_id,
#                 Invoice.customer_id == customer_id,
#                 Invoice.status.in_(["sent", "partially_paid"]),
#                 Invoice.due_date < date.today(),
#             )
#             .update({"status": "overdue"}, synchronize_session="fetch")
#         )
#
#     return {"status": "suspended", "customer_id": str(customer_id)}
#
#
# --- Replace the reinstate_customer endpoint ---
#
# @router.post("/collections/{customer_id}/reinstate")
# async def reinstate_customer(
#     customer_id: uuid.UUID,
#     ctx: AuthContext = Depends(get_auth_context),
# ):
#     await _reinstate_customer(ctx.tenant_id, customer_id)
#     return {"status": "reinstated", "customer_id": str(customer_id)}
#
#
# --- Replace the auto_suspend dunning action block in process_pending_dunning ---
#
# OLD:
#     elif action.action_type == "auto_suspend":
#         inv = session.query(Invoice).filter(Invoice.id == action.invoice_id).first()
#         if inv and inv.status not in ("paid", "voided"):
#             _suspend_customer(action.tenant_id, action.customer_id)
#             inv.status = "overdue"
#             action.result = "suspended"
#         else:
#             action.result = "skipped_paid"
#
# NEW (if process_pending_dunning can be made async):
#     elif action.action_type == "auto_suspend":
#         inv = session.query(Invoice).filter(Invoice.id == action.invoice_id).first()
#         if inv and inv.status not in ("paid", "voided"):
#             await _suspend_customer(action.tenant_id, action.customer_id)
#             inv.status = "overdue"
#             action.result = "suspended"
#         else:
#             action.result = "skipped_paid"
#
# If process_pending_dunning CANNOT be made async, wrap the call:
#     elif action.action_type == "auto_suspend":
#         inv = session.query(Invoice).filter(Invoice.id == action.invoice_id).first()
#         if inv and inv.status not in ("paid", "voided"):
#             try:
#                 loop = asyncio.get_event_loop()
#                 if loop.is_running():
#                     import nest_asyncio
#                     nest_asyncio.apply()
#                 loop.run_until_complete(
#                     _suspend_customer(action.tenant_id, action.customer_id)
#                 )
#                 inv.status = "overdue"
#                 action.result = "suspended"
#             except Exception as exc:
#                 action.result = f"error: {exc}"
#         else:
#             action.result = "skipped_paid"
