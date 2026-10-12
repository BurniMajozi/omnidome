"""Read-only company-memory recall with time for a cold local embedding model."""
import json
import httpx
from sqlalchemy import text
from services.common.db import get_engine
from services.common.internal_auth import sign_headers
with get_engine().connect() as db:
    owner=db.execute(text("SELECT id,tenant_id FROM users WHERE is_owner AND is_active ORDER BY created_at LIMIT 1")).first()
headers={"x-tenant-id":str(owner.tenant_id),"x-user-id":str(owner.id),"x-roles":"owner"}
path="/api/v1/recall"
response=httpx.get("http://tenant_memory:8025"+path,headers={**headers,**sign_headers(headers,"GET",path)},
    params={"module":"agents","q":"workflow agent memory","mode":"hybrid","limit":3,"match":"any"},timeout=40)
response.raise_for_status()
data=response.json()
print(json.dumps({"entries":len(data.get("entries",[])),"knowledge":len(data.get("knowledge",[])),"note":data.get("knowledge_note")}))
