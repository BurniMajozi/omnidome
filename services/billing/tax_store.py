"""Load a tenant's tax profile from the database (sync sessions, like the rest of billing)."""

from sqlalchemy import select

from services.billing import tax
from services.billing.models_tax import TaxProfileRow


def profile_for(session, tenant_id) -> tax.TaxProfile:
    """The tenant's saved tax position, or the legacy default (15% added on top, `configured=False`) if it has not chosen yet."""
    row = session.execute(select(TaxProfileRow).where(TaxProfileRow.tenant_id == tenant_id)).scalar_one_or_none()
    if row is None:
        return tax.legacy_profile()
    return tax.TaxProfile(country=row.country, vat_registered=row.vat_registered, vat_number=row.vat_number,
                          rate_percent=row.rate_percent, prices_include_vat=row.prices_include_vat,
                          legal_name=row.legal_name, address=row.address, registered_since=row.registered_since, configured=True)


def profile_for_tenant(tenant_id) -> tax.TaxProfile:
    """Same as profile_for but opens its own short session (for handlers that price lines before opening one)."""
    from services.billing.database import get_session
    with get_session() as session:
        return profile_for(session, tenant_id)


def price_lines(session, tenant_id, amounts) -> dict:
    """Price invoice amounts for this tenant's VAT position: {"nets", "subtotal", "vat", "total"} (see tax.split_lines)."""
    return tax.split_lines(list(amounts), profile_for(session, tenant_id))
