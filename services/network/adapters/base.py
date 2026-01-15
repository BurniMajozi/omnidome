from abc import ABC, abstractmethod
from typing import Dict, Any

class FNOAdapter(ABC):
    """Abstract Base Class for FNO Interactions"""
    
    @abstractmethod
    async def check_availability(self, address: str) -> Dict[str, Any]:
        """Check if fibre is available at the given address"""
        pass

    @abstractmethod
    async def place_order(self, customer_data: Dict[str, Any], plan_id: str) -> Dict[str, Any]:
        """Place a new installation or migration order"""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an existing order or service"""
        pass
