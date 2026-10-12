"""OmniDome's own trial intake and single-host sales demo calendar."""
import hashlib
import hmac
import html
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import text
from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_session, session_scope
from services.common.internal_auth import get_secret
from services.common.rate_limiter import RateLimiter, trusted_client_ip
from services.common import agentmail
from services.admin import iam

router = APIRouter(tags=["OmniDome onboarding"])
limiter = RateLimiter(max_requests=10, window_seconds=60, key_func=trusted_client_ip)
DDL = [
    """CREATE TABLE IF NOT EXISTS platform_demo_requests (
      id uuid PRIMARY KEY, email text NOT NULL, company text NOT NULL, name text NOT NULL,
      status text NOT NULL DEFAULT 'pending', created_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS platform_trial_requests (
      id uuid PRIMARY KEY, email text NOT NULL UNIQUE, company text NOT NULL, name text NOT NULL,
      status text NOT NULL DEFAULT 'pending', tenant_id uuid REFERENCES tenants(id), created_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS platform_demo_config (
      singleton boolean PRIMARY KEY CHECK(singleton), config jsonb NOT NULL, actor_id uuid NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS platform_demo_bookings (
      id uuid PRIMARY KEY, request_key uuid NOT NULL UNIQUE, host_id uuid NOT NULL REFERENCES users(id),
      name text NOT NULL, email text NOT NULL, company text NOT NULL, starts_at timestamptz NOT NULL,
      ends_at timestamptz NOT NULL, status text NOT NULL DEFAULT 'confirmed', version integer NOT NULL DEFAULT 1,
      token_expires timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS ix_platform_demo_busy ON platform_demo_bookings(host_id,starts_at) WHERE status='confirmed'",
    """CREATE TABLE IF NOT EXISTS platform_demo_notices (
      id uuid PRIMARY KEY, booking_id uuid NOT NULL REFERENCES platform_demo_bookings(id), version integer NOT NULL,
      kind text NOT NULL, due_at timestamptz NOT NULL, status text NOT NULL DEFAULT 'pending',
      claimed_at timestamptz, UNIQUE(booking_id,version,kind))""",
]


class TrialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: str = Field(min_length=3,max_length=254,pattern=r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")
    company: str = Field(min_length=2,max_length=150)
    name: str = Field(min_length=2,max_length=100)


class DemoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    host_id: uuid.UUID
    timezone: str = "Africa/Johannesburg"
    start_hour: int = Field(9,ge=0,le=22)
    end_hour: int = Field(16,ge=1,le=23)
    meeting_url: HttpUrl | None = None


class Booking(TrialRequest):
    starts_at: datetime
    request_key: uuid.UUID


class Manage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    token: str = Field(min_length=32,max_length=128)
    starts_at: datetime | None = None


async def config(db):
    saved = (await db.execute(text("SELECT config FROM platform_demo_config WHERE singleton=true"))).scalar_one_or_none()
    return saved or {"enabled":False}


@router.post("/public/platform/trial-request")
async def trial_request(body: TrialRequest, request: Request, db=Depends(get_async_session)):
    await limiter.check(request)
    await db.execute(text("""INSERT INTO platform_trial_requests(id,email,company,name)
      VALUES(:id,:e,:c,:n) ON CONFLICT(email) DO NOTHING"""),
      {"id":str(uuid.uuid4()),"e":str(body.email).lower(),"c":body.company,"n":body.name})
    return {"status":"requested","message":"OmniDome will review your request and send an invitation. Your 14-day trial begins when the owner accepts their verified invitation."}


@router.get("/platform/onboarding")
async def admin_read(ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await iam.require_platform_admin(ctx,db)
    requests = (await db.execute(text("SELECT * FROM platform_trial_requests ORDER BY created_at DESC LIMIT 100"))).mappings().all()
    bookings = (await db.execute(text("SELECT * FROM platform_demo_bookings WHERE ends_at>now()-interval '7 days' ORDER BY starts_at LIMIT 100"))).mappings().all()
    notices = (await db.execute(text("SELECT booking_id,kind,status FROM platform_demo_notices WHERE status IN ('failed','unknown') LIMIT 100"))).mappings().all()
    demo_requests = (await db.execute(text("SELECT * FROM platform_demo_requests ORDER BY created_at DESC LIMIT 100"))).mappings().all()
    return {"config":await config(db),"requests":[dict(r) for r in requests],"demo_requests":[dict(r) for r in demo_requests],"bookings":[dict(r) for r in bookings],"delivery_issues":[dict(r) for r in notices]}


@router.post("/public/platform/demo/request")
async def request_demo(body: TrialRequest, request: Request, db=Depends(get_async_session)):
    await limiter.check(request)
    # Serialize repeat submissions for this address without revealing other contacts.
    email=body.email.lower()
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:e,7142032))"),{"e":email})
    pending=(await db.execute(text("SELECT 1 FROM platform_demo_requests WHERE email=:e AND status='pending' LIMIT 1"),{"e":email})).first()
    if not pending:
        await db.execute(text("INSERT INTO platform_demo_requests(id,email,company,name) VALUES(:i,:e,:c,:n)"),{"i":str(uuid.uuid4()),"e":email,"c":body.company,"n":body.name})
    return {"status":"requested","message":"Your demo request has been received. OmniDome’s sales team will contact you to arrange a time."}


@router.post("/platform/onboarding/demo-requests/{ident}/contacted")
async def contacted_demo(ident: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await iam.require_platform_admin(ctx,db)
    result=await db.execute(text("UPDATE platform_demo_requests SET status='contacted' WHERE id=:i RETURNING id"),{"i":str(ident)})
    if not result.first(): raise HTTPException(404,"Demo request not found")
    await iam.audit(db,ctx,"platform.demo_request.contacted","demo_request",ident,None,{})
    return {"status":"contacted"}


@router.post("/platform/onboarding/requests/{ident}/provision")
async def provision_request(ident: uuid.UUID, request: Request, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await iam.require_platform_admin(ctx,db)
    row = (await db.execute(text("SELECT * FROM platform_trial_requests WHERE id=:i FOR UPDATE"),{"i":str(ident)})).mappings().first()
    if not row: raise HTTPException(404,"Request not found")
    if row["tenant_id"]: return {"tenant_id":str(row["tenant_id"]),"duplicate":True}
    from services.admin.main import TenantCreate, create_tenant
    result = await create_tenant(TenantCreate(name=row["company"],domain="trial-"+ident.hex[:20]+".omnidome.local",
        owner_email=row["email"],start_platform_trial=True),request,ctx,db)
    await db.execute(text("UPDATE platform_trial_requests SET status='invited',tenant_id=:t WHERE id=:i"),{"t":result["id"],"i":str(ident)})
    return {"tenant_id":result["id"],"owner_invite":result.get("owner_invite")}


@router.put("/platform/onboarding/demo")
async def save_config(body: DemoConfig, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await iam.require_platform_admin(ctx,db)
    try: ZoneInfo(body.timezone)
    except Exception: raise HTTPException(422,"Choose a valid IANA timezone")
    if body.end_hour<=body.start_hour: raise HTTPException(422,"End hour must follow start hour")
    if body.meeting_url and body.meeting_url.scheme!="https": raise HTTPException(422,"Meeting links must use HTTPS")
    await db.execute(text("SELECT pg_advisory_xact_lock(7142030)"))
    host = (await db.execute(text("SELECT id FROM users WHERE id=:u AND is_active=true"),{"u":str(body.host_id)})).first()
    if not host: raise HTTPException(422,"Choose an active OmniDome sales host")
    old = await config(db)
    if old.get("host_id") and old["host_id"]!=str(body.host_id) and (await db.execute(text("SELECT 1 FROM platform_demo_bookings WHERE status='confirmed' AND ends_at>now() LIMIT 1"))).first():
        raise HTTPException(409,"Cancel or complete existing bookings before changing the host")
    await db.execute(text("INSERT INTO platform_demo_config(singleton,config,actor_id) VALUES(true,CAST(:c AS jsonb),:a) ON CONFLICT(singleton) DO UPDATE SET config=excluded.config,actor_id=excluded.actor_id"),{"c":body.model_dump_json(),"a":str(ctx.user_id)})
    await iam.audit(db,ctx,"platform.demo.configure","calendar",None,None,{"enabled":body.enabled,"host_id":str(body.host_id)})
    return body


async def slots(db, day, cfg):
    if not cfg["enabled"]: return []
    if not (await db.execute(text("SELECT 1 FROM users WHERE id=:h AND is_active=true"),{"h":cfg["host_id"]})).first(): return []
    localzone = ZoneInfo(cfg["timezone"])
    now = datetime.now(timezone.utc)
    if day.weekday()>4 or day<now.astimezone(localzone).date() or day>now.astimezone(localzone).date()+timedelta(days=30): return []
    start = datetime.combine(day,datetime.min.time(),localzone)+timedelta(hours=cfg["start_hour"])
    end = datetime.combine(day,datetime.min.time(),localzone)+timedelta(hours=cfg["end_hour"])
    busy = (await db.execute(text("SELECT starts_at,ends_at FROM platform_demo_bookings WHERE host_id=:h AND status='confirmed' AND starts_at<:end AND ends_at>:start"),{"h":cfg["host_id"],"start":start-timedelta(minutes=15),"end":end+timedelta(minutes=15)})).all()
    # The shared staff calendar is checked as well; its writers take the same host lock.
    if (await db.execute(text("SELECT to_regclass('schedule_events')"))).scalar_one_or_none():
        busy += (await db.execute(text("SELECT start_time,end_time FROM schedule_events WHERE user_id=:h AND start_time<:end AND end_time>:start"),{"h":cfg["host_id"],"start":start-timedelta(minutes=15),"end":end+timedelta(minutes=15)})).all()
    result=[]
    while start+timedelta(minutes=30)<=end:
        utc=start.astimezone(timezone.utc)
        if utc>=now+timedelta(hours=2) and not any(utc<e+timedelta(minutes=15) and utc+timedelta(minutes=45)>s for s,e in busy): result.append(utc)
        start+=timedelta(minutes=45)
    return result


@router.get("/public/platform/demo")
async def public_demo(day: date | None = None, db=Depends(get_async_session)):
    cfg=await config(db)
    return {"enabled":cfg["enabled"],"timezone":cfg.get("timezone","Africa/Johannesburg"),"duration_minutes":30,
            "slots":await slots(db,day,cfg) if day else []}


def management_token(row):
    payload=str(row["id"])+":"+row["token_expires"].isoformat()
    return hmac.new(get_secret().encode(),payload.encode(),hashlib.sha256).hexdigest()


async def queue_notices(db, row, kind):
    now=datetime.now(timezone.utc)
    for label,due in [(kind,now)]+([( "24h",row["starts_at"]-timedelta(hours=24)),("1h",row["starts_at"]-timedelta(hours=1))] if kind!="cancelled" else []):
        if label!=kind and due<=now: continue
        await db.execute(text("INSERT INTO platform_demo_notices(id,booking_id,version,kind,due_at) VALUES(:i,:b,:v,:k,:d) ON CONFLICT DO NOTHING"),{"i":str(uuid.uuid4()),"b":str(row["id"]),"v":row["version"],"k":label,"d":due})


@router.post("/public/platform/demo/book")
async def book(body: Booking, request: Request, db=Depends(get_async_session)):
    await limiter.check(request)
    await db.execute(text("SELECT pg_advisory_xact_lock(7142030)"))
    cfg=await config(db)
    if not cfg["enabled"]: raise HTTPException(409,"OmniDome demo availability is not configured yet")
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:h,7142031))"),{"h":cfg["host_id"]})
    old=(await db.execute(text("SELECT * FROM platform_demo_bookings WHERE request_key=:k"),{"k":str(body.request_key)})).mappings().first()
    if old:
        if str(body.email).lower()!=old["email"] or body.starts_at!=old["starts_at"] or body.name!=old["name"] or body.company!=old["company"]: raise HTTPException(409,"Booking key already used")
        return {"id":old["id"],"status":old["status"],"starts_at":old["starts_at"],"token":management_token(old)}
    if not body.starts_at.tzinfo: raise HTTPException(422,"Booking time must include a timezone")
    day=body.starts_at.astimezone(ZoneInfo(cfg["timezone"])).date()
    if body.starts_at not in await slots(db,day,cfg): raise HTTPException(409,"This slot is no longer available. Choose another time.")
    row=(await db.execute(text("""INSERT INTO platform_demo_bookings(id,request_key,host_id,name,email,company,starts_at,ends_at,token_expires)
      VALUES(:i,:k,:h,:n,:e,:c,:s,:end,:expires) RETURNING *"""),{"i":str(uuid.uuid4()),"k":str(body.request_key),"h":cfg["host_id"],"n":body.name,"e":str(body.email).lower(),"c":body.company,"s":body.starts_at,"end":body.starts_at+timedelta(minutes=30),"expires":body.starts_at+timedelta(days=7)})).mappings().one()
    await queue_notices(db,row,"confirmed")
    return {"id":row["id"],"status":"confirmed","starts_at":row["starts_at"],"token":management_token(row),"email_status":"pending"}


@router.post("/public/platform/demo/manage")
async def manage(body: Manage, request: Request, db=Depends(get_async_session)):
    await limiter.check(request)
    await db.execute(text("SELECT pg_advisory_xact_lock(7142030)"))
    row=(await db.execute(text("SELECT * FROM platform_demo_bookings WHERE id=:i FOR UPDATE"),{"i":str(body.id)})).mappings().first()
    if not row or row["token_expires"]<=datetime.now(timezone.utc) or not hmac.compare_digest(management_token(row),body.token): raise HTTPException(404,"Booking link is invalid or expired")
    if row["starts_at"]<=datetime.now(timezone.utc): raise HTTPException(409,"This meeting has already started")
    if row["status"]=="cancelled": return {"status":"cancelled"}
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:h,7142031))"),{"h":str(row["host_id"])})
    cfg=await config(db)
    await db.execute(text("UPDATE platform_demo_bookings SET status='cancelled' WHERE id=:i"),{"i":str(body.id)})
    if body.starts_at:
        if not body.starts_at.tzinfo: raise HTTPException(422,"Booking time must include a timezone")
        if body.starts_at not in await slots(db,body.starts_at.astimezone(ZoneInfo(cfg["timezone"])).date(),cfg): raise HTTPException(409,"This slot is no longer available")
        updated=(await db.execute(text("UPDATE platform_demo_bookings SET status='confirmed',starts_at=:s,ends_at=:e,token_expires=:expires,version=version+1 WHERE id=:i RETURNING *"),{"s":body.starts_at,"e":body.starts_at+timedelta(minutes=30),"expires":body.starts_at+timedelta(days=7),"i":str(body.id)})).mappings().one()
    else:
        updated=(await db.execute(text("UPDATE platform_demo_bookings SET version=version+1 WHERE id=:i RETURNING *"),{"i":str(body.id)})).mappings().one()
    await db.execute(text("UPDATE platform_demo_notices SET status='superseded' WHERE booking_id=:i AND status='pending'"),{"i":str(body.id)})
    await queue_notices(db,updated,"rescheduled" if body.starts_at else "cancelled")
    return {"status":updated["status"],"starts_at":updated["starts_at"],"token":management_token(updated)}


async def deliver_notices():
    from services.common.db import get_async_engine
    if (get_async_engine().url.database or "").endswith("_test"): return
    if not agentmail.is_configured(): return
    # Claim and commit before provider I/O. Unknown delivery is exposed to the owner,
    # rather than repeatedly sending an email whose provider outcome is ambiguous.
    async with session_scope() as db:
        await db.execute(text("UPDATE platform_demo_notices SET status='unknown' WHERE status='sending' AND claimed_at<now()-interval '5 minutes'"))
        job=(await db.execute(text("SELECT * FROM platform_demo_notices WHERE status='pending' AND due_at<=now() ORDER BY due_at FOR UPDATE SKIP LOCKED LIMIT 1"))).mappings().first()
        if not job: return
        booking=(await db.execute(text("SELECT b.*,u.email AS host_email FROM platform_demo_bookings b JOIN users u ON u.id=b.host_id WHERE b.id=:i"),{"i":str(job["booking_id"])})).mappings().one()
        cfg=await config(db)
        if booking["version"]!=job["version"]:
            await db.execute(text("UPDATE platform_demo_notices SET status='superseded' WHERE id=:i"),{"i":str(job["id"])})
            return
        await db.execute(text("UPDATE platform_demo_notices SET status='sending',claimed_at=now() WHERE id=:i"),{"i":str(job["id"])})
    import os
    origin=(os.getenv("APP_PUBLIC_URL") or os.getenv("NEXT_PUBLIC_SITE_URL") or "http://localhost:3000").rstrip("/")
    link=origin+"/demo#"+str(booking["id"])+"."+management_token(booking)
    content=f"<p>OmniDome demo: {html.escape(job['kind'])}</p><p>{booking['starts_at'].isoformat()} UTC · 30 minutes</p>"
    if cfg.get("meeting_url"): content+=f'<p><a href="{html.escape(cfg["meeting_url"],quote=True)}">Join meeting</a></p>'
    content+=f'<p><a href="{html.escape(link,quote=True)}">Manage booking</a></p>'
    try:
        async with session_scope() as sending:
            current=(await sending.execute(text("SELECT version FROM platform_demo_bookings WHERE id=:i FOR UPDATE"),{"i":str(booking["id"])})).scalar_one()
            if current!=job["version"]:
                outcome="superseded"
            else:
                await agentmail.send_email(booking["email"],"OmniDome demo · "+job["kind"],content)
                await agentmail.send_email(booking["host_email"],"OmniDome demo · "+job["kind"],content+f"<p>{html.escape(booking['name'])} · {html.escape(booking['email'])}</p>")
                outcome="sent"
    except Exception:
        outcome="unknown"
    async with session_scope() as db:
        await db.execute(text("UPDATE platform_demo_notices SET status=:s WHERE id=:i"),{"s":outcome,"i":str(job["id"])})
