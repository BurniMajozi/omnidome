"""Journey Manager — orchestrates the cancel-to-save lifecycle.

When a customer initiates cancellation:
1. Look up customer data (segment, risk score, tenure, usage, etc.)
2. Find the best matching journey(s) using the rule engine
3. Select the offer (primary or fallback based on eligibility)
4. Return the offer to present to the customer
5. Record the cancel event for outcome tracking

When the customer responds (accept/reject):
6. Update the cancel event status
7. Record an outcome for ML feedback loop
8. Apply the offer (discount, plan change, etc.)
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from .rule_engine import find_best_journey


def build_customer_snapshot(
    customer_id: uuid.UUID,
    account_number: str,
    segment: str = "Standard",
    tenure_months: int = 0,
    monthly_spend_zar: Decimal = Decimal("0.00"),
    risk_score: float = 50.0,
    num_support_tickets_30d: int = 0,
    payment_days_overdue: int = 0,
    plan_id: Optional[str] = None,
    plan_type: Optional[str] = None,
    region: Optional[str] = None,
    usage_trend: str = "stable",
    autopay_enabled: bool = True,
    **extra: Any,
) -> dict:
    """Build a standardized customer snapshot for rule evaluation."""
    return {
        "customer_id": str(customer_id),
        "account_number": account_number,
        "segment": segment,
        "tenure_months": tenure_months,
        "monthly_spend_zar": float(monthly_spend_zar),
        "risk_score": risk_score,
        "num_support_tickets_30d": num_support_tickets_30d,
        "payment_days_overdue": payment_days_overdue,
        "plan_id": plan_id,
        "plan_type": plan_type,
        "region": region,
        "usage_trend": usage_trend,
        "autopay_enabled": autopay_enabled,
        **extra,
    }


def evaluate_offer_eligibility(offer: dict, customer: dict) -> bool:
    """Check if a customer is eligible for a specific offer."""
    params = offer.get("parameters", {})
    offer_type = offer.get("offer_type", "")

    # Check max total redemptions
    max_total = offer.get("max_total_redemptions")
    total_used = offer.get("total_redemptions", 0)
    if max_total is not None and total_used >= max_total:
        return False

    # Type-specific eligibility
    if offer_type == "percentage_discount":
        # No additional eligibility beyond rules
        return True

    elif offer_type == "fixed_discount":
        # Customer must have monthly spend above the discount amount
        amount = float(params.get("amount_zar", 0))
        monthly_spend = float(customer.get("monthly_spend_zar", 0))
        return monthly_spend > amount

    elif offer_type == "plan_downgrade":
        # Must have a downgrade path available
        return bool(params.get("target_plan_id"))

    elif offer_type == "service_pause":
        # Only if tenure > 3 months (tenure would be lost otherwise)
        tenure = int(customer.get("tenure_months", 0))
        return tenure >= 3

    elif offer_type == "free_months":
        # Standard eligibility
        return True

    elif offer_type == "personal_outreach":
        # Only high-value customers
        spend = float(customer.get("monthly_spend_zar", 0))
        return spend >= 500.0

    return True


def compute_offer_cost(offer: dict, customer: dict) -> Decimal:
    """Compute the cost of an offer for a customer."""
    params = offer.get("parameters", {})
    offer_type = offer.get("offer_type", "")
    monthly_spend = Decimal(str(customer.get("monthly_spend_zar", "0")))

    try:
        if offer_type == "percentage_discount":
            percent = Decimal(str(params.get("percent", 0)))
            return (monthly_spend * percent / 100).quantize(Decimal("0.01"))

        elif offer_type == "fixed_discount":
            amount = Decimal(str(params.get("amount_zar", 0)))
            return amount

        elif offer_type == "free_months":
            months = int(params.get("months", 0))
            return (monthly_spend * months).quantize(Decimal("0.01"))

        elif offer_type == "plan_downgrade":
            # Cost = difference in plan prices
            new_price = Decimal(str(params.get("new_monthly_price_zar", "0")))
            return (monthly_spend - new_price).quantize(Decimal("0.01"))

    except (ValueError, TypeError):
        pass

    return Decimal("0.00")


def select_best_offer(
    primary_offer: Optional[dict],
    fallback_offer: Optional[dict],
    customer: dict,
) -> Optional[dict]:
    """Select the best offer for a customer.

    Returns the primary offer if customer is eligible, otherwise
    the fallback offer, otherwise None.
    """
    if primary_offer and evaluate_offer_eligibility(primary_offer, customer):
        return primary_offer

    if fallback_offer and evaluate_offer_eligibility(fallback_offer, customer):
        return fallback_offer

    return None


def process_cancel_event(
    customer: dict,
    cancel_reason: Optional[str],
    journeys: list[dict],
    rules_by_journey: dict[str, list[dict]],
    offers: dict[str, dict],
) -> dict:
    """Process a cancel event and return journey + offer recommendation.

    Args:
        customer: customer snapshot (from build_customer_snapshot)
        cancel_reason: optional reason for cancellation
        journeys: active journey dicts with offer_id and fallback_offer_id
        rules_by_journey: journey_id → rules mapping
        offers: offer_id → offer dict mapping

    Returns:
        dict with keys: journey, offer, matched, cost
    """
    cancel_reason_lower = (cancel_reason or "").lower()
    customer["churn_reason"] = cancel_reason_lower

    # Find best matching journey
    best_journey = find_best_journey(customer, journeys, rules_by_journey)

    if not best_journey:
        return {"journey": None, "offer": None, "matched": False, "cost": Decimal("0")}

    journey_id = str(best_journey.get("id", ""))

    # Get offer(s)
    primary_offer_id = str(best_journey.get("offer_id", "")) if best_journey.get("offer_id") else ""
    fallback_offer_id = str(best_journey.get("fallback_offer_id", "")) if best_journey.get("fallback_offer_id") else ""

    primary_offer = offers.get(primary_offer_id) if primary_offer_id else None
    fallback_offer = offers.get(fallback_offer_id) if fallback_offer_id else None

    # Select best eligible offer
    best_offer = select_best_offer(primary_offer, fallback_offer, customer)

    cost = Decimal("0")
    if best_offer:
        cost = compute_offer_cost(best_offer, customer)

    return {
        "journey": best_journey,
        "offer": best_offer,
        "matched": True,
        "cost": cost,
    }


def compute_outcome_result(
    outcome_type: str,           # accepted, rejected, expired
    offer: Optional[dict],
    customer: dict,
    monthly_revenue_before: Decimal,
) -> dict:
    """Compute the result of a customer's decision."""

    if outcome_type == "accepted" and offer:
        params = offer.get("parameters", {})
        offer_type = offer.get("offer_type", "")

        monthly_after = monthly_revenue_before
        discount_cost = Decimal("0")

        if offer_type == "percentage_discount":
            pct = Decimal(str(params.get("percent", 0)))
            discount_cost = (monthly_revenue_before * pct / 100).quantize(Decimal("0.01"))
            monthly_after = (monthly_revenue_before - discount_cost).quantize(Decimal("0.01"))

        elif offer_type == "fixed_discount":
            amount = Decimal(str(params.get("amount_zar", 0)))
            discount_cost = amount
            monthly_after = (monthly_revenue_before - amount).quantize(Decimal("0.01"))

        elif offer_type == "free_months":
            # Revenue preserved but cost incurred
            months = int(params.get("months", 0))
            discount_cost = (monthly_revenue_before * months).quantize(Decimal("0.01"))
            monthly_after = monthly_revenue_before  # They keep paying after free months

        elif offer_type == "plan_downgrade":
            new_price = Decimal(str(params.get("new_monthly_price_zar", "0")))
            monthly_after = new_price
            discount_cost = (monthly_revenue_before - new_price).quantize(Decimal("0.01"))

        elif offer_type == "service_pause":
            # No revenue during pause, but customer retained
            duration = int(params.get("duration_months", 0))
            discount_cost = (monthly_revenue_before * duration).quantize(Decimal("0.01"))
            monthly_after = Decimal("0")

        return {
            "outcome": "accepted",
            "monthly_revenue_after": float(monthly_after),
            "discount_cost_zar": float(discount_cost),
            "retained_90d": None,  # Will be updated later via batch job
            "retained_180d": None,
        }

    elif outcome_type == "rejected":
        return {
            "outcome": "rejected",
            "monthly_revenue_after": None,
            "discount_cost_zar": 0.0,
            "retained_90d": False,
            "retained_180d": False,
        }

    else:  # expired or other
        return {
            "outcome": outcome_type,
            "monthly_revenue_after": None,
            "discount_cost_zar": 0.0,
            "retained_90d": None,
            "retained_180d": None,
        }
