"""Read-only live owner check; no household provisioning, messages or camera access."""
import json
import asyncio
import httpx
from sqlalchemy import text
from services.common.db import get_engine
from services.common.internal_auth import sign_headers

with get_engine().connect() as connection:
    owner = connection.execute(text("SELECT id,tenant_id FROM users WHERE is_owner AND is_active ORDER BY created_at LIMIT 1")).first()
headers = {"x-user-id": str(owner.id), "x-tenant-id": str(owner.tenant_id), "x-roles": "owner"}
for path in ["/api/iot/homes", "/api/iot/homes/capabilities"]:
    response = httpx.get("http://iot:8006" + path, headers={**headers, **sign_headers(headers,"GET",path)}, timeout=30)
    data = response.json()
    print(json.dumps({"path": path, "status": response.status_code, "result": len(data) if isinstance(data,list) else data}))
    response.raise_for_status()
response = httpx.get("http://iot:8006/api/iot/homes", timeout=10)
print("Unauthenticated backend status:", response.status_code)
assert response.status_code == 401
from services.admin.supabase_sync import get_client
client = get_client()
if client:
    # Platform ownership is granted in verified Supabase app_metadata, not tenant roles.
    platform_users = [user for user in asyncio.run(client.list_users())
        if "platform_admin" in (user.get("app_metadata", {}).get("roles") or [])
        and user.get("app_metadata", {}).get("is_active", True)]
    assert platform_users, "No verified Platform Owner account is configured"
    platform_user = platform_users[0]
    with get_engine().connect() as connection:
        platform_owner = connection.execute(text("SELECT id,tenant_id FROM users WHERE supabase_user_id=:sid AND is_active"),
            {"sid": platform_user["id"]}).first()
    platform_headers = {"x-user-id": str(platform_owner.id) if platform_owner else platform_user["id"],
        "x-tenant-id": str(platform_owner.tenant_id) if platform_owner else platform_user["app_metadata"]["tenant_id"],
        "x-roles": "platform_admin"}
    platform_path = "/api/iot/homes/capabilities"
    platform_response = httpx.get("http://iot:8006"+platform_path,
        headers={**platform_headers,**sign_headers(platform_headers,"GET",platform_path)},timeout=30)
    platform_response.raise_for_status()
    assert platform_response.json()["can_assign_gateway"] is True
    print("Verified Platform Owner gateway assignment capability: enabled")
path="/api/workflows/capabilities"
response = httpx.get("http://agent-orchestrator:8021"+path,headers={**headers,**sign_headers(headers,"GET",path)},timeout=30)
response.raise_for_status()
data=response.json()
serialized=json.dumps(data)
assert all(event in serialized for event in ["iot.home.offline","iot.home.recovered","iot.support.requested"])
print("HomeDome workflow event catalogue: verified")
