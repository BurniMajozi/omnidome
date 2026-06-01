"""Rule Engine — evaluates journey rules against customer attributes.

Rule format:
  attribute: customer field name (risk_score, segment, tenure_months, etc.)
  operator: comparison operator
  value: comparison value with type

All rules in a rule group are AND'd together.
Multiple rule groups within a journey are OR'd together.
"""

from typing import Any, Optional

# Supported attributes and their expected types
ATTRIBUTE_TYPES = {
    "risk_score": "number",
    "segment": "string",
    "tenure_months": "number",
    "monthly_spend_zar": "number",
    "payment_days_overdue": "number",
    "num_support_tickets_30d": "number",
    "plan_type": "string",
    "region": "string",
    "usage_trend": "string",       # "declining", "stable", "growing"
    "churn_reason": "string",       # why they're cancelling
    "competitor_mention": "boolean",
    "autopay_enabled": "boolean",
}


def _get_nested_attr(obj: dict, attr: str) -> Any:
    """Get attribute from dict, supporting dot notation for nested fields."""
    if "." in attr:
        parts = attr.split(".")
        current = obj
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current
    return obj.get(attr)


def _to_number(value: Any) -> Optional[float]:
    """Safely convert to number."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_string(value: Any) -> Optional[str]:
    """Safely convert to lowercase string."""
    if value is None:
        return None
    return str(value).strip().lower()


def evaluate_rule(customer: dict, rule: dict) -> bool:
    """Evaluate a single rule against customer data.

    Args:
        customer: dict of customer attributes
        rule: dict with keys: attribute, operator, value

    Returns:
        True if customer matches this rule, False otherwise.
    """
    attribute = rule.get("attribute", "")
    operator = rule.get("operator", "")
    value_spec = rule.get("value", {})

    customer_value = _get_nested_attr(customer, attribute)

    # If customer doesn't have this attribute, rule doesn't match
    if customer_value is None:
        return False

    # Resolve the comparison value from the spec
    if isinstance(value_spec, dict):
        if "value" in value_spec:
            compare_value = value_spec["value"]
        elif "values" in value_spec:
            compare_value = value_spec["values"]
        elif "min" in value_spec and "max" in value_spec:
            compare_value = value_spec
        else:
            return False
    else:
        compare_value = value_spec

    expected_type = ATTRIBUTE_TYPES.get(attribute, "string")

    # --- Numeric comparisons ---
    if expected_type == "number":
        c_val = _to_number(customer_value)
        if c_val is None:
            return False

        if operator == "eq":
            return c_val == _to_number(compare_value)
        elif operator == "ne":
            return c_val != _to_number(compare_value)
        elif operator == "gt":
            return c_val > _to_number(compare_value)
        elif operator == "gte":
            return c_val >= _to_number(compare_value)
        elif operator == "lt":
            return c_val < _to_number(compare_value)
        elif operator == "lte":
            return c_val <= _to_number(compare_value)
        elif operator == "between":
            min_val = _to_number(compare_value.get("min"))
            max_val = _to_number(compare_value.get("max"))
            if min_val is None or max_val is None:
                return False
            return min_val <= c_val <= max_val
        elif operator == "in":
            # Check if customer value is in the list
            values = compare_value if isinstance(compare_value, list) else [compare_value]
            return c_val in [_to_number(v) for v in values if _to_number(v) is not None]
        return False

    # --- String comparisons ---
    if expected_type == "string":
        c_val = _to_string(customer_value)
        if c_val is None:
            return False

        if operator == "eq":
            return c_val == _to_string(compare_value)
        elif operator == "ne":
            return c_val != _to_string(compare_value)
        elif operator == "contains":
            return _to_string(compare_value) in c_val
        elif operator == "in":
            values = compare_value if isinstance(compare_value, list) else [compare_value]
            compare_strings = [_to_string(v) for v in values]
            return c_val in compare_strings
        elif operator == "not_in":
            values = compare_value if isinstance(compare_value, list) else [compare_value]
            compare_strings = [_to_string(v) for v in values]
            return c_val not in compare_strings
        return False

    # --- Boolean ---
    if expected_type == "boolean":
        if operator == "eq":
            return bool(customer_value) == bool(compare_value)
        elif operator == "ne":
            return bool(customer_value) != bool(compare_value)
        return False

    return False


def evaluate_rule_group(customer: dict, rules: list[dict]) -> bool:
    """Evaluate all rules in a group (AND logic)."""
    if not rules:
        return True  # Empty rule group matches everyone
    return all(evaluate_rule(customer, rule) for rule in rules if rule.get("is_active", True))


def evaluate_journey_rules(customer: dict, journey_rules: list[dict]) -> bool:
    """Evaluate all rule groups for a journey (OR between groups)."""
    if not journey_rules:
        return True  # No rules = matches everyone

    # Group rules by rule_group field
    groups: dict[int, list[dict]] = {}
    for rule in journey_rules:
        group_id = rule.get("rule_group", 0)
        groups.setdefault(group_id, []).append(rule)

    # OR across groups
    return any(
        evaluate_rule_group(customer, group_rules)
        for group_rules in groups.values()
    )


def find_best_journey(
    customer: dict,
    journeys: list[dict],
    rules_by_journey: dict[str, list[dict]],
) -> Optional[dict]:
    """Find the highest-priority journey for a customer.

    Args:
        customer: customer attribute snapshot
        journeys: list of journey dicts (must have id, priority)
        rules_by_journey: mapping of journey_id → list of rule dicts

    Returns:
        The best matching journey dict, or None.
    """
    matching = []
    for journey in journeys:
        journey_id = str(journey.get("id", ""))
        journey_rules = rules_by_journey.get(journey_id, [])

        if evaluate_journey_rules(customer, journey_rules):
            matching.append(journey)

    if not matching:
        return None

    # Highest priority first
    matching.sort(key=lambda j: j.get("priority", 0), reverse=True)
    return matching[0]
