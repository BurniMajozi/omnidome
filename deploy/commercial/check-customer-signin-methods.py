"""Read-only account and provider diagnostics; never reads or prints passwords/tokens."""
import asyncio
import json
import os
import httpx
from sqlalchemy import text
from services.common.db import get_engine
from services.admin.supabase_sync import get_client

addresses = ["test@omnidome.local", "bunibraai@gmail.com", "burnibraai@gmail.com"]

async def inspect():
    client = get_client()
    assert client
    accounts = await client.list_users()
    with get_engine().connect() as connection:
        for email in addresses:
            matched = [u for u in accounts if (u.get("email") or "").lower() == email]
            local = connection.execute(text("SELECT id,is_active,tenant_id FROM users WHERE lower(email)=:email"), {"email":email}).mappings().all()
            linked = connection.execute(text("SELECT count(*) FROM customer_portal_accounts WHERE user_id IN (SELECT id FROM users WHERE lower(email)=:email)"), {"email":email}).scalar_one()
            print(json.dumps({"email":email,"auth_accounts":len(matched),"active_local_users":sum(bool(u["is_active"]) for u in local),
                "portal_links":linked,"auth_providers":[u.get("app_metadata",{}).get("providers",[]) for u in matched],
                "confirmed":[bool(u.get("email_confirmed_at")) for u in matched],"banned":[bool(u.get("banned_until")) for u in matched]}))
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.get(client.url+"/auth/v1/settings", headers={"apikey":os.environ["SUPABASE_ANON_KEY"]})
        r.raise_for_status()
        settings=r.json()
        print(json.dumps({"password_email_enabled":settings.get("external",{}).get("email"),"google_enabled":settings.get("external",{}).get("google"),"signup_disabled":settings.get("disable_signup")}))

asyncio.run(inspect())
