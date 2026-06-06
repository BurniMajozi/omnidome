"""MetroFibre FNO adapter (API-based).

MetroFibre Networx operates a GPON fibre network across South Africa's
major metros.  They provide a REST API for ISP partners.

Environment variables:
    METROFIBRE_API_URL   — base URL (default https://api.metrofibre.co.za/v1)
    METROFIBRE_API_KEY   — bearer token for partner API
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

class MetroFibreProduct(BaseModel):
    """A single fibre product available at an address on MetroFibre."""
    code: str
    name: str
    technology: str = "GPON"
    download_mbps: int
    upload_mbps: int
    monthly_price_cents: Optional[int] = None


class MetroFibreAvailabilityResponse(BaseModel):
    """Structured response from MetroFibre coverage check."""
    available: bool
    products: List[MetroFibreProduct] = Field(default_factory=list)
    estimated_install_days: int = Field(default=14, ge=1, le=365)
    area_name: Optional[str] = None
    estate_id: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class MetroFibreOrderResponse(BaseModel):
    """Structured response from MetroFibre order placement."""
    order_id: str
    status: str
    estimated_install_date: Optional[str] = None
    fno_reference: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class MetroFibreOrderStatus(BaseModel):
    """Structured response from MetroFibre order status query."""
    status: str
    technician_eta: Optional[str] = None
    scheduled_date: Optional[str] = None
    completed: bool = False
    raw: Optional[Dict[str, Any]] = None


class MetroFibreProvisionResponse(BaseModel):
    """Structured response from MetroFibre service provisioning."""
    success: bool
    circuit_id: Optional[str] = None
    vlan_id: Optional[int] = None
    ont_serial: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# MetroFibreAdapter class
# ---------------------------------------------------------------------------

class MetroFibreAdapter(APIFNOAdapter):
    """MetroFibre Networx API adapter.

    Extends the generic APIFNOAdapter with MetroFibre-specific endpoint paths
    and response parsing.  All methods return dicts matching the base-class
    interface contract.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.metrofibre.co.za/v1"):
        super().__init__(fno_name="metrofibre", api_key=api_key, base_url=base_url)

    # -- client lifecycle ---------------------------------------------------

    async def close(self) -> None:
        """Close the underlying httpx client (no-op for stateless adapter)."""
        pass  # APIFNOAdapter uses per-request clients; nothing to close

    # -- public API methods -------------------------------------------------

    async def check_availability(self, address: str) -> Dict[str, Any]:
        """Check if MetroFibre fibre is available at the given address.

        Returns a dict with:
            available (bool), products (list), estimated_install_days (int),
            area_name (str|None), estate_id (str|None)
        """
        logger.info("MetroFibre availability check: %s", address)
        try:
            data = await self._get("/coverage", {"address": address})
            products = [
                MetroFibreProduct(
                    code=p.get("code", ""),
                    name=p.get("name", ""),
                    technology=p.get("technology", "GPON"),
                    download_mbps=p.get("download_mbps", 0),
                    upload_mbps=p.get("upload_mbps", 0),
                    monthly_price_cents=p.get("monthly_price_cents"),
                )
                for p in data.get("products", [])
            ]
            result = MetroFibreAvailabilityResponse(
                available=data.get("covered", False),
                products=products,
                estimated_install_days=data.get("estimated_install_days", 14),
                area_name=data.get("estate_name"),
                estate_id=data.get("estate_id"),
                raw=data,
            )
            return result.model_dump(exclude_none=True)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "MetroFibre availability HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return MetroFibreAvailabilityResponse(
                available=False,
                raw={"error": str(exc), "status_code": exc.response.status_code},
            ).model_dump(exclude_none=True)
        except httpx.RequestError as exc:
            logger.warning("MetroFibre availability request error: %s", exc)
            return MetroFibreAvailabilityResponse(
                available=False,
                raw={"error": str(exc)},
            ).model_dump(exclude_none=True)

    async def place_order(
        self,
        customer_id: str,
        product_code: str,
        address: str,
    ) -> Dict[str, Any]:
        """Place a new installation order with MetroFibre.

        Returns a dict with:
            order_id (str), status (str), estimated_install_date (str|None),
            fno_reference (str|None)
        """
        logger.info(
            "MetroFibre place_order: customer=%s product=%s address=%s",
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
            result = MetroFibreOrderResponse(
                order_id=data.get("order_id", data.get("id", "")),
                status=data.get("status", "SUBMITTED"),
                estimated_install_date=data.get("estimated_install_date"),
                fno_reference=data.get("metrofibre_reference"),
                raw=data,
            )
            return result.model_dump(exclude_none=True)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "MetroFibre place_order HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return MetroFibreOrderResponse(
                order_id="",
                status="FAILED",
                raw={"error": str(exc), "status_code": exc.response.status_code},
            ).model_dump(exclude_none=True)
        except httpx.RequestError as exc:
            logger.warning("MetroFibre place_order request error: %s", exc)
            return MetroFibreOrderResponse(
                order_id="",
                status="FAILED",
                raw={"error": str(exc)},
            ).model_dump(exclude_none=True)

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Query the current status of a MetroFibre order.

        Returns a dict with:
            status (str), technician_eta (str|None),
            scheduled_date (str|None), completed (bool)
        """
        logger.info("MetroFibre get_order_status: %s", order_id)
        try:
            data = await self._get(f"/orders/{order_id}")
            result = MetroFibreOrderStatus(
                status=data.get("status", "UNKNOWN"),
                technician_eta=data.get("technician_eta"),
                scheduled_date=data.get("scheduled_date"),
                completed=data.get("completed", False),
                raw=data,
            )
            return result.model_dump(exclude_none=True)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "MetroFibre get_order_status HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return MetroFibreOrderStatus(
                status="ERROR",
                raw={"error": str(exc), "status_code": exc.response.status_code},
            ).model_dump(exclude_none=True)
        except httpx.RequestError as exc:
            logger.warning("MetroFibre get_order_status request error: %s", exc)
            return MetroFibreOrderStatus(
                status="ERROR",
                raw={"error": str(exc)},
            ).model_dump(exclude_none=True)

    async def provision_service(
        self,
        order_id: str,
        ont_serial: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Provision / activate a MetroFibre service after physical install.

        Returns a dict with:
            success (bool), circuit_id (str|None), vlan_id (int|None),
            ont_serial (str|None)
        """
        logger.info(
            "MetroFibre provision_service: order=%s ont=%s",
            order_id,
            ont_serial,
        )
        payload: Dict[str, Any] = {"order_id": order_id}
        if ont_serial:
            payload["ont_serial_number"] = ont_serial
        try:
            data = await self._post("/services/provision", payload)
            result = MetroFibreProvisionResponse(
                success=data.get("status", "").upper() in ("PROVISIONED", "ACTIVE"),
                circuit_id=data.get("circuit_id"),
                vlan_id=data.get("vlan_id"),
                ont_serial=data.get("ont_serial_number", ont_serial),
                raw=data,
            )
            return result.model_dump(exclude_none=True)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "MetroFibre provision_service HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return MetroFibreProvisionResponse(
                success=False,
                raw={"error": str(exc), "status_code": exc.response.status_code},
            ).model_dump(exclude_none=True)
        except httpx.RequestError as exc:
            logger.warning("MetroFibre provision_service request error: %s", exc)
            return MetroFibreProvisionResponse(
                success=False,
                raw={"error": str(exc)},
            ).model_dump(exclude_none=True)
