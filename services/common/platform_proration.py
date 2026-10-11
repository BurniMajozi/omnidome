"""Reset the billing cycle, crediting unused prepaid time to the second."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from services.common.platform_usage import add_months

def money(value): return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def change_quote(priced, current, now=None):
    now = now or datetime.now(timezone.utc)
    result = deepcopy(priced)
    end = add_months(now, 12 if priced["period"] == "annually" else 1)
    credit = Decimal("0")
    old = current.get("active_quote")
    if old and current.get("billing_mode") == "payment" and current.get("period_start") and current.get("period_end"):
        start, old_end = (datetime.fromisoformat(current[k]) for k in ("period_start", "period_end"))
        duration = Decimal(str((old_end-start).total_seconds()))
        remaining = Decimal(str(max(0, (old_end-now).total_seconds())))
        if duration > 0:
            credit = money(Decimal(old.get("recurring_net_zar", old["net_zar"])) * min(Decimal(1), remaining/duration))
    balance = Decimal(current.get("credit_net_zar", "0"))
    available = money(credit+balance)
    full = Decimal(priced["net_zar"])
    used = min(full, available)
    net = money(full-used)
    rate = Decimal(priced["vat_rate"])
    total = money(Decimal(priced["total_zar"])-min(Decimal(priced["total_zar"]),money(used*(1+rate))))
    vat = total-net
    result.update(recurring_net_zar=priced["net_zar"], recurring_total_zar=priced["total_zar"],
                  net_zar=str(net), vat_zar=str(vat), total_zar=str(total), amount_cents=int(total*100))
    if used:
        result["lines"].append({"description":"Unused prepaid time and account credit", "quantity":1,"net_zar":str(-used)})
    result["proration"] = {"unused_net_credit":str(credit),"account_net_credit":str(balance),
        "credit_applied":str(used),"credit_remaining":str(money(available-used)),
        "period_start":now.isoformat(),"period_end":end.isoformat(),
        "valid_until":(now+timedelta(minutes=15)).isoformat(),"basis":"new_cycle_less_unused_prepaid_time"}
    return result

def quote_expired(priced, now=None):
    expiry = (priced.get("proration") or {}).get("valid_until")
    return bool(expiry and (now or datetime.now(timezone.utc)) >= datetime.fromisoformat(expiry))
