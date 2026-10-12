"""Tenant-scoped workflow tools; execution is approval gated, editing is not exposed."""
import hashlib
import json
import uuid
from sqlalchemy import select
from services.common.db import session_scope
from services.agent_orchestrator.models import Workflow

WORKFLOW_TOOLS = frozenset({"workflows.list","workflows.run"})

def definition_hash(workflow):
    return hashlib.sha256(json.dumps(workflow.definition or {},sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

async def freeze_arguments(session,tenant_id,arguments):
    try: ident=uuid.UUID(str(arguments.get("workflow_id")))
    except (TypeError,ValueError): raise ValueError("A valid workflow_id is required")
    wf=(await session.execute(select(Workflow).where(Workflow.id==ident,Workflow.tenant_id==uuid.UUID(str(tenant_id))))).scalar_one_or_none()
    if not wf or wf.status!="active": raise ValueError("An active workflow in this tenant is required")
    input_data=arguments.get("input",{})
    if not isinstance(input_data,dict) or len(json.dumps(input_data,default=str))>50000:
        raise ValueError("Workflow input must be an object under 50 KB")
    return {"workflow_id":str(ident),"input":input_data,"expected_definition_hash":definition_hash(wf),
            "workflow_definition":wf.definition,
            "workflow_name":wf.name,"step_summary":[{"id":n.get("id"),"type":n.get("type"),"name":n.get("name")} for n in (wf.definition or {}).get("nodes",[])][:50]}

async def run_tool(name,arguments,tenant_id,user_id):
    if not tenant_id or not user_id: return {"success":False,"error":"Verified tenant and user identity are required"}
    try:
        tenant=uuid.UUID(str(tenant_id));user=uuid.UUID(str(user_id))
        if name=="workflows.list":
            async with session_scope() as s:
                rows=(await s.execute(select(Workflow).where(Workflow.tenant_id==tenant,Workflow.status=="active").order_by(Workflow.name).limit(100))).scalars().all()
                return {"success":True,"data":[{"id":str(w.id),"name":w.name,"description":w.description,"status":w.status,
                    "steps":len((w.definition or {}).get("nodes",[]))} for w in rows]}
        if not arguments.get("expected_definition_hash"):
            return {"success":False,"error":"Run this workflow through the approval gate so its definition is frozen for review"}
        from services.agent_orchestrator.workflow_engine import run_workflow
        result=await run_workflow(uuid.UUID(str(arguments["workflow_id"])),str(tenant),str(user),arguments.get("input",{}),
            trigger="agent",expected_definition_hash=arguments["expected_definition_hash"])
        return {"success":result.get("status") in {"succeeded","awaiting_approval"},"data":result,"error":result.get("error")}
    except (ValueError,KeyError) as exc:
        return {"success":False,"error":str(exc)}
