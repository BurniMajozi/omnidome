"""Generic REST-API adapter for FNOs that expose an API.

Used as the default API-mode adapter when no FNO-specific subclass exists.
FNO-specific subclasses (Vumatel, MetroFibre, etc.) override URL paths and
payload shapes while still leveraging the common httpx session management.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import httpx

from .base import FNOAdapter

logger = logging.getLogger(__name__)


class APIFNOAdapter(FNOAdapter):
    """Adapter for FNOs that provide a REST API."""

    def __init__(self, fno_name: str, api_key: str, base_url: str):
        self.fno_name = fno_name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

    # -- helpers ----------------------------------------------------------

    async def _get(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}{path}", headers=self._headers, params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, payload: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}{path}", headers=self._headers, json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    # -- interface --------------------------------------------------------

    async def check_availability(self, address: str) -> Dict[str, Any]:
        logger.info("API check_availability [%s] address=%s", self.fno_name, address)
        try:
            data = await self._get("/coverage/check", {"address": address})
            return {
                "fno": self.fno_name,
                "available": data.get("available", False),
                "technologies": data.get("technologies", []),
                "adapter_type": "api",
            }
        except httpx.HTTPError as exc:
            logger.warning("API availability check failed for %s: %s", self.fno_name, exc)
            return {"fno": self.fno_name, "available": False, "error": str(exc), "adapter_type": "api"}

    async def place_order(self, customer_data: Dict[str, Any], plan_id: str) -> Dict[str, Any]:
        logger.info("API place_order [%s] plan=%s", self.fno_name, plan_id)
        payload = {"customer": customer_data, "plan_id": plan_id}
        try:
            data = await self._post("/orders", payload)
            return {"status": "SUBMITTED", "order_id": data.get("order_id", ""), "adapter_type": "api"}
        except httpx.HTTPError as exc:
            return {"status": "FAILED", "error": str(exc), "adapter_type": "api"}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        logger.info("API cancel_order [%s] order=%s", self.fno_name, order_id)
        try:
            data = await self._post(f"/orders/{order_id}/cancel")
            return {"status": data.get("status", "CANCELLED"), "adapter_type": "api"}
        except httpx.HTTPError as exc:
            return {"status": "FAILED", "error": str(exc), "adapter_type": "api"}

    async def check_coverage(self, latitude: str, longitude: str) -> Dict[str, Any]:
        logger.info("API check_coverage [%s] lat=%s lon=%s", self.fno_name, latitude, longitude)
        try:
            data = await self._get("/coverage/gps", {"lat": latitude, "lon": longitude})
            return {
                "fno": self.fno_name,
                "available": data.get("available", False),
                "technology": data.get("technology"),
                "max_speed_mbps": data.get("max_speed_mbps"),
                "adapter_type": "api",
            }
        except httpx.HTTPError as exc:
            return {"fno": self.fno_name, "available": False, "error": str(exc), "adapter_type": "api"}

    async def provision_service(self, order_id: str, ont_serial: str | None = None) -> Dict[str, Any]:
        logger.info("API provision_service [%s] order=%s", self.fno_name, order_id)
        payload = {"order_id": order_id}
        if ont_serial:
            payload["ont_serial"] = ont_serial
        try:
            data = await self._post("/services/provision", payload)
            return {
                "status": data.get("status", "PROVISIONED"),
                "fno_account_id": data.get("account_id", ""),
                "adapter_type": "api",
            }
        except httpx.HTTPError as exc:
            return {"status": "FAILED", "error": str(exc), "adapter_type": "api"}

    async def change_speed(self, fno_account_id: str, new_profile: str) -> Dict[str, Any]:
        logger.info("API change_speed [%s] account=%s profile=%s", self.fno_name, fno_account_id, new_profile)
        try:
            data = await self._post(f"/services/{fno_account_id}/speed", {"profile": new_profile})
            return {"status": "CHANGED", "new_profile": new_profile, "adapter_type": "api"}
        except httpx.HTTPError as exc:
            return {"status": "FAILED", "error": str(exc), "adapter_type": "api"}

    async def suspend_service(self, fno_account_id: str) -> Dict[str, Any]:
        logger.info("API suspend_service [%s] account=%s", self.fno_name, fno_account_id)
        try:
            await self._post(f"/services/{fno_account_id}/suspend")
            return {"status": "SUSPENDED", "adapter_type": "api"}
        except httpx.HTTPError as exc:
            return {"status": "FAILED", "error": str(exc), "adapter_type": "api"}

    async def resume_service(self, fno_account_id: str) -> Dict[str, Any]:
        logger.info("API resume_service [%s] account=%s", self.fno_name, fno_account_id)
        try:
            await self._post(f"/services/{fno_account_id}/resume")
            return {"status": "ACTIVE", "adapter_type": "api"}
        except httpx.HTTPError as exc:
            return {"status": "FAILED", "error": str(exc), "adapter_type": "api"}

    async def report_fault(self, fno_account_id: str, description: str) -> Dict[str, Any]:
        logger.info("API report_fault [%s] account=%s", self.fno_name, fno_account_id)
        try:
            data = await self._post(
                f"/services/{fno_account_id}/faults",
                {"description": description},
            )
            return {"ticket_id": data.get("ticket_id", ""), "status": "LOGGED", "adapter_type": "api"}
        except httpx.HTTPError as exc:
            return {"status": "FAILED", "error": str(exc), "adapter_type": "api"}
