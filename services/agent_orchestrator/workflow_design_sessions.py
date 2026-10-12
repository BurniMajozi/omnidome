"""Private persisted designer conversations; no workflows are activated here."""
import json
import uuid
from fastapi import HTTPException
from sqlalchemy import text
from services.common.db import session_scope
DDL="""CREATE TABLE IF NOT EXISTS workflow_design_sessions (
 id uuid PRIMARY KEY,tenant_id uuid NOT NULL,user_id uuid NOT NULL,title text NOT NULL,
 history jsonb NOT NULL DEFAULT '[]', draft jsonb,updated_at timestamptz NOT NULL DEFAULT now())"""
async def ensure(db):
    await db.execute(text("SELECT pg_advisory_xact_lock(7142021)"));await db.execute(text(DDL))
async def read(ctx,session_id):
    async with session_scope() as db:
        await ensure(db)
        row=(await db.execute(text("SELECT id,title,history,draft,updated_at FROM workflow_design_sessions WHERE id=:id AND tenant_id=:t AND user_id=:u"),{"id":str(session_id),"t":str(ctx.tenant_id),"u":str(ctx.user_id)})).mappings().first()
        if not row:raise HTTPException(404,"Design conversation not found")
        return dict(row)
async def listing(ctx):
    async with session_scope() as db:
        await ensure(db)
        return [dict(row) for row in (await db.execute(text("SELECT id,title,updated_at FROM workflow_design_sessions WHERE tenant_id=:t AND user_id=:u ORDER BY updated_at DESC LIMIT 30"),{"t":str(ctx.tenant_id),"u":str(ctx.user_id)})).mappings().all()]
async def append(ctx,session_id,prompt,result):
    async with session_scope() as db:
        await ensure(db)
        if session_id:
            row=(await db.execute(text("SELECT history FROM workflow_design_sessions WHERE id=:id AND tenant_id=:t AND user_id=:u FOR UPDATE"),{"id":str(session_id),"t":str(ctx.tenant_id),"u":str(ctx.user_id)})).mappings().first()
            if not row:raise HTTPException(404,"Design conversation not found")
            history=row["history"] or []
        else:
            session_id=uuid.uuid4();history=[]
            await db.execute(text("INSERT INTO workflow_design_sessions(id,tenant_id,user_id,title) VALUES(:id,:t,:u,:title)"),{"id":str(session_id),"t":str(ctx.tenant_id),"u":str(ctx.user_id),"title":prompt[:120]})
        history=[*history,{"role":"user","content":prompt},{"role":"assistant","content":result["message"]}][-24:]
        await db.execute(text("UPDATE workflow_design_sessions SET history=CAST(:h AS jsonb),draft=CAST(:d AS jsonb),updated_at=now() WHERE id=:id"),{"h":json.dumps(history),"d":json.dumps(result["draft"]),"id":str(session_id)})
        return {**result,"session_id":str(session_id),"history":history[-12:]}
