"""
OmniDome Compliance Service v2 — Main Application
Port: 8019
Covers: Contract Management, Tax, H&S, CIPC, Bylaw, BBBEE, Leave, Vehicles,
        Foreign Workers, Travel, DR/BCP, Compliance Scoring, e-Services Gateway,
        Document Understanding, Financial Scenarios, ICASA, POPI, RICA,
        Breach Register, Funding Opportunities
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_auth_context
from services.common.entitlements import EntitlementGuard
from services.common.db import get_async_session as get_db, get_async_engine, run_with_db_retry
from services.common.middleware import configure_production

logger = logging.getLogger("compliance")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

guard = EntitlementGuard(
    module_id="compliance",
    public_paths={"/health", "/docs", "/openapi.json"},
)


async def _init_schema() -> None:
    """Optional create_all (dev) + the idempotent, advisory-locked migration. Retried while Postgres comes up."""
    from services.compliance import database as cdb

    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        async with get_async_engine().begin() as conn:
            await conn.run_sync(cdb.Base.metadata.create_all)
        logger.info("Compliance tables ensured")
    await cdb.run_migrations(get_async_engine())


@asynccontextmanager
async def _lifespan(app: FastAPI):
    guard.ensure_startup()
    logger.info(
        "compliance starting: pid=%s workers=%s (Dockerfile hard-codes --workers 2; "
        "docker-compose.local.yml overrides to 1) roles_enforced=%s",
        os.getpid(), os.getenv("WEB_CONCURRENCY", "1"),
        os.getenv("COMPLIANCE_ENFORCE_ROLES", "true"),
    )
    try:
        import resource  # POSIX only
        logger.info("compliance memory at startup: maxrss=%s KiB", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except Exception:  # noqa: BLE001 - not available on Windows
        pass
    await run_with_db_retry(_init_schema, logger=logger)
    yield


app = FastAPI(
    title="OmniDome Compliance Service",
    version="2.0.0",
    description="Comprehensive compliance management for South African telecom operators",
    lifespan=_lifespan,
)

configure_production(app)


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)

# ── Route Registration ──────────────────────────────────────────────────

from services.compliance.routes.contracts import router as contracts_router
from services.compliance.routes.regulatory import (
    tax_router, hs_router, cipc_router, bylaw_router, bbbee_router,
)
from services.compliance.routes.hr_operations import (
    leave_router, vehicle_router, fw_router, travel_router,
)
from services.compliance.routes.operations import (
    dr_router, score_router, eservice_router, doc_router,
)
from services.compliance.routes.compliance import (
    icasa_router, popi_router, rica_router, breach_router, funding_router,
)
from services.compliance.routes.documents import router as documents_router
from services.compliance.routes.statutory import router as statutory_router

# Contracts & SLAs
app.include_router(contracts_router, prefix="/api/v1")

# Regulatory: Tax, H&S, CIPC, Bylaw, BBBEE
app.include_router(tax_router, prefix="/api/v1")
app.include_router(hs_router, prefix="/api/v1")
app.include_router(cipc_router, prefix="/api/v1")
app.include_router(bylaw_router, prefix="/api/v1")
app.include_router(bbbee_router, prefix="/api/v1")

# HR Operations: Leave, Vehicles, Foreign Workers, Travel
app.include_router(leave_router, prefix="/api/v1")
app.include_router(vehicle_router, prefix="/api/v1")
app.include_router(fw_router, prefix="/api/v1")
app.include_router(travel_router, prefix="/api/v1")

# Operations: DR/BCP, Scoring, e-Services, Documents
app.include_router(dr_router, prefix="/api/v1")
app.include_router(score_router, prefix="/api/v1")
app.include_router(eservice_router, prefix="/api/v1")
app.include_router(doc_router, prefix="/api/v1")

# Compliance: ICASA, POPI, RICA, Breaches, Funding
app.include_router(icasa_router, prefix="/api/v1")
app.include_router(popi_router, prefix="/api/v1")
app.include_router(rica_router, prefix="/api/v1")
app.include_router(breach_router, prefix="/api/v1")
app.include_router(funding_router, prefix="/api/v1")

# Document Understanding: Upload, Fetch, OCR, Extract
app.include_router(documents_router, prefix="/api/v1")

# EMP201 working papers (prepare / mark-filed; nothing is filed with SARS by this service)
app.include_router(statutory_router, prefix="/api/v1")

# Cross-Service Connectors: Sales SLA, Technician Safety, Finance, POPIA, RICA, Orchestrator
from services.compliance.cross_service import router as cross_service_router
app.include_router(cross_service_router, prefix="/api/v1")


# ── Health ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "compliance", "version": "2.0.0"}


# ── Compliance Overview Dashboard ───────────────────────────────────────

@app.get("/api/v1/dashboard/overview")
async def compliance_overview(
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Overview for the CALLER'S tenant only: latest score snapshot per category (history is not
    averaged in), overall score = mean over assessed categories (null when none), counts."""
    from datetime import date, datetime, timedelta

    from services.compliance import crud, scoring
    from services.compliance.database import (
        ComplianceScore, Contract, ContractStatus,
        BreachRegister, PopiDataAccessRequest, ComplianceObligation,
        TaxReturn, TaxReturnStatus, HsIncident, FundingOpportunity, BbbeeScorecard,
    )

    tenant = str(ctx.tenant_id)

    async def count(model, *where) -> int:
        q = select(func.count(model.id)).where(model.tenant_id == tenant, *where)
        return (await db.execute(q)).scalar() or 0

    rows = await crud.list_rows(db, ctx, ComplianceScore, order_by=ComplianceScore.calculated_at.desc())
    latest = scoring.latest_per_category(rows)
    categories = [
        {
            "name": s_.category.value if hasattr(s_.category, "value") else str(s_.category),
            "score": float(s_.score),
            "status": s_.status.value if hasattr(s_.status, "value") else str(s_.status),
            "issues": s_.issues_count or 0,
            "critical": s_.critical_issues or 0,
            "calculated_at": s_.calculated_at.isoformat() if s_.calculated_at else None,
        }
        for s_ in latest
    ]
    overall_score = scoring.overall_score(latest)  # None when nothing has been assessed

    today = date.today()
    expiring_contracts = await count(
        Contract, Contract.expiry_date <= today + timedelta(days=90), Contract.status == ContractStatus.active)
    overdue_dsar = await count(
        PopiDataAccessRequest, PopiDataAccessRequest.due_date < datetime.utcnow(), PopiDataAccessRequest.status != "completed")
    open_breaches = await count(BreachRegister, BreachRegister.status.in_(["identified", "investigating"]))
    pending_obligations = await count(ComplianceObligation, ComplianceObligation.status == "pending_review")
    tax_overdue = await count(TaxReturn, TaxReturn.status == TaxReturnStatus.overdue)
    hs_open = await count(HsIncident, HsIncident.status == "open")
    funding_matched = await count(FundingOpportunity, FundingOpportunity.status == "identified")

    bbbee = (await db.execute(
        select(BbbeeScorecard).where(BbbeeScorecard.tenant_id == tenant).order_by(BbbeeScorecard.id.desc()).limit(1)
    )).scalar_one_or_none()
    bbbee_level = (
        bbbee.overall_level.value if bbbee and hasattr(bbbee.overall_level, "value")
        else str(bbbee.overall_level) if bbbee else "pending"
    )

    return {
        "overall_score": overall_score,
        "assessed_categories": len(categories),
        "categories": categories,
        "expiring_contracts": expiring_contracts,
        "overdue_dsar": overdue_dsar,
        "open_breaches": open_breaches,
        "pending_obligations": pending_obligations,
        "tax_overdue": tax_overdue,
        "hs_open_incidents": hs_open,
        "bbbee_level": bbbee_level,
        "funding_matched": funding_matched,
    }
