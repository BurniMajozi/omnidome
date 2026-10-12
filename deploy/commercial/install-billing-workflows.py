"""Install approved starter workflows in the primary tenant and verify a labelled notice."""
import uuid
import httpx
from sqlalchemy import text
from services.common.db import get_engine
from services.common.internal_auth import sign_headers

tenant=uuid.UUID("00000000-0000-0000-0000-000000000001")
with get_engine().connect() as db:
    owner=db.execute(text("SELECT id FROM users WHERE tenant_id=:t AND is_active AND is_owner ORDER BY created_at LIMIT 1"),{"t":str(tenant)}).scalar_one_or_none()
if not owner: raise RuntimeError("No active owner in the requested primary tenant; nothing installed")
identity={"x-user-id":str(owner),"x-tenant-id":str(tenant),"x-roles":"owner","x-modules":"admin,agents,billing"}
base="http://agent-orchestrator:8021"

def request(method,path,body=None):
    headers={**identity,**sign_headers(identity,method,path)}
    response=httpx.request(method,base+path,headers=headers,json=body,timeout=60)
    response.raise_for_status()
    return response.json()

result=request("POST","/api/workflows/templates/billing")
assert len(result['data'])==6 and all(item['installed'] for item in result['data'])
for item in result['data']: print("Installed",item['name'],item['status'])
# A clearly labelled manual notification test, not a fabricated live payment event.
workflow=result['data'][0]['workflow_id']
run=request("POST",f"/api/workflows/{workflow}/run",{"input":{"verification":True,"event":{"payload":{"available":"8 test credits"}}}})
assert run['status']=="succeeded",run.get('error')
print("Labelled manual notification verification",run['run_id'],run['status'])
with get_engine().connect() as db:
    notices=db.execute(text("SELECT title FROM notifications WHERE tenant_id=:t AND subject_type='workflow_run' AND subject_id=:r"),{"t":str(tenant),"r":run['run_id']}).scalars().all()
assert notices and all(title.startswith("[TEST]") for title in notices)
print("Owner-only test notifications",len(notices))
