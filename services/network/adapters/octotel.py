"""Octotel FNO adapter (API-based).

Octotel operates a fibre-to-the-home network concentrated in the
Western Cape.  They provide a REST API for ISP partner provisioning.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .api_adapter import APIFNOAdapter

logger = logging.getLogger(__name__)


class OctotelAdapter(APIFNOAdapter):
    """Octotel API adapter."""

    def __init__(self, api_key: str, base_url: str = "https://api.octotel.co.za/v1"):
        super().__init__(fno_name="octotel", api_key=api_key, base_url=base_url)

    async def check_availability(self, address: str) -> Dict[str, Any]:
        logger.info("Octotel API coverage check: %s", address)
        try:
            data = await self._get("/coverage/lookup", {"address": address})
            return {
                "fno": "octotel",
                "available": data.get("fibre_available", False),
                "technologies": data.get("technologies", ["GPON"]),
                "area_name": data.get("zone_name"),
                "adapter_type": "api",
            }
        except Exception as exc:
            logger.warning("Octotel availability check failed: %s", exc)
            return {"fno": "octotel", "available": False, "error": str(exc), "adapter_type": "api"}
