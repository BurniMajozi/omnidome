# Sales — Lifecycle Bridge Patch
#
# In services/sales/main.py, modify these routes to call the lifecycle service:
#
# 1. At top of file, add:
#    LIFECYCLE_URL = os.getenv("LIFECYCLE_SERVICE_URL", "http://lifecycle:8018")
#
# 2. In close_deal_won() (after commission insert, before _dispatch_provisioning),
#    add a call to the lifecycle from-sale bridge:
#
#    lifecycle_payload = {
#        "tenant_id": str(tenant_id),
#        "customer_id": str(deal["contact_id"]),
#        "deal_id": str(deal_id),
#        "agent_id": str(deal["agent_id"]) if deal["agent_id"] else None,
#        "plan": str(deal["package_id"]) if deal["package_id"] else None,
#        "monthly_recurring_revenue": float(deal["value_zar"] or 0) / 12,
#        "lead_id": str(deal["lead_id"]) if deal["lead_id"] else None,
#    }
#    try:
#        with httpx.Client(timeout=5) as client:
#            client.post(
#                f"{LIFECYCLE_URL}/lifecycle/from-sale",
#                json=lifecycle_payload,
#                headers={"X-Tenant-Id": str(tenant_id)},
#            )
#    except Exception:
#        pass  # Don't fail the sale if lifecycle is down
#
# 3. In close_deal_lost(), optionally record the loss:
#    lifecycle_payload = {
#        "tenant_id": str(tenant_id),
#        "customer_id": str(deal["contact_id"]),
#        "to_stage": "Closed Lost",
#        "reason": reason,
#        "trigger_source": "sale",
#    }
#
# This ensures every deal close (won/lost) automatically updates the customer
# lifecycle record without any manual intervention.
