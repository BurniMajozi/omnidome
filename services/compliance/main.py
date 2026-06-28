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

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.db import get_async_session as get_db
from services.common.middleware import configure_production

logger = logging.getLogger("compliance")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(
    title="OmniDome Compliance Service",
    version="2.0.0",
    description="Comprehensive compliance management for South African telecom operators",
)

configure_production(app)


@app.on_event("startup")
async def startup() -> None:
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        from services.compliance.database import Base
        from services.common.db import get_async_engine
        async with get_async_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Compliance tables ensured")

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


# ── Health ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "compliance", "version": "2.0.0"}


# ── Compliance Overview Dashboard ───────────────────────────────────────

@app.get("/api/v1/dashboard/overview")
async def compliance_overview(db: AsyncSession = Depends(get_db)):
    """Aggregated compliance overview — scores, counts, and category breakdown."""
    from services.compliance.database import (
        ComplianceScore, Contract, ContractStatus,
        BreachRegister, PopiDataAccessRequest, ComplianceObligation,
        TaxReturn, HsIncident, FundingOpportunity, BbbeeScorecard,
    )
    from datetime import datetime, timedelta

    # Compliance scores
    scores_result = await db.execute(select(ComplianceScore).order_by(ComplianceScore.calculated_at.desc()))
    scores = scores_result.scalars().all()

    categories = [
        {
            "name": s.category.value if hasattr(s.category, "value") else str(s.category),
            "score": float(s.score),
            "status": s.status.value if hasattr(s.status, "value") else str(s.status),
            "issues": s.issues_count or 0,
            "critical": s.critical_issues or 0,
        }
        for s in scores
    ]
    overall_score = (
        round(sum(c["score"] for c in categories) / len(categories))
        if categories else 0
    )

    # Expiring contracts (90 days)
    cutoff = datetime.utcnow() + timedelta(days=90)
    exp_result = await db.execute(
        select(func.count(Contract.id)).where(
            Contract.expiry_date <= cutoff,
            Contract.status == ContractStatus.active,
        )
    )
    expiring_contracts = exp_result.scalar() or 0

    # Overdue DSARs
    dsar_result = await db.execute(
        select(func.count(PopiDataAccessRequest.id)).where(
            PopiDataAccessRequest.due_date < datetime.utcnow(),
            PopiDataAccessRequest.status != "completed",
        )
    )
    overdue_dsar = dsar_result.scalar() or 0

    # Open breaches
    breach_result = await db.execute(
        select(func.count(BreachRegister.id)).where(
            BreachRegister.status.in_(["identified", "investigating"])
        )
    )
    open_breaches = breach_result.scalar() or 0

    # Pending obligations
    obl_result = await db.execute(
        select(func.count(ComplianceObligation.id)).where(
            ComplianceObligation.status == "pending_review"
        )
    )
    pending_obligations = obl_result.scalar() or 0

    # Overdue tax
    tax_result = await db.execute(
        select(func.count(TaxReturn.id)).where(TaxReturn.status == "overdue")
    )
    tax_overdue = tax_result.scalar() or 0

    # Open H&S incidents
    hs_result = await db.execute(
        select(func.count(HsIncident.id)).where(HsIncident.status == "open")
    )
    hs_open = hs_result.scalar() or 0

    # BBBEE level (most recent)
    bbbee_result = await db.execute(
        select(BbbeeScorecard).order_by(BbbeeScorecard.id.desc()).limit(1)
    )
    bbbee = bbbee_result.scalar_one_or_none()
    bbbee_level = (
        bbbee.overall_level.value if bbbee and hasattr(bbbee.overall_level, "value")
        else str(bbbee.overall_level) if bbbee else "pending"
    )

    # Funding matched
    funding_result = await db.execute(
        select(func.count(FundingOpportunity.id)).where(FundingOpportunity.status == "identified")
    )
    funding_matched = funding_result.scalar() or 0

    return {
        "overall_score": overall_score,
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
