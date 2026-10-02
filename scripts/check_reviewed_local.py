"""Read-only signed smoke checks. Prints statuses/counts, never identities or secrets."""
import sys
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.common.internal_auth import sign_headers

config = dotenv_values(ROOT / '.env')
engine = create_engine(make_url(config['DATABASE_URL']).set(drivername='postgresql+psycopg2', host='127.0.0.1', port=5432))
tenant = '00000000-0000-0000-0000-000000000001'
with engine.connect() as conn:
    user = conn.execute(text('SELECT id FROM users WHERE tenant_id=:tenant AND is_active=true ORDER BY created_at LIMIT 1'), {'tenant':tenant}).scalar_one()
engine.dispose()
identity = {'x-tenant-id':tenant, 'x-user-id':str(user), 'x-roles':'org_admin', 'x-permissions':'*.read', 'x-modules':'*'}
checks = {
 'finance': (8015, ['/overview','/journal-entries','/trial-balance','/statements','/periods']),
 'communication': (8020, ['/api/v1/channels','/api/v1/channels/summary','/api/v1/tasks','/api/v1/approvals']),
 'billing': (8003, ['/invoices','/payments','/reports/revenue','/reports/aging']),
 'crm': (8001, ['/customers?page_size=1','/leads?status=NEW','/dashboard-summary']),
 'sales': (8002, ['/deals/summary','/commissions/report','/leads/funnel']),
 'lifecycle': (8018, ['/lifecycle/dashboard','/lifecycle/stages']),
 'iot': (8006, ['/api/iot/devices','/api/iot/integrations']),
 'support': (8008, ['/tickets','/reports/fcr-stats']),
 'network': (8005, ['/devices','/radius/accounts']),
 'call_center': (8007, ['/agents','/sessions','/queues/dashboard/summary']),
 'inventory': (8010, ['/products','/stock','/warehouses','/suppliers','/purchase-orders']),
}
failed = []
with httpx.Client(timeout=30, trust_env=False) as client:
    for service in sys.argv[1:] or checks:
        port, paths = checks[service]
        for path in paths:
            headers = dict(identity)
            headers.update(sign_headers(headers, 'GET', urlsplit(path).path, secret=config['INTERNAL_AUTH_SECRET']))
            try:
                response = client.get(f'http://127.0.0.1:{port}{path}', headers=headers)
                info = ''
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data,list): info=f' rows={len(data)}'
                    elif isinstance(data,dict):
                        info=' '+str({key:data[key] for key in ('total','count','won_count','open_count','lost_count') if key in data})
                else:
                    failed.append((service,path,response.status_code))
                print(f'{service} {path}: {response.status_code}{info}',flush=True)
            except Exception as error:
                failed.append((service,path,type(error).__name__))
                print(f'{service} {path}: {type(error).__name__}',flush=True)
        unsigned = client.get(f'http://127.0.0.1:{port}{urlsplit(paths[0]).path}')
        print(f'{service} unsigned: {unsigned.status_code}',flush=True)
        if unsigned.status_code !=401: failed.append((service,'unsigned',unsigned.status_code))
sys.exit(bool(failed))
