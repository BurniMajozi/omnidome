"""HR service database layer — SQLAlchemy async models and session management."""

import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, Numeric, Time
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.db import get_async_engine


class Base(DeclarativeBase):
    pass


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(20), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    job_title: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    hire_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    email: Mapped[Optional[str]] = mapped_column(String(200))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    # Link to call center agent (optional — only for employees who are also CC agents)
    call_center_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    leave_type: Mapped[str] = mapped_column(String(50), nullable=False)
    start_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class PerformanceReview(Base):
    __tablename__ = "performance_reviews"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    review_period: Mapped[str] = mapped_column(String(20), nullable=False)
    tickets_resolved: Mapped[int] = mapped_column(Integer, default=0)
    avg_resolution_time: Mapped[int] = mapped_column(Integer, default=0)
    fcr_rate: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    kpi_score: Mapped[Optional[float]] = mapped_column(Numeric(4, 2))
    sentiment_score: Mapped[Optional[float]] = mapped_column(Numeric(4, 2))
    attrition_risk: Mapped[Optional[str]] = mapped_column(String(10))
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Staff Schedule ──────────────────────────────────────────────────────

class StaffSchedule(Base):
    __tablename__ = "staff_schedules"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    schedule_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    shift_start: Mapped[datetime] = mapped_column(Time, nullable=False)
    shift_end: Mapped[datetime] = mapped_column(Time, nullable=False)
    shift_type: Mapped[str] = mapped_column(String(30), default="REGULAR")  # REGULAR, OVERTIME, ON_CALL, SPLIT
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="SCHEDULED")  # SCHEDULED, CONFIRMED, COMPLETED, CANCELLED
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Training ────────────────────────────────────────────────────────────

class TrainingCourse(Base):
    __tablename__ = "training_courses"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100), nullable=False)  # ONBOARDING, TECHNICAL, COMPLIANCE, SOFT_SKILLS, PRODUCT
    duration_hours: Mapped[float] = mapped_column(Numeric(5, 1), default=1.0)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")  # DRAFT, ACTIVE, ARCHIVED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class TrainingEnrollment(Base):
    __tablename__ = "training_enrollments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    course_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("training_courses.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="ENROLLED")  # ENROLLED, IN_PROGRESS, COMPLETED, FAILED, DROPPED
    progress_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Benefits ────────────────────────────────────────────────────────────

class BenefitEnrollment(Base):
    __tablename__ = "benefit_enrollments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    benefit_type: Mapped[str] = mapped_column(String(50), nullable=False)  # LEAVE, MEDICAL_AID, PENSION, LIFE_COVER, SHARES, BONUS, OTHER
    # For leave: track balance
    leave_balance_days: Mapped[Optional[float]] = mapped_column(Numeric(5, 1))
    leave_used_days: Mapped[Optional[float]] = mapped_column(Numeric(5, 1), default=0)
    # For shares
    shares_allocated: Mapped[Optional[int]] = mapped_column(Integer)
    shares_vested: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    vesting_date: Mapped[Optional[datetime]] = mapped_column(Date)
    # For bonuses
    bonus_amount_zar: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    bonus_period: Mapped[Optional[str]] = mapped_column(String(20))  # e.g. "2025-Q4", "2025-ANNUAL"
    bonus_status: Mapped[Optional[str]] = mapped_column(String(20))  # PENDING, APPROVED, PAID
    # For medical/pension
    employer_contribution_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    enrolled: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_from: Mapped[Optional[datetime]] = mapped_column(Date)
    effective_to: Mapped[Optional[datetime]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Disciplinary Actions ────────────────────────────────────────────────

class DisciplinaryAction(Base):
    __tablename__ = "disciplinary_actions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)  # VERBAL_WARNING, WRITTEN_WARNING, FINAL_WARNING, SUSPENSION, DISMISSAL
    incident_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[Optional[str]] = mapped_column(Text)
    suspension_days: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN, UNDER_REVIEW, RESOLVED, APPEALED, CLOSED
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Staff Exit ──────────────────────────────────────────────────────────

class StaffExit(Base):
    __tablename__ = "staff_exits"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    exit_type: Mapped[str] = mapped_column(String(30), nullable=False)  # RESIGNATION, TERMINATION, RETIREMENT, REDUNDANCY, CONTRACT_END
    reason: Mapped[Optional[str]] = mapped_column(Text)
    notice_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    last_working_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    # Exit checklist
    exit_interview_done: Mapped[bool] = mapped_column(Boolean, default=False)
    assets_returned: Mapped[bool] = mapped_column(Boolean, default=False)
    access_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    final_payout_zar: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING, IN_PROGRESS, COMPLETED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Onboarding Task ─────────────────────────────────────────────────────

class OnboardingTask(Base):
    __tablename__ = "onboarding_tasks"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    task_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_department: Mapped[str] = mapped_column(String(100), nullable=False)  # HR, IT, FINANCE, MANAGER
    status: Mapped[str] = mapped_column(String(20), default="TODO")  # TODO, IN_PROGRESS, DONE, SKIPPED
    due_date: Mapped[Optional[datetime]] = mapped_column(Date)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Session factory ────────────────────────────────────────────────────

_session_factory: Optional[async_sessionmaker] = None


def _get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        engine = get_async_engine()
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_tables():
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
