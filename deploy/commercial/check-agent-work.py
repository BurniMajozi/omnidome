"""Read-only live checks for the persistent work conversation and billing wallet."""
import json
import uuid
import httpx
from sqlalchemy import text
from services.common.db import get_engine
from services.common.internal_auth import sign_headers
with get_engine().connect() as db:
    owner = db.execute(text("SELECT id,tenant_id FROM users WHERE is_owner AND is_active ORDER BY created_at LIMIT 1")).first()
    latest = db.execute(text("SELECT id FROM agent_jobs WHERE tenant_id=:t ORDER BY created_at DESC LIMIT 1"), {"t":owner.tenant_id}).scalar_one_or_none()
headers = {"x-tenant-id":str(owner.tenant_id),"x-user-id":str(owner.id),"x-roles":"owner","x-modules":"admin,agents"}
def get(path):
    return httpx.get("http://agent-orchestrator:8021"+path,headers={**headers,**sign_headers(headers,"GET",path)},timeout=30)
checks = {}
checks["job_list"] = get("/api/agents/jobs").status_code == 200
checks["budget_read"] = get("/api/agents/budgets/tenant").status_code == 200
checks["billing_wallet"] = get("/api/agents/budgets/credits").status_code == 200
checks["other_thread_hidden"] = get("/api/agents/jobs/"+str(uuid.uuid4())+"/thread").status_code == 404
if latest:
    response=get(f"/api/agents/jobs/{latest}/thread")
    checks["old_conversation_reopens"] = response.status_code == 200 and bool(response.json().get("turns"))
checks["web_page"] = httpx.get("http://web:3000/dashboard/admin/agents",timeout=30).status_code == 200
print(json.dumps(checks))
assert all(checks.values()), "Agent work live check failed"
