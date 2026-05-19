"""HR pydantic schemas."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class EmployeeIn(BaseModel):
    employee_code: str = Field(min_length=1, max_length=60)
    full_name: str
    email: str | None = None
    department: str | None = None
    title: str | None = None
    hire_date: date | None = None
    salary: Decimal = Decimal("0")
    status: str = "active"


class EmployeeOut(ORMModel):
    id: str
    employee_code: str
    full_name: str
    email: str | None
    department: str | None
    title: str | None
    hire_date: date | None
    salary: Decimal
    status: str


class AttendanceIn(BaseModel):
    employee_id: str
    clock_in: datetime
    clock_out: datetime | None = None
    source: str = "manual"


class AttendanceOut(ORMModel):
    id: str
    employee_id: str
    clock_in: datetime
    clock_out: datetime | None
    source: str


class LeaveIn(BaseModel):
    employee_id: str
    start_date: date
    end_date: date
    leave_type: str
    reason: str | None = None


class LeaveOut(ORMModel):
    id: str
    employee_id: str
    start_date: date
    end_date: date
    leave_type: str
    status: str
    reason: str | None


class LeaveDecision(BaseModel):
    status: str  # approved|rejected|cancelled


class ReviewIn(BaseModel):
    employee_id: str
    reviewer_id: str | None = None
    period: str
    score: Decimal = Decimal("0")
    notes: str = ""


class ReviewOut(ORMModel):
    id: str
    employee_id: str
    reviewer_id: str | None
    period: str
    score: Decimal
    notes: str


class JobOpeningIn(BaseModel):
    title: str
    department: str | None = None
    description: str = ""


class JobOpeningOut(ORMModel):
    id: str
    title: str
    department: str | None
    status: str
    description: str


class CandidateIn(BaseModel):
    job_opening_id: str | None = None
    full_name: str
    email: str | None = None
    stage: str = "applied"
    rating: Decimal = Decimal("0")


class CandidateOut(ORMModel):
    id: str
    job_opening_id: str | None
    full_name: str
    email: str | None
    stage: str
    rating: Decimal


class OnboardingTaskIn(BaseModel):
    employee_id: str | None = None
    title: str
    status: str = "open"
    due_date: date | None = None


class OnboardingTaskOut(ORMModel):
    id: str
    employee_id: str | None
    title: str
    status: str
    due_date: date | None


class OrgUnitIn(BaseModel):
    name: str
    parent_id: str | None = None
    manager_employee_id: str | None = None


class OrgUnitOut(ORMModel):
    id: str
    name: str
    parent_id: str | None
    manager_employee_id: str | None


class TrainingIn(BaseModel):
    employee_id: str
    course_name: str
    status: str = "assigned"
    completed_at: datetime | None = None


class TrainingOut(ORMModel):
    id: str
    employee_id: str
    course_name: str
    status: str
    completed_at: datetime | None


class DisciplinaryIn(BaseModel):
    employee_id: str
    incident_date: date
    severity: str
    notes: str = ""


class DisciplinaryOut(ORMModel):
    id: str
    employee_id: str
    incident_date: date
    severity: str
    notes: str


class HRAnalyticsOut(BaseModel):
    headcount: int
    active: int
    on_leave: int
    by_department: dict[str, int]
    avg_salary: Decimal
    open_positions: int
    candidates_in_pipeline: int
    pending_leave_requests: int
