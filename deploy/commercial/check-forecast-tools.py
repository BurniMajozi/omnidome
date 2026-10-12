"""Read-only deployed tool and forecast catalogue checks."""
import httpx
from sqlalchemy import text
from services.common.db import get_engine
from services.common.internal_auth import sign_headers
from services.agent_orchestrator.ask_user import Questions,tool_schema
from services.agent_orchestrator.tools import tool_registry
body={'questions':[{'header':'Retry Workflow','question':'Which workflow?','options':[{'label':'A','description':'Active'},{'label':'B','description':'Active'}]}]}
Questions.model_validate(body)
print('Question header limit',tool_schema()['properties']['questions']['items']['properties']['header']['maxLength'])
for name in ('forecast.catalog','forecast.runs','forecast.request'):
    tool=tool_registry.get(name)
    assert tool is not None
    print('Forecast tool',name,'approval',tool.requires_approval)
with get_engine().connect() as db:
    row=db.execute(text('SELECT id,tenant_id FROM users WHERE is_owner AND is_active ORDER BY created_at LIMIT 1')).first()
headers={'x-user-id':str(row.id),'x-tenant-id':str(row.tenant_id),'x-roles':'platform_admin'}
for path in ('/api/fno/bi/metrics/catalog','/api/fno/bi/forecast/runs'):
    response=httpx.get('http://fno_intelligence:8024'+path,headers={**headers,**sign_headers(headers,'GET',path)},timeout=30)
    response.raise_for_status();data=response.json()
    print('Forecast API',path,'records',len(data.get('metrics',data.get('runs',[]))))
