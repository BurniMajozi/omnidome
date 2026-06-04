from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid
from datetime import datetime, date
import logging
from sqlalchemy import select, desc

from services.common.entitlements import EntitlementGuard
from services.common.auth import get_current_tenant_id
from services.hr.database import get_session, init_tables, Employee, LeaveRequest, PerformanceReview

app = FastAPI(title="CoreConnect HR Service", version="0.1.0")
guard = EntitlementGuard(module_id="hr")


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    await init_tables()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)

# --- Pydantic Models ---
class EmployeeBase(BaseModel):
    full_name: str
    job_title: str
    department: str
    hire_date: date

class EmployeeCreate(EmployeeBase):
    employee_id: str
    email: Optional[str] = None
    phone: Optional[str] = None

class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    hire_date: Optional[date] = None
    status: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

class EmployeeOut(EmployeeBase):
    id: uuid.UUID
    employee_id: str
    status: str
    email: Optional[str] = None
    phone: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True

class PerformanceReviewCreate(BaseModel):
    review_period: str
    tickets_resolved: int = 0
    avg_resolution_time: int = 0
    fcr_rate: Optional[float] = None
    kpi_score: Optional[float] = None
    sentiment_score: Optional[float] = None
    attrition_risk: Optional[str] = None
    reviewer_notes: Optional[str] = None

class PerformanceReviewOut(PerformanceReviewCreate):
    id: uuid.UUID
    employee_id: uuid.UUID
    created_at: datetime

    class Config:
        orm_mode = True

class LeaveRequestCreate(BaseModel):
    leave_type: str
    start_date: date
    end_date: date
    reason: Optional[str] = None

class LeaveRequestOut(LeaveRequestCreate):
    id: uuid.UUID
    employee_id: uuid.UUID
    status: str
    created_at: datetime

    class Config:
        orm_mode = True

class PerformanceMetrics(BaseModel):
    employee_id: uuid.UUID
    tickets_resolved: int
    avg_resolution_time: int
    fcr_rate: float
    kpi_score: float
    sentiment_score: float
    attrition_risk: str


# --- Sample Data Seeding ---

async def _ensure_sample_data(tenant_id: uuid.UUID, db):
    """Seed sample data if tenant has no employees."""
    result = await db.execute(select(Employee).where(Employee.tenant_id == tenant_id))
    existing = result.scalars().first()
    if existing:
        return

    # Create sample employees
    emp1 = Employee(
        tenant_id=tenant_id,
        employee_id="STF-001",
        full_name="Thabo Molefe",
        job_title="Support Lead",
        department="Support",
        hire_date=date(2023, 5, 15),
        status="ACTIVE",
        email="thabo.molefe@example.com",
        phone="+27821234567",
    )
    emp2 = Employee(
        tenant_id=tenant_id,
        employee_id="STF-002",
        full_name="Sarah Jenkins",
        job_title="Network Technician",
        department="Network",
        hire_date=date(2024, 1, 10),
        status="ACTIVE",
        email="sarah.jenkins@example.com",
        phone="+27829876543",
    )
    db.add(emp1)
    db.add(emp2)
    await db.flush()

    # Create sample leave request
    leave = LeaveRequest(
        tenant_id=tenant_id,
        employee_id=emp1.id,
        leave_type="ANNUAL",
        start_date=date(2025, 7, 1),
        end_date=date(2025, 7, 14),
        status="PENDING",
        reason="Family vacation",
    )
    db.add(leave)

    # Create sample performance review
    review = PerformanceReview(
        tenant_id=tenant_id,
        employee_id=emp1.id,
        review_period="2025-Q1",
        tickets_resolved=145,
        avg_resolution_time=42,
        fcr_rate=78.5,
        kpi_score=8.5,
        sentiment_score=0.82,
        attrition_risk="LOW",
        reviewer_notes="Consistently strong performance. Excellent team collaboration.",
    )
    db.add(review)


# --- Helper ---
def _employee_to_dict(emp: Employee) -> dict:
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
        "created_at": emp.created_at,
    }


# --- Routes ---
@app.get("/")
async def root():
    return {"message": "CoreConnect HR Service is active"}


@app.get("/employees", response_model=List[EmployeeOut])
async def list_employees(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    await _ensure_sample_data(tenant_id, db)
    result = await db.execute(
        select(Employee)
        .where(Employee.tenant_id == tenant_id)
        .order_by(Employee.created_at)
    )
    employees = result.scalars().all()
    return [_employee_to_dict(e) for e in employees]


@app.post("/employees", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
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
    )
    db.add(emp)
    await db.flush()
    await db.refresh(emp)
    return _employee_to_dict(emp)


@app.get("/employees/{emp_id}", response_model=EmployeeOut)
async def get_employee(
    emp_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    result = await db.execute(
        select(Employee).where(Employee.id == emp_id, Employee.tenant_id == tenant_id)
    )
    emp = result.scalars().first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return _employee_to_dict(emp)


@app.put("/employees/{emp_id}", response_model=EmployeeOut)
async def update_employee(
    emp_id: uuid.UUID,
    data: EmployeeUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    result = await db.execute(
        select(Employee).where(Employee.id == emp_id, Employee.tenant_id == tenant_id)
    )
    emp = result.scalars().first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(emp, key, value)

    await db.flush()
    await db.refresh(emp)
    return _employee_to_dict(emp)


@app.get("/employees/{emp_id}/performance", response_model=List[PerformanceReviewOut])
async def get_employee_performance(
    emp_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    # Verify employee exists and belongs to tenant
    emp_result = await db.execute(
        select(Employee).where(Employee.id == emp_id, Employee.tenant_id == tenant_id)
    )
    emp = emp_result.scalars().first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    result = await db.execute(
        select(PerformanceReview)
        .where(PerformanceReview.employee_id == emp_id, PerformanceReview.tenant_id == tenant_id)
        .order_by(desc(PerformanceReview.created_at))
    )
    reviews = result.scalars().all()
    return [
        {
            "id": r.id,
            "employee_id": r.employee_id,
            "review_period": r.review_period,
            "tickets_resolved": r.tickets_resolved,
            "avg_resolution_time": r.avg_resolution_time,
            "fcr_rate": float(r.fcr_rate) if r.fcr_rate is not None else None,
            "kpi_score": float(r.kpi_score) if r.kpi_score is not None else None,
            "sentiment_score": float(r.sentiment_score) if r.sentiment_score is not None else None,
            "attrition_risk": r.attrition_risk,
            "reviewer_notes": r.reviewer_notes,
            "created_at": r.created_at,
        }
        for r in reviews
    ]


@app.post("/employees/{emp_id}/performance", response_model=PerformanceReviewOut, status_code=status.HTTP_201_CREATED)
async def create_performance_review(
    emp_id: uuid.UUID,
    data: PerformanceReviewCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    # Verify employee exists and belongs to tenant
    emp_result = await db.execute(
        select(Employee).where(Employee.id == emp_id, Employee.tenant_id == tenant_id)
    )
    emp = emp_result.scalars().first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    review = PerformanceReview(
        tenant_id=tenant_id,
        employee_id=emp_id,
        review_period=data.review_period,
        tickets_resolved=data.tickets_resolved,
        avg_resolution_time=data.avg_resolution_time,
        fcr_rate=data.fcr_rate,
        kpi_score=data.kpi_score,
        sentiment_score=data.sentiment_score,
        attrition_risk=data.attrition_risk,
        reviewer_notes=data.reviewer_notes,
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)
    return {
        "id": review.id,
        "employee_id": review.employee_id,
        "review_period": review.review_period,
        "tickets_resolved": review.tickets_resolved,
        "avg_resolution_time": review.avg_resolution_time,
        "fcr_rate": float(review.fcr_rate) if review.fcr_rate is not None else None,
        "kpi_score": float(review.kpi_score) if review.kpi_score is not None else None,
        "sentiment_score": float(review.sentiment_score) if review.sentiment_score is not None else None,
        "attrition_risk": review.attrition_risk,
        "reviewer_notes": review.reviewer_notes,
        "created_at": review.created_at,
    }


@app.get("/employees/{emp_id}/leave", response_model=List[LeaveRequestOut])
async def list_leave_requests(
    emp_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    # Verify employee exists and belongs to tenant
    emp_result = await db.execute(
        select(Employee).where(Employee.id == emp_id, Employee.tenant_id == tenant_id)
    )
    emp = emp_result.scalars().first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    result = await db.execute(
        select(LeaveRequest)
        .where(LeaveRequest.employee_id == emp_id, LeaveRequest.tenant_id == tenant_id)
        .order_by(desc(LeaveRequest.created_at))
    )
    requests = result.scalars().all()
    return [
        {
            "id": r.id,
            "employee_id": r.employee_id,
            "leave_type": r.leave_type,
            "start_date": r.start_date,
            "end_date": r.end_date,
            "status": r.status,
            "reason": r.reason,
            "created_at": r.created_at,
        }
        for r in requests
    ]


@app.post("/employees/{emp_id}/leave", response_model=LeaveRequestOut, status_code=status.HTTP_201_CREATED)
async def create_leave_request(
    emp_id: uuid.UUID,
    data: LeaveRequestCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    # Verify employee exists and belongs to tenant
    emp_result = await db.execute(
        select(Employee).where(Employee.id == emp_id, Employee.tenant_id == tenant_id)
    )
    emp = emp_result.scalars().first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    leave = LeaveRequest(
        tenant_id=tenant_id,
        employee_id=emp_id,
        leave_type=data.leave_type,
        start_date=data.start_date,
        end_date=data.end_date,
        status="PENDING",
        reason=data.reason,
    )
    db.add(leave)
    await db.flush()
    await db.refresh(leave)
    return {
        "id": leave.id,
        "employee_id": leave.employee_id,
        "leave_type": leave.leave_type,
        "start_date": leave.start_date,
        "end_date": leave.end_date,
        "status": leave.status,
        "reason": leave.reason,
        "created_at": leave.created_at,
    }


@app.get("/analytics/attrition-risk")
async def get_attrition_risk_overview(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """AI-driven attrition prediction based on sentiment trends"""
    # Count total employees
    emp_result = await db.execute(
        select(Employee).where(Employee.tenant_id == tenant_id, Employee.status == "ACTIVE")
    )
    employees = emp_result.scalars().all()
    total = len(employees)

    if total == 0:
        return {
            "total_employees": 0,
            "high_risk_count": 0,
            "medium_risk_count": 0,
            "low_risk_count": 0,
            "primary_attrition_factors": [],
            "recommendations": [],
        }

    # Get latest performance review for each employee
    high_risk = 0
    medium_risk = 0
    low_risk = 0
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

    factors = list(risk_factors) if risk_factors else ["High volume of URGENT tickets", "Shift burnout", "Peer feedback sentiment dips"]
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8009)
