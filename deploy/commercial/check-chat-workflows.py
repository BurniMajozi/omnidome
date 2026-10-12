"""Read-only live checks; invalid requests never persist or execute workflows."""
import json
import uuid
import httpx
from sqlalchemy import text
from services.common.db import get_engine
from services.common.internal_auth import sign_headers
with get_engine().connect() as connection:
    owner = connection.execute(text("SELECT id,tenant_id FROM users WHERE is_active AND is_owner ORDER BY created_at LIMIT 1")).first()
    assert owner, "No active tenant owner"
    tables = connection.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('chat_workflow_attachments','chat_workflow_requests')")).scalar_one()
headers = {"x-tenant-id": str(owner.tenant_id), "x-user-id": str(owner.id), "x-roles": "owner", "x-modules": "admin,agents"}
def request(method, path, body=None, roles=None):
    identity = {**headers, **({"x-roles": roles} if roles else {})}
    return httpx.request(method, "http://agent-orchestrator:8021" + path,
                         headers={**identity, **sign_headers(identity, method, path)}, json=body, timeout=20)
result = {}
result["tables_ready"] = tables == 2
result["workflow_list"] = request("GET", "/api/workflows").status_code == 200
result["private_conversation_lookup"] = request("GET", "/api/chat-workflows/" + str(uuid.uuid4())).status_code == 404
result["design_validation"] = request("POST", "/api/workflows/design", {"prompt": ""}).status_code == 422
result["staff_cannot_design"] = request("POST", "/api/workflows/design", {"prompt": "Summarise my chat"}, "org_user").status_code == 403
result["anonymous_denied"] = httpx.get("http://agent-orchestrator:8021/api/chat-workflows/" + str(uuid.uuid4())).status_code == 401
result["workflow_page"] = httpx.get("http://web:3000/dashboard/admin/workflows", timeout=30).status_code == 200
print(json.dumps(result))
assert all(result.values()), "Chat workflow live check failed"
