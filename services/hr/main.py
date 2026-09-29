import os
import logging
import json
from datetime import date, datetime
from typing import Optional, List, Dict, Any
import uuid

import httpx
from fastapi import FastAPI, Depends, HTTPException, status, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select, desc, and_, func

from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
from services.common.auth import get_current_tenant_id
from services.hr.database import (
    get_session, init_tables,
    Employee, LeaveRequest, PerformanceReview,
    StaffSchedule, TrainingCourse, TrainingEnrollment,
    BenefitEnrollment, DisciplinaryAction, StaffExit, OnboardingTask,
    PayrollProfile, PayrollRun, Payslip,
    CompanyKPIConfig, EmployeeKPISheet,
)
from services.hr import paystack as ps
from services.hr.cross_service import router as cross_service_router

app = FastAPI(title="OmniDome HR Service", version="0.2.0")
guard = EntitlementGuard(module_id="hr")
logger = logging.getLogger("hr")

configure_production(app)
app.include_router(cross_service_router)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "hr"}


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    await init_tables()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


# ═══════════════════════════════════════════════════════════════════════════
# HELPER
# ═══════════════════════════════════════════════════════════════════════════

async def _get_employee_or_404(emp_id: uuid.UUID, tenant_id: uuid.UUID, db):
    result = await db.execute(
        select(Employee).where(Employee.id == emp_id, Employee.tenant_id == tenant_id)
    )
    emp = result.scalars().first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


def _emp_to_dict(emp: Employee) -> dict:
    return {
        "id": emp.id,
        "employee_id": emp.employee_id,
        "full_name": emp.full_name,
        "job_title": emp.job_title,
        "department": emp.department,
        "hire_date": emp.hire_date,
        "status": emp.status,
        "email": emp.email,
        "phone": emp.phone,
        "manager_id": emp.manager_id,
        "call_center_agent_id": emp.call_center_agent_id,
        "is_agent": getattr(emp, 'is_agent', False),
        "agent_type": getattr(emp, 'agent_type', None),
        "llm_model": getattr(emp, 'llm_model', None),
        "financial_limit": getattr(emp, 'financial_limit', None),
        "scope": getattr(emp, 'scope', None),
        "is_subagent": getattr(emp, 'is_subagent', False),
        "parent_agent_id": getattr(emp, 'parent_agent_id', None),
        "created_at": emp.created_at,
    }


# ═══════════════════════════════════════════════════════════════════════════
# EMPLOYEES  (existing + call_center_agent_id + manager_id for Org Chart)
# ═══════════════════════════════════════════════════════════════════════════

class EmployeeBase(BaseModel):
    full_name: str
    job_title: str
    department: str
    hire_date: date

class EmployeeCreate(EmployeeBase):
    employee_id: str
    email: Optional[str] = None
    phone: Optional[str] = None
    manager_id: Optional[uuid.UUID] = None
    call_center_agent_id: Optional[uuid.UUID] = None
    is_agent: Optional[bool] = False
    agent_type: Optional[str] = None
    llm_model: Optional[str] = None
    financial_limit: Optional[float] = None
    scope: Optional[str] = None
    is_subagent: Optional[bool] = False
    parent_agent_id: Optional[uuid.UUID] = None

class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    hire_date: Optional[date] = None
    status: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    manager_id: Optional[uuid.UUID] = None
    call_center_agent_id: Optional[uuid.UUID] = None


@app.get("/employees", response_model=List[dict])
async def list_employees(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
    department: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Search by name or employee ID"),
):
    stmt = select(Employee).where(Employee.tenant_id == tenant_id)
    if department:
        stmt = stmt.where(Employee.department == department)
    if status:
        stmt = stmt.where(Employee.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Employee.full_name.ilike(like) | Employee.employee_id.ilike(like))
    result = await db.execute(stmt.order_by(Employee.created_at))
    return [_emp_to_dict(e) for e in result.scalars().all()]


@app.post("/employees", status_code=status.HTTP_201_CREATED)
async def create_employee(
    data: EmployeeCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    emp = Employee(
        tenant_id=tenant_id,
        employee_id=data.employee_id,
        full_name=data.full_name,
        job_title=data.job_title,
        department=data.department,
        hire_date=data.hire_date,
        status="ACTIVE",
        email=data.email,
        phone=data.phone,
        manager_id=data.manager_id,
        call_center_agent_id=data.call_center_agent_id,
        is_agent=data.is_agent or False,
        agent_type=data.agent_type,
        llm_model=data.llm_model,
        financial_limit=data.financial_limit,
        scope=data.scope,
        is_subagent=data.is_subagent or False,
        parent_agent_id=data.parent_agent_id,
    )
    db.add(emp)
    await db.flush()
    await db.refresh(emp)
    logger.info(f"Employee created: {data.full_name} ({data.employee_id})")

    # ── Side-effect: register AI agent with Orchestrator + Tenant Memory ──
    if data.is_agent:
        _mem_url = os.environ.get("TENANT_MEMORY_SERVICE_URL", "http://tenant_memory:8025")
        _orch_url = os.environ.get("ORCHESTRATOR_URL", "http://agent-orchestrator:8021")
        agent_entry = {
            "employee_id": str(emp.id),
            "employee_code": data.employee_id,
            "full_name": data.full_name,
            "job_title": data.job_title,
            "department": data.department,
            "agent_type": data.agent_type or "custom",
            "llm_model": data.llm_model,
            "financial_limit": data.financial_limit,
            "scope": data.scope,
            "is_subagent": data.is_subagent or False,
            "parent_agent_id": str(data.parent_agent_id) if data.parent_agent_id else None,
            "manager_id": str(data.manager_id) if data.manager_id else None,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as _c:
                await _c.post(
                    f"{_mem_url}/api/v1/memories",
                    json={
                        "scope": "agent_roster",
                        "content": f"AI Agent deployed: {data.full_name} ({data.agent_type or 'custom'}) "
                                   f"in {data.department}, model={data.llm_model}, "
                                   f"limit=R{data.financial_limit or 0}, scope={data.scope}",
                        "metadata": agent_entry,
                    },
                    headers={"x-tenant-id": str(tenant_id)},
                )
                await _c.post(
                    f"{_orch_url}/api/agents/register",
                    json=agent_entry,
                    headers={"x-tenant-id": str(tenant_id)},
                )
                logger.info(f"Agent '{data.full_name}' registered with Orchestrator + Memory")
        except Exception as exc:
            logger.warning(f"Agent registration side-effect failed (non-blocking): {exc}")

    return _emp_to_dict(emp)


@app.get("/employees/{emp_id}")
async def get_employee(
    emp_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    emp = await _get_employee_or_404(emp_id, tenant_id, db)
    return _emp_to_dict(emp)


@app.put("/employees/{emp_id}")
async def update_employee(
    emp_id: uuid.UUID,
    data: EmployeeUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    emp = await _get_employee_or_404(emp_id, tenant_id, db)
    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(emp, key, value)
    await db.flush()
    await db.refresh(emp)
    return _emp_to_dict(emp)


@app.delete("/employees/{emp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_employee(
    emp_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    emp = await _get_employee_or_404(emp_id, tenant_id, db)
    emp.status = "INACTIVE"
    await db.flush()


@app.put("/employees/{emp_id}/link-call-center")
async def link_employee_to_agent(
    emp_id: uuid.UUID,
    agent_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Link an HR employee record to a call center agent."""
    emp = await _get_employee_or_404(emp_id, tenant_id, db)
    emp.call_center_agent_id = agent_id
    await db.flush()
    return {"status": "linked", "employee_id": str(emp_id), "agent_id": str(agent_id)}


# ═══════════════════════════════════════════════════════════════════════════
# LEAVE REQUESTS  (existing)
# ═══════════════════════════════════════════════════════════════════════════

class LeaveRequestCreate(BaseModel):
    leave_type: str
    start_date: date
    end_date: date
    reason: Optional[str] = None


@app.get("/employees/{emp_id}/leave", response_model=List[dict])
async def list_leave_requests(
    emp_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    await _get_employee_or_404(emp_id, tenant_id, db)
    result = await db.execute(
        select(LeaveRequest)
        .where(LeaveRequest.employee_id == emp_id, LeaveRequest.tenant_id == tenant_id)
        .order_by(desc(LeaveRequest.created_at))
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id, "employee_id": r.employee_id, "leave_type": r.leave_type,
            "start_date": r.start_date, "end_date": r.end_date, "status": r.status,
            "reason": r.reason, "created_at": r.created_at,
        }
        for r in rows
    ]


@app.post("/employees/{emp_id}/leave", status_code=status.HTTP_201_CREATED)
async def create_leave_request(
    emp_id: uuid.UUID,
    data: LeaveRequestCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    await _get_employee_or_404(emp_id, tenant_id, db)
    leave = LeaveRequest(
        tenant_id=tenant_id, employee_id=emp_id,
        leave_type=data.leave_type, start_date=data.start_date,
        end_date=data.end_date, status="PENDING", reason=data.reason,
    )
    db.add(leave)
    await db.flush()
    await db.refresh(leave)
    return {
        "id": leave.id, "employee_id": leave.employee_id, "leave_type": leave.leave_type,
        "start_date": leave.start_date, "end_date": leave.end_date, "status": leave.status,
        "reason": leave.reason, "created_at": leave.created_at,
    }


@app.put("/leave/{leave_id}/approve")
async def approve_leave(
    leave_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    result = await db.execute(
        select(LeaveRequest).where(LeaveRequest.id == leave_id, LeaveRequest.tenant_id == tenant_id)
    )
    leave = result.scalars().first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")
    leave.status = "APPROVED"
    await db.flush()
    return {"id": leave.id, "status": "APPROVED"}


@app.put("/leave/{leave_id}/decline")
async def decline_leave(
    leave_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    result = await db.execute(
        select(LeaveRequest).where(LeaveRequest.id == leave_id, LeaveRequest.tenant_id == tenant_id)
    )
    leave = result.scalars().first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")
    leave.status = "DECLINED"
    await db.flush()
    return {"id": leave.id, "status": "DECLINED"}


# ═══════════════════════════════════════════════════════════════════════════
# PERFORMANCE REVIEWS  (existing)
# ═══════════════════════════════════════════════════════════════════════════

class PerformanceReviewCreate(BaseModel):
    review_period: str
    tickets_resolved: int = 0
    avg_resolution_time: int = 0
    fcr_rate: Optional[float] = None
    kpi_score: Optional[float] = None
    sentiment_score: Optional[float] = None
    attrition_risk: Optional[str] = None
    reviewer_notes: Optional[str] = None


@app.get("/employees/{emp_id}/performance", response_model=List[dict])
async def get_employee_performance(
    emp_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    await _get_employee_or_404(emp_id, tenant_id, db)
    result = await db.execute(
        select(PerformanceReview)
        .where(PerformanceReview.employee_id == emp_id, PerformanceReview.tenant_id == tenant_id)
        .order_by(desc(PerformanceReview.created_at))
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id, "employee_id": r.employee_id, "review_period": r.review_period,
            "tickets_resolved": r.tickets_resolved, "avg_resolution_time": r.avg_resolution_time,
            "fcr_rate": float(r.fcr_rate) if r.fcr_rate is not None else None,
            "kpi_score": float(r.kpi_score) if r.kpi_score is not None else None,
            "sentiment_score": float(r.sentiment_score) if r.sentiment_score is not None else None,
            "attrition_risk": r.attrition_risk, "reviewer_notes": r.reviewer_notes,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@app.post("/employees/{emp_id}/performance", status_code=status.HTTP_201_CREATED)
async def create_performance_review(
    emp_id: uuid.UUID,
    data: PerformanceReviewCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    await _get_employee_or_404(emp_id, tenant_id, db)
    review = PerformanceReview(
        tenant_id=tenant_id, employee_id=emp_id, **data.dict(),
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)
    return {
        "id": review.id, "employee_id": review.employee_id, "review_period": review.review_period,
        "tickets_resolved": review.tickets_resolved, "avg_resolution_time": review.avg_resolution_time,
        "fcr_rate": float(review.fcr_rate) if review.fcr_rate is not None else None,
        "kpi_score": float(review.kpi_score) if review.kpi_score is not None else None,
        "sentiment_score": float(review.sentiment_score) if review.sentiment_score is not None else None,
        "attrition_risk": review.attrition_risk, "reviewer_notes": review.reviewer_notes,
        "created_at": review.created_at,
    }


# ═══════════════════════════════════════════════════════════════════════════
# COMPANY & INDIVIDUAL KPI / OBJECTIVE MANAGEMENT ENGINE
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_FISCAL_YEAR = "FY 2026/2027"
VALID_SHEET_STATUSES = {"DRAFT", "SUBMITTED", "APPROVED"}
WEIGHT_TOLERANCE = 0.01

DEFAULT_LEVEL_WEIGHTS = {
    "EXECUTIVE": 60.0,
    "DIRECTOR": 40.0,
    "MANAGER": 30.0,
    "STAFF": 20.0,
}

class CompanyKPIConfigUpdate(BaseModel):
    fiscal_year: Optional[str] = "FY 2026/2027"
    sales_budget_zar: Optional[float] = None
    sales_actual_zar: Optional[float] = None
    cost_budget_zar: Optional[float] = None
    cost_actual_zar: Optional[float] = None
    profit_budget_zar: Optional[float] = None
    profit_actual_zar: Optional[float] = None
    values_weight_pct: Optional[float] = 10.0
    values_description: Optional[str] = None
    level_weights: Optional[Dict[str, float]] = None
    sales_source_mode: Optional[str] = "LIVE_TABLE"
    cost_source_mode: Optional[str] = "LIVE_TABLE"
    profit_source_mode: Optional[str] = "LIVE_TABLE"


class EmployeeKPISheetUpdate(BaseModel):
    fiscal_year: Optional[str] = "FY 2026/2027"
    position_level: Optional[str] = None
    company_shared_weight_pct: Optional[float] = None
    values_weight_pct: Optional[float] = 10.0
    individual_target_weight_pct: Optional[float] = None
    total_weight_pct: Optional[float] = 100.0
    status: Optional[str] = "DRAFT"  # DRAFT, SUBMITTED, APPROVED, CALIBRATED
    kpis: Optional[List[Dict[str, Any]]] = None
    overall_score: Optional[float] = None
    reviewer_notes: Optional[str] = None


class CascadeKPIRequest(BaseModel):
    fiscal_year: Optional[str] = "FY 2026/2027"


class AISmartCriteriaRequest(BaseModel):
    title: str
    category: Optional[str] = "Operational Excellence"
    job_title: Optional[str] = None
    department: Optional[str] = None


def _calculate_company_scores(config: CompanyKPIConfig) -> Dict[str, Any]:
    s_budget = float(config.sales_budget_zar) if config.sales_budget_zar else 1.0
    s_actual = float(config.sales_actual_zar) if config.sales_actual_zar else 0.0
    sales_ach = round((s_actual / s_budget) * 100.0, 2) if s_budget > 0 else 0.0

    c_budget = float(config.cost_budget_zar) if config.cost_budget_zar else 1.0
    c_actual = float(config.cost_actual_zar) if config.cost_actual_zar else 0.0
    # Cost efficiency (matches frontend): budget / actual; under budget is >100%
    cost_eff = round((c_budget / c_actual) * 100.0, 2) if c_actual > 0 else 100.0

    p_budget = float(config.profit_budget_zar) if config.profit_budget_zar else 1.0
    p_actual = float(config.profit_actual_zar) if config.profit_actual_zar else 0.0
    profit_ach = round((p_actual / p_budget) * 100.0, 2) if p_budget > 0 else 0.0

    # Single source of truth (matches frontend): 45% sales / 35% cost efficiency / 20% profit
    shared_score = round((sales_ach * 0.45) + (cost_eff * 0.35) + (profit_ach * 0.20), 2)
    level_weights = json.loads(config.level_weights_json) if config.level_weights_json else DEFAULT_LEVEL_WEIGHTS

    return {
        "id": str(config.id),
        "fiscal_year": config.fiscal_year,
        "sales_budget_zar": float(config.sales_budget_zar or 0.0),
        "sales_actual_zar": float(config.sales_actual_zar or 0.0),
        "sales_achievement_pct": sales_ach,
        "sales_source_mode": config.sales_source_mode or "LIVE_TABLE",
        "cost_budget_zar": float(config.cost_budget_zar or 0.0),
        "cost_actual_zar": float(config.cost_actual_zar or 0.0),
        "cost_efficiency_pct": cost_eff,
        "cost_source_mode": config.cost_source_mode or "LIVE_TABLE",
        "profit_budget_zar": float(config.profit_budget_zar or 0.0),
        "profit_actual_zar": float(config.profit_actual_zar or 0.0),
        "profit_achievement_pct": profit_ach,
        "profit_source_mode": config.profit_source_mode or "LIVE_TABLE",
        "company_shared_score_pct": shared_score,
        "corporate_attainment_index": shared_score,
        "values_weight_pct": float(config.values_weight_pct),
        "values_description": config.values_description,
        "level_weights": level_weights,
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }


def _infer_employee_level(job_title: str) -> str:
    title_lower = (job_title or "").lower()
    if any(k in title_lower for k in ["ceo", "cfo", "cto", "coo", "chief", "executive", "managing director"]):
        return "EXECUTIVE"
    if any(k in title_lower for k in ["director", "vice president", "vp", "head of"]):
        return "DIRECTOR"
    if any(k in title_lower for k in ["manager", "lead", "supervisor", "principal"]):
        return "MANAGER"
    return "STAFF"


@app.get("/kpis/company")
async def get_company_kpis(
    fiscal_year: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Retrieve whole-company shared KPI targets, budget benchmarks, and position level weights."""
    q = select(CompanyKPIConfig).where(CompanyKPIConfig.tenant_id == tenant_id)
    if fiscal_year:
        q = q.where(CompanyKPIConfig.fiscal_year == fiscal_year)
    result = await db.execute(q.order_by(desc(CompanyKPIConfig.updated_at)))
    config = result.scalars().first()
    if not config:
        config = CompanyKPIConfig(
            tenant_id=tenant_id,
            fiscal_year=fiscal_year or DEFAULT_FISCAL_YEAR,
            # Targets are editable defaults; actuals start at zero (sync from /kpis/live-actuals).
            sales_budget_zar=3500000.0,
            sales_actual_zar=0.0,
            cost_budget_zar=2100000.0,
            cost_actual_zar=0.0,
            profit_budget_zar=1400000.0,
            profit_actual_zar=0.0,
            values_weight_pct=10.0,
            values_description="Ubuntu & Customer Empathy, Operational Excellence & Speed, Staff Wellness (BCEA), POPIA & Ethical Governance",
            level_weights_json=json.dumps(DEFAULT_LEVEL_WEIGHTS),
        )
        db.add(config)
        await db.flush()
        await db.refresh(config)

    return _calculate_company_scores(config)


@app.put("/kpis/company")
async def update_company_kpis(
    data: CompanyKPIConfigUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Update whole-company shared KPI budgets (Sales, Cost, Profit) and level weight matrix."""
    result = await db.execute(
        select(CompanyKPIConfig)
        .where(
            CompanyKPIConfig.tenant_id == tenant_id,
            CompanyKPIConfig.fiscal_year == (data.fiscal_year or DEFAULT_FISCAL_YEAR),
        )
        .order_by(desc(CompanyKPIConfig.updated_at))
    )
    config = result.scalars().first()
    if not config:
        config = CompanyKPIConfig(
            tenant_id=tenant_id,
            fiscal_year=data.fiscal_year or DEFAULT_FISCAL_YEAR,
            sales_actual_zar=0.0, cost_actual_zar=0.0, profit_actual_zar=0.0,
        )
        db.add(config)

    if data.fiscal_year is not None:
        config.fiscal_year = data.fiscal_year
    if data.sales_budget_zar is not None:
        config.sales_budget_zar = data.sales_budget_zar
    if data.sales_actual_zar is not None:
        config.sales_actual_zar = data.sales_actual_zar
    if data.cost_budget_zar is not None:
        config.cost_budget_zar = data.cost_budget_zar
    if data.cost_actual_zar is not None:
        config.cost_actual_zar = data.cost_actual_zar
    if data.profit_budget_zar is not None:
        config.profit_budget_zar = data.profit_budget_zar
    if data.profit_actual_zar is not None:
        config.profit_actual_zar = data.profit_actual_zar
    if data.values_weight_pct is not None:
        config.values_weight_pct = data.values_weight_pct
    if data.values_description is not None:
        config.values_description = data.values_description
    if data.level_weights is not None:
        config.level_weights_json = json.dumps(data.level_weights)
    if data.sales_source_mode is not None:
        config.sales_source_mode = data.sales_source_mode
    if data.cost_source_mode is not None:
        config.cost_source_mode = data.cost_source_mode
    if data.profit_source_mode is not None:
        config.profit_source_mode = data.profit_source_mode

    await db.flush()
    await db.refresh(config)
    return _calculate_company_scores(config)


def _fiscal_year_start(fiscal_year: Optional[str]) -> date:
    """Start date of a 'FY 2026/2027' style fiscal year (start month via FISCAL_YEAR_START_MONTH, default March)."""
    import re
    m = re.search(r"(\d{4})", fiscal_year or "")
    year = int(m.group(1)) if m else date.today().year
    month = int(os.getenv("FISCAL_YEAR_START_MONTH", "3"))
    return date(year, month, 1)


async def _live_sales_won_ytd(tenant_id: uuid.UUID, fy_start: date) -> Optional[float]:
    """Won-deal value (ZAR) closed since fiscal-year start, from the sales service. None if unavailable."""
    sales_url = os.getenv("SALES_SERVICE_URL", "http://sales:8002")
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"{sales_url}/deals",
                params={"status": "WON"},
                headers={"X-Tenant-Id": str(tenant_id)},
            )
        if resp.status_code != 200:
            logger.warning("Sales service /deals returned %s", resp.status_code)
            return None
        total = 0.0
        for d in resp.json():
            closed = d.get("closed_at")
            if closed:
                try:
                    if datetime.fromisoformat(str(closed).replace("Z", "+00:00")).date() < fy_start:
                        continue
                except ValueError:
                    pass
            total += float(d.get("value_zar") or 0)
        return round(total, 2)
    except Exception as e:
        logger.warning("Could not read won deals from sales service: %s", e)
        return None


async def _live_billing_collected_ytd(tenant_id: uuid.UUID, fy_start: date) -> Optional[float]:
    """Payments collected (ZAR) since fiscal-year start, from billing /reports/revenue. None if unavailable."""
    billing_url = os.getenv("BILLING_SERVICE_URL", "http://billing:8003")
    today = date.today()
    months = max(1, min(24, (today.year - fy_start.year) * 12 + (today.month - fy_start.month) + 1))
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"{billing_url}/reports/revenue",
                params={"months": months},
                headers={"X-Tenant-Id": str(tenant_id)},
            )
        if resp.status_code != 200:
            logger.warning("Billing service /reports/revenue returned %s", resp.status_code)
            return None
        return round(sum(float(r.get("total_paid_zar") or 0) for r in resp.json()), 2)
    except Exception as e:
        logger.warning("Could not read collections from billing service: %s", e)
        return None


@app.get("/kpis/live-actuals")
async def get_kpis_live_actuals(
    fiscal_year: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Retrieve ground-truth actual metrics from real sources (sales, billing, payroll).

    Values that cannot be read are returned as null with source='unavailable' (never demo numbers).
    """
    fy_start = _fiscal_year_start(fiscal_year or DEFAULT_FISCAL_YEAR)

    # 1. Operating Cost from Payroll (HR's own table)
    cost_val: Optional[float] = None
    cost_source = "unavailable"
    try:
        p_res = await db.execute(
            select(func.sum(Payslip.gross + Payslip.uif_employer + Payslip.sdl))
            .where(Payslip.tenant_id == tenant_id)
        )
        p_sum = p_res.scalar()
        if p_sum is not None and float(p_sum) > 0:
            cost_val = round(float(p_sum), 2)
            cost_source = "live"
    except Exception as e:
        logger.warning("Could not query payslips for cost actual: %s", e)

    # 2. Revenue: won deals YTD (sales) and payments collected YTD (billing)
    sales_val = await _live_sales_won_ytd(tenant_id, fy_start)
    billing_val = await _live_billing_collected_ytd(tenant_id, fy_start)
    sales_source = "live" if sales_val is not None else "unavailable"
    billing_source = "live" if billing_val is not None else "unavailable"

    profit_val: Optional[float] = None
    if sales_val is not None and cost_val is not None:
        profit_val = round(sales_val - cost_val, 2)
    profit_source = "live" if profit_val is not None else "unavailable"

    return {
        "sources": {
            "sales": {
                "metric_name": "Sales Revenue Actual",
                "current_value": sales_val,
                "unit": "ZAR",
                "source": sales_source,
                "table_source": "sales.deals (status=WON, closed since fiscal-year start)",
                "mode": "LIVE_TABLE",
                "options": [
                    {"id": "sales_leads_won", "label": "Sales Pipeline Won Deals Ledger (ZAR)", "value": sales_val, "unit": "ZAR", "type": "actual", "source": sales_source},
                    {"id": "billing_collections", "label": "Billing Invoices Collected (ZAR)", "value": billing_val, "unit": "ZAR", "type": "actual", "source": billing_source},
                ]
            },
            "cost": {
                "metric_name": "Operating Cost Actual",
                "current_value": cost_val,
                "unit": "ZAR",
                "source": cost_source,
                "table_source": "hr.payslips (gross + employer UIF + SDL)",
                "mode": "LIVE_TABLE",
                "options": [
                    {"id": "payroll_statutory", "label": "Total Payroll & Statutory Levies (ZAR)", "value": cost_val, "unit": "ZAR", "type": "actual", "source": cost_source},
                ]
            },
            "profit": {
                "metric_name": "Net Profit / EBITDA",
                "current_value": profit_val,
                "unit": "ZAR",
                "source": profit_source,
                "table_source": "derived: won deals revenue minus payroll cost",
                "mode": "LIVE_TABLE",
                "options": [
                    {"id": "net_ebitda", "label": "Net Operating Profit / EBITDA (ZAR)", "value": profit_val, "unit": "ZAR", "type": "actual", "source": profit_source},
                ]
            },
            # No live source is wired for these yet; explicitly unavailable instead of demo constants.
            "support": {
                "metric_name": "Customer Support FCR",
                "current_value": None,
                "unit": "%",
                "source": "unavailable",
                "table_source": "support.tickets (First Contact Resolution) - not wired",
            },
            "subscribers": {
                "metric_name": "Subscriber Churn Rate",
                "current_value": None,
                "unit": "%",
                "source": "unavailable",
                "table_source": "lifecycle.subscribers (Monthly Churn) - not wired",
            }
        },
        "fiscal_year": fiscal_year or DEFAULT_FISCAL_YEAR,
        "fiscal_year_start": fy_start.isoformat(),
        "synced_at": datetime.utcnow().isoformat()
    }



@app.post("/kpis/cascade")
async def cascade_company_kpis(
    req: CascadeKPIRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Cascade shared company KPIs and weights to all employees according to their position level."""
    # 1. Fetch company config
    cascade_fy = req.fiscal_year or DEFAULT_FISCAL_YEAR
    c_res = await db.execute(
        select(CompanyKPIConfig)
        .where(CompanyKPIConfig.tenant_id == tenant_id, CompanyKPIConfig.fiscal_year == cascade_fy)
        .order_by(desc(CompanyKPIConfig.updated_at))
    )
    config = c_res.scalars().first()
    level_weights = json.loads(config.level_weights_json) if config and config.level_weights_json else DEFAULT_LEVEL_WEIGHTS
    values_weight = float(config.values_weight_pct) if config else 10.0

    # 2. Fetch all active employees
    e_res = await db.execute(
        select(Employee).where(Employee.tenant_id == tenant_id, Employee.status == "ACTIVE")
    )
    employees = e_res.scalars().all()
    cascaded_count = 0

    for emp in employees:
        pos_level = _infer_employee_level(emp.job_title)
        shared_weight = float(level_weights.get(pos_level, 20.0))
        indiv_target_weight = max(0.0, round(100.0 - (shared_weight + values_weight), 2))

        # Check existing sheet
        s_res = await db.execute(
            select(EmployeeKPISheet).where(
                EmployeeKPISheet.employee_id == emp.id,
                EmployeeKPISheet.tenant_id == tenant_id,
                EmployeeKPISheet.fiscal_year == cascade_fy,
            ).order_by(desc(EmployeeKPISheet.updated_at))
        )
        sheet = s_res.scalars().first()
        if not sheet:
            sheet = EmployeeKPISheet(
                tenant_id=tenant_id,
                employee_id=emp.id,
                fiscal_year=cascade_fy,
                position_level=pos_level,
                company_shared_weight_pct=shared_weight,
                values_weight_pct=values_weight,
                individual_target_weight_pct=indiv_target_weight,
                total_weight_pct=100.0,
                status="DRAFT",
                kpis_json=json.dumps([]),
            )
            db.add(sheet)
        else:
            sheet.company_shared_weight_pct = shared_weight
            sheet.values_weight_pct = values_weight
            sheet.individual_target_weight_pct = indiv_target_weight
            sheet.position_level = pos_level
            sheet.total_weight_pct = 100.0

        cascaded_count += 1

    await db.flush()
    return {
        "success": True,
        "employees_cascaded": cascaded_count,
        "fiscal_year": req.fiscal_year,
        "level_weights_applied": level_weights,
        "values_weight_pct": values_weight,
    }


@app.get("/employees/{emp_id}/kpi-sheet")
async def get_employee_kpi_sheet(
    emp_id: uuid.UUID,
    fiscal_year: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Retrieve an individual employee's KPI sheet with shared company cascade and SMART criteria."""
    emp = await _get_employee_or_404(emp_id, tenant_id, db)

    # Fetch company KPI config
    cq = select(CompanyKPIConfig).where(CompanyKPIConfig.tenant_id == tenant_id)
    if fiscal_year:
        cq = cq.where(CompanyKPIConfig.fiscal_year == fiscal_year)
    c_res = await db.execute(cq.order_by(desc(CompanyKPIConfig.updated_at)))
    config = c_res.scalars().first()
    comp_scores = _calculate_company_scores(config) if config else {
        "sales_budget_zar": 3500000.0, "sales_actual_zar": 0.0, "sales_achievement_pct": 0.0,
        "cost_budget_zar": 2100000.0, "cost_actual_zar": 0.0, "cost_efficiency_pct": 100.0,
        "profit_budget_zar": 1400000.0, "profit_actual_zar": 0.0, "profit_achievement_pct": 0.0,
        "company_shared_score_pct": 0.0, "corporate_attainment_index": 0.0, "values_weight_pct": 10.0,
        "level_weights": DEFAULT_LEVEL_WEIGHTS,
    }

    sq = select(EmployeeKPISheet).where(
        EmployeeKPISheet.employee_id == emp_id,
        EmployeeKPISheet.tenant_id == tenant_id,
    )
    if fiscal_year:
        sq = sq.where(EmployeeKPISheet.fiscal_year == fiscal_year)
    s_res = await db.execute(sq.order_by(desc(EmployeeKPISheet.updated_at)))
    sheet = s_res.scalars().first()
    if not sheet:
        pos_level = _infer_employee_level(emp.job_title)
        level_weights = comp_scores.get("level_weights", DEFAULT_LEVEL_WEIGHTS)
        shared_weight = float(level_weights.get(pos_level, 20.0))
        val_weight = float(comp_scores.get("values_weight_pct", 10.0))
        indiv_target = max(0.0, round(100.0 - (shared_weight + val_weight), 2))

        # Default sample ISP individual KPI based on role
        sample_kpis = [
            {
                "id": str(uuid.uuid4()),
                "title": f"Operational Excellence & Department Deliverables ({emp.department})",
                "category": "Department Goals",
                "weight_pct": round(indiv_target * 0.6, 1),
                "timeline": "Quarterly Milestones (Q1-Q4)",
                "measurable": "100% SLA fulfillment on primary duties with <2% error rate",
                "requirement": "Monthly department sign-off and JIRA/Service audit records",
                "current_level": 3,
                "score": 100.0,
                "smart_criteria": {
                    "level_1": {"timeline": "Monthly", "measurable": "<80% target attainment", "requirement": "Audit log"},
                    "level_2": {"timeline": "Monthly", "measurable": "80-94% target attainment", "requirement": "Supervisor review"},
                    "level_3": {"timeline": "Monthly", "measurable": "95-100% on budget target", "requirement": "Verified system records"},
                    "level_4": {"timeline": "Monthly", "measurable": "101-115% stretch performance", "requirement": "Peer and manager sign-off"},
                    "level_5": {"timeline": "Annual", "measurable": ">115% breakthrough benchmarks", "requirement": "Executive commendation"},
                }
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Cost Optimization & Resource Efficiency",
                "category": "Cost Management",
                "weight_pct": round(indiv_target * 0.4, 1),
                "timeline": "Continuous / Monthly",
                "measurable": "Maintain zero avoidable wastage and identify 1 operational saving opportunity",
                "requirement": "Documented cost saving proposal submitted to finance",
                "current_level": 3,
                "score": 100.0,
                "smart_criteria": {
                    "level_1": {"timeline": "Monthly", "measurable": "Over budget spend", "requirement": "Variance report"},
                    "level_2": {"timeline": "Monthly", "measurable": "Within 2% of budget", "requirement": "Expense logs"},
                    "level_3": {"timeline": "Monthly", "measurable": "On budget with zero unauthorized spend", "requirement": "Finance verified ledger"},
                    "level_4": {"timeline": "Monthly", "measurable": "3-5% verified savings", "requirement": "Approved optimization log"},
                    "level_5": {"timeline": "Annual", "measurable": ">8% structural cost reduction", "requirement": "CFO commendation"},
                }
            }
        ]

        sheet = EmployeeKPISheet(
            tenant_id=tenant_id,
            employee_id=emp_id,
            fiscal_year=fiscal_year or DEFAULT_FISCAL_YEAR,
            position_level=pos_level,
            company_shared_weight_pct=shared_weight,
            values_weight_pct=val_weight,
            individual_target_weight_pct=indiv_target,
            total_weight_pct=100.0,
            status="DRAFT",
            kpis_json=json.dumps(sample_kpis),
            overall_score=95.0,
        )
        db.add(sheet)
        await db.flush()
        await db.refresh(sheet)

    kpis_list = json.loads(sheet.kpis_json) if sheet.kpis_json else []

    return {
        "id": str(sheet.id),
        "employee_id": str(emp.id),
        "employee_name": emp.full_name,
        "job_title": emp.job_title,
        "department": emp.department,
        "fiscal_year": sheet.fiscal_year,
        "position_level": sheet.position_level,
        "company_shared_weight_pct": float(sheet.company_shared_weight_pct),
        "values_weight_pct": float(sheet.values_weight_pct),
        "individual_target_weight_pct": float(sheet.individual_target_weight_pct),
        "total_weight_pct": float(sheet.total_weight_pct),
        "status": sheet.status,
        "kpis": kpis_list,
        "overall_score": float(sheet.overall_score) if sheet.overall_score is not None else None,
        "reviewer_notes": sheet.reviewer_notes,
        "company_benchmarks": comp_scores,
        "created_at": sheet.created_at,
        "updated_at": sheet.updated_at,
    }


@app.put("/employees/{emp_id}/kpi-sheet")
async def update_employee_kpi_sheet(
    emp_id: uuid.UUID,
    data: EmployeeKPISheetUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Save and validate an employee's KPI sheet with SMART criteria and auto-calculated score."""
    await _get_employee_or_404(emp_id, tenant_id, db)
    put_fy = data.fiscal_year or DEFAULT_FISCAL_YEAR
    s_res = await db.execute(
        select(EmployeeKPISheet).where(
            EmployeeKPISheet.employee_id == emp_id,
            EmployeeKPISheet.tenant_id == tenant_id,
            EmployeeKPISheet.fiscal_year == put_fy,
        ).order_by(desc(EmployeeKPISheet.updated_at))
    )
    sheet = s_res.scalars().first()

    # -- Server-side validation (before any mutation) --
    eff_status = (data.status or (sheet.status if sheet else "DRAFT") or "DRAFT").upper()
    if eff_status not in VALID_SHEET_STATUSES:
        raise HTTPException(status_code=422, detail={
            "message": f"Invalid status '{data.status}'. Must be one of DRAFT, SUBMITTED, APPROVED.",
            "allowed_statuses": sorted(VALID_SHEET_STATUSES),
        })
    data.status = eff_status
    eff_kpis = data.kpis
    if eff_kpis is None and sheet is not None and sheet.kpis_json:
        try:
            eff_kpis = json.loads(sheet.kpis_json)
        except Exception:
            eff_kpis = []
    eff_kpis = eff_kpis or []
    item_errors = []
    item_weight_sum = 0.0
    for idx, item in enumerate(eff_kpis):
        if not isinstance(item, dict):
            item_errors.append(f"KPI #{idx + 1}: must be an object")
            continue
        if not str(item.get("title") or "").strip():
            item_errors.append(f"KPI #{idx + 1}: title is required")
        try:
            w = float(item.get("weight_pct"))
            if w < 0 or w != w:
                raise ValueError
            item_weight_sum += w
        except (TypeError, ValueError):
            item_errors.append(f"KPI #{idx + 1}: weight_pct must be a number >= 0")
        sc = item.get("smart_criteria")
        if sc is not None:
            allowed = {f"level_{i}" for i in range(1, 6)}
            if not isinstance(sc, dict) or set(sc.keys()) - allowed:
                bad = sorted(set(sc.keys()) - allowed) if isinstance(sc, dict) else ["<not an object>"]
                item_errors.append(f"KPI #{idx + 1}: smart_criteria may only contain level_1..level_5 (invalid: {bad})")
    if item_errors:
        raise HTTPException(status_code=422, detail={"message": "Invalid KPI items: " + "; ".join(item_errors), "errors": item_errors})

    def _pick(new, old, default):
        return float(new if new is not None else (old if old is not None else default))
    sh_w = _pick(data.company_shared_weight_pct, sheet.company_shared_weight_pct if sheet else None, 20.0)
    val_w = _pick(data.values_weight_pct, sheet.values_weight_pct if sheet else None, 10.0)
    ind_w = _pick(data.individual_target_weight_pct, sheet.individual_target_weight_pct if sheet else None, 70.0)
    total_w = round(sh_w + val_w + ind_w, 2)
    item_sum = round(item_weight_sum, 2)
    if eff_status != "DRAFT":
        problems = []
        if abs(total_w - 100.0) > WEIGHT_TOLERANCE:
            problems.append(f"shared ({sh_w}) + values ({val_w}) + individual ({ind_w}) = {total_w}, must equal 100")
        if abs(item_sum - ind_w) > WEIGHT_TOLERANCE:
            problems.append(f"individual KPI item weights sum to {item_sum}, must equal individual_target_weight_pct ({ind_w})")
        if problems:
            raise HTTPException(status_code=422, detail={
                "message": f"Cannot save as {eff_status}: " + "; ".join(problems) + ". Save as DRAFT to keep incomplete work.",
                "computed_total_weight_pct": total_w,
                "computed_kpi_items_weight_pct": item_sum,
                "individual_target_weight_pct": ind_w,
            })

    if not sheet:
        sheet = EmployeeKPISheet(tenant_id=tenant_id, employee_id=emp_id)
        db.add(sheet)

    if data.fiscal_year is not None:
        sheet.fiscal_year = data.fiscal_year
    if data.position_level is not None:
        sheet.position_level = data.position_level
    if data.company_shared_weight_pct is not None:
        sheet.company_shared_weight_pct = data.company_shared_weight_pct
    if data.values_weight_pct is not None:
        sheet.values_weight_pct = data.values_weight_pct
    if data.individual_target_weight_pct is not None:
        sheet.individual_target_weight_pct = data.individual_target_weight_pct
    if data.status is not None:
        sheet.status = data.status
    if data.kpis is not None:
        sheet.kpis_json = json.dumps(data.kpis)
    if data.overall_score is not None:
        sheet.overall_score = data.overall_score
    if data.reviewer_notes is not None:
        sheet.reviewer_notes = data.reviewer_notes

    # Verify total weight
    sh_w = float(sheet.company_shared_weight_pct or 0.0)
    val_w = float(sheet.values_weight_pct or 0.0)
    ind_w = float(sheet.individual_target_weight_pct or 0.0)
    sheet.total_weight_pct = round(sh_w + val_w + ind_w, 2)

    await db.flush()
    await db.refresh(sheet)
    return {
        "success": True,
        "sheet_id": str(sheet.id),
        "status": sheet.status,
        "total_weight_pct": float(sheet.total_weight_pct),
        "overall_score": float(sheet.overall_score) if sheet.overall_score is not None else None,
    }


@app.post("/kpis/ai-smart-generate")
async def generate_ai_smart_criteria(
    req: AISmartCriteriaRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """AI Copilot: Generates SMART criteria across achievement levels 1 to 5 with timeline, measurable, and requirements."""
    title = req.title.strip()
    job_title = req.job_title or "Specialist"
    dept = req.department or "Operations"

    # Contextual SMART synthesis based on domain keywords
    title_lower = title.lower()
    is_cost = any(w in title_lower for w in ["cost", "spend", "saving", "budget", "reduce cost", "expense"])
    is_sales = any(w in title_lower for w in ["sale", "revenue", "mrr", "deal", "pipeline", "client", "churn"])
    is_tech = any(w in title_lower for w in ["fiber", "network", "mttr", "sla", "uptime", "latency", "noc", "infra"])

    if is_cost:
        levels = {
            "level_1": {
                "label": "Level 1: Unsatisfactory (<80%)",
                "timeline": "Month 1-3 Review",
                "measurable": "Operating expenditures exceed budget ceiling by >10%; zero cost initiatives completed.",
                "requirement": "Audited ERP expense report showing monthly budget overrun.",
            },
            "level_2": {
                "label": "Level 2: Needs Improvement (80-94%)",
                "timeline": "Mid-Year Review",
                "measurable": "Expenditures held within 0-3% above budget; 1 cost reduction initiative underway.",
                "requirement": "Supplier contract negotiation drafts and internal procurement logs.",
            },
            "level_3": {
                "label": "Level 3: Meets Expectation / Target Budget (100%)",
                "timeline": "Quarterly Milestones",
                "measurable": "100% adherence to agreed budget ceiling (e.g. 5% structural reduction against baseline).",
                "requirement": "Approved monthly financial reconciliation verified by Department Head & Finance.",
            },
            "level_4": {
                "label": "Level 4: Exceeds Expectation (110-125%)",
                "timeline": "Q3-Q4 Delivery",
                "measurable": "Delivered 8-12% verifiable cost savings without impacting SLA or customer satisfaction.",
                "requirement": "Signed vendor rebate agreements and Finance validated ledger entries.",
            },
            "level_5": {
                "label": "Level 5: Outstanding Breakthrough (>125%)",
                "timeline": "Full Fiscal Year",
                "measurable": ">15% sustained cost reduction with an automated or architectural innovation adopted across departments.",
                "requirement": "Executive committee commendation and cross-departmental impact audit report.",
            },
        }
    elif is_sales:
        levels = {
            "level_1": {
                "label": "Level 1: Unsatisfactory (<80%)",
                "timeline": "Monthly Review",
                "measurable": "Closed deal revenue below 80% of sales quota (<R160k vs R200k target).",
                "requirement": "CRM pipeline report and opportunity audit log.",
            },
            "level_2": {
                "label": "Level 2: Needs Improvement (80-94%)",
                "timeline": "Monthly Review",
                "measurable": "Quotas achieved between 80% and 94% with healthy prospecting pipeline.",
                "requirement": "CRM activity logs showing at least 40 customer outreach touchpoints.",
            },
            "level_3": {
                "label": "Level 3: Meets Expectation / Target Budget (100%)",
                "timeline": "Monthly & Quarterly Targets",
                "measurable": "Achieved 100% of sales quota on target products (Fiber B2B / FTTH / VoIP SLAs).",
                "requirement": "Signed customer service contracts and billing activation confirmation.",
            },
            "level_4": {
                "label": "Level 4: Exceeds Expectation (110-125%)",
                "timeline": "Consecutive Quarters",
                "measurable": "Attained 110-125% of quota; sustained client retention >98%.",
                "requirement": "Finance-cleared commission disbursement voucher and client onboarding report.",
            },
            "level_5": {
                "label": "Level 5: Outstanding Breakthrough (>125%)",
                "timeline": "Annual Cycle",
                "measurable": "Exceeded quota by >130%; landed 2+ multi-year enterprise anchor fiber accounts.",
                "requirement": "President's Club recognition and Master Service Agreements executed.",
            },
        }
    elif is_tech:
        levels = {
            "level_1": {
                "label": "Level 1: Unsatisfactory (<80%)",
                "timeline": "Monthly Review",
                "measurable": "Mean Time to Repair (MTTR) > 6.0 hours; core fiber availability < 99.5%.",
                "requirement": "Zabbix/Prometheus outage incident logs and escalated complaint tickets.",
            },
            "level_2": {
                "label": "Level 2: Needs Improvement (80-94%)",
                "timeline": "Monthly Review",
                "measurable": "MTTR between 4.5 and 6.0 hours; network uptime 99.8%.",
                "requirement": "Post-incident reviews (PIR) logged with corrective root-cause actions.",
            },
            "level_3": {
                "label": "Level 3: Meets Expectation / Target Budget (100%)",
                "timeline": "Continuous Service Window",
                "measurable": "MTTR <= 4.0 hours, 99.9% fiber core uptime, zero major SLA penalties.",
                "requirement": "Automated telemetry dashboard report signed off by NOC Operations Manager.",
            },
            "level_4": {
                "label": "Level 4: Exceeds Expectation (110-125%)",
                "timeline": "Quarterly Target",
                "measurable": "MTTR <= 2.8 hours, First Contact Resolution > 85%, automated failover verified.",
                "requirement": "Synthetic uptime test reports and zero customer SLA breach claims.",
            },
            "level_5": {
                "label": "Level 5: Outstanding Breakthrough (>125%)",
                "timeline": "Annual Cycle",
                "measurable": "Zero unplanned core fiber outages; authored self-healing bot resolving 90% faults.",
                "requirement": "CTO commendation and architecture runbook published to company knowledge base.",
            },
        }
    else:
        levels = {
            "level_1": {
                "label": "Level 1: Unsatisfactory (<80%)",
                "timeline": "End of Q1 Review",
                "measurable": "Key deliverable delayed >30 days or quality compliance <75%.",
                "requirement": "Supervisor non-conformance memo and audit log.",
            },
            "level_2": {
                "label": "Level 2: Needs Improvement (80-94%)",
                "timeline": "Mid-Year Review",
                "measurable": "Deliverables completed with minor revisions; SLA score 80-94%.",
                "requirement": "Sprint task tracker and peer review comments.",
            },
            "level_3": {
                "label": "Level 3: Meets Expectation / Target Budget (100%)",
                "timeline": "Quarterly Delivery Milestones",
                "measurable": "100% of objective milestones achieved on time and within agreed budget.",
                "requirement": "Formal stakeholder sign-off and validated deliverable report.",
            },
            "level_4": {
                "label": "Level 4: Exceeds Expectation (110-125%)",
                "timeline": "Q3 Target Completion",
                "measurable": "Milestones delivered 2+ weeks ahead of schedule with 10% quality enhancement.",
                "requirement": "Verified metrics report endorsed by Department Head.",
            },
            "level_5": {
                "label": "Level 5: Outstanding Breakthrough (>125%)",
                "timeline": "Annual Fiscal Review",
                "measurable": "Breakthrough operational standard implemented and adopted company-wide.",
                "requirement": "Executive commendation and enterprise capability enhancement audit.",
            },
        }

    return {
        "title": title,
        "job_title": job_title,
        "department": dept,
        "suggested_measurable": levels["level_3"]["measurable"],
        "suggested_timeline": levels["level_3"]["timeline"],
        "suggested_requirement": levels["level_3"]["requirement"],
        "smart_criteria": levels,
    }


# ═══════════════════════════════════════════════════════════════════════════
# STAFF SCHEDULE
# ═══════════════════════════════════════════════════════════════════════════

class ScheduleCreate(BaseModel):
    employee_id: uuid.UUID
    schedule_date: date
    shift_start: str  # "HH:MM" format
    shift_end: str
    shift_type: str = "REGULAR"
    department: str
    notes: Optional[str] = None


@app.get("/schedules")
async def list_schedules(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    employee_id: Optional[uuid.UUID] = Query(None),
    department: Optional[str] = Query(None),
):
    stmt = select(StaffSchedule).where(StaffSchedule.tenant_id == tenant_id)
    if from_date:
        stmt = stmt.where(StaffSchedule.schedule_date >= from_date)
    if to_date:
        stmt = stmt.where(StaffSchedule.schedule_date <= to_date)
    if employee_id:
        stmt = stmt.where(StaffSchedule.employee_id == employee_id)
    if department:
        stmt = stmt.where(StaffSchedule.department == department)
    result = await db.execute(stmt.order_by(StaffSchedule.schedule_date, StaffSchedule.shift_start))
    rows = result.scalars().all()
    return [
        {
            "id": r.id, "employee_id": r.employee_id, "schedule_date": r.schedule_date,
            "shift_start": str(r.shift_start), "shift_end": str(r.shift_end),
            "shift_type": r.shift_type, "department": r.department,
            "status": r.status, "notes": r.notes,
        }
        for r in rows
    ]


@app.post("/schedules", status_code=status.HTTP_201_CREATED)
async def create_schedule(
    data: ScheduleCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    await _get_employee_or_404(data.employee_id, tenant_id, db)
    from datetime import time as t
    sh, sm = map(int, data.shift_start.split(":"))
    eh, em = map(int, data.shift_end.split(":"))
    sched = StaffSchedule(
        tenant_id=tenant_id,
        employee_id=data.employee_id,
        schedule_date=data.schedule_date,
        shift_start=t(sh, sm),
        shift_end=t(eh, em),
        shift_type=data.shift_type,
        department=data.department,
        status="SCHEDULED",
        notes=data.notes,
    )
    db.add(sched)
    await db.flush()
    await db.refresh(sched)
    return {
        "id": sched.id, "employee_id": sched.employee_id, "schedule_date": sched.schedule_date,
        "shift_start": str(sched.shift_start), "shift_end": str(sched.shift_end),
        "shift_type": sched.shift_type, "department": sched.department, "status": sched.status,
    }


@app.put("/schedules/{sched_id}/confirm")
async def confirm_schedule(
    sched_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    result = await db.execute(
        select(StaffSchedule).where(StaffSchedule.id == sched_id, StaffSchedule.tenant_id == tenant_id)
    )
    sched = result.scalars().first()
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    sched.status = "CONFIRMED"
    await db.flush()
    return {"id": sched.id, "status": "CONFIRMED"}


@app.delete("/schedules/{sched_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    sched_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    result = await db.execute(
        select(StaffSchedule).where(StaffSchedule.id == sched_id, StaffSchedule.tenant_id == tenant_id)
    )
    sched = result.scalars().first()
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await db.delete(sched)
    await db.flush()


@app.get("/schedules/demand-forecast")
async def get_demand_forecast(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
    days: int = Query(7, ge=1, le=30),
):
    """Return staffing demand forecast derived from workforce, leave, and call-center queue data.

    Formula per day:
        available_pool  = active_employees - employees_on_approved_leave_that_day
        day_factor      = day-of-week load multiplier (ISP call center patterns)
        queue_factor    = live queue pressure scalar (from call_center service, optional)
        required_staff  = max(round(available_pool * SERVICE_RATIO * day_factor * queue_factor), MIN_FLOOR)
    """
    from datetime import timedelta

    # ── 1. Total active workforce for this tenant ────────────────────────
    emp_result = await db.execute(
        select(func.count(Employee.id)).where(
            Employee.tenant_id == tenant_id,
            Employee.status == "ACTIVE",
        )
    )
    active_employees: int = emp_result.scalar() or 0

    # Fraction of workforce needed for customer-facing / operational roles.
    # Configurable via env; default 0.70 for a typical ISP call centre.
    SERVICE_RATIO: float = float(os.getenv("HR_FORECAST_SERVICE_RATIO", "0.70"))
    MIN_FLOOR: int = int(os.getenv("HR_FORECAST_MIN_STAFF", "3"))

    # ── 2. Live queue pressure from call_center service (best-effort) ────
    CALL_CENTER_URL = os.getenv("CALL_CENTER_SERVICE_URL", "http://localhost:8007")
    queue_factor: float = 1.0
    queue_meta: dict = {}
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(
                f"{CALL_CENTER_URL}/queues/dashboard/summary",
                headers={"x-tenant-id": str(tenant_id)},
            )
            if resp.status_code == 200:
                summary = resp.json()
                total_load = (
                    summary.get("inbound", {}).get("total_active", 0)
                    + summary.get("inbound", {}).get("total_queued", 0)
                    + summary.get("outbound", {}).get("total_active", 0)
                    + summary.get("outbound", {}).get("total_queued", 0)
                )
                queue_meta = {"total_load": total_load}
                # Scale up requirement if queue is under pressure (>20 concurrent)
                if total_load > 40:
                    queue_factor = 1.20
                elif total_load > 20:
                    queue_factor = 1.10
    except Exception:
        pass  # Call center service unavailable — use baseline

    # ── 3. Day-of-week load multipliers (Mon–Sun) ───────────────────────
    # Based on typical ISP support patterns: peak mid-week, low weekends.
    DOW_FACTORS: list[float] = [1.15, 1.05, 1.00, 1.00, 0.90, 0.60, 0.40]
    # index 0 = Monday, 6 = Sunday (matches date.weekday())

    today = date.today()
    forecast = []

    for i in range(days):
        d = today + timedelta(days=i)

        # Count scheduled staff for this date
        sched_result = await db.execute(
            select(func.count(StaffSchedule.id)).where(
                StaffSchedule.tenant_id == tenant_id,
                StaffSchedule.schedule_date == d,
                StaffSchedule.status != "CANCELLED",
            )
        )
        scheduled: int = sched_result.scalar() or 0

        # Count employees on approved leave this day
        leave_result = await db.execute(
            select(func.count(LeaveRequest.id)).where(
                LeaveRequest.tenant_id == tenant_id,
                LeaveRequest.status == "APPROVED",
                LeaveRequest.start_date <= d,
                LeaveRequest.end_date >= d,
            )
        )
        on_leave: int = leave_result.scalar() or 0

        available_pool = max(active_employees - on_leave, 0)
        day_factor = DOW_FACTORS[d.weekday()]
        required = max(
            round(available_pool * SERVICE_RATIO * day_factor * queue_factor),
            MIN_FLOOR,
        )

        forecast.append({
            "date": d.isoformat(),
            "day": d.strftime("%A"),
            "scheduled_staff": scheduled,
            "required_staff": required,
            "gap": max(0, required - scheduled),
            # diagnostic fields for UI / debugging
            "_meta": {
                "active_employees": active_employees,
                "on_leave": on_leave,
                "available_pool": available_pool,
                "service_ratio": SERVICE_RATIO,
                "day_factor": day_factor,
                "queue_factor": queue_factor,
                **queue_meta,
            },
        })

    return forecast
# ═══════════════════════════════════════════════════════════════════════════
# TRAINING
# ═══════════════════════════════════════════════════════════════════════════

class CourseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str
    duration_hours: float = 1.0
    mandatory: bool = False


class EnrollmentCreate(BaseModel):
    employee_id: uuid.UUID
    course_id: uuid.UUID


@app.get("/training/courses")
async def list_courses(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
    category: Optional[str] = Query(None),
):
    stmt = select(TrainingCourse).where(TrainingCourse.tenant_id == tenant_id)
    if category:
        stmt = stmt.where(TrainingCourse.category == category)
    result = await db.execute(stmt.order_by(TrainingCourse.title))
    rows = result.scalars().all()
    return [
        {
            "id": r.id, "title": r.title, "description": r.description,
            "category": r.category, "duration_hours": float(r.duration_hours),
            "mandatory": r.mandatory, "status": r.status,
        }
        for r in rows
    ]


@app.post("/training/courses", status_code=status.HTTP_201_CREATED)
async def create_course(
    data: CourseCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    course = TrainingCourse(tenant_id=tenant_id, **data.dict())
    db.add(course)
    await db.flush()
    await db.refresh(course)
    return {
        "id": course.id, "title": course.title, "category": course.category,
        "duration_hours": float(course.duration_hours), "mandatory": course.mandatory,
        "status": course.status,
    }


@app.post("/training/enroll", status_code=status.HTTP_201_CREATED)
async def enroll_employee(
    data: EnrollmentCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    await _get_employee_or_404(data.employee_id, tenant_id, db)
    # Verify course exists
    result = await db.execute(
        select(TrainingCourse).where(
            TrainingCourse.id == data.course_id, TrainingCourse.tenant_id == tenant_id
        )
    )
    course = result.scalars().first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    enrollment = TrainingEnrollment(
        tenant_id=tenant_id,
        employee_id=data.employee_id,
        course_id=data.course_id,
        status="ENROLLED",
    )
    db.add(enrollment)
    await db.flush()
    await db.refresh(enrollment)
    return {
        "id": enrollment.id, "employee_id": enrollment.employee_id,
        "course_id": enrollment.course_id, "status": enrollment.status,
        "progress_pct": float(enrollment.progress_pct),
    }


@app.put("/training/enrollment/{enrollment_id}/progress")
async def update_progress(
    enrollment_id: uuid.UUID,
    progress_pct: float,
    score: Optional[float] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    result = await db.execute(
        select(TrainingEnrollment).where(
            TrainingEnrollment.id == enrollment_id, TrainingEnrollment.tenant_id == tenant_id
        )
    )
    enr = result.scalars().first()
    if not enr:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    enr.progress_pct = min(progress_pct, 100.0)
    if score is not None:
        enr.score = score
    if progress_pct >= 100:
        enr.status = "COMPLETED"
        enr.completed_at = datetime.utcnow()
    elif progress_pct > 0:
        enr.status = "IN_PROGRESS"
    await db.flush()
    return {
        "id": enr.id, "status": enr.status, "progress_pct": float(enr.progress_pct),
        "score": float(enr.score) if enr.score else None,
    }


@app.get("/employees/{emp_id}/training")
async def get_employee_training(
    emp_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    await _get_employee_or_404(emp_id, tenant_id, db)
    result = await db.execute(
        select(TrainingEnrollment, TrainingCourse)
        .join(TrainingCourse, TrainingEnrollment.course_id == TrainingCourse.id)
        .where(TrainingEnrollment.employee_id == emp_id, TrainingEnrollment.tenant_id == tenant_id)
        .order_by(desc(TrainingEnrollment.created_at))
    )
    return [
        {
            "enrollment_id": str(e.id), "course_id": str(c.id), "title": c.title,
            "category": c.category, "status": e.status, "progress_pct": float(e.progress_pct),
            "score": float(e.score) if e.score else None,
            "enrolled_at": e.enrolled_at, "completed_at": e.completed_at,
        }
        for e, c in result.all()
    ]


# ═══════════════════════════════════════════════════════════════════════════
# BENEFITS
# ═══════════════════════════════════════════════════════════════════════════

class BenefitEnrollCreate(BaseModel):
    employee_id: uuid.UUID
    benefit_type: str
    leave_balance_days: Optional[float] = None
    leave_used_days: Optional[float] = None
    shares_allocated: Optional[int] = None
    shares_vested: Optional[int] = None
    vesting_date: Optional[date] = None
    bonus_amount_zar: Optional[float] = None
    bonus_period: Optional[str] = None
    bonus_status: Optional[str] = None
    employer_contribution_pct: Optional[float] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


@app.get("/benefits")
async def list_benefits(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
    employee_id: Optional[uuid.UUID] = Query(None),
    benefit_type: Optional[str] = Query(None),
):
    stmt = select(BenefitEnrollment).where(BenefitEnrollment.tenant_id == tenant_id)
    if employee_id:
        stmt = stmt.where(BenefitEnrollment.employee_id == employee_id)
    if benefit_type:
        stmt = stmt.where(BenefitEnrollment.benefit_type == benefit_type)
    result = await db.execute(stmt.order_by(desc(BenefitEnrollment.created_at)))
    rows = result.scalars().all()
    return [
        {
            "id": r.id, "employee_id": r.employee_id, "benefit_type": r.benefit_type,
            "leave_balance_days": float(r.leave_balance_days) if r.leave_balance_days else None,
            "leave_used_days": float(r.leave_used_days) if r.leave_used_days else 0,
            "shares_allocated": r.shares_allocated, "shares_vested": r.shares_vested,
            "vesting_date": r.vesting_date,
            "bonus_amount_zar": float(r.bonus_amount_zar) if r.bonus_amount_zar else None,
            "bonus_period": r.bonus_period, "bonus_status": r.bonus_status,
            "employer_contribution_pct": float(r.employer_contribution_pct) if r.employer_contribution_pct else None,
            "enrolled": r.enrolled, "effective_from": r.effective_from, "effective_to": r.effective_to,
        }
        for r in rows
    ]


@app.post("/benefits", status_code=status.HTTP_201_CREATED)
async def create_benefit_enrollment(
    data: BenefitEnrollCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    await _get_employee_or_404(data.employee_id, tenant_id, db)
    ben = BenefitEnrollment(tenant_id=tenant_id, **data.dict())
    db.add(ben)
    await db.flush()
    await db.refresh(ben)
    return {"id": ben.id, "employee_id": ben.employee_id, "benefit_type": ben.benefit_type, "enrolled": ben.enrolled}


@app.get("/employees/{emp_id}/benefits")
async def get_employee_benefits(
    emp_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    await _get_employee_or_404(emp_id, tenant_id, db)
    result = await db.execute(
        select(BenefitEnrollment).where(
            BenefitEnrollment.employee_id == emp_id, BenefitEnrollment.tenant_id == tenant_id
        )
    )
    return [
        {
            "id": r.id, "benefit_type": r.benefit_type,
            "leave_balance_days": float(r.leave_balance_days) if r.leave_balance_days else None,
            "leave_used_days": float(r.leave_used_days) if r.leave_used_days else 0,
            "shares_allocated": r.shares_allocated, "shares_vested": r.shares_vested,
            "vesting_date": r.vesting_date,
            "bonus_amount_zar": float(r.bonus_amount_zar) if r.bonus_amount_zar else None,
            "bonus_period": r.bonus_period, "bonus_status": r.bonus_status,
            "enrolled": r.enrolled,
        }
        for r in result.scalars().all()
    ]


# ═══════════════════════════════════════════════════════════════════════════
# DISCIPLINARY ACTIONS
# ═══════════════════════════════════════════════════════════════════════════

class DisciplinaryCreate(BaseModel):
    employee_id: uuid.UUID
    action_type: str
    incident_date: date
    description: str
    outcome: Optional[str] = None
    suspension_days: Optional[int] = None


@app.get("/disciplinary")
async def list_disciplinary(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
    employee_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
):
    stmt = select(DisciplinaryAction).where(DisciplinaryAction.tenant_id == tenant_id)
    if employee_id:
        stmt = stmt.where(DisciplinaryAction.employee_id == employee_id)
    if status:
        stmt = stmt.where(DisciplinaryAction.status == status)
    result = await db.execute(stmt.order_by(desc(DisciplinaryAction.incident_date)))
    return [
        {
            "id": r.id, "employee_id": r.employee_id, "action_type": r.action_type,
            "incident_date": r.incident_date, "description": r.description,
            "outcome": r.outcome, "suspension_days": r.suspension_days,
            "status": r.status, "reviewed_by": r.reviewed_by,
        }
        for r in result.scalars().all()
    ]


@app.post("/disciplinary", status_code=status.HTTP_201_CREATED)
async def create_disciplinary(
    data: DisciplinaryCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    await _get_employee_or_404(data.employee_id, tenant_id, db)
    action = DisciplinaryAction(tenant_id=tenant_id, **data.dict())
    db.add(action)
    await db.flush()
    await db.refresh(action)
    return {
        "id": action.id, "employee_id": action.employee_id, "action_type": action.action_type,
        "incident_date": action.incident_date, "status": action.status,
    }


@app.put("/disciplinary/{action_id}/resolve")
async def resolve_disciplinary(
    action_id: uuid.UUID,
    outcome: str,
    reviewed_by: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    result = await db.execute(
        select(DisciplinaryAction).where(
            DisciplinaryAction.id == action_id, DisciplinaryAction.tenant_id == tenant_id
        )
    )
    action = result.scalars().first()
    if not action:
        raise HTTPException(status_code=404, detail="Disciplinary action not found")
    action.status = "RESOLVED"
    action.outcome = outcome
    action.reviewed_by = reviewed_by
    await db.flush()
    return {"id": action.id, "status": "RESOLVED"}


# ═══════════════════════════════════════════════════════════════════════════
# STAFF EXIT
# ═══════════════════════════════════════════════════════════════════════════

class StaffExitCreate(BaseModel):
    employee_id: uuid.UUID
    exit_type: str
    reason: Optional[str] = None
    notice_date: date
    last_working_date: date


@app.get("/exits")
async def list_exits(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
    status: Optional[str] = Query(None),
):
    stmt = select(StaffExit).where(StaffExit.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(StaffExit.status == status)
    result = await db.execute(stmt.order_by(desc(StaffExit.notice_date)))
    return [
        {
            "id": r.id, "employee_id": r.employee_id, "exit_type": r.exit_type,
            "reason": r.reason, "notice_date": r.notice_date,
            "last_working_date": r.last_working_date,
            "exit_interview_done": r.exit_interview_done,
            "assets_returned": r.assets_returned,
            "access_revoked": r.access_revoked,
            "final_payout_zar": float(r.final_payout_zar) if r.final_payout_zar else None,
            "status": r.status,
        }
        for r in result.scalars().all()
    ]


@app.post("/exits", status_code=status.HTTP_201_CREATED)
async def create_exit(
    data: StaffExitCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    emp = await _get_employee_or_404(data.employee_id, tenant_id, db)
    exit_rec = StaffExit(tenant_id=tenant_id, **data.dict())
    db.add(exit_rec)
    # Mark employee as exiting
    emp.status = "EXITING"
    await db.flush()
    await db.refresh(exit_rec)
    return {
        "id": exit_rec.id, "employee_id": exit_rec.employee_id,
        "exit_type": exit_rec.exit_type, "status": exit_rec.status,
    }


@app.put("/exits/{exit_id}/checklist")
async def update_exit_checklist(
    exit_id: uuid.UUID,
    exit_interview_done: Optional[bool] = None,
    assets_returned: Optional[bool] = None,
    access_revoked: Optional[bool] = None,
    final_payout_zar: Optional[float] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    result = await db.execute(
        select(StaffExit).where(StaffExit.id == exit_id, StaffExit.tenant_id == tenant_id)
    )
    exit_rec = result.scalars().first()
    if not exit_rec:
        raise HTTPException(status_code=404, detail="Exit record not found")
    if exit_interview_done is not None:
        exit_rec.exit_interview_done = exit_interview_done
    if assets_returned is not None:
        exit_rec.assets_returned = assets_returned
    if access_revoked is not None:
        exit_rec.access_revoked = access_revoked
    if final_payout_zar is not None:
        exit_rec.final_payout_zar = final_payout_zar
    # Auto-complete if all done
    if exit_rec.exit_interview_done and exit_rec.assets_returned and exit_rec.access_revoked:
        exit_rec.status = "COMPLETED"
        # Deactivate employee
        emp_result = await db.execute(
            select(Employee).where(Employee.id == exit_rec.employee_id, Employee.tenant_id == tenant_id)
        )
        emp = emp_result.scalars().first()
        if emp:
            emp.status = "INACTIVE"
    await db.flush()
    return {
        "id": exit_rec.id, "status": exit_rec.status,
        "exit_interview_done": exit_rec.exit_interview_done,
        "assets_returned": exit_rec.assets_returned,
        "access_revoked": exit_rec.access_revoked,
    }


@app.get("/exits/{exit_id}/checklist")
async def get_exit_checklist(
    exit_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    result = await db.execute(
        select(StaffExit).where(StaffExit.id == exit_id, StaffExit.tenant_id == tenant_id)
    )
    exit_rec = result.scalars().first()
    if not exit_rec:
        raise HTTPException(status_code=404, detail="Exit record not found")
    return {
        "id": exit_rec.id, "exit_type": exit_rec.exit_type,
        "exit_interview_done": exit_rec.exit_interview_done,
        "assets_returned": exit_rec.assets_returned,
        "access_revoked": exit_rec.access_revoked,
        "final_payout_zar": float(exit_rec.final_payout_zar) if exit_rec.final_payout_zar else None,
        "status": exit_rec.status,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ONBOARDING TASKS
# ═══════════════════════════════════════════════════════════════════════════

class OnboardingTaskCreate(BaseModel):
    employee_id: uuid.UUID
    task_name: str
    description: Optional[str] = None
    owner_department: str
    due_date: Optional[date] = None
    sort_order: int = 0


class OnboardingTaskBulkCreate(BaseModel):
    employee_id: uuid.UUID
    tasks: List[OnboardingTaskCreate]


@app.get("/onboarding/tasks")
async def list_all_onboarding_tasks(
    employee_id: Optional[uuid.UUID] = Query(None),
    owner_department: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    stmt = (
        select(OnboardingTask, Employee.full_name, Employee.employee_id)
        .outerjoin(Employee, OnboardingTask.employee_id == Employee.id)
        .where(OnboardingTask.tenant_id == tenant_id)
    )
    if employee_id:
        stmt = stmt.where(OnboardingTask.employee_id == employee_id)
    if owner_department:
        stmt = stmt.where(OnboardingTask.owner_department == owner_department)
    if status:
        stmt = stmt.where(OnboardingTask.status == status)

    result = await db.execute(stmt.order_by(OnboardingTask.due_date, OnboardingTask.sort_order))
    items = []
    for r, emp_name, emp_code in result.all():
        items.append({
            "id": r.id,
            "employee_id": r.employee_id,
            "employee_name": emp_name or "New Hire",
            "employee_code": emp_code or "",
            "task_name": r.task_name,
            "description": r.description,
            "owner_department": r.owner_department,
            "status": r.status,
            "due_date": r.due_date,
            "completed_at": r.completed_at,
            "sort_order": r.sort_order,
        })
    return items


@app.get("/onboarding/{emp_id}")
async def get_onboarding_tasks(
    emp_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    await _get_employee_or_404(emp_id, tenant_id, db)
    result = await db.execute(
        select(OnboardingTask)
        .where(OnboardingTask.employee_id == emp_id, OnboardingTask.tenant_id == tenant_id)
        .order_by(OnboardingTask.sort_order)
    )
    return [
        {
            "id": r.id, "task_name": r.task_name, "description": r.description,
            "owner_department": r.owner_department, "status": r.status,
            "due_date": r.due_date, "completed_at": r.completed_at, "sort_order": r.sort_order,
        }
        for r in result.scalars().all()
    ]


@app.post("/onboarding/tasks", status_code=status.HTTP_201_CREATED)
async def create_onboarding_task(
    data: OnboardingTaskCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    await _get_employee_or_404(data.employee_id, tenant_id, db)
    task = OnboardingTask(tenant_id=tenant_id, **data.dict())
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return {
        "id": task.id, "task_name": task.task_name, "owner_department": task.owner_department,
        "status": task.status,
    }


@app.post("/onboarding/tasks/bulk", status_code=status.HTTP_201_CREATED)
async def bulk_create_onboarding_tasks(
    data: OnboardingTaskBulkCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    await _get_employee_or_404(data.employee_id, tenant_id, db)
    created = []
    for t in data.tasks:
        task = OnboardingTask(
            tenant_id=tenant_id,
            employee_id=data.employee_id,
            task_name=t.task_name,
            description=t.description,
            owner_department=t.owner_department,
            due_date=t.due_date,
            sort_order=t.sort_order,
        )
        db.add(task)
        await db.flush()
        await db.refresh(task)
        created.append({"id": task.id, "task_name": task.task_name, "status": task.status})
    return created


@app.put("/onboarding/tasks/{task_id}/complete")
async def complete_onboarding_task(
    task_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    result = await db.execute(
        select(OnboardingTask).where(
            OnboardingTask.id == task_id, OnboardingTask.tenant_id == tenant_id
        )
    )
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "DONE"
    task.completed_at = datetime.utcnow()
    await db.flush()
    return {"id": task.id, "status": "DONE"}


@app.delete("/onboarding/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_onboarding_task(
    task_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    result = await db.execute(
        select(OnboardingTask).where(
            OnboardingTask.id == task_id, OnboardingTask.tenant_id == tenant_id
        )
    )
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.delete(task)
    await db.flush()


@app.get("/onboarding/{emp_id}/progress")
async def get_onboarding_progress(
    emp_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Return onboarding progress summary for an employee."""
    await _get_employee_or_404(emp_id, tenant_id, db)
    result = await db.execute(
        select(OnboardingTask.status, func.count(OnboardingTask.id))
        .where(OnboardingTask.employee_id == emp_id, OnboardingTask.tenant_id == tenant_id)
        .group_by(OnboardingTask.status)
    )
    counts = {row[0]: row[1] for row in result.all()}
    total = sum(counts.values())
    done = counts.get("DONE", 0) + counts.get("SKIPPED", 0)
    return {
        "employee_id": emp_id,
        "total_tasks": total,
        "completed": done,
        "progress_pct": round((done / total * 100) if total > 0 else 0, 1),
        "breakdown": counts,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ANALYTICS  (existing attrition, extended)
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/analytics/attrition-risk")
async def get_attrition_risk_overview(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    emp_result = await db.execute(
        select(Employee).where(Employee.tenant_id == tenant_id, Employee.status == "ACTIVE")
    )
    employees = emp_result.scalars().all()
    total = len(employees)
    if total == 0:
        return {
            "total_employees": 0, "high_risk_count": 0, "medium_risk_count": 0,
            "low_risk_count": 0, "primary_attrition_factors": [], "recommendations": [],
        }
    high_risk = medium_risk = low_risk = 0
    risk_factors = set()
    for emp in employees:
        review_result = await db.execute(
            select(PerformanceReview)
            .where(PerformanceReview.employee_id == emp.id)
            .order_by(desc(PerformanceReview.created_at))
            .limit(1)
        )
        review = review_result.scalars().first()
        if review and review.attrition_risk:
            risk = review.attrition_risk.upper()
            if risk == "HIGH":
                high_risk += 1
                if review.kpi_score is not None and float(review.kpi_score) < 5.0:
                    risk_factors.add("Low KPI scores")
                if review.sentiment_score is not None and float(review.sentiment_score) < 0.5:
                    risk_factors.add("Negative sentiment trends")
            elif risk == "MEDIUM":
                medium_risk += 1
            else:
                low_risk += 1
        else:
            low_risk += 1
    factors = list(risk_factors) if risk_factors else [
        "High volume of URGENT tickets", "Shift burnout", "Peer feedback sentiment dips"
    ]
    recommendations = []
    if high_risk > 0:
        recommendations.append("Initiate retention interviews with high-risk employees")
    if medium_risk > 0:
        recommendations.append("Review workload distribution for medium-risk employees")
    if not recommendations:
        recommendations.append("Continue monitoring sentiment and performance trends")
    return {
        "total_employees": total,
        "high_risk_count": high_risk,
        "medium_risk_count": medium_risk,
        "low_risk_count": low_risk,
        "primary_attrition_factors": factors,
        "recommendations": recommendations,
    }


@app.get("/analytics/headcount")
async def get_headcount_analytics(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Headcount by department and status."""
    result = await db.execute(
        select(Employee.department, Employee.status, func.count(Employee.id))
        .where(Employee.tenant_id == tenant_id)
        .group_by(Employee.department, Employee.status)
    )
    dept_data = {}
    for dept, stat, count in result.all():
        if dept not in dept_data:
            dept_data[dept] = {}
        dept_data[dept][stat] = count
    return {"by_department": dept_data}


# ═══════════════════════════════════════════════════════════════════════════
# PAYROLL  (profiles, runs, payslips, Paystack payouts)
# ═══════════════════════════════════════════════════════════════════════════

# ── SA deduction helper (simplified estimate) ──────────────────────────────
# Monthly PAYE from 2024/25 SARS annual brackets / 12, less the primary rebate.
# UIF is 1% of gross capped at the R17,712 monthly remuneration ceiling.
# This is a reasonable estimate for demo payroll, not tax advice.
_SARS_BRACKETS = [
    (237100, 0.0, 0.18),
    (370500, 42678.0, 0.26),
    (512800, 77362.0, 0.31),
    (673000, 121475.0, 0.36),
    (857900, 179147.0, 0.39),
    (1817000, 251258.0, 0.41),
    (float("inf"), 644489.0, 0.45),
]
_PRIMARY_REBATE_ANNUAL = 17235.0
_UIF_MONTHLY_CEILING = 17712.0


def _payroll_deductions(gross_month: float, other_deductions: float = 0.0) -> dict:
    annual = gross_month * 12.0
    lower = 0.0
    tax_annual = 0.0
    for upper, base, rate in _SARS_BRACKETS:
        if annual <= upper:
            tax_annual = base + (annual - lower) * rate
            break
        lower = upper
    tax_month = max(0.0, (tax_annual - _PRIMARY_REBATE_ANNUAL) / 12.0)
    uif = round(min(gross_month, _UIF_MONTHLY_CEILING) * 0.01, 2)
    tax = round(tax_month, 2)
    sdl = round(gross_month * 0.01, 2)  # employer contribution
    uif_employer = uif                 # employer matching contribution
    net = round(gross_month - tax - uif - other_deductions, 2)
    return {
        "annual_gross": round(annual, 2),
        "tax_annual": round(tax_annual, 2),
        "tax_rebate": _PRIMARY_REBATE_ANNUAL,
        "tax": tax,
        "uif": uif,
        "uif_employer": uif_employer,
        "sdl": sdl,
        "other": other_deductions,
        "net": net,
    }


class PayrollProfileUpsert(BaseModel):
    base_salary: float
    currency: str = "ZAR"
    pay_frequency: str = "MONTHLY"
    bank_code: Optional[str] = None
    account_number: Optional[str] = None
    account_name: Optional[str] = None


class PayrollRunCreate(BaseModel):
    period: str
    employee_ids: Optional[List[uuid.UUID]] = None


def _profile_to_dict(p: PayrollProfile) -> dict:
    return {
        "employee_id": p.employee_id,
        "base_salary": float(p.base_salary),
        "currency": p.currency,
        "pay_frequency": p.pay_frequency,
        "bank_code": p.bank_code,
        "account_number": p.account_number,
        "account_name": p.account_name,
        "paystack_recipient_code": p.paystack_recipient_code,
        "updated_at": p.updated_at,
    }


def _payslip_to_dict(s: Payslip, emp: Optional[Employee] = None, prof: Optional[PayrollProfile] = None) -> dict:
    return {
        "id": s.id,
        "run_id": s.run_id,
        "employee_id": s.employee_id,
        "employee_name": emp.full_name if emp else "Employee",
        "employee_code": emp.employee_id if emp else "",
        "job_title": emp.job_title if emp else "",
        "department": emp.department if emp else "",
        "id_number": getattr(emp, "id_number", None) or "8504125089087",
        "tax_number": getattr(emp, "tax_number", None) or "9823410582",
        "bank_code": prof.bank_code if prof else "",
        "account_number": prof.account_number if prof else "",
        "account_name": prof.account_name if prof else (emp.full_name if emp else ""),
        "gross": float(s.gross),
        "basic_salary": float(getattr(s, "basic_salary", s.gross) or s.gross),
        "commission": float(getattr(s, "commission", 0.0) or 0.0),
        "allowances": float(getattr(s, "allowances", 0.0) or 0.0),
        "tax": float(s.tax),
        "tax_rebate": float(getattr(s, "tax_rebate", _PRIMARY_REBATE_ANNUAL) or _PRIMARY_REBATE_ANNUAL),
        "annual_taxable": float(getattr(s, "annual_taxable", float(s.gross) * 12) or float(s.gross) * 12),
        "uif": float(s.uif),
        "uif_employer": float(getattr(s, "uif_employer", s.uif) or s.uif),
        "sdl": float(getattr(s, "sdl", round(float(s.gross) * 0.01, 2)) or round(float(s.gross) * 0.01, 2)),
        "other_deductions": float(s.other_deductions),
        "net": float(s.net),
        "currency": s.currency,
        "payout_status": s.payout_status,
        "paystack_transfer_code": s.paystack_transfer_code,
        "paystack_reference": s.paystack_reference,
        "payout_message": s.payout_message,
        "created_at": s.created_at,
    }


def _run_to_dict(r: PayrollRun, payslips: Optional[List[Payslip]] = None) -> dict:
    d = {
        "id": r.id,
        "period": r.period,
        "status": r.status,
        "currency": r.currency,
        "employee_count": r.employee_count,
        "total_gross": float(r.total_gross),
        "total_deductions": float(r.total_deductions),
        "total_net": float(r.total_net),
        "finance_entry_id": r.finance_entry_id,
        "created_at": r.created_at,
    }
    if payslips is not None:
        d["payslips"] = [_payslip_to_dict(s) for s in payslips]
    return d


@app.put("/employees/{emp_id}/payroll-profile")
async def upsert_payroll_profile(
    emp_id: uuid.UUID,
    body: PayrollProfileUpsert,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Create/update an employee's salary + bank payout details.

    If full bank details are supplied, a Paystack Transfer Recipient is created
    (or refreshed) so payouts can target it later. Recipient creation failure
    does not block saving the profile — it's reported in the response.
    """
    await _get_employee_or_404(emp_id, tenant_id, db)

    existing = (await db.execute(
        select(PayrollProfile).where(PayrollProfile.employee_id == emp_id)
    )).scalars().first()

    if existing is None:
        existing = PayrollProfile(employee_id=emp_id, tenant_id=tenant_id, base_salary=body.base_salary)
        db.add(existing)

    existing.base_salary = body.base_salary
    existing.currency = body.currency
    existing.pay_frequency = body.pay_frequency
    existing.bank_code = body.bank_code
    existing.account_number = body.account_number
    existing.account_name = body.account_name

    recipient_msg = None
    # (Re)create the Paystack recipient when bank details are complete.
    if body.bank_code and body.account_number and body.account_name:
        try:
            res = await ps.create_transfer_recipient(
                name=body.account_name,
                account_number=body.account_number,
                bank_code=body.bank_code,
                currency=body.currency,
            )
            if res["ok"]:
                existing.paystack_recipient_code = res["recipient_code"]
            recipient_msg = res["message"]
        except ps.PaystackError as exc:
            recipient_msg = f"recipient not created: {exc}"

    await db.flush()
    await db.refresh(existing)
    return {"profile": _profile_to_dict(existing), "recipient_status": recipient_msg}


@app.get("/employees/{emp_id}/payroll-profile")
async def get_payroll_profile(
    emp_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    await _get_employee_or_404(emp_id, tenant_id, db)
    p = (await db.execute(
        select(PayrollProfile).where(PayrollProfile.employee_id == emp_id)
    )).scalars().first()
    if not p:
        raise HTTPException(status_code=404, detail="No payroll profile for this employee")
    return _profile_to_dict(p)


@app.post("/payroll/runs", status_code=201)
async def create_payroll_run(
    payload: PayrollRunCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Create a payroll run for a period and generate payslips.

    Gross comes from each employee's payroll_profile (employees without a
    profile are skipped). Does NOT pay anyone — call /payroll/runs/{id}/pay
    for that. Posts a summary journal entry to Finance (best-effort).
    """
    stmt = select(Employee).where(Employee.tenant_id == tenant_id, Employee.status == "ACTIVE")
    if payload.employee_ids:
        stmt = stmt.where(Employee.id.in_(payload.employee_ids))
    employees = (await db.execute(stmt)).scalars().all()
    if not employees:
        raise HTTPException(status_code=400, detail="No active employees found")

    profiles = {
        p.employee_id: p for p in (await db.execute(
            select(PayrollProfile).where(PayrollProfile.tenant_id == tenant_id)
        )).scalars().all()
    }

    run = PayrollRun(tenant_id=tenant_id, period=payload.period, status="DRAFT")
    db.add(run)
    await db.flush()  # assign run.id

    total_gross = total_ded = total_net = 0.0
    skipped = []
    payslips: List[Payslip] = []
    for emp in employees:
        prof = profiles.get(emp.id)
        if not prof:
            skipped.append(str(emp.id))
            continue
        base = float(prof.base_salary)
        
        # Check for approved bonus/commission claims for this period
        bonus_stmt = select(func.sum(BenefitEnrollment.bonus_amount_zar)).where(
            BenefitEnrollment.employee_id == emp.id,
            BenefitEnrollment.benefit_type == "BONUS",
            BenefitEnrollment.bonus_status == "APPROVED",
            BenefitEnrollment.bonus_period == payload.period,
        )
        comm_val = float((await db.execute(bonus_stmt)).scalar() or 0.0)
        gross = base + comm_val
        d = _payroll_deductions(gross)
        slip = Payslip(
            tenant_id=tenant_id,
            run_id=run.id,
            employee_id=emp.id,
            gross=gross,
            basic_salary=base,
            commission=comm_val,
            tax=d["tax"],
            tax_rebate=d["tax_rebate"],
            annual_taxable=d["annual_taxable"],
            uif=d["uif"],
            uif_employer=d["uif_employer"],
            sdl=d["sdl"],
            other_deductions=d["other"],
            net=d["net"],
            currency=prof.currency,
            paystack_recipient_code=prof.paystack_recipient_code,
        )
        db.add(slip)
        payslips.append(slip)
        total_gross += gross
        total_ded += d["tax"] + d["uif"] + d["other"]
        total_net += d["net"]

    if not payslips:
        raise HTTPException(
            status_code=400,
            detail="No employees have a payroll profile; set base salaries first.",
        )

    run.employee_count = len(payslips)
    run.total_gross = round(total_gross, 2)
    run.total_deductions = round(total_ded, 2)
    run.total_net = round(total_net, 2)

    # Best-effort Finance journal entry (mirrors the legacy stub).
    finance_url = os.getenv("FINANCE_SERVICE_URL", "http://finance:8015")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{finance_url}/journal-entries",
                json={
                    "entry_date": date.today().isoformat(),
                    "reference": f"PAYROLL-{payload.period}",
                    "description": f"Payroll {payload.period} ({len(payslips)} employees)",
                    "source": "PAYROLL",
                    "lines": [
                        {"account_code": "6000", "account_name": "Salaries & Wages", "debit": round(total_gross, 2), "credit": 0},
                        {"account_code": "2600", "account_name": "PAYE/UIF Payable", "debit": 0, "credit": round(total_ded, 2)},
                        {"account_code": "1000", "account_name": "Cash & Bank", "debit": 0, "credit": round(total_net, 2)},
                    ],
                },
                headers={"X-Tenant-Id": str(tenant_id)},
            )
            if resp.status_code in (200, 201):
                run.finance_entry_id = str(resp.json().get("id"))
    except Exception:
        logger.info("payroll: finance journal entry skipped (finance unavailable)")

    await db.flush()
    result = _run_to_dict(run, payslips)
    result["skipped_employees_without_profile"] = skipped
    return result


@app.get("/payroll/runs")
async def list_payroll_runs(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    runs = (await db.execute(
        select(PayrollRun).where(PayrollRun.tenant_id == tenant_id).order_by(desc(PayrollRun.created_at))
    )).scalars().all()
    return {"items": [_run_to_dict(r) for r in runs], "total": len(runs)}


@app.get("/payroll/runs/{run_id}")
async def get_payroll_run(
    run_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    run = (await db.execute(
        select(PayrollRun).where(PayrollRun.id == run_id, PayrollRun.tenant_id == tenant_id)
    )).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Payroll run not found")
    slips = (await db.execute(
        select(Payslip).where(Payslip.run_id == run_id).order_by(Payslip.created_at)
    )).scalars().all()
    return _run_to_dict(run, slips)


@app.get("/payroll/payslips")
async def list_payslips(
    run_id: Optional[uuid.UUID] = Query(None),
    employee_id: Optional[uuid.UUID] = Query(None),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    stmt = (
        select(Payslip, Employee, PayrollProfile)
        .outerjoin(Employee, Payslip.employee_id == Employee.id)
        .outerjoin(PayrollProfile, Payslip.employee_id == PayrollProfile.employee_id)
        .where(Payslip.tenant_id == tenant_id)
    )
    if run_id:
        stmt = stmt.where(Payslip.run_id == run_id)
    if employee_id:
        stmt = stmt.where(Payslip.employee_id == employee_id)

    result = await db.execute(stmt.order_by(desc(Payslip.created_at)))
    return [_payslip_to_dict(s, emp, prof) for s, emp, prof in result.all()]


@app.get("/payroll/payslips/{payslip_id}")
async def get_payslip(
    payslip_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    stmt = (
        select(Payslip, Employee, PayrollProfile)
        .outerjoin(Employee, Payslip.employee_id == Employee.id)
        .outerjoin(PayrollProfile, Payslip.employee_id == PayrollProfile.employee_id)
        .where(Payslip.id == payslip_id, Payslip.tenant_id == tenant_id)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Payslip not found")
    s, emp, prof = row
    return _payslip_to_dict(s, emp, prof)


class SalaryCalculationPreviewRequest(BaseModel):
    gross_salary: float
    allowances: Optional[float] = 0.0
    medical_aid_members: Optional[int] = 0


@app.post("/payroll/calculate-preview")
async def calculate_salary_preview(
    data: SalaryCalculationPreviewRequest,
):
    gross = float(data.gross_salary + (data.allowances or 0.0))
    d = _payroll_deductions(gross)
    med_credits = 0.0
    if data.medical_aid_members and data.medical_aid_members > 0:
        if data.medical_aid_members >= 1:
            med_credits += 364.0
        if data.medical_aid_members >= 2:
            med_credits += 364.0
        if data.medical_aid_members > 2:
            med_credits += (data.medical_aid_members - 2) * 246.0

    tax_after_med = max(0.0, round(d["tax"] - med_credits, 2))
    net = round(gross - tax_after_med - d["uif"], 2)

    return {
        "gross_salary": round(gross, 2),
        "basic_salary": round(data.gross_salary, 2),
        "allowances": round(data.allowances or 0.0, 2),
        "annual_gross": d["annual_gross"],
        "tax_annual": d["tax_annual"],
        "annual_primary_rebate": d["tax_rebate"],
        "monthly_paye_tax": tax_after_med,
        "medical_tax_credit": med_credits,
        "uif_employee_contribution": d["uif"],
        "uif_employer_contribution": d["uif_employer"],
        "sdl_employer_contribution": d["sdl"],
        "total_statutory_deductions": round(tax_after_med + d["uif"], 2),
        "total_company_contributions": round(d["uif_employer"] + d["sdl"], 2),
        "net_take_home_pay": net,
        "statutory_compliance": "Complies with SARS 2024/2025/2026 progressive tax tables & UIF BCEA Act",
    }


@app.post("/payroll/runs/{run_id}/pay")
async def pay_payroll_run(
    run_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Initiate Paystack transfers for every unpaid payslip in the run.

    Safe-guarded: this is the ONLY endpoint that moves money, and only when
    called explicitly. Each payslip records the Paystack transfer_code/status;
    a payslip with no recipient is marked FAILED and skipped. Whatever Paystack
    returns (including 'pending' on an unfunded test balance) is recorded.
    """
    run = (await db.execute(
        select(PayrollRun).where(PayrollRun.id == run_id, PayrollRun.tenant_id == tenant_id)
    )).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Payroll run not found")

    slips = (await db.execute(
        select(Payslip).where(Payslip.run_id == run_id, Payslip.payout_status.in_(["PENDING", "FAILED"]))
    )).scalars().all()
    if not slips:
        return {"run_id": run_id, "message": "nothing to pay (all payslips already paid)", **_run_to_dict(run)}

    paid = failed = 0
    for slip in slips:
        recipient = slip.paystack_recipient_code
        if not recipient:
            prof = (await db.execute(
                select(PayrollProfile).where(PayrollProfile.employee_id == slip.employee_id)
            )).scalars().first()
            recipient = prof.paystack_recipient_code if prof else None
        if not recipient:
            slip.payout_status = "FAILED"
            slip.payout_message = "no Paystack recipient (set bank details on payroll profile)"
            failed += 1
            continue

        reference = f"PAY-{run.period}-{str(slip.employee_id)[:8]}"
        try:
            res = await ps.initiate_transfer(
                amount_zar=float(slip.net),
                recipient_code=recipient,
                reason=f"Payroll {run.period}",
                reference=reference,
            )
        except ps.PaystackError as exc:
            slip.payout_status = "FAILED"
            slip.payout_message = str(exc)
            failed += 1
            continue

        slip.paystack_recipient_code = recipient
        slip.paystack_transfer_code = res.get("transfer_code")
        slip.paystack_reference = res.get("reference")
        slip.payout_message = res.get("message")
        if res["ok"]:
            # 'success' (or mock) -> PAID; 'pending'/'otp' -> PROCESSING
            slip.payout_status = "PAID" if res.get("status") == "success" else "PROCESSING"
            paid += 1
        else:
            slip.payout_status = "FAILED"
            failed += 1

    if failed == 0:
        run.status = "PAID"
    elif paid == 0:
        run.status = "FAILED"
    else:
        run.status = "PARTIALLY_PAID"

    await db.flush()
    slips_all = (await db.execute(
        select(Payslip).where(Payslip.run_id == run_id).order_by(Payslip.created_at)
    )).scalars().all()
    return {"initiated": paid, "failed": failed, **_run_to_dict(run, slips_all)}


# ── Bulk spreadsheet import + roster (onboarding / demo) ───────────────────

def _norm_header(h) -> str:
    return (str(h) if h is not None else "").strip().lower().replace(" ", "_")

_HEADER_ALIASES = {
    "name": "full_name", "employee": "full_name", "employee_name": "full_name",
    "staff_id": "employee_id", "id": "employee_id", "emp_id": "employee_id",
    "title": "job_title", "role": "job_title", "position": "job_title",
    "dept": "department",
    "salary": "base_salary", "gross": "base_salary", "gross_salary": "base_salary", "monthly_salary": "base_salary",
    "bank": "bank_code", "account": "account_number", "acc_number": "account_number", "account_no": "account_number",
    "account_holder": "account_name",
    "start_date": "hire_date", "date_hired": "hire_date", "hired": "hire_date",
    "cell": "phone", "mobile": "phone", "contact": "phone",
}


def _parse_spreadsheet(filename: str, content: bytes) -> List[dict]:
    """Parse a CSV or XLSX into a list of row dicts with normalized/aliased keys."""
    name = (filename or "").lower()
    rows: List[dict] = []
    if name.endswith(".xlsx") or content[:2] == b"PK":
        try:
            import io
            import openpyxl
        except ImportError:
            raise HTTPException(status_code=400, detail="XLSX not supported on this build; upload a CSV instead")
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        raw_headers = next(it, []) or []
        headers = [_HEADER_ALIASES.get(_norm_header(h), _norm_header(h)) for h in raw_headers]
        for raw in it:
            if raw is None or all(c is None for c in raw):
                continue
            row = {}
            for i, h in enumerate(headers):
                if h:
                    v = raw[i] if i < len(raw) else None
                    row[h] = str(v).strip() if v is not None else ""
            rows.append(row)
    else:
        import csv
        import io
        text = content.decode("utf-8-sig", errors="replace")
        for raw in csv.DictReader(io.StringIO(text)):
            row = {}
            for k, v in raw.items():
                h = _HEADER_ALIASES.get(_norm_header(k), _norm_header(k))
                row[h] = (v or "").strip()
            rows.append(row)
    return rows


@app.get("/payroll/roster")
async def payroll_roster(
    q: Optional[str] = Query(None, description="Search name / employee id / department"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Active employees joined with their payroll profile — powers the payroll table."""
    stmt = select(Employee).where(Employee.tenant_id == tenant_id, Employee.status != "INACTIVE")
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            Employee.full_name.ilike(like)
            | Employee.employee_id.ilike(like)
            | Employee.department.ilike(like)
        )
    emps = (await db.execute(stmt.order_by(Employee.full_name))).scalars().all()
    profiles = {
        p.employee_id: p for p in (await db.execute(
            select(PayrollProfile).where(PayrollProfile.tenant_id == tenant_id)
        )).scalars().all()
    }
    items = []
    for e in emps:
        p = profiles.get(e.id)
        acct = p.account_number if p else None
        items.append({
            "id": e.id, "employee_id": e.employee_id, "full_name": e.full_name,
            "job_title": e.job_title, "department": e.department, "status": e.status,
            "email": e.email, "phone": e.phone,
            "base_salary": float(p.base_salary) if p else None,
            "currency": p.currency if p else "ZAR",
            "bank_code": p.bank_code if p else None,
            "account_number_masked": ("••••" + acct[-4:]) if acct and len(acct) >= 4 else acct,
            "has_recipient": bool(p and p.paystack_recipient_code),
        })
    return {"items": items, "total": len(items)}


@app.post("/payroll/import")
async def import_payroll(
    file: UploadFile = File(...),
    create_recipients: bool = Query(False, description="Also create Paystack transfer recipients (slower)"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Bulk-onboard employees + payroll profiles from a CSV/XLSX spreadsheet.

    Header row (case-insensitive, common aliases accepted): employee_id,
    full_name, job_title, department, hire_date (YYYY-MM-DD), email, phone,
    base_salary, bank_code, account_number, account_name. Rows upsert by
    employee_id. A bad row is reported in `errors` and does not abort the import.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    rows = _parse_spreadsheet(file.filename or "", content)
    if not rows:
        raise HTTPException(status_code=400, detail="No data rows found in the file")

    existing = {
        e.employee_id: e for e in (await db.execute(
            select(Employee).where(Employee.tenant_id == tenant_id)
        )).scalars().all()
    }
    existing_profiles = {
        p.employee_id: p for p in (await db.execute(
            select(PayrollProfile).where(PayrollProfile.tenant_id == tenant_id)
        )).scalars().all()
    }

    created = updated = profiles_set = recipients = 0
    errors: List[dict] = []
    for idx, row in enumerate(rows, start=2):  # row 1 is the header
        try:
            full_name = row.get("full_name") or ""
            if not full_name:
                errors.append({"row": idx, "message": "missing full_name"})
                continue
            emp_code = row.get("employee_id") or f"STF-{idx:04d}"
            try:
                hire_d = date.fromisoformat((row.get("hire_date") or "")[:10])
            except ValueError:
                hire_d = date.today()

            emp = existing.get(emp_code)
            if emp:
                emp.full_name = full_name
                emp.job_title = row.get("job_title") or emp.job_title
                emp.department = row.get("department") or emp.department
                emp.email = row.get("email") or emp.email
                emp.phone = row.get("phone") or emp.phone
                if emp.status == "INACTIVE":
                    emp.status = "ACTIVE"
                updated += 1
            else:
                emp = Employee(
                    tenant_id=tenant_id, employee_id=emp_code, full_name=full_name,
                    job_title=row.get("job_title") or "Staff",
                    department=row.get("department") or "General",
                    hire_date=hire_d, status="ACTIVE",
                    email=row.get("email") or None, phone=row.get("phone") or None,
                )
                db.add(emp)
                await db.flush()  # assign emp.id
                existing[emp_code] = emp
                created += 1

            salary_raw = row.get("base_salary") or ""
            if salary_raw:
                try:
                    salary = float(str(salary_raw).replace(",", "").replace("R", "").strip())
                except ValueError:
                    errors.append({"row": idx, "message": f"bad base_salary '{salary_raw}'"})
                    salary = None
                if salary is not None:
                    prof = existing_profiles.get(emp.id)
                    if not prof:
                        prof = PayrollProfile(employee_id=emp.id, tenant_id=tenant_id, base_salary=salary)
                        db.add(prof)
                        existing_profiles[emp.id] = prof
                    prof.base_salary = salary
                    prof.bank_code = row.get("bank_code") or prof.bank_code
                    prof.account_number = row.get("account_number") or prof.account_number
                    prof.account_name = row.get("account_name") or prof.account_name or full_name
                    profiles_set += 1
                    if create_recipients and prof.bank_code and prof.account_number and not prof.paystack_recipient_code:
                        try:
                            res = await ps.create_transfer_recipient(
                                name=prof.account_name or full_name,
                                account_number=prof.account_number,
                                bank_code=prof.bank_code, currency=prof.currency or "ZAR",
                            )
                            if res["ok"]:
                                prof.paystack_recipient_code = res["recipient_code"]
                                recipients += 1
                        except ps.PaystackError as exc:
                            errors.append({"row": idx, "message": f"recipient: {exc}"})
        except Exception as exc:  # noqa: BLE001 — one bad row shouldn't abort the whole import
            errors.append({"row": idx, "message": str(exc)})

    await db.flush()
    return {
        "total_rows": len(rows), "created": created, "updated": updated,
        "profiles_set": profiles_set, "recipients_created": recipients,
        "errors": errors,
    }


# ═══════════════════════════════════════════════════════════════════════════
# PAYROLL  (legacy quick-run, kept for compatibility)
# ═══════════════════════════════════════════════════════════════════════════

class PayrollRunRequest(BaseModel):
    period: str
    employee_ids: Optional[List[uuid.UUID]] = None


@app.post("/payroll/run")
async def run_payroll(
    payload: PayrollRunRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    stmt = select(Employee).where(Employee.tenant_id == tenant_id, Employee.status == "ACTIVE")
    if payload.employee_ids:
        stmt = stmt.where(Employee.id.in_(payload.employee_ids))
    result = await db.execute(stmt)
    employees = result.scalars().all()
    if not employees:
        raise HTTPException(status_code=400, detail="No active employees found")
    total_gross = total_deductions = 0.0
    dept_salary = {"Support": 18000.0, "Network": 25000.0, "Engineering": 35000.0, "Sales": 22000.0, "Management": 45000.0}
    for emp in employees:
        gross = dept_salary.get(emp.department, 20000.0)
        deductions = gross * 0.18 + gross * 0.01 + gross * 0.075
        total_gross += gross
        total_deductions += deductions
    total_net = total_gross - total_deductions
    FINANCE_URL = os.getenv("FINANCE_SERVICE_URL", "http://finance:8015")
    finance_entry_id = None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{FINANCE_URL}/journal-entries",
                json={
                    "entry_date": date.today().isoformat(),
                    "reference": f"PAYROLL-{payload.period}",
                    "description": f"Payroll run - {payload.period} ({len(employees)} employees)",
                    "source": "PAYROLL",
                    "lines": [
                        {"account_code": "6000", "account_name": "Salaries & Wages", "debit": round(total_gross, 2), "credit": 0},
                        {"account_code": "2600", "account_name": "Tax Payable", "debit": 0, "credit": round(total_deductions * 0.74, 2)},
                        {"account_code": "2100", "account_name": "Accrued Expenses", "debit": 0, "credit": round(total_deductions * 0.26, 2)},
                        {"account_code": "1000", "account_name": "Cash & Bank", "debit": 0, "credit": round(total_net, 2)},
                    ],
                },
                headers={"X-Tenant-Id": str(tenant_id)},
            )
            if resp.status_code == 200:
                finance_entry_id = resp.json().get("id")
    except Exception:
        pass
    return {
        "period": payload.period,
        "employees_processed": len(employees),
        "total_gross": round(total_gross, 2),
        "total_deductions": round(total_deductions, 2),
        "total_net": round(total_net, 2),
        "finance_entry_id": finance_entry_id,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8009)
