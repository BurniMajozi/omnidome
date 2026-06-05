"""FNO Intelligence Service — main entry point. Port 8024."""

import logging
import os

from fastapi import FastAPI

from services.fno_intelligence.database import init_tables
from services.fno_intelligence.routes import router

logger = logging.getLogger("fno_intelligence")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(
    title="OmniDome FNO Intelligence Service",
    version="1.0.0",
    description="FNO browser automation, data extraction, competitive intelligence, and operational automation.",
)

app.include_router(router, prefix="/api/fno")


@app.on_event("startup")
async def startup():
    await init_tables()
    logger.info("FNO Intelligence service started")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "fno_intelligence", "version": "1.0.0"}
