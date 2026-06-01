"""SQLAlchemy models for the HR Service."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.common.db import Base as CommonBase


class Base(CommonBase):
    __abstract__ = True


# ── Enums ──────────────────────────────────────────────────────────────────

EMPLOYEE_STATUS = SAEnum(
    "active", "on_leave", "terminated",
    name="employee_status", create_type=True,
)

LEAVE_TYPE = SAEnum(
    "annual", "sick", "family", "unpaid",
    name="leave_type", create_type=True,
)

LEAVE_STATUS = SAEnum(
    "pending", "approved", "rejected",
    name="leave_status", create_type=True,
)

REVIEW_RATING = SAEnum(
    "exceeds", "meets", "needs_improvement", "unsatisfactory",
    name="review_rating", create_type=True,
)

REVIEW_STATUS = SAEnum(
    "draft", "submitted", "acknowledged",
    name="review_status", create_type=True,
)


# ── Employee ───────────────────────────────────────────────────────────────

class Employee(Base):
    __tablename__ = "hr_employees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=True)
    employee_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    department: Mapped[str] = mapped_column(String(100), nullable=False, default="Unassigned")
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    manager_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(EMPLOYEE_STATUS, nullable=False, default="active")
    hire_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    salary_band: Mapped[str] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Self-referential relationship
    manager = relationship("Employee", remote_side="Employee.id", backref="direct_reports", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("tenant_id", "employee_number", name="uq_hr_employees_tenant_emp_number"),
        Index("ix_hr_employees_tenant_department", "tenant_id", "department"),
        Index("ix_hr_employees_tenant_status", "tenant_id", "status"),
    )


# ── Department ─────────────────────────────────────────────────────────────

class Department(Base):
    __tablename__ = "hr_departments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    head_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    head = relationship("Employee", lazy="selectin")

    __table_args__ = (
        Index("ix_hr_departments_tenant", "tenant_id"),
    )


# ── Leave Request ──────────────────────────────────────────────────────────

class LeaveRequest(Base):
    __tablename__ = "hr_leave_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="CASCADE"), nullable=False
    )
    leave_type: Mapped[str] = mapped_column(LEAVE_TYPE, nullable=False)
    start_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(LEAVE_STATUS, nullable=False, default="pending")
    approved_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    employee = relationship("Employee", foreign_keys=[employee_id], lazy="selectin")
    approver = relationship("Employee", foreign_keys=[approved_by], lazy="selectin")

    __table_args__ = (
        Index("ix_hr_leave_tenant_employee", "tenant_id", "employee_id"),
        Index("ix_hr_leave_tenant_status", "tenant_id", "status"),
        Index("ix_hr_leave_dates", "tenant_id", "start_date", "end_date"),
    )


# ── Performance Review ─────────────────────────────────────────────────────

class PerformanceReview(Base):
    __tablename__ = "hr_performance_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="CASCADE"), nullable=False
    )
    review_period: Mapped[str] = mapped_column(String(50), nullable=False)
    rating: Mapped[str] = mapped_column(REVIEW_RATING, nullable=True)
    goals: Mapped[str] = mapped_column(Text, nullable=True)
    achievements: Mapped[str] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(REVIEW_STATUS, nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    employee = relationship("Employee", foreign_keys=[employee_id], lazy="selectin")
    reviewer = relationship("Employee", foreign_keys=[reviewer_id], lazy="selectin")

    __table_args__ = (
        Index("ix_hr_perf_tenant_employee", "tenant_id", "employee_id"),
        Index("ix_hr_perf_tenant_status", "tenant_id", "status"),
    )
