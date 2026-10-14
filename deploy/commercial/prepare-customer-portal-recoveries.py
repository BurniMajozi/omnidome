"""Operator-only recovery handoff. Output is private; never commit or log its URLs."""
import asyncio
import json
from urllib.parse import urlparse, parse_qs
from services.admin.supabase_sync import get_client

async def prepare():
    client = get_client()
    assert client
    users = await client.list_users()
    links = []
    for email in ["burnibraai@gmail.com", "test@omnidome.local"]:
        assert any((u.get("email") or "").lower()==email for u in users)
        result = await client._req("POST", "/admin/generate_link", json={"type":"recovery","email":email,
            "redirect_to":"http://localhost:3000/auth/reset"})
        link = result.get("action_link") or result.get("properties",{}).get("action_link")
        assert link and urlparse(link).hostname == urlparse(client.url).hostname
        assert parse_qs(urlparse(link).query).get("redirect_to")==["http://localhost:3000/auth/reset"]
        links.append({"email":email,"recovery_url":link})
    print(json.dumps(links))

asyncio.run(prepare())
