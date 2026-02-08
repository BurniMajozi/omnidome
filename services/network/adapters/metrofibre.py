"""MetroFibre FNO adapter (API-based).

MetroFibre Networx operates a GPON fibre network across South Africa's
major metros.  They provide a REST API for ISP partners.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .api_adapter import APIFNOAdapter

logger = logging.getLogger(__name__)


class MetroFibreAdapter(APIFNOAdapter):
    """MetroFibre Networx API adapter."""

    def __init__(self, api_key: str, base_url: str = "https://api.metrofibre.co.za/v1"):
        super().__init__(fno_name="metrofibre", api_key=api_key, base_url=base_url)

    async def check_availability(self, address: str) -> Dict[str, Any]:
        logger.info("MetroFibre API coverage check: %s", address)
        try:
            data = await self._get("/coverage", {"address": address})
            return {
                "fno": "metrofibre",
                "available": data.get("covered", False),
                "technologies": data.get("technologies", ["GPON"]),
                "area_name": data.get("estate_name"),
                "adapter_type": "api",
            }
        except Exception as exc:
            logger.warning("MetroFibre availability check failed: %s", exc)
            return {"fno": "metrofibre", "available": False, "error": str(exc), "adapter_type": "api"}
