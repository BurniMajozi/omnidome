"""Factory to resolve the correct FNO adapter based on provider name and config.

Uses FNO-specific subclasses when available, falling back to the generic
APIFNOAdapter or BrowserFNOAdapter for unknown providers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .base import FNOAdapter
from .api_adapter import APIFNOAdapter
from .browser_adapter import BrowserFNOAdapter
from .vumatel import VumatelAdapter
from .openserve import OpenserveAdapter
from .metrofibre import MetroFibreAdapter
from .frogfoot import FrogfootAdapter
from .octotel import OctotelAdapter

logger = logging.getLogger(__name__)

# Registry of FNO-specific adapter constructors
_FNO_REGISTRY: Dict[str, type] = {
    "vumatel": VumatelAdapter,
    "openserve": OpenserveAdapter,
    "metrofibre": MetroFibreAdapter,
    "frogfoot": FrogfootAdapter,
    "octotel": OctotelAdapter,
}


class FNOFactory:
    """Factory to resolve the correct FNO adapter based on config."""

    @staticmethod
    def get_adapter(fno_name: str, config: Dict[str, Any]) -> FNOAdapter:
        """Return the best adapter for the given FNO and config.

        Resolution order:
          1. If a registered FNO-specific class exists → use it.
          2. Else if config has ``api_key`` → generic APIFNOAdapter.
          3. Else → generic BrowserFNOAdapter (portal automation).
        """
        fno_key = fno_name.lower()

        if fno_key in _FNO_REGISTRY:
            adapter_cls = _FNO_REGISTRY[fno_key]
            if issubclass(adapter_cls, APIFNOAdapter):
                return adapter_cls(
                    api_key=config.get("api_key", ""),
                    base_url=config.get("base_url", ""),
                )
            else:
                # BrowserFNOAdapter subclass
                return adapter_cls(
                    portal_url=config.get("portal_url", ""),
                    credentials=config.get("credentials", {}),
                )

        # Fallback for unknown FNOs
        if config.get("api_key"):
            logger.info("Using generic API adapter for FNO: %s", fno_name)
            return APIFNOAdapter(
                fno_name=fno_name,
                api_key=config["api_key"],
                base_url=config.get("base_url", ""),
            )

        logger.info("Using generic Browser adapter for FNO: %s", fno_name)
        return BrowserFNOAdapter(
            fno_name=fno_name,
            portal_url=config.get("portal_url", ""),
            credentials=config.get("credentials", {}),
        )

    @staticmethod
    def list_providers() -> list[str]:
        """Return all registered FNO provider names."""
        return list(_FNO_REGISTRY.keys())
