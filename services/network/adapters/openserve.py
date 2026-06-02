"""Openserve FNO adapter — full API/LAY-based integration.

Openserve (Telkom's wholesale fibre arm) uses a LAY (Line Assignment) workflow
for ISP partner integrations.  Coverage checks and order management go through
the Openserve Connect platform via a REST API.

Environment variables:
    OPENSERVE_API_URL   — base URL (default http://openserve-mock:9002)
    OPENSERVE_API_KEY   — bearer token for partner API

The LAY workflow:
    1. Line Availability Check  (is there a spare port at the DSLAM/OLT?)
    2. Place Order              (reserve the line / create LAY reference)
    3. Track Order Status       (monitor through LAY states)
    4. Provision Service        (activate the line, assign VLAN / circuit)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class OpenserveProduct(BaseModel):
    """A single product available at an address on Openserve."""
    code: str
    name: str
    technology: str = "GPON"
    download_mbps: int
    upload_mbps: int
    monthly_price_cents: Optional[int] = None


class OpenserveAvailabilityResponse(BaseModel):
    """Structured response from Openserve line availability check."""
    available: bool
    products: List[OpenserveProduct] = Field(default_factory=list)
    estimated_install_days: int = Field(default=21, ge=1, le=365)
    exchange_code: Optional[str] = None
    port_available: bool = False
    raw: Optional[Dict[str, Any]] = None


class OpenserveOrderResponse(BaseModel):
    """Structured response from Openserve order placement (LAY)."""
    order_id: str
    status: str
    estimated_install_date: Optional[str] = None
    lay_reference: Optional[str] = None  # LAY workflow reference
    raw: Optional[Dict[str, Any]] = None


class OpenserveOrderStatus(BaseModel):
    """Structured response from Openserve order status query."""
    status: str
    technician_eta: Optional[str] = None
    scheduled_date: Optional[str] = None
    lay_state: Optional[str] = None  # LAY-specific state machine value
    completed: bool = False
    raw: Optional[Dict[str, Any]] = None


class OpenserveProvisionResponse(BaseModel):
    """Structured response from Openserve service provisioning."""
    success: bool
    circuit_id: Optional[str] = None
    vlan_id: Optional[int] = None
    line_id: Optional[str] = None  # Openserve line identifier
    raw: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# OpenserveAPI class
# ---------------------------------------------------------------------------


class OpenserveAPI:
    """Async httpx-based client for the Openserve Connect partner API (LAY)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("OPENSERVE_API_KEY", "")
        self.base_url = (
            base_url
            or os.getenv("OPENSERVE_API_URL", "http://openserve-mock:9002")
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
                    "X-Partner-LAY": "true",  # signal LAY workflow
                },
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "OpenserveAPI":
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

    async def _patch(self, path: str, payload: Optional[dict] = None) -> dict:
        client = await self._get_client()
        resp = await client.patch(path, json=payload or {})
        resp.raise_for_status()
        return resp.json()

    # -- LAY workflow helpers -----------------------------------------------

    def _extract_lay_state(self, data: dict) -> Optional[str]:
        """Pull the LAY state from an API response envelope."""
        return (
            data.get("lay_state")
            or data.get("LAYState")
            or (data.get("lay") or {}).get("state")
        )

    def _extract_lay_reference(self, data: dict) -> Optional[str]:
        """Pull the LAY reference number from an API response envelope."""
        return (
            data.get("lay_reference")
            or data.get("LAYReference")
            or (data.get("lay") or {}).get("reference")
        )

    # -- public API methods -------------------------------------------------

    async def check_availability(self, address: str) -> dict:
        """Check if Openserve fibre is available at the given address.

        Uses the LAY line-availability endpoint to determine whether a spare
        port exists on the nearest DSLAM / OLT.

        Returns a dict with:
            available (bool), products (list), estimated_install_days (int),
            exchange_code (str|None), port_available (bool)
        """
        logger.info("Openserve availability check: %s", address)
        try:
            data = await self._get(
                "/api/v1/lay/line-availability",
                params={"address": address},
            )
            products = [
                OpenserveProduct(
                    code=p.get("code", ""),
                    name=p.get("name", ""),
                    technology=p.get("technology", "GPON"),
                    download_mbps=p.get("download_mbps", 0),
                    upload_mbps=p.get("upload_mbps", 0),
                    monthly_price_cents=p.get("monthly_price_cents"),
                )
                for p in data.get("products", [])
            ]
            result = OpenserveAvailabilityResponse(
                available=data.get("available", data.get("feasible", False)),
                products=products,
                estimated_install_days=data.get("estimated_install_days", 21),
                exchange_code=data.get("exchange_code"),
                port_available=data.get("port_available", False),
                raw=data,
            )
            return result.model_dump(exclude_none=True)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Openserve availability HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return OpenserveAvailabilityResponse(
                available=False,
                raw={"error": str(exc), "status_code": exc.response.status_code},
            ).model_dump(exclude_none=True)
        except httpx.RequestError as exc:
            logger.warning("Openserve availability request error: %s", exc)
            return OpenserveAvailabilityResponse(
                available=False,
                raw={"error": str(exc)},
            ).model_dump(exclude_none=True)

    async def place_order(
        self,
        customer_id: str,
        product_code: str,
        address: str,
    ) -> dict:
        """Place a new order via the Openserve LAY workflow.

        Returns a dict with:
            order_id (str), status (str), estimated_install_date (str|None),
            lay_reference (str|None)
        """
        logger.info(
            "Openserve place_order: customer=%s product=%s address=%s",
            customer_id,
            product_code,
            address,
        )
        payload = {
            "customer_id": customer_id,
            "product_code": product_code,
            "service_address": address,
            "workflow": "LAY",
            "order_type": "new_installation",
        }
        try:
            data = await self._post("/api/v1/lay/orders", payload)
            result = OpenserveOrderResponse(
                order_id=data.get("order_id", data.get("id", "")),
                status=data.get("status", "LAY_SUBMITTED"),
                estimated_install_date=data.get("estimated_install_date"),
                lay_reference=self._extract_lay_reference(data),
                raw=data,
            )
            return result.model_dump(exclude_none=True)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Openserve place_order HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return OpenserveOrderResponse(
                order_id="",
                status="FAILED",
                raw={"error": str(exc), "status_code": exc.response.status_code},
            ).model_dump(exclude_none=True)
        except httpx.RequestError as exc:
            logger.warning("Openserve place_order request error: %s", exc)
            return OpenserveOrderResponse(
                order_id="",
                status="FAILED",
                raw={"error": str(exc)},
            ).model_dump(exclude_none=True)

    async def get_order_status(self, order_id: str) -> dict:
        """Query the current status of an Openserve LAY order.

        Returns a dict with:
            status (str), technician_eta (str|None),
            scheduled_date (str|None), lay_state (str|None), completed (bool)
        """
        logger.info("Openserve get_order_status: %s", order_id)
        try:
            data = await self._get(f"/api/v1/lay/orders/{order_id}")
            result = OpenserveOrderStatus(
                status=data.get("status", "UNKNOWN"),
                technician_eta=data.get("technician_eta"),
                scheduled_date=data.get("scheduled_date"),
                lay_state=self._extract_lay_state(data),
                completed=data.get("completed", False),
                raw=data,
            )
            return result.model_dump(exclude_none=True)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Openserve get_order_status HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return OpenserveOrderStatus(
                status="ERROR",
                raw={"error": str(exc), "status_code": exc.response.status_code},
            ).model_dump(exclude_none=True)
        except httpx.RequestError as exc:
            logger.warning("Openserve get_order_status request error: %s", exc)
            return OpenserveOrderStatus(
                status="ERROR",
                raw={"error": str(exc)},
            ).model_dump(exclude_none=True)

    async def provision_service(
        self,
        order_id: str,
        ont_serial: Optional[str] = None,
    ) -> dict:
        """Provision / activate an Openserve service via the LAY completion step.

        Returns a dict with:
            success (bool), circuit_id (str|None), vlan_id (int|None),
            line_id (str|None)
        """
        logger.info(
            "Openserve provision_service: order=%s ont=%s",
            order_id,
            ont_serial,
        )
        payload: Dict[str, Any] = {
            "order_id": order_id,
            "lay_action": "COMPLETE",
        }
        if ont_serial:
            payload["ont_serial_number"] = ont_serial
        try:
            data = await self._post(
                "/api/v1/lay/services/provision", payload
            )
            result = OpenserveProvisionResponse(
                success=data.get("status", "").upper()
                in ("PROVISIONED", "ACTIVE", "LAY_COMPLETE"),
                circuit_id=data.get("circuit_id"),
                vlan_id=data.get("vlan_id"),
                line_id=data.get("line_id"),
                raw=data,
            )
            return result.model_dump(exclude_none=True)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Openserve provision_service HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return OpenserveProvisionResponse(
                success=False,
                raw={"error": str(exc), "status_code": exc.response.status_code},
            ).model_dump(exclude_none=True)
        except httpx.RequestError as exc:
            logger.warning("Openserve provision_service request error: %s", exc)
            return OpenserveProvisionResponse(
                success=False,
                raw={"error": str(exc)},
            ).model_dump(exclude_none=True)
