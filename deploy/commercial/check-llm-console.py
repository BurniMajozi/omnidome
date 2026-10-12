"""Read-only model console checks; never send prompts, keys or charges."""
import json
import httpx
from sqlalchemy import text
from services.common.db import get_engine
from services.common.internal_auth import sign_headers
with get_engine().connect() as db:
    owner = db.execute(text("SELECT id,tenant_id FROM users WHERE is_owner AND is_active ORDER BY created_at LIMIT 1")).first()
headers={"x-tenant-id":str(owner.tenant_id),"x-user-id":str(owner.id),"x-roles":"platform_admin"}
for path in ('/api/llm-console/capabilities','/api/llm-console','/api/llm-console/choices','/api/llm-console/analytics'):
    response=httpx.get('http://agent-orchestrator:8021'+path,headers={**headers,**sign_headers(headers,'GET',path)},timeout=30)
    response.raise_for_status()
    data=response.json()
    if path=='/api/llm-console':
        assert len(data['config']['profiles'])==3
        assert all('key' not in key for key in data['keys'])
        print('Model slots',json.dumps({'count':3,'enabled':data['config']['enabled'],'key_configured':data['keys'][0]['configured']}))
    elif path.endswith('choices'): print('Tenant choices managed',data['managed'])
    elif path.endswith('analytics'): print('Analytics model groups',len(data['models']))
    else: assert data['platform_owner'] is True; print('Platform Owner recognised')
response=httpx.get('http://web:3000/dashboard/admin/agents',timeout=30)
response.raise_for_status()
print('Agent Manager HTTP',response.status_code)
