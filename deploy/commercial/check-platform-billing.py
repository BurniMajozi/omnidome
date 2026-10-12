"""Signed read-only checks. Never print credentials or initiate a payment."""
import json
import uuid
import httpx
from sqlalchemy import text
from services.common.db import get_engine
from services.common.internal_auth import sign_headers

with get_engine().connect() as connection:
    tenant = str(connection.execute(text("SELECT id FROM tenants ORDER BY created_at LIMIT 1")).scalar_one())
headers = {"x-tenant-id": tenant, "x-user-id": str(uuid.UUID(int=0)), "x-roles": "platform_admin", "x-modules": "admin,billing,agents,memory"}

def read(base, path, params=None, timeout=30):
    signed = {**headers, **sign_headers(headers, "GET", path)}
    response = httpx.get(base + path, headers=signed, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()

for mode in ("hybrid", "keyword"):
    try:
        memory = read("http://tenant_memory:8025", "/api/v1/recall", {"module": "billing", "q": "platform billing credit pricing", "match": "any", "mode": mode, "limit": 3}, timeout=8)
        print("Memory", mode, json.dumps({"entries": len(memory.get("entries", [])), "knowledge": len(memory.get("knowledge", [])), "note": memory.get("knowledge_note"), "summaries": [str(s.get("summary", ""))[:400] for s in memory.get("summaries", [])]}, default=str))
        break
    except (httpx.HTTPError, ValueError) as error:
        print("Memory", mode, "unavailable", type(error).__name__)
policy = read("http://admin:8013", "/pricing/credits")
print("Credit policy", json.dumps({key: policy.get(key) for key in ("enabled", "minimum_zar", "price_per_credit_zar")}))
for suffix in ("usage", "usage/logs", "pricing/orders", "usage/delivery-controls"):
    body = read("http://admin:8013", f"/tenants/{tenant}/{suffix}")
    print("Endpoint", suffix, "OK", "keys", sorted(body) if isinstance(body, dict) else "list")

with get_engine().connect() as connection:
    owner = connection.execute(text("SELECT id,tenant_id FROM users WHERE is_active AND is_owner ORDER BY created_at LIMIT 1")).first()
if owner:
    headers = {"x-tenant-id": str(owner.tenant_id), "x-user-id": str(owner.id), "x-roles": "owner", "x-modules": "admin,billing"}
    for suffix in ("usage", "usage/logs", "pricing/orders", "usage/delivery-controls"):
        read("http://admin:8013", f"/tenants/{owner.tenant_id}/{suffix}")
        print("Tenant owner endpoint", suffix, "OK")
else:
    print("Tenant owner live check unavailable: no active owner found; test database checks cover this role.")
