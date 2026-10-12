"""Serialize staff calendar writes with OmniDome sales demo reservations."""
from sqlalchemy import text
from fastapi import HTTPException


async def check_calendar_write(db, host, start, end):
    if db.bind.dialect.name != "postgresql": return
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:h,7142031))"),{"h":str(host)})
    if not (await db.execute(text("SELECT to_regclass('platform_demo_bookings')"))).scalar_one_or_none(): return
    conflict=(await db.execute(text("""SELECT 1 FROM platform_demo_bookings WHERE host_id=:h
      AND status='confirmed' AND starts_at < CAST(:end AS timestamptz) + interval '15 minutes'
      AND ends_at > CAST(:start AS timestamptz) - interval '15 minutes' LIMIT 1"""),{"h":str(host),"start":start,"end":end})).first()
    if conflict: raise HTTPException(409,"This host has an OmniDome demo booking at that time")
