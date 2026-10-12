"""Read-only live editor checks. No saved workflows, agent calls or messages."""
import httpx
from sqlalchemy import text
from services.common.db import get_engine
from services.common.internal_auth import sign_headers
with get_engine().connect() as db:
    owner=db.execute(text("SELECT id,tenant_id FROM users WHERE is_owner AND is_active ORDER BY created_at LIMIT 1")).first()
headers={'x-user-id':str(owner.id),'x-tenant-id':str(owner.tenant_id),'x-roles':'platform_admin'}
def read(path):
    response=httpx.get('http://agent-orchestrator:8021'+path,headers={**headers,**sign_headers(headers,'GET',path)},timeout=30)
    response.raise_for_status();return response.json()
capabilities=read('/api/workflows/capabilities')
assert 'sales.deal.won' in [row['type'] for row in capabilities['events']]
assert 'platform.billing.credits.low' in [row['type'] for row in capabilities['events']]
assert 'condition' in capabilities['node_types'] and not capabilities['loops']
print('Workflow events',len(capabilities['events']),'node types',len(capabilities['node_types']))
sessions=read('/api/workflows/design/sessions')
print('Private design conversation list',isinstance(sessions['data'],list))
response=httpx.get('http://web:3000/dashboard/admin/workflows',timeout=30);response.raise_for_status()
print('Workflow editor HTTP',response.status_code)
