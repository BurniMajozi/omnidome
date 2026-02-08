"""Vumatel FNO adapter (API-based).

Vumatel is one of South Africa's largest open-access fibre network operators,
operating primarily in Gauteng, Western Cape and KZN.  They expose a partner
REST API for coverage checks, order management, and provisioning.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .api_adapter import APIFNOAdapter

logger = logging.getLogger(__name__)


class VumatelAdapter(APIFNOAdapter):
    """Vumatel-specific API adapter with custom endpoint paths."""

    def __init__(self, api_key: str, base_url: str = "https://api.vumatel.co.za/v1"):
        super().__init__(fno_name="vumatel", api_key=api_key, base_url=base_url)

    async def check_availability(self, address: str) -> Dict[str, Any]:
        logger.info("Vumatel API coverage check: %s", address)
        try:
            data = await self._get("/feasibility", {"address": address})
            return {
                "fno": "vumatel",
                "available": data.get("feasible", False),
                "technologies": data.get("technologies", ["GPON"]),
                "area_name": data.get("precinct_name"),
                "adapter_type": "api",
            }
        except Exception as exc:
            logger.warning("Vumatel availability check failed: %s", exc)
            return {"fno": "vumatel", "available": False, "error": str(exc), "adapter_type": "api"}

    async def provision_service(self, order_id: str, ont_serial: str | None = None) -> Dict[str, Any]:
        logger.info("Vumatel provision: order=%s ont=%s", order_id, ont_serial)
        payload: Dict[str, Any] = {"order_reference": order_id}
        if ont_serial:
            payload["ont_serial_number"] = ont_serial
        try:
            data = await self._post("/installations/activate", payload)
            return {
                "status": data.get("status", "PROVISIONED"),
                "fno_account_id": data.get("vumatel_account_id", ""),
                "adapter_type": "api",
            }
        except Exception as exc:
            return {"status": "FAILED", "error": str(exc), "adapter_type": "api"}
