"""Read-only login diagnosis for the account shown in the user's screenshot."""
import asyncio
import json
from sqlalchemy import text
from services.common.db import get_engine
from services.admin.supabase_sync import get_client

email = "test@omnidome.local"
with get_engine().connect() as connection:
    users = connection.execute(text("SELECT id,tenant_id,is_active,supabase_user_id FROM users WHERE lower(email)=:email"), {"email":email}).mappings().all()
    customers = connection.execute(text("SELECT id,tenant_id FROM customers WHERE lower(email)=:email"), {"email":email}).mappings().all()
    homes = connection.execute(text("SELECT count(*) FROM iot_homes WHERE owner_user_id IN (SELECT id FROM users WHERE lower(email)=:email)"), {"email":email}).scalar_one()
print(json.dumps({"local_user_count":len(users),"active_local_users":sum(bool(u["is_active"]) for u in users),
    "supabase_linked_users":sum(bool(u["supabase_user_id"]) for u in users),"crm_customer_count":len(customers),"assigned_home_count":homes}))
client = get_client()
if client:
    matches = [user for user in asyncio.run(client.list_users()) if (user.get("email") or "").lower()==email]
    print(json.dumps({"supabase_account_count":len(matches),"email_confirmed":any(bool(u.get("email_confirmed_at")) for u in matches)}))
else:
    print("Supabase admin lookup is not configured")
