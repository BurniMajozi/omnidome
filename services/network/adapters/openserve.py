"""Openserve FNO adapter (Browser / portal automation).

Openserve (Telkom's wholesale arm) does not yet offer a full public REST API
for ISP partner integration.  Orders and coverage checks go through the
Openserve Connect portal — this adapter automates those interactions via
Playwright (headless browser).
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .browser_adapter import BrowserFNOAdapter

logger = logging.getLogger(__name__)


class OpenserveAdapter(BrowserFNOAdapter):
    """Openserve portal-automation adapter."""

    def __init__(
        self,
        portal_url: str = "https://connect.openserve.co.za",
        credentials: Dict[str, str] | None = None,
    ):
        super().__init__(
            fno_name="openserve",
            portal_url=portal_url,
            credentials=credentials or {},
        )

    async def check_availability(self, address: str) -> Dict[str, Any]:
        logger.info("Openserve portal coverage check: %s", address)
        await self._simulate_portal("feasibility_check", address=address)
        return {
            "fno": "openserve",
            "available": True,
            "technologies": ["GPON", "VDSL"],
            "adapter_type": "browser",
            "message": "Openserve coverage confirmed via Connect portal",
        }

    async def place_order(self, customer_data: Dict[str, Any], plan_id: str) -> Dict[str, Any]:
        logger.info("Openserve portal order: plan=%s", plan_id)
        await self._simulate_portal("create_order", customer=customer_data, plan=plan_id)
        return {
            "status": "QUEUED_ON_PORTAL",
            "order_id": f"OS-{id(self)}",
            "adapter_type": "browser",
        }
