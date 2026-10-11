"""Tenant tax position: is the tenant a VAT vendor, at what rate, and are its prices VAT-inclusive.

South African rules this encodes (SARS, VAT Act 89 of 1991; figures effective 1 April 2026, verified against SARS pages on
2026-10-11, see docs/vat-tax.md):

* Only a registered VAT **vendor** charges VAT. Registration is compulsory when taxable supplies exceed R2.3 million in any
  consecutive 12 months (or are contractually certain to), and voluntary above R120,000. The application is due within
  21 business days of exceeding the threshold. A business below the threshold, or not registered, may trade without VAT.
* A vendor's document is a "Tax invoice" and must carry the supplier's name, address and VAT number, a serial number and date,
  a description, quantity, the value, the VAT charged and the total; a full invoice (above R5,000) also needs the recipient's
  name and address, and their VAT number when the recipient is a vendor. A non-vendor issues a plain "Invoice" with no VAT.
* Prices quoted by a vendor are deemed VAT-inclusive (section 64/65), so VAT-inclusive pricing is the safe default.

The tenant decides whether it charges VAT; OmniDome never assumes it for them once they have saved a profile. Tenants that have
not saved one yet keep the legacy behaviour (15% added on top) and are told to confirm.

Everything here is pure maths plus one profile lookup; money is Decimal and rounds half up to the cent.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional, Sequence

CENT = Decimal("0.01")
ZA = "ZA"
VAT_NUMBER_ZA = re.compile(r"^4\d{9}$")
VAT_NUMBER_OTHER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .-]{2,18}[A-Za-z0-9]$")

# SARS thresholds in force from 1 April 2026 (compulsory R2.3m, voluntary R120,000). SARS administers them although the
# legislation was not yet promulgated when verified, so they are overridable rather than hard-coded.
COMPULSORY_THRESHOLD = Decimal(os.getenv("ZA_VAT_COMPULSORY_THRESHOLD_ZAR", "2300000"))
VOLUNTARY_THRESHOLD = Decimal(os.getenv("ZA_VAT_VOLUNTARY_THRESHOLD_ZAR", "120000"))
APPROACHING_FRACTION = Decimal("0.8")
FULL_INVOICE_ABOVE = Decimal("5000")      # a full (not abridged) tax invoice is required above this consideration


def za_rate_percent() -> Decimal:
    try:
        return Decimal(os.getenv("ZA_VAT_RATE_PERCENT", "15"))
    except Exception:  # noqa: BLE001
        return Decimal("15")


# Only countries whose standard rate is verified are listed with a default. For any other country the tenant enters its own rate.
COUNTRIES = (
    {"code": "ZA", "name": "South Africa", "default_rate_percent": None, "authority": "SARS", "thresholds": True},
    {"code": "OTHER", "name": "Another country", "default_rate_percent": None, "authority": None, "thresholds": False},
)


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class TaxProfile:
    country: str = ZA
    vat_registered: bool = True
    vat_number: Optional[str] = None
    rate_percent: Decimal = Decimal("15")
    prices_include_vat: bool = False
    legal_name: Optional[str] = None
    address: Optional[str] = None
    registered_since: Optional[date] = None
    configured: bool = False          # False = the tenant has not chosen yet: legacy behaviour, and the UI asks them to

    @property
    def rate(self) -> Decimal:
        """VAT as a fraction (0.15). Zero when the tenant does not charge VAT."""
        return (self.rate_percent / Decimal(100)) if self.vat_registered else Decimal(0)

    @property
    def charges_vat(self) -> bool:
        return self.vat_registered and self.rate > 0

    def document_title(self, credit_note: bool = False) -> str:
        if credit_note:
            return "Tax credit note" if self.charges_vat else "Credit note"
        return "Tax invoice" if self.charges_vat else "Invoice"

    def public(self) -> dict:
        return {"configured": self.configured, "country": self.country, "vat_registered": self.vat_registered,
                "vat_number": self.vat_number, "rate_percent": float(self.rate_percent) if self.vat_registered else 0.0,
                "prices_include_vat": self.prices_include_vat, "legal_name": self.legal_name, "address": self.address,
                "registered_since": self.registered_since.isoformat() if self.registered_since else None}


def legacy_profile() -> TaxProfile:
    return TaxProfile(rate_percent=za_rate_percent())


# ---------------------------------------------------------------------------
# Splitting an amount into net / VAT / total
# ---------------------------------------------------------------------------

def split(amount, profile: TaxProfile) -> tuple[Decimal, Decimal, Decimal]:
    """(net, vat, total) for one amount, according to the tenant's tax position.

    * not charging VAT: the amount is the whole price: (amount, 0, amount)
    * VAT-inclusive: the amount is the total the customer pays: net = total / (1 + rate), vat = total - net
    * VAT-exclusive: the amount is the net: vat = net * rate (rounded half up), total = net + vat
    """
    amount = money(amount)
    if not profile.charges_vat:
        return amount, Decimal("0.00"), amount
    if profile.prices_include_vat:
        net = money(amount / (Decimal(1) + profile.rate))
        return net, amount - net, amount
    vat = money(amount * profile.rate)
    return amount, vat, amount + vat


def split_lines(amounts: Sequence, profile: TaxProfile) -> dict:
    """Price several lines as one document. Exclusive: VAT is charged once on the sum (what SARS accepts and what the legacy code
    did). Inclusive: each line's net is carved out of its own total and VAT is whatever remains, so net + VAT is exactly the
    total the customer was quoted and the lines always add up."""
    amounts = [money(a) for a in amounts]
    if not profile.charges_vat or not profile.prices_include_vat:
        subtotal = sum(amounts, Decimal("0.00"))
        _, vat, total = split(subtotal, profile)
        return {"nets": amounts, "subtotal": subtotal, "vat": vat, "total": total}
    nets = [split(a, profile)[0] for a in amounts]
    total = sum(amounts, Decimal("0.00"))
    subtotal = sum(nets, Decimal("0.00"))
    return {"nets": nets, "subtotal": subtotal, "vat": total - subtotal, "total": total}


def line_rate_percent(profile: TaxProfile) -> Decimal:
    """Default per-line VAT percent for the invoice builder: the tenant's rate, or 0 when it does not charge VAT."""
    return (profile.rate_percent if profile.charges_vat else Decimal(0)).quantize(CENT)


# ---------------------------------------------------------------------------
# Validation of what a tenant saves
# ---------------------------------------------------------------------------

class TaxProfileError(ValueError):
    pass


def validate_profile(*, country: str, vat_registered: bool, vat_number: Optional[str], rate_percent: Optional[Decimal],
                     prices_include_vat: bool, legal_name: Optional[str], address: Optional[str],
                     registered_since: Optional[date]) -> TaxProfile:
    country = (country or "").strip().upper()
    if len(country) != 2 or not country.isalpha():
        raise TaxProfileError("country must be a two-letter ISO code")
    legal_name, address = (legal_name or "").strip() or None, (address or "").strip() or None
    number = (vat_number or "").strip().replace(" ", "") or None
    if not vat_registered:
        # Not a vendor: no VAT number on documents, no VAT charged, plain "Invoice".
        return TaxProfile(country=country, vat_registered=False, vat_number=None, rate_percent=Decimal(0),
                          prices_include_vat=prices_include_vat, legal_name=legal_name, address=address, registered_since=None,
                          configured=True)
    if not legal_name or not address:
        raise TaxProfileError("A VAT vendor must give its registered name and address: they are required on every tax invoice")
    if country == ZA:
        if not number or not VAT_NUMBER_ZA.match(number):
            raise TaxProfileError("A South African VAT number is 10 digits and starts with 4")
        rate = za_rate_percent()
        if rate_percent is not None and Decimal(rate_percent) != rate:
            raise TaxProfileError(f"The South African standard VAT rate is {rate.normalize()}%")
    else:
        if not number or not VAT_NUMBER_OTHER.match(number):
            raise TaxProfileError("Enter your VAT / tax registration number")
        if rate_percent is None or not Decimal(0) < Decimal(rate_percent) <= Decimal(30):
            raise TaxProfileError("Enter your country's VAT rate (between 0 and 30%)")
        rate = Decimal(rate_percent)
    return TaxProfile(country=country, vat_registered=True, vat_number=number, rate_percent=rate, prices_include_vat=prices_include_vat,
                      legal_name=legal_name, address=address, registered_since=registered_since, configured=True)


# ---------------------------------------------------------------------------
# Should this tenant be charging VAT? (South Africa)
# ---------------------------------------------------------------------------

def registration_status(profile: TaxProfile, turnover_12m: Decimal, trailing_3m: Decimal) -> dict:
    """Where the tenant stands against SARS's registration thresholds, from the ex-VAT value of what it invoiced.

    `turnover_12m` is the last 12 months of invoiced subtotals (credit notes net off). `trailing_3m` is the last 3 months, used
    to warn when the current run-rate will cross the compulsory threshold within a year (SARS also looks forward)."""
    if profile.country != ZA:
        return {"applicable": False, "status": "not_applicable",
                "message": "VAT registration thresholds are tracked for South Africa only. Check your country's tax authority."}
    turnover_12m = money(turnover_12m)
    run_rate = money(trailing_3m * 4)
    base = {"applicable": True, "turnover_12m_zar": float(turnover_12m), "run_rate_12m_zar": float(run_rate),
            "compulsory_threshold_zar": float(COMPULSORY_THRESHOLD), "voluntary_threshold_zar": float(VOLUNTARY_THRESHOLD),
            "register_within_business_days": 21, "source": "SARS, in force from 1 April 2026"}
    if profile.vat_registered and profile.configured:
        return {**base, "status": "registered",
                "message": "You are registered: charge VAT on every taxable supply and issue tax invoices."}
    if turnover_12m > COMPULSORY_THRESHOLD:
        return {**base, "status": "must_register",
                "message": "Taxable supplies in the last 12 months exceed the compulsory threshold. SARS requires you to apply for VAT "
                           "registration within 21 business days of exceeding it."}
    if run_rate > COMPULSORY_THRESHOLD:
        return {**base, "status": "will_exceed",
                "message": "At your current pace you will pass the compulsory threshold within 12 months. Plan your VAT registration."}
    if turnover_12m >= COMPULSORY_THRESHOLD * APPROACHING_FRACTION:
        return {**base, "status": "approaching",
                "message": "You are within 20% of the compulsory registration threshold."}
    if turnover_12m > VOLUNTARY_THRESHOLD:
        return {**base, "status": "may_register",
                "message": "You are above the voluntary threshold: you may register for VAT if you meet SARS's conditions, but you are not "
                           "required to, and you may keep trading without charging VAT."}
    return {**base, "status": "below_threshold",
            "message": "You are below the voluntary registration threshold. You are not required to register or charge VAT."}


def twelve_month_window(today: date) -> tuple[date, date, date]:
    """(12 months ago, 3 months ago, today) as plain dates for turnover queries."""
    return today - timedelta(days=365), today - timedelta(days=91), today
