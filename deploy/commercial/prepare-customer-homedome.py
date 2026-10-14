"""Link the existing local gateway to the already-authorised customer pilot.

Does not read Home Assistant credentials or devices. The owner connects their
gateway token through HomeDome's encrypted Connection form.
"""
import asyncio
import json
import httpx
from sqlalchemy import text
from services.common.db import get_engine
from services.common.internal_auth import sign_headers
from services.admin.supabase_sync import get_client

with get_engine().connect() as connection:
    customer = connection.execute(text("""SELECT u.id AS user_id,u.tenant_id,a.customer_id FROM users u
        JOIN customer_portal_accounts a ON a.user_id=u.id AND a.tenant_id=u.tenant_id
        WHERE lower(u.email)='burnibraai@gmail.com' AND u.is_active""")).first()
    assert customer, "The authorised customer's verified portal account must exist"
    home = connection.execute(text(
        "SELECT id FROM iot_homes WHERE tenant_id=:tenant AND customer_id=:customer AND owner_user_id=:user ORDER BY id LIMIT 1"),
        {"tenant":str(customer.tenant_id),"customer":str(customer.customer_id),"user":str(customer.user_id)}).scalar()
    client = get_client()
    assert client
    owners = [u for u in asyncio.run(client.list_users()) if "platform_admin" in (u.get("app_metadata",{}).get("roles") or [])]
    assert owners
    actor = connection.execute(text("SELECT id FROM users WHERE supabase_user_id=:sid AND is_active"), {"sid":owners[0]["id"]}).scalar()
headers={"x-user-id":str(actor or owners[0]["id"]),"x-tenant-id":str(customer.tenant_id),"x-roles":"platform_admin"}
def post(path, body=None):
    response=httpx.post("http://iot:8006"+path,headers={**headers,**sign_headers(headers,"POST",path)},json=body,timeout=30)
    response.raise_for_status()
    return response.json()
if not home:
    home=post("/api/iot/homes",{"name":"HomeDome home","customer_id":str(customer.customer_id),"owner_user_id":str(customer.user_id)})["id"]
post("/api/iot/homes/"+str(home)+"/gateway")
with get_engine().connect() as connection:
    ready=connection.execute(text("SELECT ha_token_encrypted IS NOT NULL FROM iot_homes WHERE id=:home"),{"home":str(home)}).scalar_one()
print(json.dumps({"customer_home_prepared":True,"gateway_assigned":True,"token_configured":bool(ready)}))
