"""Relevant read-only RAG recall; bounded snippets, no credentials or full documents."""
import json
import httpx
from sqlalchemy import text
from services.common.db import get_engine
from services.common.internal_auth import sign_headers

with get_engine().connect() as connection:
    owner = connection.execute(text("SELECT id,tenant_id FROM users WHERE is_owner AND is_active ORDER BY created_at LIMIT 1")).first()
headers = {"x-user-id":str(owner.id), "x-tenant-id":str(owner.tenant_id), "x-roles":"owner"}
path = "/api/v1/recall"
response = httpx.get("http://tenant_memory:8025" + path, headers={**headers, **sign_headers(headers,"GET",path)},
    params={"module":"iot", "q":"HomeDome Home Assistant IoT Imou cameras sensors", "mode":"hybrid", "limit":3, "match":"any"},timeout=90)
response.raise_for_status()
data=response.json()
print(json.dumps({"entries":len(data.get("entries",[])), "knowledge":len(data.get("knowledge",[])), "note":data.get("knowledge_note")}))
