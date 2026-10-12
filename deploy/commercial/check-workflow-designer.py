"""Request one real, unsaved workflow proposal. No workflow, approval or notification is created."""
import json
import httpx
from sqlalchemy import text
from services.common.db import get_engine
from services.common.internal_auth import sign_headers
with get_engine().connect() as connection:
    owner = connection.execute(text("SELECT id,tenant_id FROM users WHERE is_active AND is_owner ORDER BY created_at LIMIT 1")).first()
    assert owner
headers = {"x-tenant-id": str(owner.tenant_id), "x-user-id": str(owner.id), "x-roles": "owner", "x-modules": "admin,agents"}
path = "/api/workflows/design"
response = httpx.post("http://agent-orchestrator:8021" + path,
    headers={**headers, **sign_headers(headers, "POST", path)}, timeout=125,
    json={"prompt": "When platform credits run low, make a short draft usage review for the owner and add a private owner notification asking them to review Platform Billing. No external emails or charges."})
if response.status_code != 200:
    print(json.dumps({"status": response.status_code, "error": response.json().get("detail")}))
    raise SystemExit(1)
draft = response.json()["draft"]
nodes = draft["definition"]["nodes"]
assert draft["status"] == "draft" and draft["schedule_enabled"] is False
assert all(n["config"].get("draft_only") is True for n in nodes if n["type"] == "agent_invoke")
print(json.dumps({"status": 200, "nodes": len(nodes), "types": [n["type"] for n in nodes],
                  "trigger": draft["trigger_event"], "saved": False, "active": False}))
