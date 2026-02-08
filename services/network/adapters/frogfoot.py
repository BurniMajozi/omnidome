"""Frogfoot FNO adapter (API-based).

Frogfoot Networks operates an open-access fibre network in several
South African cities.  They expose a REST API for ISP partners.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .api_adapter import APIFNOAdapter

logger = logging.getLogger(__name__)


class FrogfootAdapter(APIFNOAdapter):
    """Frogfoot Networks API adapter."""

    def __init__(self, api_key: str, base_url: str = "https://api.frogfoot.com/v2"):
        super().__init__(fno_name="frogfoot", api_key=api_key, base_url=base_url)

    async def check_availability(self, address: str) -> Dict[str, Any]:
        logger.info("Frogfoot API coverage check: %s", address)
        try:
            data = await self._get("/feasibility/check", {"address": address})
            return {
                "fno": "frogfoot",
                "available": data.get("feasible", False),
                "technologies": data.get("technologies", ["GPON"]),
                "adapter_type": "api",
            }
        except Exception as exc:
            logger.warning("Frogfoot availability check failed: %s", exc)
            return {"fno": "frogfoot", "available": False, "error": str(exc), "adapter_type": "api"}
