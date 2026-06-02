"""Vumatel FNO adapter — full API-based integration.

Vumatel is one of South Africa's largest open-access fibre network operators,
operating primarily in Gauteng, Western Cape and KZN.  They expose a partner
REST API for coverage checks, order management, and provisioning.

Environment variables:
    VUMATEL_API_URL   — base URL (default http://vumatel-mock:9001)
    VUMATEL_API_KEY   — bearer token for partner API
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any, List, Optional

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class VumatelProduct(BaseModel):
    """A single fibre product available at an address."""
    code: str
    name: str
    technology: str = "GPON"
    download_mbps: int
    upload_mbps: int
    monthly_price_cents: Optional[int] = None


class VumatelAvailabilityResponse(BaseModel):
    """Structured response from Vumatel feasibility check."""
    available: bool
    products: List[VumatelProduct] = Field(default_factory=list)
    estimated_install_days: int = Field(default=14, ge=1, le=365)
    area_name: Optional[str] = None
    precinct_id: Optional[str] = None
    raw: Optional[dict[str, Any]] = None


class VumatelOrderResponse(BaseModel):
    """Structured response from Vumatel order placement."""
    order_id: str
    status: str
    estimated_install_date: Optional[str] = None
    fno_reference: Optional[str] = None
    raw: Optional[dict[str, Any]] = None


class VumatelOrderStatus(BaseModel):
    """Structured response from Vumatel order status query."""
    status: str
    technician_eta: Optional[str] = None
    scheduled_date: Optional[str] = None
    completed: bool = False
    raw: Optional[dict[str, Any]] = None


class VumatelProvisionResponse(BaseModel):
    """Structured response from Vumatel service provisioning."""
    success: bool
    circuit_id: Optional[str] = None
    vlan_id: Optional[int] = None
    ont_serial: Optional[str] = None
    raw: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# VumatelAPI class
# ---------------------------------------------------------------------------


class VumatelAPI:
    """Async httpx-based client for the Vumatel partner REST API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("VUMATEL_API_KEY", "")
        self.base_url = (
            base_url
            or os.getenv("VUMATEL_API_URL", "http://vumatel-mock:9001")
        ).rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    # -- client lifecycle ---------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "VumatelAPI":
        await self._get_client()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # -- request helpers ----------------------------------------------------

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        client = await self._get_client()
        resp = await client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, payload: Optional[dict] = None) -> dict:
        client = await self._get_client()
        resp = await client.post(path, json=payload or {})
        resp.raise_for_status()
        return resp.json()

    async def _put(self, path: str, payload: Optional[dict] = None) -> dict:
        client = await self._get_client()
        resp = await client.put(path, json=payload or {})
        resp.raise_for_status()
        return resp.json()

    # -- public API methods -------------------------------------------------

    async def check_availability(self, address: str) -> dict:
        """Check if Vumatel fibre is available at the given address.

        Returns a dict with:
            available (bool), products (list), estimated_install_days (int),
            area_name (str|None), precinct_id (str|None)
        """
        logger.info("Vumatel availability check: %s", address)
        try:
            data = await self._get(
                "/api/v1/feasibility", params={"address": address}
            )
            products = [
                VumatelProduct(
                    code=p.get("code", ""),
                    name=p.get("name", ""),
                    technology=p.get("technology", "GPON"),
                    download_mbps=p.get("download_mbps", 0),
                    upload_mbps=p.get("upload_mbps", 0),
                    monthly_price_cents=p.get("monthly_price_cents"),
                )
                for p in data.get("products", [])
            ]
            result = VumatelAvailabilityResponse(
                available=data.get("feasible", False),
                products=products,
                estimated_install_days=data.get("estimated_install_days", 14),
                area_name=data.get("precinct_name"),
                precinct_id=data.get("precinct_id"),
                raw=data,
            )
            return result.model_dump(exclude_none=True)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Vumatel availability HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return VumatelAvailabilityResponse(
                available=False,
                raw={"error": str(exc), "status_code": exc.response.status_code},
            ).model_dump(exclude_none=True)
        except httpx.RequestError as exc:
            logger.warning("Vumatel availability request error: %s", exc)
            return VumatelAvailabilityResponse(
                available=False,
                raw={"error": str(exc)},
            ).model_dump(exclude_none=True)

    async def place_order(
        self,
        customer_id: str,
        product_code: str,
        address: str,
    ) -> dict:
        """Place a new installation order with Vumatel.

        Returns a dict with:
            order_id (str), status (str), estimated_install_date (str|None),
            fno_reference (str|None)
        """
        logger.info(
            "Vumatel place_order: customer=%s product=%s address=%s",
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
            data = await self._post("/api/v1/orders", payload)
            result = VumatelOrderResponse(
                order_id=data.get("order_id", data.get("id", "")),
                status=data.get("status", "SUBMITTED"),
                estimated_install_date=data.get("estimated_install_date"),
                fno_reference=data.get("vumatel_reference"),
                raw=data,
            )
            return result.model_dump(exclude_none=True)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Vumatel place_order HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return VumatelOrderResponse(
                order_id="",
                status="FAILED",
                raw={"error": str(exc), "status_code": exc.response.status_code},
            ).model_dump(exclude_none=True)
        except httpx.RequestError as exc:
            logger.warning("Vumatel place_order request error: %s", exc)
            return VumatelOrderResponse(
                order_id="",
                status="FAILED",
                raw={"error": str(exc)},
            ).model_dump(exclude_none=True)

    async def get_order_status(self, order_id: str) -> dict:
        """Query the current status of a Vumatel order.

        Returns a dict with:
            status (str), technician_eta (str|None),
            scheduled_date (str|None), completed (bool)
        """
        logger.info("Vumatel get_order_status: %s", order_id)
        try:
            data = await self._get(f"/api/v1/orders/{order_id}")
            result = VumatelOrderStatus(
                status=data.get("status", "UNKNOWN"),
                technician_eta=data.get("technician_eta"),
                scheduled_date=data.get("scheduled_date"),
                completed=data.get("completed", False),
                raw=data,
            )
            return result.model_dump(exclude_none=True)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Vumatel get_order_status HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return VumatelOrderStatus(
                status="ERROR",
                raw={"error": str(exc), "status_code": exc.response.status_code},
            ).model_dump(exclude_none=True)
        except httpx.RequestError as exc:
            logger.warning("Vumatel get_order_status request error: %s", exc)
            return VumatelOrderStatus(
                status="ERROR",
                raw={"error": str(exc)},
            ).model_dump(exclude_none=True)

    async def provision_service(
        self,
        order_id: str,
        ont_serial: Optional[str] = None,
    ) -> dict:
        """Provision / activate a Vumatel service after physical install.

        Returns a dict with:
            success (bool), circuit_id (str|None), vlan_id (int|None),
            ont_serial (str|None)
        """
        logger.info(
            "Vumatel provision_service: order=%s ont=%s",
            order_id,
            ont_serial,
        )
        payload: dict[str, Any] = {"order_id": order_id}
        if ont_serial:
            payload["ont_serial_number"] = ont_serial
        try:
            data = await self._post("/api/v1/services/provision", payload)
            result = VumatelProvisionResponse(
                success=data.get("status", "").upper() in ("PROVISIONED", "ACTIVE"),
                circuit_id=data.get("circuit_id"),
                vlan_id=data.get("vlan_id"),
                ont_serial=data.get("ont_serial_number", ont_serial),
                raw=data,
            )
            return result.model_dump(exclude_none=True)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Vumatel provision_service HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return VumatelProvisionResponse(
                success=False,
                raw={"error": str(exc), "status_code": exc.response.status_code},
            ).model_dump(exclude_none=True)
        except httpx.RequestError as exc:
            logger.warning("Vumatel provision_service request error: %s", exc)
            return VumatelProvisionResponse(
                success=False,
                raw={"error": str(exc)},
            ).model_dump(exclude_none=True)
