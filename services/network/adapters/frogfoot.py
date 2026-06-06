"""Frogfoot FNO adapter (API-based).

Frogfoot Networks operates an open-access fibre network in several
South African cities.  They expose a REST API for ISP partners.

Environment variables:
    FROGFOOT_API_URL   — base URL (default https://api.frogfoot.com/v2)
    FROGFOOT_API_KEY   — bearer token for partner API
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from .api_adapter import APIFNOAdapter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------

class FrogfootProduct(BaseModel):
    """A single fibre product available at an address on Frogfoot."""
    code: str
    name: str
    technology: str = "GPON"
    download_mbps: int
    upload_mbps: int
    monthly_price_cents: Optional[int] = None


class FrogfootAvailabilityResponse(BaseModel):
    """Structured response from Frogfoot feasibility check."""
    available: bool
    products: List[FrogfootProduct] = Field(default_factory=list)
    estimated_install_days: int = Field(default=14, ge=1, le=365)
    node_id: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class FrogfootOrderResponse(BaseModel):
    """Structured response from Frogfoot order placement."""
    order_id: str
    status: str
    estimated_install_date: Optional[str] = None
    fno_reference: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class FrogfootOrderStatus(BaseModel):
    """Structured response from Frogfoot order status query."""
    status: str
    technician_eta: Optional[str] = None
    scheduled_date: Optional[str] = None
    completed: bool = False
    raw: Optional[Dict[str, Any]] = None


class FrogfootProvisionResponse(BaseModel):
    """Structured response from Frogfoot service provisioning."""
    success: bool
    circuit_id: Optional[str] = None
    vlan_id: Optional[int] = None
    ont_serial: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# FrogfootAdapter class
# ---------------------------------------------------------------------------

class FrogfootAdapter(APIFNOAdapter):
    """Frogfoot Networks API adapter.

    Extends the generic APIFNOAdapter with Frogfoot-specific endpoint paths
    and response parsing.  All methods return dicts matching the base-class
    interface contract.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.frogfoot.com/v2"):
        super().__init__(fno_name="frogfoot", api_key=api_key, base_url=base_url)

    # -- client lifecycle ---------------------------------------------------

    async def close(self) -> None:
        """Close the underlying httpx client (no-op for stateless adapter)."""
        pass  # APIFNOAdapter uses per-request clients; nothing to close

    # -- public API methods -------------------------------------------------

    async def check_availability(self, address: str) -> Dict[str, Any]:
        """Check if Frogfoot fibre is available at the given address.

        Returns a dict with:
            available (bool), products (list), estimated_install_days (int),
            node_id (str|None)
        """
        logger.info("Frogfoot availability check: %s", address)
        try:
            data = await self._get("/feasibility/check", {"address": address})
            products = [
                FrogfootProduct(
                    code=p.get("code", ""),
                    name=p.get("name", ""),
                    technology=p.get("technology", "GPON"),
                    download_mbps=p.get("download_mbps", 0),
                    upload_mbps=p.get("upload_mbps", 0),
                    monthly_price_cents=p.get("monthly_price_cents"),
                )
                for p in data.get("products", [])
            ]
            result = FrogfootAvailabilityResponse(
                available=data.get("feasible", False),
                products=products,
                estimated_install_days=data.get("estimated_install_days", 14),
                node_id=data.get("node_id"),
                raw=data,
            )
            return result.model_dump(exclude_none=True)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Frogfoot availability HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return FrogfootAvailabilityResponse(
                available=False,
                raw={"error": str(exc), "status_code": exc.response.status_code},
            ).model_dump(exclude_none=True)
        except httpx.RequestError as exc:
            logger.warning("Frogfoot availability request error: %s", exc)
            return FrogfootAvailabilityResponse(
                available=False,
                raw={"error": str(exc)},
            ).model_dump(exclude_none=True)

    async def place_order(
        self,
        customer_id: str,
        product_code: str,
        address: str,
    ) -> Dict[str, Any]:
        """Place a new installation order with Frogfoot.

        Returns a dict with:
            order_id (str), status (str), estimated_install_date (str|None),
            fno_reference (str|None)
        """
        logger.info(
            "Frogfoot place_order: customer=%s product=%s address=%s",
            customer_id,
            product_code,
            address,
        )
        payload = {
            "customer_id": customer_id,
            "product_code": product_code,
            "installation_address": address,
            "order_type": "new_installation",
        }
        try:
            data = await self._post("/orders", payload)
            result = FrogfootOrderResponse(
                order_id=data.get("order_id", data.get("id", "")),
                status=data.get("status", "SUBMITTED"),
                estimated_install_date=data.get("estimated_install_date"),
                fno_reference=data.get("frogfoot_reference"),
                raw=data,
            )
            return result.model_dump(exclude_none=True)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Frogfoot place_order HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return FrogfootOrderResponse(
                order_id="",
                status="FAILED",
                raw={"error": str(exc), "status_code": exc.response.status_code},
            ).model_dump(exclude_none=True)
        except httpx.RequestError as exc:
            logger.warning("Frogfoot place_order request error: %s", exc)
            return FrogfootOrderResponse(
                order_id="",
                status="FAILED",
                raw={"error": str(exc)},
            ).model_dump(exclude_none=True)

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Query the current status of a Frogfoot order.

        Returns a dict with:
            status (str), technician_eta (str|None),
            scheduled_date (str|None), completed (bool)
        """
        logger.info("Frogfoot get_order_status: %s", order_id)
        try:
            data = await self._get(f"/orders/{order_id}")
            result = FrogfootOrderStatus(
                status=data.get("status", "UNKNOWN"),
                technician_eta=data.get("technician_eta"),
                scheduled_date=data.get("scheduled_date"),
                completed=data.get("completed", False),
                raw=data,
            )
            return result.model_dump(exclude_none=True)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Frogfoot get_order_status HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return FrogfootOrderStatus(
                status="ERROR",
                raw={"error": str(exc), "status_code": exc.response.status_code},
            ).model_dump(exclude_none=True)
        except httpx.RequestError as exc:
            logger.warning("Frogfoot get_order_status request error: %s", exc)
            return FrogfootOrderStatus(
                status="ERROR",
                raw={"error": str(exc)},
            ).model_dump(exclude_none=True)

    async def provision_service(
        self,
        order_id: str,
        ont_serial: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Provision / activate a Frogfoot service after physical install.

        Returns a dict with:
            success (bool), circuit_id (str|None), vlan_id (int|None),
            ont_serial (str|None)
        """
        logger.info(
            "Frogfoot provision_service: order=%s ont=%s",
            order_id,
            ont_serial,
        )
        payload: Dict[str, Any] = {"order_id": order_id}
        if ont_serial:
            payload["ont_serial_number"] = ont_serial
        try:
            data = await self._post("/services/provision", payload)
            result = FrogfootProvisionResponse(
                success=data.get("status", "").upper() in ("PROVISIONED", "ACTIVE"),
                circuit_id=data.get("circuit_id"),
                vlan_id=data.get("vlan_id"),
                ont_serial=data.get("ont_serial_number", ont_serial),
                raw=data,
            )
            return result.model_dump(exclude_none=True)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Frogfoot provision_service HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return FrogfootProvisionResponse(
                success=False,
                raw={"error": str(exc), "status_code": exc.response.status_code},
            ).model_dump(exclude_none=True)
        except httpx.RequestError as exc:
            logger.warning("Frogfoot provision_service request error: %s", exc)
            return FrogfootProvisionResponse(
                success=False,
                raw={"error": str(exc)},
            ).model_dump(exclude_none=True)
