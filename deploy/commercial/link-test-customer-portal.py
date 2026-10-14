"""User-authorised pilot association: existing test login, existing same-tenant customer."""
import asyncio
import json
import os
import httpx
from sqlalchemy import text
from services.common.db import get_engine
from services.common.internal_auth import sign_headers
from services.admin.supabase_sync import get_client

email = os.getenv("CUSTOMER_PORTAL_EMAIL", "test@omnidome.local").strip().lower()
assert email in {"test@omnidome.local", "burnibraai@gmail.com"}, "Only the user-requested pilot logins are supported"

with get_engine().connect() as connection:
    user = connection.execute(text("SELECT id,tenant_id FROM users WHERE lower(email)=:email AND is_active AND supabase_user_id IS NOT NULL"), {"email":email}).first()
    assert user, "The confirmed local test login must already exist"
    existing = connection.execute(text("SELECT customer_id FROM customer_portal_accounts WHERE user_id=:user AND tenant_id=:tenant"),
        {"user":str(user.id),"tenant":str(user.tenant_id)}).scalar()
    if existing:
        customer = connection.execute(text("SELECT id,account_number FROM customers WHERE id=:id AND tenant_id=:tenant"),
            {"id":str(existing),"tenant":str(user.tenant_id)}).first()
    else:
        customer = connection.execute(text("""SELECT id,account_number FROM customers WHERE tenant_id=:tenant
            ORDER BY CASE WHEN lower(COALESCE(email,'')) LIKE '%test%' OR lower(COALESCE(first_name,'')) LIKE '%test%'
                OR lower(COALESCE(first_name,'')) LIKE '%demo%' THEN 0 ELSE 1 END, created_at, id LIMIT 1"""),
            {"tenant":str(user.tenant_id)}).first()
    assert customer, "No existing CRM customer belongs to this login's tenant"
    client = get_client()
    assert client, "Platform Owner verification requires Supabase admin configuration"
    owners = [item for item in asyncio.run(client.list_users())
        if "platform_admin" in (item.get("app_metadata",{}).get("roles") or []) and item.get("app_metadata",{}).get("is_active",True)]
    assert owners, "A verified Platform Owner is required"
    owner = connection.execute(text("SELECT id FROM users WHERE supabase_user_id=:sid AND is_active"), {"sid":owners[0]["id"]}).scalar()
headers = {"x-user-id":str(owner or owners[0]["id"]),"x-tenant-id":str(user.tenant_id),"x-roles":"platform_admin"}
path="/api/iot/homes/accounts"
response=httpx.post("http://iot:8006"+path,headers={**headers,**sign_headers(headers,"POST",path)},
    json={"customer_id":str(customer.id),"owner_user_id":str(user.id)},timeout=30)
response.raise_for_status()
path="/api/iot/homes/profile"
customer_headers={"x-user-id":str(user.id),"x-tenant-id":str(user.tenant_id),"x-roles":"customer"}
response=httpx.get("http://iot:8006"+path,headers={**customer_headers,**sign_headers(customer_headers,"GET",path)},timeout=30)
response.raise_for_status()
assert response.json()["id"]==str(customer.id)
print(json.dumps({"portal_account_linked":True,"account_number":customer.account_number,"profile_status":response.status_code}))
