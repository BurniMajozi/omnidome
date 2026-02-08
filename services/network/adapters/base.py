"""Abstract Base Class for FNO (Fibre Network Operator) adapters.

Each South African FNO (Vumatel, Openserve, MetroFibre, Frogfoot, Octotel)
may expose a REST API or only a web portal.  Concrete adapters implement
this interface using whichever integration method the FNO supports.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class FNOAdapter(ABC):
    """Abstract Base Class for FNO Interactions."""

    fno_name: str = "unknown"

    @abstractmethod
    async def check_availability(self, address: str) -> Dict[str, Any]:
        """Check if fibre is available at the given address.

        Returns dict with at least: available (bool), technologies (list[str]).
        """

    @abstractmethod
    async def place_order(
        self, customer_data: Dict[str, Any], plan_id: str
    ) -> Dict[str, Any]:
        """Place a new installation or migration order.

        Returns dict with at least: order_id (str), status (str).
        """

    @abstractmethod
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an existing order.

        Returns dict with at least: status (str).
        """

    @abstractmethod
    async def check_coverage(
        self, latitude: str, longitude: str
    ) -> Dict[str, Any]:
        """Check coverage by GPS coordinates.

        Returns dict with: available (bool), technology (str), max_speed_mbps (int).
        """

    @abstractmethod
    async def provision_service(
        self, order_id: str, ont_serial: str | None = None
    ) -> Dict[str, Any]:
        """Activate / provision a service after physical install.

        Returns dict with: status (str), fno_account_id (str).
        """

    @abstractmethod
    async def change_speed(
        self, fno_account_id: str, new_profile: str
    ) -> Dict[str, Any]:
        """Change the speed profile for an active service.

        Returns dict with: status (str), new_profile (str).
        """

    @abstractmethod
    async def suspend_service(self, fno_account_id: str) -> Dict[str, Any]:
        """Suspend (soft-disconnect) an active service.

        Returns dict with: status (str).
        """

    @abstractmethod
    async def resume_service(self, fno_account_id: str) -> Dict[str, Any]:
        """Resume a previously suspended service.

        Returns dict with: status (str).
        """

    @abstractmethod
    async def report_fault(
        self, fno_account_id: str, description: str
    ) -> Dict[str, Any]:
        """Log a fault / trouble ticket with the FNO.

        Returns dict with: ticket_id (str), status (str).
        """
