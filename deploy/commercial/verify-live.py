"""Run inside agent-orchestrator; read-only checks, no identity or secrets printed."""
import asyncio
import json
import hashlib
import os
from pathlib import Path
from urllib.parse import urlparse
import httpx
from sqlalchemy import text
from services.common import internal_auth
from services.common.db import session_scope


async def main():
    async with session_scope() as db:
        row=(await db.execute(text("""SELECT u.id,u.tenant_id,r.name FROM users u
            JOIN user_roles ur ON ur.user_id=u.id JOIN roles r ON r.id=ur.role_id
            WHERE u.is_active=true AND r.name='platform_admin' ORDER BY u.created_at LIMIT 1"""))).mappings().first()
        if not row:
            candidates=(await db.execute(text("SELECT id,tenant_id,supabase_user_id FROM users WHERE is_active=true AND supabase_user_id IS NOT NULL LIMIT 100"))).mappings().all()
            key=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
            base=os.getenv("SUPABASE_URL","").rstrip("/")
            if not key or not base:
                raise RuntimeError("Platform Owner verification requires the server's Supabase configuration")
            async with httpx.AsyncClient(timeout=30) as client:
                for candidate in candidates:
                    response=await client.get(base+"/auth/v1/admin/users/"+str(candidate["supabase_user_id"]),
                        headers={"apikey":key,"Authorization":"Bearer "+key})
                    if response.status_code!=200:
                        continue
                    metadata=response.json().get("app_metadata",{})
                    if metadata.get("is_platform_admin") or "platform_admin" in metadata.get("roles",[]):
                        row={**candidate,"name":"platform_admin"}
                        break
            if not row:
                raise RuntimeError("No verified Platform Owner found; no identity was elevated")
    def headers(method,url):
        result={"X-Tenant-Id":str(row["tenant_id"]),"X-User-Id":str(row["id"]),"X-Roles":row["name"]}
        result.update(internal_auth.sign_headers(result,method,urlparse(url).path,internal_auth.get_secret()))
        return result
    async with httpx.AsyncClient(timeout=60) as client:
        base="http://admin:8013/tenants/"+str(row["tenant_id"])
        for path in ("/usage","/usage/costs"):
            url=base+path
            response=await client.get(url,headers=headers("GET",url))
            body=response.json()
            print(json.dumps({"check":path,"status":response.status_code,
                "charges_enabled":body.get("charges_enabled"),
                "margin_available":body.get("margin_available"),
                "draft_provider_rates":len(body.get("draft_rate_card",{}).get("rates",[]))}),flush=True)
            response.raise_for_status()
        url="http://tenant_memory:8025/api/v1/knowledge/context"
        for url in ("http://admin:8013/provider-costs/receipts",base+"/usage/cost-allocations"):
            response=await client.get(url,headers=headers("GET",url))
            print(json.dumps({"check":"supplier evidence read","status":response.status_code,"records":len(response.json()) if response.status_code==200 else None}),flush=True)
            response.raise_for_status()
        url="http://tenant_memory:8025/api/v1/knowledge/context"
        response=await client.post(url,headers=headers("POST",url),json={
            "query":"Platform pricing, marketing provider costs and tenant memory","k":5,"budget_tokens":1000})
        body=response.json()
        print(json.dumps({"check":"RAG context","status":response.status_code,
            "citations":len(body.get("citations",[])),"context_present":bool(body.get("context"))}),flush=True)
        response.raise_for_status()
    for file in ("platform_usage.py","provider_pricing.py","platform-pricing.json"):
        data=Path("/app/services/common/"+file).read_bytes()
        print(json.dumps({"file":file,"sha256":hashlib.sha256(data).hexdigest()}),flush=True)


if __name__=="__main__":
    asyncio.run(main())
