"""FNO adapter package — South African Fibre Network Operator integrations.

Provides a factory function to resolve the correct API client based on FNO name.
Each adapter exposes the same four core methods:
    - check_availability(address)
    - place_order(customer_id, product_code, address)
    - get_order_status(order_id)
    - provision_service(order_id, ont_serial?)
"""

from typing import Any, Dict

from .base import FNOAdapter
from .factory import FNOFactory
from .openserve import OpenserveAPI
from .vumatel import VumatelAPI

# Also export the new concrete API classes so routes can import them directly
__all__ = [
    "FNOAdapter",
    "FNOFactory",
    "VumatelAPI",
    "OpenserveAPI",
    "get_adapter",
]


def get_adapter(fno_name: str, **kwargs: Any) -> Any:
    """Factory: return the correct FNO API adapter by name.

    Args:
        fno_name: FNO identifier (case-insensitive). Supported:
            "vumatel", "openserve", "metrofibre", "frogfoot", "octotel"
        **kwargs: Optional overrides (api_key, base_url, timeout, etc.)

    Returns:
        An instance of the matching adapter class.

    Raises:
        ValueError if *fno_name* is not a recognised FNO.
    """
    key = fno_name.lower().strip()

    if key == "vumatel":
        return VumatelAPI(
            api_key=kwargs.get("api_key"),
            base_url=kwargs.get("base_url"),
            timeout=kwargs.get("timeout", 30.0),
        )

    if key == "openserve":
        return OpenserveAPI(
            api_key=kwargs.get("api_key"),
            base_url=kwargs.get("base_url"),
            timeout=kwargs.get("timeout", 30.0),
        )

    # For other FNOs, fall back to the legacy factory (browser / generic API)
    from .api_adapter import APIFNOAdapter
    from .browser_adapter import BrowserFNOAdapter
    from .metrofibre import MetroFibreAdapter
    from .frogfoot import FrogfootAdapter
    from .octotel import OctotelAdapter

    _LEGACY_MAP: Dict[str, type] = {
        "metrofibre": MetroFibreAdapter,
        "frogfoot": FrogfootAdapter,
        "octotel": OctotelAdapter,
    }

    if key in _LEGACY_MAP:
        cls = _LEGACY_MAP[key]
        # These legacy adapters take (api_key, base_url) in their __init__
        return cls(
            api_key=kwargs.get("api_key", ""),
            base_url=kwargs.get("base_url", ""),
        )

    raise ValueError(
        f"Unknown FNO provider: '{fno_name}'. "
        f"Supported: vumatel, openserve, metrofibre, frogfoot, octotel"
    )
