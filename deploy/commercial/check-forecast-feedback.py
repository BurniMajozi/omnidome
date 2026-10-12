"""Bounded tenant log diagnostics; print structure and errors, never provider keys."""
import json
from sqlalchemy import text
from services.common.db import get_engine
with get_engine().connect() as db:
    tenant=db.execute(text("SELECT tenant_id FROM users WHERE is_owner AND is_active ORDER BY created_at LIMIT 1")).scalar_one()
    rows=db.execute(text("""SELECT m.role,m.content,m.tool_calls,m.tool_results FROM agent_messages m
      JOIN agent_conversations c ON c.id=m.conversation_id WHERE c.tenant_id=:t AND c.id IN (
        SELECT conversation_id FROM agent_messages WHERE content ILIKE '%forecast%' OR content ILIKE '%Retry Workflow%')
      ORDER BY m.created_at DESC LIMIT 30"""),{'t':str(tenant)}).mappings().all()
    print('Matched forecast conversation messages',len(rows))
    for row in rows:
        calls=row['tool_calls'] or []
        if isinstance(calls,dict):calls=[calls]
        for call in calls:
            function=call.get('function',call);name=function.get('name','')
            if name!='ask_user':continue
            args=function.get('arguments') or call.get('arguments') or {}
            if isinstance(args,str):
                try:args=json.loads(args)
                except ValueError:args={}
            print(json.dumps({'tool':name,'questions':[{'header':q.get('header'),'header_length':len(q.get('header','')),'options':len(q.get('options',[]))} for q in args.get('questions',[])]}))
        content=row['content'] or ''
        if any(word in content.lower() for word in ('1–3 questions','forecast','retry workflow','chronos')):
            print(json.dumps({'role':row['role'],'excerpt':content[:350]}))
    exists=db.execute(text("SELECT to_regclass('forecast_runs')")).scalar()
    if exists:
        print('Forecast queue',json.dumps([dict(row) for row in db.execute(text("SELECT status,count(*) AS count FROM forecast_runs WHERE tenant_id=:t GROUP BY status"),{'t':str(tenant)}).mappings()]))
    if db.execute(text("SELECT to_regclass('tenant_metric_facts')")).scalar():
        rows=db.execute(text("SELECT metric_key,count(*) AS periods,min(period_start) AS first,max(period_start) AS latest FROM tenant_metric_facts WHERE tenant_id=:t AND kind='actual' GROUP BY metric_key ORDER BY metric_key"),{'t':str(tenant)}).mappings().all()
        print('Actual metric history',json.dumps([dict(row) for row in rows],default=str))
