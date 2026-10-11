"""Retryable verified-payment grants; serialize workers per tenant across remote calls."""
import asyncio
import logging
import json
from datetime import datetime, timezone
from sqlalchemy import text
from services.common.db import session_scope
from services.common.platform_usage import add_months
from services.common.autumn_client import AutumnClient, AutumnError

logger = logging.getLogger(__name__)


def period(active, now):
    anchor = active["starts_at"]
    index = max(0, (now.year-anchor.year)*12+now.month-anchor.month)
    if add_months(anchor, index) > now:
        index -= 1
    return max(0, index), min(add_months(anchor, max(0, index)+1), active["expires_at"])


async def reconcile(db, active, client, now=None):
    now = now or datetime.now(timezone.utc)
    tenant = str(active["tenant_id"])
    generation = active["generation"]
    old_grants = (await db.execute(text("SELECT id,payload FROM platform_usage_outbox WHERE tenant_id=:t AND generation<>:g AND action='grant' AND status='done'"), {"t": tenant,"g":generation})).mappings().all()
    for grant in old_grants:
        try:
            await client.call("balances.delete", {"customer_id":"tenant_"+tenant,"balance_id":grant["payload"]["balance_id"]})
        except AutumnError as exc:
            if exc.code != "http_404":
                raise
        await db.execute(text("UPDATE platform_usage_outbox SET status='superseded' WHERE id=:id"), {"id":grant["id"]})
    await db.execute(text("UPDATE platform_usage_outbox SET status='superseded' WHERE tenant_id=:t AND generation<>:g AND status='pending'"), {"t":tenant,"g":generation})
    if active["expires_at"] <= now:
        return "expired"
    policy = active["policy"]
    # Never provision zero-quantity or legacy implicit grants.
    if policy.get("legacy") or policy["monthly_credits"] == 0:
        return "no_allowance"
    await client.ensure_feature()
    customer = "tenant_" + tenant
    await client.call("customers.get_or_create", {"customer_id": customer})
    index, expires = period(active, now)
    balance_id = f"od:{tenant}:{generation}:{index}"
    # The local grant receipt is durable and unique. Remote 409 requires proving
    # the existing grant identity/quantity, not treating every conflict as success.
    grant_id = "grant:" + balance_id
    existing = (await db.execute(text("SELECT status FROM platform_usage_outbox WHERE id=:id"), {"id": grant_id})).scalar()
    if existing == "done":
        return "synced"
    payload = {"customer_id": customer, "feature_id": policy["feature_id"], "balance_id": balance_id,
               "included_grant": policy["monthly_credits"], "expires_at": int(expires.timestamp()*1000)}
    await db.execute(text("""INSERT INTO platform_usage_outbox(id,tenant_id,generation,action,payload)
      VALUES(:id,:t,:g,'grant',CAST(:p AS jsonb)) ON CONFLICT(id) DO NOTHING"""),
      {"id": grant_id, "t": tenant, "g": generation, "p": json.dumps(payload)})
    try:
        await client.call("balances.create", payload)
    except AutumnError as exc:
        if exc.code != "http_409":
            raise
        cursor = None
        match = None
        seen = set()
        for _ in range(100):
            query = {"customer_id": customer, "feature_id": policy["feature_id"], "limit": 100,
                     "statuses": ["active", "expired"]}
            if cursor:
                query["start_cursor"] = cursor
            result = await client.call("balances.list", query)
            match = next((row for row in result.get("list", []) if row.get("id") == balance_id), None)
            if match or not result.get("has_more"):
                break
            cursor = result.get("next_cursor")
            if not cursor or cursor in seen:
                raise AutumnError("grant_conflict")
            seen.add(cursor)
        if not match or match.get("included_grant") != policy["monthly_credits"] or match.get("expires_at") != payload["expires_at"]:
            raise AutumnError("grant_conflict")
    await db.execute(text("UPDATE platform_usage_outbox SET status='done',completed_at=now(),error_code=NULL WHERE id=:id"), {"id": grant_id})
    return "synced"


async def tick(client=None):
    client = client or AutumnClient()
    async with session_scope() as db:
        tenants = (await db.execute(text("SELECT tenant_id FROM platform_usage_entitlements"))).scalars().all()
    for tenant in tenants:
        async with session_scope() as db:
            locked = (await db.execute(text("SELECT pg_try_advisory_xact_lock(hashtextextended(:t,715))"), {"t": str(tenant)})).scalar()
            if not locked:
                continue
            active = (await db.execute(text("SELECT * FROM platform_usage_entitlements WHERE tenant_id=:t FOR UPDATE"), {"t": str(tenant)})).mappings().one()
            try:
                async with db.begin_nested():
                    status = await reconcile(db, active, client)
                    if status in {"synced", "expired", "no_allowance"}:
                        await db.execute(text("UPDATE platform_usage_outbox SET status='done',completed_at=now(),error_code=NULL WHERE tenant_id=:t AND generation=:g AND action='reconcile'"), {"t": str(tenant), "g": active["generation"]})
            except AutumnError as exc:
                await db.execute(text("UPDATE platform_usage_outbox SET attempts=attempts+1,error_code=:e WHERE tenant_id=:t AND generation=:g AND action='reconcile'"), {"e": exc.code, "t": str(tenant), "g": active["generation"]})
                logger.warning("Autumn synchronization pending (%s)", exc.code)


async def main():
    while True:
        try:
            await tick()
        except Exception:
            logger.error("Autumn worker tick failed", exc_info=False)
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
