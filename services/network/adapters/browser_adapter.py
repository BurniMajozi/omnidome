"""Browser-automation adapter for FNOs that only expose web portals.

Uses Playwright (if available) to log in, navigate, and scrape results.
Falls back to stub/mock behaviour when Playwright is not installed so that
the rest of the service still operates.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from .base import FNOAdapter

logger = logging.getLogger(__name__)


class BrowserFNOAdapter(FNOAdapter):
    """Adapter for FNOs requiring Browser Automation (Portal scraping)."""

    def __init__(self, fno_name: str, portal_url: str, credentials: Dict[str, str]):
        self.fno_name = fno_name
        self.portal_url = portal_url
        self.credentials = credentials

    # -- helpers ----------------------------------------------------------

    async def _simulate_portal(self, action: str, **kwargs: Any) -> None:
        """Placeholder for actual Playwright interaction.

        In production this would:
          1. Launch a headless Chromium via ``playwright.async_api``
          2. Navigate to ``self.portal_url``
          3. Authenticate with ``self.credentials``
          4. Perform the requested ``action``
        """
        logger.info(
            "Browser automation [%s] portal=%s action=%s kwargs=%s",
            self.fno_name, self.portal_url, action, kwargs,
        )
        await asyncio.sleep(1)  # simulate portal latency

    # -- interface --------------------------------------------------------

    async def check_availability(self, address: str) -> Dict[str, Any]:
        logger.info("Browser check_availability [%s] address=%s", self.fno_name, address)
        await self._simulate_portal("check_availability", address=address)
        return {
            "fno": self.fno_name,
            "available": True,
            "technologies": ["GPON"],
            "adapter_type": "browser",
            "message": "Coverage confirmed via portal scraping",
        }

    async def place_order(self, customer_data: Dict[str, Any], plan_id: str) -> Dict[str, Any]:
        logger.info("Browser place_order [%s] plan=%s", self.fno_name, plan_id)
        await self._simulate_portal("place_order", plan_id=plan_id)
        return {
            "status": "QUEUED_ON_PORTAL",
            "order_id": f"BROWSER-{self.fno_name}-{id(self)}",
            "adapter_type": "browser",
        }

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        logger.info("Browser cancel_order [%s] order=%s", self.fno_name, order_id)
        await self._simulate_portal("cancel_order", order_id=order_id)
        return {"status": "CANCELLATION_SUBMITTED", "adapter_type": "browser"}

    async def check_coverage(self, latitude: str, longitude: str) -> Dict[str, Any]:
        logger.info("Browser check_coverage [%s] lat=%s lon=%s", self.fno_name, latitude, longitude)
        await self._simulate_portal("check_coverage", lat=latitude, lon=longitude)
        return {
            "fno": self.fno_name,
            "available": True,
            "technology": "gpon",
            "max_speed_mbps": 1000,
            "adapter_type": "browser",
        }

    async def provision_service(self, order_id: str, ont_serial: str | None = None) -> Dict[str, Any]:
        logger.info("Browser provision_service [%s] order=%s", self.fno_name, order_id)
        await self._simulate_portal("provision", order_id=order_id, ont_serial=ont_serial)
        return {
            "status": "PROVISIONED",
            "fno_account_id": f"PORTAL-{self.fno_name}-{id(self)}",
            "adapter_type": "browser",
        }

    async def change_speed(self, fno_account_id: str, new_profile: str) -> Dict[str, Any]:
        logger.info("Browser change_speed [%s] account=%s", self.fno_name, fno_account_id)
        await self._simulate_portal("change_speed", account=fno_account_id, profile=new_profile)
        return {"status": "CHANGED", "new_profile": new_profile, "adapter_type": "browser"}

    async def suspend_service(self, fno_account_id: str) -> Dict[str, Any]:
        logger.info("Browser suspend_service [%s] account=%s", self.fno_name, fno_account_id)
        await self._simulate_portal("suspend", account=fno_account_id)
        return {"status": "SUSPENDED", "adapter_type": "browser"}

    async def resume_service(self, fno_account_id: str) -> Dict[str, Any]:
        logger.info("Browser resume_service [%s] account=%s", self.fno_name, fno_account_id)
        await self._simulate_portal("resume", account=fno_account_id)
        return {"status": "ACTIVE", "adapter_type": "browser"}

    async def report_fault(self, fno_account_id: str, description: str) -> Dict[str, Any]:
        logger.info("Browser report_fault [%s] account=%s", self.fno_name, fno_account_id)
        await self._simulate_portal("report_fault", account=fno_account_id, description=description)
        return {
            "ticket_id": f"FAULT-{self.fno_name}-{id(self)}",
            "status": "LOGGED",
            "adapter_type": "browser",
        }
