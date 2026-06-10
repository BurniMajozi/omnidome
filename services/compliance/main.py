"""
OmniDome Compliance Service v2 — Main Application
Port: 8019
Covers: Contract Management, Tax, H&S, CIPC, Bylaw, BBBEE, Leave, Vehicles,
        Foreign Workers, Travel, DR/BCP, Compliance Scoring, e-Services Gateway,
        Document Understanding, Financial Scenarios, ICASA, POPI, RICA,
        Breach Register, Funding Opportunities
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="OmniDome Compliance Service",
    version="2.0.0",
    description="Comprehensive compliance management for South African telecom operators",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Route Registration ──────────────────────────────────────────────────

from services.compliance.routes.contracts import router as contracts_router
from services.compliance.routes.regulatory import (
    tax_router, hs_router, cipc_router, bylaw_router, bbbee_router,
)
from services.compliance.routes.hr_operations import (
    leave_router, vehicle_router, fw_router, travel_router,
)
from services.compliance.routes.operations import (
    dr_router, score_router, eservice_router, doc_router, scenario_router,
)
from services.compliance.routes.compliance import (
    icasa_router, popi_router, rica_router, breach_router, funding_router,
)

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

# Operations: DR/BCP, Scoring, e-Services, Documents, Financial Scenarios
app.include_router(dr_router, prefix="/api/v1")
app.include_router(score_router, prefix="/api/v1")
app.include_router(eservice_router, prefix="/api/v1")
app.include_router(doc_router, prefix="/api/v1")
app.include_router(scenario_router, prefix="/api/v1")

# Compliance: ICASA, POPI, RICA, Breaches, Funding
app.include_router(icasa_router, prefix="/api/v1")
app.include_router(popi_router, prefix="/api/v1")
app.include_router(rica_router, prefix="/api/v1")
app.include_router(breach_router, prefix="/api/v1")
app.include_router(funding_router, prefix="/api/v1")


# ── Health ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "compliance", "version": "2.0.0"}


# ── Compliance Overview Dashboard ───────────────────────────────────────

@app.get("/api/v1/dashboard/overview")
async def compliance_overview():
    """Aggregated compliance overview across all categories."""
    return {
        "categories": [c.value for c in __import__(
            "services.compliance.database", fromlist=["ComplianceCategory"]
        ).ComplianceCategory],
        "platforms": [p.value for p in __import__(
            "services.compliance.database", fromlist=["EservicePlatform"]
        ).EservicePlatform],
        "status": "operational",
    }
