from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin
from sqlalchemy import UniqueConstraint


class Employee(IdMixin, TenantMixin, TimestampMixin, Base):
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    employee_code: Mapped[str] = mapped_column(String(60), index=True)
    full_name: Mapped[str] = mapped_column(String(180), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    department: Mapped[str | None] = mapped_column(String(120))
    title: Mapped[str | None] = mapped_column(String(120))
    hire_date: Mapped[date | None] = mapped_column(Date)
    salary: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    status: Mapped[str] = mapped_column(String(30), default="active")
    # Employee codes are unique within a tenant, not globally.
    __table_args__ = (UniqueConstraint("tenant_id", "employee_code", name="uq_employees_tenant_code"),)


class AttendanceRecord(IdMixin, TenantMixin, TimestampMixin, Base):
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    clock_in: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    clock_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(40), default="manual")


class LeaveRequest(IdMixin, TenantMixin, TimestampMixin, Base):
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    leave_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    reason: Mapped[str | None] = mapped_column(Text)


class PerformanceReview(IdMixin, TenantMixin, TimestampMixin, Base):
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    period: Mapped[str] = mapped_column(String(60))
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    notes: Mapped[str] = mapped_column(Text, default="")


class JobOpening(IdMixin, TenantMixin, TimestampMixin, Base):
    title: Mapped[str] = mapped_column(String(180), index=True)
    department: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="open")
    description: Mapped[str] = mapped_column(Text, default="")


class Candidate(IdMixin, TenantMixin, TimestampMixin, Base):
    job_opening_id: Mapped[str | None] = mapped_column(ForeignKey("job_openings.id", ondelete="SET NULL"))
    full_name: Mapped[str] = mapped_column(String(180), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    stage: Mapped[str] = mapped_column(String(80), default="applied")
    rating: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)


class OnboardingTask(IdMixin, TenantMixin, TimestampMixin, Base):
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(30), default="open")
    due_date: Mapped[date | None] = mapped_column(Date)


class OrgUnit(IdMixin, TenantMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(160), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("org_units.id", ondelete="SET NULL"))
    manager_employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))


class TrainingRecord(IdMixin, TenantMixin, TimestampMixin, Base):
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    course_name: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(30), default="assigned")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DisciplinaryRecord(IdMixin, TenantMixin, TimestampMixin, Base):
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    incident_date: Mapped[date] = mapped_column(Date)
    severity: Mapped[str] = mapped_column(String(40))
    notes: Mapped[str] = mapped_column(Text, default="")
