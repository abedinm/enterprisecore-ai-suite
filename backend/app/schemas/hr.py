"""HR pydantic schemas."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ---- Employees ----------------------------------------------------------
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


# ---- Attendance --------------------------------------------------------
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


class AttendanceSummaryOut(BaseModel):
    employee_id: str
    days_present: int
    hours_total: Decimal
    last_clock_in: datetime | None


# ---- Leave -------------------------------------------------------------
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


class LeaveBalanceOut(BaseModel):
    employee_id: str
    by_type: dict[str, int]
    total_taken: int


# ---- Reviews -----------------------------------------------------------
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


# ---- Recruitment -------------------------------------------------------
class JobOpeningIn(BaseModel):
    title: str
    department: str | None = None
    status: str = "open"
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


# ---- Onboarding -------------------------------------------------------
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


# ---- Org chart --------------------------------------------------------
class OrgUnitIn(BaseModel):
    name: str
    parent_id: str | None = None
    manager_employee_id: str | None = None


class OrgUnitOut(ORMModel):
    id: str
    name: str
    parent_id: str | None
    manager_employee_id: str | None


class OrgUnitNode(BaseModel):
    id: str
    name: str
    manager_employee_id: str | None
    manager_name: str | None = None
    headcount: int = 0
    children: list["OrgUnitNode"] = []


OrgUnitNode.model_rebuild()


# ---- Training ---------------------------------------------------------
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


# ---- Discipline ------------------------------------------------------
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


# ---- Payslips --------------------------------------------------------
class PayslipLineRow(BaseModel):
    label: str
    amount: Decimal
    kind: str


class PayslipOut(BaseModel):
    payroll_run_id: str
    employee_id: str | None
    employee_name: str | None = None
    period_start: date
    period_end: date
    gross: Decimal
    deductions: Decimal
    net: Decimal
    currency: str = "USD"
    lines: list[PayslipLineRow] = []


# ---- Self service ----------------------------------------------------
class SelfServiceOut(BaseModel):
    employee: EmployeeOut | None
    recent_attendance: list[AttendanceOut] = []
    upcoming_leaves: list[LeaveOut] = []
    open_onboarding: list[OnboardingTaskOut] = []
    training: list[TrainingOut] = []
    payslips: list[PayslipOut] = []


# ---- Analytics -------------------------------------------------------
class HRAnalyticsOut(BaseModel):
    headcount: int
    active: int
    on_leave: int
    by_department: dict[str, int]
    avg_salary: Decimal
    open_positions: int
    candidates_in_pipeline: int
    pending_leave_requests: int
    by_status: dict[str, int] = {}
    hires_by_month: dict[str, int] = {}
    review_avg: Decimal = Decimal("0")
    training_completion_rate: Decimal = Decimal("0")
    disciplinary_count: int = 0
