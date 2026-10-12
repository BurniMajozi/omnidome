"""Owner notifications from verified platform billing events; no AI spend or sends."""
import json
import uuid
from sqlalchemy import text
from services.common.db import session_scope
from services.common.event_bus import notify
from services.common.platform_billing_events import PREFIX

NOTICE_DDL = """CREATE TABLE IF NOT EXISTS workflow_notice_effects (
    run_id uuid NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE, node_id text NOT NULL,
    recipient_id uuid NOT NULL, tenant_id uuid NOT NULL,
    notification_id uuid, PRIMARY KEY(run_id,node_id,recipient_id))"""
NOTICE_FK_DDL = [
    "ALTER TABLE workflow_notice_effects DROP CONSTRAINT IF EXISTS workflow_notice_effects_run_id_fkey",
    "ALTER TABLE workflow_notice_effects ADD CONSTRAINT workflow_notice_effects_run_id_fkey FOREIGN KEY(run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE",
]

def template(key, title, description, body, severity="info"):
    event = PREFIX+key
    return {"key":key,"name":"Platform billing: "+title,"description":description,"trigger_event":event,
        "definition":{"nodes":[
            {"id":"trigger","type":"trigger","name":title,"config":{"event":event}},
            {"id":"owner_notice","type":"notification","name":"Notify tenant owner","config":{
                "title":title,"body":body,"severity":severity,"audience":"owners","link":"/platform-billing"}},
            {"id":"end","type":"end","name":"Done","config":{}}],
            "edges":[{"from":"trigger","to":"owner_notice"},{"from":"owner_notice","to":"end"}]}}

TEMPLATES = [
    template("credits.low","Platform credits running low","Alerts owners once per billing period when spendable credits reach 20% of capacity or 10 credits.",
        "You have {{input.event.payload.available}} spendable platform credits. Review usage by panel or choose a top-up from R50. No card has been charged.","warning"),
    template("credits.exhausted","Platform credit limit reached","Alerts owners when spendable metered capacity is exhausted; no automatic recharge.",
        "Spendable platform credits are exhausted or fully reserved. New metered agent work may be paused. Review usage and top-up options. No automatic charge was made.","critical"),
    template("credits.topped_up","Platform credit top-up confirmed","Confirms credits only after a verified Paystack payment and ledger grant.",
        "{{input.event.payload.credits_added}} credits were added for R{{input.event.payload.total_zar}}. Invoice {{input.event.payload.reference}} is available in Platform Billing & Usage."),
    template("subscription.payment_failed","Platform subscription payment failed","Alerts owners to a verified provider payment-failure event; does not retry or send email.",
        "Paystack reported a failed platform subscription payment. Review the subscription and invoice in Platform Billing & Usage. No retry or customer message was sent.","warning"),
    template("plan.activated","Platform plan activated or renewed","Confirms paid provisioning after commercial validation; includes invoice and intent.",
        "{{input.event.payload.plan_name}} was activated or renewed ({{input.event.payload.intent}}). Invoice {{input.event.payload.reference}}: R{{input.event.payload.total_zar}}. Review your allocation and panel access."),
    template("payment.review","Platform payment needs review","Alerts owners when a payment was received but automatic provisioning was withheld.",
        "Payment for invoice {{input.event.payload.reference}} was received, but the order needs review. Access was not provisioned automatically. Ask the Platform Owner to review the order.","warning"),
]

def workflow_id(tenant,key):
    return uuid.uuid5(uuid.NAMESPACE_URL,f"omnidome:platform-billing-workflow:{tenant}:{key}:v1")

async def install(tenant):
    async with session_scope() as db:
        for item in TEMPLATES:
            await db.execute(text("""INSERT INTO workflows(id,tenant_id,name,description,definition,status,trigger_event,schedule_enabled)
                VALUES(:id,:t,:name,:description,CAST(:definition AS jsonb),'active',:event,false)
                ON CONFLICT(id) DO NOTHING"""), {"id":str(workflow_id(tenant,item["key"])),"t":str(tenant),
                "name":item["name"],"description":item["description"],"definition":json.dumps(item["definition"]),"event":item["trigger_event"]})

async def status(tenant):
    async with session_scope() as db:
        rows=(await db.execute(text("SELECT id,name,status,trigger_event FROM workflows WHERE tenant_id=:t"),{"t":str(tenant)})).mappings().all()
    by_id={str(row["id"]):dict(row) for row in rows}
    return [{"key":item["key"],"name":item["name"],"description":item["description"],"trigger_event":item["trigger_event"],
        "installed":str(workflow_id(tenant,item["key"])) in by_id,
        "workflow_id":str(workflow_id(tenant,item["key"])),"status":by_id.get(str(workflow_id(tenant,item["key"])),{}).get("status")} for item in TEMPLATES]

async def send_notice(tenant,run_id,node_id,config):
    """Transactional, idempotent owner-only bell notification."""
    if config.get("audience","owners")!="owners": raise ValueError("Billing notices must target tenant owners")
    severity=config.get("severity","info")
    if severity not in {"info","warning","critical"}: raise ValueError("Invalid notification severity")
    title=str(config.get("title") or "Workflow notification")[:200]
    body=str(config.get("body") or "")[:2000]
    link=str(config.get("link") or "/platform-billing")
    if not link.startswith("/") or link.startswith("//"): raise ValueError("Notification links must stay inside the platform")
    count=0
    async with session_scope() as db:
        run=(await db.execute(text("SELECT id FROM workflow_runs WHERE id=:r AND tenant_id=:t"),{"r":str(run_id),"t":str(tenant)})).first()
        if not run: raise ValueError("Workflow run does not belong to this tenant")
        owners=(await db.execute(text("""SELECT DISTINCT u.id FROM users u
            LEFT JOIN user_roles ur ON ur.user_id=u.id AND ur.tenant_id=u.tenant_id
            LEFT JOIN roles r ON r.id=ur.role_id
            WHERE u.tenant_id=:t AND u.is_active AND (u.is_owner OR r.name='owner')"""),{"t":str(tenant)})).scalars().all()
        if not owners: raise ValueError("No active tenant owner can receive this billing notice")
        for owner in owners:
            claimed=(await db.execute(text("""INSERT INTO workflow_notice_effects(run_id,node_id,recipient_id,tenant_id)
                VALUES(:r,:n,:u,:t) ON CONFLICT DO NOTHING RETURNING run_id"""),{"r":str(run_id),"n":node_id,"u":str(owner),"t":str(tenant)})).first()
            if not claimed: continue
            notice=await notify(db,tenant,title,body=body,category="billing",severity=severity,link=link,
                recipient_id=owner,source="billing_workflow",subject=("workflow_run",run_id))
            await db.execute(text("UPDATE workflow_notice_effects SET notification_id=:id WHERE run_id=:r AND node_id=:n AND recipient_id=:u"),
                {"id":str(notice),"r":str(run_id),"n":node_id,"u":str(owner)})
            count+=1
    return {"ok":True,"notifications_created":count,"audience":"owners"}
