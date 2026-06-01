"""Openserve FNO adapter (API-based).

Openserve is South Africa's largest FTTH network operator (Telkom subsidiary).
They expose a partner API for coverage checks, order management, and provisioning.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .api_adapter import APIFNOAdapter

logger = logging.getLogger(__name__)


class OpenserveAdapter(APIFNOAdapter):
    """Openserve-specific API adapter with OAuth2 authentication."""

    def __init__(self, api_key: str, base_url: str = "https://api.openserve.co.za/v2"):
        super().__init__(fno_name="openserve", api_key=api_key, base_url=base_url)
        self._token: str | None = None

    async def _get_headers(self) -> Dict[str, str]:
        """Openserve uses OAuth2 bearer tokens."""
        if not self._token:
            self._token = await self._authenticate()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }

    async def _authenticate(self) -> str:
        """OAuth2 client credentials flow."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.base_url}/oauth/token",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.api_key,
                        "client_secret": self.api_key,  # Openserve uses API key as both
                    },
                )
                if resp.status_code == 200:
                    return resp.json().get("access_token", "")
                logger.error("Openserve auth failed: %s", resp.status_code)
        except Exception as exc:
            logger.error("Openserve auth error: %s", exc)
        return ""

    async def check_availability(self, address: str) -> Dict[str, Any]:
        logger.info("Openserve API coverage check: %s", address)
        try:
            data = await self._get("/coverage/check", {"address": address})
            return {
                "fno": "openserve",
                "available": data.get("available", False),
                "technologies": data.get("technologies", ["GPON"]),
                "area_name": data.get("area_name"),
                "max_speed_mbps": data.get("max_speed_mbps", 1000),
                "adapter_type": "api",
            }
        except Exception as exc:
            logger.warning("Openserve availability check failed: %s", exc)
            return {"fno": "openserve", "available": False, "error": str(exc), "adapter_type": "api"}

    async def place_order(self, customer_data: Dict[str, Any], plan_id: str) -> Dict[str, Any]:
        logger.info("Openserve place order: plan=%s", plan_id)
        payload = {
            "customer": {
                "first_name": customer_data.get("first_name"),
                "last_name": customer_data.get("last_name"),
                "email": customer_data.get("email"),
                "phone": customer_data.get("phone"),
                "id_number": customer_data.get("id_number"),
            },
            "service": {
                "plan_id": plan_id,
                "address": customer_data.get("address"),
            },
        }
        try:
            data = await self._post("/orders", payload)
            return {
                "order_id": data.get("order_id", ""),
                "status": data.get("status", "PENDING"),
                "estimated_days": data.get("estimated_days", 14),
                "adapter_type": "api",
            }
        except Exception as exc:
            return {"status": "FAILED", "error": str(exc), "adapter_type": "api"}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        try:
            data = await self._post(f"/orders/{order_id}/cancel", {})
            return {"status": data.get("status", "CANCELLED"), "adapter_type": "api"}
        except Exception as exc:
            return {"status": "FAILED", "error": str(exc), "adapter_type": "api"}

    async def check_coverage(self, latitude: str, longitude: str) -> Dict[str, Any]:
        try:
            data = await self._get("/coverage/area", {"lat": latitude, "lng": longitude})
            return {
                "available": data.get("available", False),
                "technology": data.get("technology", "GPON"),
                "max_speed_mbps": data.get("max_speed_mbps", 1000),
                "adapter_type": "api",
            }
        except Exception as exc:
            return {"available": False, "error": str(exc), "adapter_type": "api"}

    async def provision_service(self, order_id: str, ont_serial: str | None = None) -> Dict[str, Any]:
        logger.info("Openserve provision: order=%s ont=%s", order_id, ont_serial)
        payload = {"order_id": order_id}
        if ont_serial:
            payload["ont_serial"] = ont_serial
        try:
            data = await self._post("/services/provision", payload)
            return {
                "status": data.get("status", "ACTIVE"),
                "fno_account_id": data.get("service_id", ""),
                "adapter_type": "api",
            }
        except Exception as exc:
            return {"status": "FAILED", "error": str(exc), "adapter_type": "api"}

    async def change_speed(self, fno_account_id: str, new_profile: str) -> Dict[str, Any]:
        try:
            data = await self._put(f"/services/{fno_account_id}/speed", {"profile": new_profile})
            return {
                "status": data.get("status", "UPDATED"),
                "new_profile": new_profile,
                "adapter_type": "api",
            }
        except Exception as exc:
            return {"status": "FAILED", "error": str(exc), "adapter_type": "api"}

    async def suspend_service(self, fno_account_id: str) -> Dict[str, Any]:
        try:
            data = await self._post(f"/services/{fno_account_id}/suspend", {})
            return {"status": data.get("status", "SUSPENDED"), "adapter_type": "api"}
        except Exception as exc:
            return {"status": "FAILED", "error": str(exc), "adapter_type": "api"}

    async def resume_service(self, fno_account_id: str) -> Dict[str, Any]:
        try:
            data = await self._post(f"/services/{fno_account_id}/resume", {})
            return {"status": data.get("status", "ACTIVE"), "adapter_type": "api"}
        except Exception as exc:
            return {"status": "FAILED", "error": str(exc), "adapter_type": "api"}

    async def report_fault(self, fno_account_id: str, description: str) -> Dict[str, Any]:
        try:
            data = await self._post(f"/services/{fno_account_id}/faults", {
                "description": description,
                "priority": "MEDIUM",
            })
            return {
                "ticket_id": data.get("fault_id", ""),
                "status": "OPEN",
                "adapter_type": "api",
            }
        except Exception as exc:
            return {"status": "FAILED", "error": str(exc), "adapter_type": "api"}
