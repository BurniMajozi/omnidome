"""FNO Intelligence Service — main entry point. Port 8024."""

import logging
import os

from fastapi import FastAPI

from services.common.middleware import configure_production
from services.fno_intelligence.database import init_tables
from services.common.background_tasks import schedule_background
from services.fno_intelligence.opportunity_routes import router as opportunity_router, run_tender_scheduler
from services.fno_intelligence.market_routes import router as market_router, run_market_scheduler
from services.fno_intelligence.routes import router, sweep_stuck_passed_home_imports
from services.fno_intelligence.analytics_routes import router as analytics_router, sweep_stuck_runs
from services.fno_intelligence.competitors import run_competitor_scheduler
from services.fno_intelligence.bi_routes import router as bi_router

logger = logging.getLogger("fno_intelligence")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(
    title="OmniDome FNO Intelligence Service",
    version="1.0.0",
    description="FNO browser automation, data extraction, competitive intelligence, and operational automation.",
)

configure_production(app)

app.include_router(router, prefix="/api/fno")
app.include_router(opportunity_router, prefix="/api/fno")
app.include_router(market_router, prefix="/api/fno")
app.include_router(analytics_router, prefix="/api/fno")
app.include_router(bi_router, prefix="/api/fno")  # BI Studio / Deck Studio


@app.on_event("startup")
async def startup():
    await init_tables()
    swept = await sweep_stuck_passed_home_imports()
    if swept:
        logger.info("Marked %d interrupted passed-home import(s) as failed", swept)
    schedule_background(run_tender_scheduler())
    schedule_background(run_market_scheduler())
    swept_runs = await sweep_stuck_runs()
    if swept_runs:
        logger.info("Marked %d interrupted analytics run(s) as failed", swept_runs)
    schedule_background(run_competitor_scheduler())  # global loop; only scans competitors a user gave a schedule (kill switch: ANALYTICS_COMPETITOR_SCHEDULER_ENABLED=false)
    logger.info("FNO Intelligence service started")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "fno_intelligence", "version": "1.0.0"}
