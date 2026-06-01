"""
Patch file: Replace synchronous httpx calls in CRM Customer 360 view
with service_call() from the resilient http_client.

OLD CODE (commented out):
    # async def _fetch_service_data(url: str, headers: dict) -> list:
    #     \"\"\"Fetch data from a sibling service; return empty list on failure.\"\"\"
    #     try:
    #         async with httpx.AsyncClient(timeout=5.0) as client:
    #             resp = await client.get(url, headers=headers)
    #             if resp.status_code == 200:
    #                 data = resp.json()
    #                 return data if isinstance(data, list) else data.get(\"items\", [])
    #     except Exception:
    #         pass
    #     return []
    #
    # # In get_customer_360:
    # billing_data, support_data, network_data = [], [], []
    # try:
    #     billing_data = await _fetch_service_data(
    #         f\"{BILLING_URL}/invoices?customer_id={cid}\", headers
    #     )
    # except Exception:
    #     pass
    # try:
    #     support_data = await _fetch_service_data(
    #         f\"{SUPPORT_URL}/tickets?customer_id={cid}\", headers
    #     )
    # except Exception:
    #     pass
    # try:
    #     network_data = await _fetch_service_data(
    #         f\"{NETWORK_URL}/services?customer_id={cid}\", headers
    #     )
    # except Exception:
    #     pass

NEW CODE (active below):
"""

# ---------------------------------------------------------------------------
# Replacement: _fetch_service_data and the cross-service call block
# in services/crm/routes/customers.py :: get_customer_360
# ---------------------------------------------------------------------------

import uuid
import logging
from typing import Optional

# Remove: import httpx
# Remove: BILLING_URL, SUPPORT_URL, NETWORK_URL constants (service_call resolves URLs internally)
# Add import:
from services.common.http_client import service_get

logger = logging.getLogger("crm.customers")


def _forward_headers(ctx) -> dict:
    """Build auth headers for cross-service calls.
    
    OLD:
        return {
            \"X-User-Id\": str(ctx.user_id),
            \"X-Tenant-Id\": str(ctx.tenant_id),
        }
    
    NEW: With service_call, tenant_id and user_id are passed directly;
    _forward_headers is no longer needed but kept for reference.
    """
    return {
        "X-User-Id": str(ctx.user_id),
        "X-Tenant-Id": str(ctx.tenant_id),
    }


async def _fetch_service_data(
    service_name: str,
    path: str,
    ctx,  # AuthContext
) -> list:
    """Fetch data from a sibling service via the resilient HTTP client.

    Replace:
        OLD:
            async def _fetch_service_data(url: str, headers: dict) -> list:
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        resp = await client.get(url, headers=headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            return data if isinstance(data, list) else data.get(\"items\", [])
                except Exception:
                    pass
                return []

    NEW: Uses service_get which provides circuit breaker + retry + logging.
    """
    try:
        result = await service_get(
            service_name,
            path,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            timeout=5.0,
        )
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("items", [])
        return []
    except Exception as exc:
        logger.warning(
            "Cross-service call failed: %s %s — %s", service_name, path, exc
        )
        return []


# ---------------------------------------------------------------------------
# Replacement for the cross-service aggregation block inside
# get_customer_360 (around line 189-216 of the original file)
#
# OLD:
#     billing_data, support_data, network_data = [], [], []
#     try:
#         billing_data = await _fetch_service_data(
#             f\"{BILLING_URL}/invoices?customer_id={cid}\", headers
#         )
#     except Exception:
#         pass
#     try:
#         support_data = await _fetch_service_data(
#             f\"{SUPPORT_URL}/tickets?customer_id={cid}\", headers
#         )
#     except Exception:
#         pass
#     try:
#         network_data = await _fetch_service_data(
#             f\"{NETWORK_URL}/services?customer_id={cid}\", headers
#         )
#     except Exception:
#         pass
#
#     view.billing = billing_data
#     view.support = support_data
#     view.network = network_data
#     view.services = network_data  # alias
#
# NEW:
# ---------------------------------------------------------------------------

# --- This block replaces lines ~189-216 in services/crm/routes/customers.py ---

#     billing_data, support_data, network_data = [], [], []
#     cid = str(customer_id)
#     headers = _forward_headers(ctx)

    # NEW CODE:
    billing_data = await _fetch_service_data(
        "billing", f"/invoices?customer_id={str(customer_id)}", ctx,
    )
    support_data = await _fetch_service_data(
        "support", f"/tickets?customer_id={str(customer_id)}", ctx,
    )
    network_data = await _fetch_service_data(
        "network", f"/services?customer_id={str(customer_id)}", ctx,
    )

    # (view.billing = billing_data, etc. stays the same — no change needed)


# ---------------------------------------------------------------------------
# FULL REPLACEMENT for _fetch_service_data reference in router
# (In case you want to patch the entire get_customer_360 function)
# ---------------------------------------------------------------------------

# The complete new version of the get_customer_360 function is included here
# for direct copy-paste into services/crm/routes/customers.py:

# --- BEGIN FULL REPLACEMENT FUNCTION ---
#
# @router.get(\"/{customer_id}\", response_model=Customer360)
# async def get_customer_360(
#     customer_id: uuid.UUID,
#     ctx: AuthContext = Depends(get_auth_context),
# ):
#     with get_session() as session:
#         customer = (
#             session.query(Customer)
#             .filter(Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id)
#             .first()
#         )
#         if not customer:
#             raise HTTPException(status_code=404, detail=\"Customer not found\")
#
#         tags = (
#             session.query(CustomerTag)
#             .filter(CustomerTag.customer_id == customer_id, CustomerTag.tenant_id == ctx.tenant_id)
#             .all()
#         )
#         notes_count = (
#             session.query(func.count(CustomerNote.id))
#             .filter(CustomerNote.customer_id == customer_id, CustomerNote.tenant_id == ctx.tenant_id)
#             .scalar()
#         ) or 0
#
#         result = Customer360.model_validate(customer)
#         result.tags = [t.tag for t in tags]
#         result.notes_count = notes_count
#
#     # Aggregate cross-service data (resilient, with circuit breaker + retry)
#     billing_data = await _fetch_service_data(
#         \"billing\", f\"/invoices?customer_id={str(customer_id)}\", ctx,
#     )
#     support_data = await _fetch_service_data(
#         \"support\", f\"/tickets?customer_id={str(customer_id)}\", ctx,
#     )
#     network_data = await _fetch_service_data(
#         \"network\", f\"/services?customer_id={str(customer_id)}\", ctx,
#     )
#
#     result.billing = billing_data
#     result.support = support_data
#     result.network = network_data
#     result.services = network_data  # alias
#
#     return result
#
# --- END FULL REPLACEMENT FUNCTION ---


# ---------------------------------------------------------------------------
# IMPORTS TO CHANGE in services/crm/routes/customers.py
# ---------------------------------------------------------------------------
# REMOVE:
#   import httpx
#   BILLING_URL = os.getenv(...)
#   SUPPORT_URL = os.getenv(...)
#   NETWORK_URL = os.getenv(...)
#
# ADD:
#   from services.common.http_client import service_get
#
# KEEP:
#   from services.common.auth import AuthContext, get_auth_context
#   (used to pass tenant_id / user_id to service_get)
