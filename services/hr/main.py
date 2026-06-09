import os
import logging
from datetime import date, datetime
from typing import Optional, List
import uuid

import httpx
from fastapi import FastAPI, Depends, HTTPException, status, Query
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
)

app = FastAPI(title="OmniDome HR Service", version="0.2.0")
guard = EntitlementGuard(module_id="hr")
logger = logging.getLogger("hr")

configure_production(app)


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
        "call_center_agent_id": emp.call_center_agent_id,
        "created_at": emp.created_at,
    }


# ═══════════════════════════════════════════════════════════════════════════
# EMPLOYEES  (existing + call_center_agent_id)
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
    call_center_agent_id: Optional[uuid.UUID] = None

class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    hire_date: Optional[date] = None
    status: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    call_center_agent_id: Optional[uuid.UUID] = None


@app.get("/employees", response_model=List[dict])
async def list_employees(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
    department: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    stmt = select(Employee).where(Employee.tenant_id == tenant_id)
    if department:
        stmt = stmt.where(Employee.department == department)
    if status:
        stmt = stmt.where(Employee.status == status)
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
        call_center_agent_id=data.call_center_agent_id,
    )
    db.add(emp)
    await db.flush()
    await db.refresh(emp)
    logger.info(f"Employee created: {data.full_name} ({data.employee_id})")
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
    """Return staffing demand forecast based on call center queue data."""
    from datetime import timedelta
    today = date.today()
    forecast = []
    for i in range(days):
        d = today + timedelta(days=day)
        # Count scheduled staff for this date
        result = await db.execute(
            select(func.count(StaffSchedule.id)).where(
                StaffSchedule.tenant_id == tenant_id,
                StaffSchedule.schedule_date == d,
                StaffSchedule.status != "CANCELLED",
            )
        )
        scheduled = result.scalar() or 0
        forecast.append({
            "date": d.isoformat(),
            "day": d.strftime("%A"),
            "scheduled_staff": scheduled,
            "required_staff": max(scheduled, 28),  # TODO: derive from queue data
            "gap": max(0, 28 - scheduled),
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
# PAYROLL  (existing, kept for compatibility)
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
