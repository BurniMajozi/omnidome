"""Prepare recovery for the user-requested local test account, without sending email.

Run only as an operator. The JSON output contains a one-use credential: pass it
directly to the user's browser, never save it in documentation or application logs.
The password is chosen by the human in the existing OmniDome reset screen.
"""
import asyncio
import json
from urllib.parse import urlparse, parse_qs
from services.admin.supabase_sync import get_client


async def prepare():
    client = get_client()
    assert client, "Supabase admin configuration is required"
    users = await client.list_users()
    assert any("platform_admin" in (user.get("app_metadata",{}).get("roles") or [])
        for user in users), "A verified Platform Owner must exist"
    assert any((user.get("email") or "").lower()=="test@omnidome.local" for user in users), "Test account not found"
    result = await client._req("POST", "/admin/generate_link", json={"type":"recovery",
        "email":"test@omnidome.local", "redirect_to":"http://localhost:3000/auth/reset"})
    link = result.get("action_link") or result.get("properties",{}).get("action_link")
    assert link and urlparse(link).hostname == urlparse(client.url).hostname, "Unexpected recovery destination"
    assert parse_qs(urlparse(link).query).get("redirect_to") == ["http://localhost:3000/auth/reset"], "Recovery redirect was not accepted"
    print(json.dumps({"recovery_url":link}))


asyncio.run(prepare())
