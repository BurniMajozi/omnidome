"""OmniDome's own VAT position, for the fees OmniDome charges tenants (gateway commission, payout fees).

Everything OmniDome charges is VAT-inclusive: the advertised 6% / 5.5% / 5% is the total the tenant pays, and when OmniDome is
a VAT vendor the VAT it must account for is carved out of that fee (fee x rate / (1 + rate)). The supplier profile is the one
Codex's platform invoicing already keeps (`platform_invoice_supplier`, edited under Admin -> Platform Billing), falling back to the
shipped catalogue default (VAT-registered, 15%).
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


def vat_inside(amount_cents: int, session) -> int:
    """VAT contained in a VAT-inclusive fee of `amount_cents`: 0 unless OmniDome is a VAT vendor."""
    pos = position(session)
    if not pos["registered"] or amount_cents <= 0:
        return 0
    net = (Decimal(amount_cents) / (Decimal(1) + pos["rate"])).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(amount_cents - net)
