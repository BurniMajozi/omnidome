from .base import FNOAdapter
from .api_adapter import APIFNOAdapter
from .browser_adapter import BrowserFNOAdapter
from typing import Dict, Any

class FNOFactory:
    """Factory to resolve the correct FNO adapter based on config"""
    
    @staticmethod
    def get_adapter(fno_name: str, config: Dict[str, Any]) -> FNOAdapter:
        # Fluid Logic: Use API if key exists, else fallback to Browser
        if config.get("api_key"):
            return APIFNOAdapter(
                fno_name=fno_name,
                api_key=config["api_key"],
                base_url=config.get("base_url", "")
            )
        else:
            return BrowserFNOAdapter(
                fno_name=fno_name,
                portal_url=config.get("portal_url", ""),
                credentials=config.get("credentials", {})
            )
