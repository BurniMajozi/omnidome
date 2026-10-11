"""OmniDome's own VAT position, for the fees OmniDome charges tenants (gateway commission, payout fees).

OmniDome's fees are quoted EXCLUSIVE of VAT: the 6% / 5.5% / 5% commission is the fee before VAT, and when OmniDome is a VAT
vendor the VAT (15%) is added on top, so the tenant pays fee + VAT (6.9% / 6.325% / 5.75% all-in). The supplier profile is the one
Codex's platform invoicing keeps (`platform_invoice_supplier`, edited under Admin -> Platform Billing), falling back to the shipped
catalogue default (VAT-registered, 15%). Unregistered means no VAT is added.
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import text


def position(session) -> dict:
    """{"registered": bool, "rate": Decimal} as of now."""
    from services.common.platform_pricing import catalog
    data = catalog()
    profile = dict(data.get("supplier") or {})
    try:
        with session.begin_nested():
            row = session.execute(text("SELECT profile FROM platform_invoice_supplier WHERE singleton = true")).scalar()
        if row:
            profile = dict(row) if isinstance(row, dict) else dict(__import__("json").loads(row))
    except Exception:  # noqa: BLE001  (table absent in this environment: use the catalogue default)
        pass
    rate = Decimal(str(data.get("tax_policy", {}).get("rate", "0.15")))
    return {"registered": bool(profile.get("vat_registered", False)), "rate": rate}


def vat_on(fee_cents: int, session) -> int:
    """VAT added on top of a VAT-exclusive fee of `fee_cents` (rounded half up); 0 unless OmniDome is a VAT vendor."""
    pos = position(session)
    if not pos["registered"] or fee_cents <= 0:
        return 0
    return int((Decimal(fee_cents) * pos["rate"]).quantize(Decimal(1), rounding=ROUND_HALF_UP))
