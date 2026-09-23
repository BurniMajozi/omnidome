"""Customer-suppression check for passed-homes import (Ticket 3): a
"normalized" prospect row that matches an existing contact or an active
network service at (roughly) the same address gets marked
status="suppressed_customer" instead -- never create a lead for someone
who's already a customer.

Design: prefetch ALL of the tenant's Contacts + active NetworkServices ONCE
per import (same batching precedent as _process_passed_home_import's
dedup_key prefetch in routes.py), grouped by postal_code, then fuzzy-match
in pure Python via difflib.SequenceMatcher -- not one pg_trgm query per row,
which at up to 2 extra DB round-trips per non-duplicate row would put
Ticket 1's <60s/10k-row acceptance target at real risk.

Every service in this repo shares one physical Postgres database (see
docker-compose.yaml: all services read the same DATABASE_URL), so this
imports services.sales.models.Contact and services.network.models.
NetworkService directly and queries them through fno_intelligence's own
session -- the same established cross-service pattern already used by
routes.py's _notify_affected_customers() and services/crm/routes/
customer_360.py, not an HTTP call to another service.

Matching compares only the STREET segment on both sides (FNOPassedHome.
address_line1 vs the text before Contact.physical_address's first comma),
not the full address string -- candidates are already grouped by exact
postal_code, so most share the same suburb/city text; comparing full
strings would let that shared, non-discriminating portion inflate the
similarity score between genuinely different houses in the same postal
code / on the same street.
"""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Optional
from uuid import UUID

if TYPE_CHECKING:
    # Deferred at runtime (see load() below) so this module stays importable
    # -- and street_segment()/best_match()/check() stay pure-logic testable
    # -- without SQLAlchemy installed, matching passed_homes.py/geocoding.py's
    # convention. `from __future__ import annotations` above makes the
    # AsyncSession type hint on load() a string, never evaluated at runtime.
    from sqlalchemy.ext.asyncio import AsyncSession

# difflib.SequenceMatcher.ratio() scale, not pg_trgm's -- tuned for short SA
# street segments ("14 Protea Ave" vs "14 Protea Avenue"), see tests.
# Deliberately lenient (favors suppressing a real customer's row over
# missing one) per this ticket's "never create a lead for someone already
# a customer" intent.
SIMILARITY_THRESHOLD = 0.6


def street_segment(address: Optional[str]) -> str:
    """The leading, most-discriminating part of a free-text address: the
    text before the first comma, lowercased and whitespace-collapsed."""
    if not address:
        return ""
    return " ".join(address.split(",")[0].split()).lower()


def best_match(address_line1: Optional[str], candidates: list) -> Optional[tuple]:
    """candidates: list of (id, comparison_address) tuples already narrowed
    to the same postal_code. Returns (id, score) for the highest-scoring
    candidate at or above SIMILARITY_THRESHOLD, or None."""
    target = street_segment(address_line1)
    if not target:
        return None
    best = None
    for cid, comparison_address in candidates:
        score = SequenceMatcher(None, target, street_segment(comparison_address)).ratio()
        if score >= SIMILARITY_THRESHOLD and (best is None or score > best[1]):
            best = (cid, score)
    return best


class SuppressionCandidates:
    """Prefetched, postal_code-grouped Contact + active NetworkService
    addresses for one tenant. Build once per import via `load()`, then call
    `check()` per row -- no further DB queries."""

    def __init__(self):
        self.contacts_by_postal: dict = defaultdict(list)
        self.services_by_postal: dict = defaultdict(list)

    @classmethod
    async def load(cls, session: "AsyncSession", tenant_id: UUID) -> "SuppressionCandidates":
        """Prefetch both sources independently. Each is wrapped in its own
        SAVEPOINT (begin_nested()) and caught separately: a service that
        isn't deployed in a given environment yet (no network_services
        table, confirmed missing in local dev when this was built) must not
        take down the whole import over an entirely optional, best-effort
        check -- and without the savepoint, a failed query leaves the
        session's transaction aborted, so every later query on it (the
        actual FNOPassedHome inserts) would fail too, not just this one.
        """
        import logging
        from sqlalchemy import select

        self = cls()

        try:
            from services.sales.models import Contact
            async with session.begin_nested():
                contact_rows = await session.execute(
                    select(Contact.id, Contact.postal_code, Contact.physical_address).where(
                        Contact.tenant_id == tenant_id,
                        Contact.postal_code.isnot(None),
                        Contact.physical_address.isnot(None),
                    )
                )
                for cid, postal_code, physical_address in contact_rows.all():
                    self.contacts_by_postal[postal_code].append((cid, physical_address))
        except Exception as e:
            logging.getLogger("fno_intelligence").warning(
                "Suppression: contacts prefetch failed, skipping contact-based suppression: %s", e
            )

        try:
            from services.network.models import NetworkService
            async with session.begin_nested():
                service_rows = await session.execute(
                    select(NetworkService.id, NetworkService.postal_code, NetworkService.address_line1).where(
                        NetworkService.tenant_id == tenant_id,
                        NetworkService.status == "active",
                    )
                )
                for sid, postal_code, address_line1 in service_rows.all():
                    self.services_by_postal[postal_code].append((sid, address_line1))
        except Exception as e:
            logging.getLogger("fno_intelligence").warning(
                "Suppression: active-services prefetch failed, skipping service-based suppression: %s", e
            )

        return self

    def check(self, *, address_line1: Optional[str], postal_code: Optional[str]) -> Optional[str]:
        """Returns a reject_reason string if this address should be
        suppressed, else None. An active-service match takes priority over
        a contact match in the returned reason when both would hit, since
        it's the stronger "definitely a paying customer" signal (a bare
        Contact record can be an unconverted PROSPECT, not necessarily a
        customer -- see this ticket's design notes)."""
        if not postal_code or not address_line1:
            return None

        if best_match(address_line1, self.services_by_postal.get(postal_code, [])):
            return "existing_active_service"
        if best_match(address_line1, self.contacts_by_postal.get(postal_code, [])):
            return "existing_contact"
        return None
